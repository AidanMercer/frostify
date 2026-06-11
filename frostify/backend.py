import hashlib
import json
import subprocess
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface
from spotipy.exceptions import SpotifyException

from .auth import make_auth, make_client
from .config import DATA_CACHE_DIR

TTL_PLAYLISTS = 1800
TTL_TRACKS = 900
TTL_SEARCH = 3600

_MPRIS_PATH = "/org/mpris/MediaPlayer2"
_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
# how often to re-read full state from spotifyd over D-Bus. It's local IPC with no
# rate limit, so this is cheap; in-between ticks interpolate the progress bar locally.
_SYNC_EVERY = 2   # seconds (== ticks, since the timer is 1s)


def _img(images, smallest=False):
    if not images:
        return ""
    return images[-1]["url"] if smallest else images[0]["url"]


def _json_val(node):
    """Recursively strip busctl --json `{"type","data"}` wrappers into plain Python."""
    if isinstance(node, dict):
        if len(node) == 2 and "type" in node and "data" in node:
            return _json_val(node["data"])
        return {k: _json_val(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_json_val(v) for v in node]
    return node


class Backend(QObject):
    loggedInChanged = Signal(bool)
    playlistsLoaded = Signal(list)
    tracksLoaded = Signal(list, str)
    searchLoaded = Signal(list)
    nowPlaying = Signal("QVariant")
    devicesLoaded = Signal(list)   # kept for QML compat; no longer used
    error = Signal(str)
    toast = Signal(str)

    def __init__(self):
        super().__init__()
        # one worker thread for all Web API calls
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._auth = make_auth()
        self._sp = make_client(self._auth)

        # now-playing state. Full state is re-read from spotifyd over D-Bus every
        # _SYNC_EVERY seconds; between reads the progress bar is interpolated locally.
        self._np_id = None
        self._np_liked = False
        self._np_track_path = ""       # mpris:trackid (object path) for SetPosition
        self._local_np = None          # last full nowPlaying dict
        self._np_playing_since = 0.0   # monotonic: (now - since)*1000 = progressMs
        self._np_duration_ms = 0
        self._spotifyd_device_id = None  # cached Spotify Connect device ID
        self._user_id = None             # cached Spotify user id (for creating playlists)
        self._tick = 0

        # 1s timer — drives both local interpolation and the periodic D-Bus re-read
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        # D-Bus: used only to SEND commands (PlayPause/Next/Previous). Reads go through
        # busctl --json because PySide6's QDBusArgument can't demarshal MPRIS's a{sv} maps.
        self._bus = QDBusConnection.sessionBus()
        self._service = ""
        self._player = None

        for sub in ("tracks", "search"):
            (DATA_CACHE_DIR / sub).mkdir(parents=True, exist_ok=True)

    # ---- spotifyd discovery / control (D-Bus, local IPC, no rate limits) ----

    def _rebind(self):
        """Find spotifyd's live MPRIS bus name and bind the control interface.
        spotifyd only registers the name once it becomes the active device, and the
        name carries a per-process .instanceNNN suffix, so we discover it each time.
        Returns True when spotifyd is present."""
        reply = QDBusInterface(
            "org.freedesktop.DBus", "/org/freedesktop/DBus",
            "org.freedesktop.DBus", self._bus,
        ).call("ListNames")
        names = reply.arguments()[0] if reply.arguments() else []
        svc = next((str(n) for n in names
                    if str(n).startswith("org.mpris.MediaPlayer2.spotifyd")), "")
        if not svc:
            self._service, self._player = "", None
            return False
        if svc != self._service:
            self._service = svc
            self._player = QDBusInterface(svc, _MPRIS_PATH, _PLAYER_IFACE, self._bus)
        return True

    def _control(self, method, *args):
        """Send a no-/typed-arg MPRIS command, then re-sync shortly after so the UI
        reflects the new state without waiting for the next periodic read."""
        if self._rebind():
            self._player.call(method, *args)
        QTimer.singleShot(150, self._sync)

    def _read_state(self):
        """Read full now-playing state from spotifyd via busctl --json (clean demarshalling)."""
        if not self._rebind():
            return {"active": False}
        cmd = ["busctl", "--user", "--json=short", "get-property",
               self._service, _MPRIS_PATH, _PLAYER_IFACE,
               "PlaybackStatus", "Metadata", "Position"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        except Exception:
            return {"active": False}
        if res.returncode != 0:
            self._service = ""  # likely gone — rediscover next time
            return {"active": False}

        vals = {}
        for name, line in zip(("PlaybackStatus", "Metadata", "Position"),
                              res.stdout.strip().splitlines()):
            try:
                vals[name] = _json_val(json.loads(line))
            except Exception:
                vals[name] = None

        status = vals.get("PlaybackStatus") or "Stopped"
        meta   = vals.get("Metadata") or {}
        try:
            pos_us = int(vals.get("Position") or 0)
        except (ValueError, TypeError):
            pos_us = 0

        is_playing = status == "Playing"
        if status not in ("Playing", "Paused") or not meta:
            return {"active": False}

        track_path = str(meta.get("mpris:trackid") or "")
        url        = str(meta.get("xesam:url") or "")
        name       = str(meta.get("xesam:title") or "")
        artists    = meta.get("xesam:artist") or []
        artist     = ", ".join(artists) if isinstance(artists, list) else str(artists)
        album      = str(meta.get("xesam:album") or "")
        image      = str(meta.get("mpris:artUrl") or "")
        try:
            dur_us = int(meta.get("mpris:length", 0) or 0)
        except (ValueError, TypeError):
            dur_us = 0

        # the bare Spotify ID lives in the url ("spotify:track:XXX") or trackid path
        # ("/spotify/track/XXX"); we need it for the liked-status check
        if url.startswith("spotify:track:"):
            track_id = url.split(":")[-1]
        elif "/track/" in track_path:
            track_id = track_path.rsplit("/", 1)[-1]
        else:
            track_id = ""
        uri = url or (f"spotify:track:{track_id}" if track_id else "")

        progress_ms = pos_us // 1000
        duration_ms = dur_us // 1000

        self._np_track_path = track_path
        self._np_duration_ms = duration_ms
        if is_playing:
            self._np_playing_since = time.monotonic() - (progress_ms / 1000)

        return {
            "active":     True,
            "isPlaying":  is_playing,
            "id":         track_id,
            "uri":        uri,
            "name":       name,
            "artist":     artist,
            "album":      album,
            "image":      image,
            "progressMs": progress_ms,
            "durationMs": duration_ms,
            "liked":      False,
        }

    def _sync(self):
        """Re-read full state from spotifyd, emit it, and refresh liked status on track change."""
        data = self._read_state()
        if data.get("active"):
            tid = data.get("id", "")
            if tid and tid == self._np_id:
                data["liked"] = self._np_liked        # carry forward known liked state
            elif tid:
                self._np_id = tid
                self._submit(self._check_liked_task, tid)
        else:
            self._np_id = None
        self._local_np = data
        self.nowPlaying.emit(data)

    def _check_liked_task(self, tid):
        """Worker: ask Spotify if the current track is liked, then update the UI."""
        try:
            liked = self._sp.current_user_saved_tracks_contains([tid])[0] if tid else False
        except Exception:
            liked = False
        self._np_liked = liked
        snap = self._local_np
        if snap and snap.get("id") == tid:
            data = {**snap, "liked": liked}
            self._local_np = data
            self.nowPlaying.emit(data)

    # ---- timer: periodic D-Bus re-read + local progress interpolation ----

    def _on_tick(self):
        self._tick += 1
        if self._tick % _SYNC_EVERY == 0:
            self._sync()          # cheap local D-Bus read; catches track/status changes
            return
        snap = self._local_np     # in-between: interpolate the bar, no I/O
        if not snap or not snap.get("active") or not snap.get("isPlaying"):
            return
        progress = min(int((time.monotonic() - self._np_playing_since) * 1000),
                       self._np_duration_ms)
        self.nowPlaying.emit({**snap, "progressMs": progress})

    # ---- threading helpers ----

    def _submit(self, fn, *args):
        self._pool.submit(self._guard, fn, *args)

    def _guard(self, fn, *args):
        try:
            fn(*args)
        except SpotifyException as e:
            traceback.print_exc()
            self.error.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))

    # ---- disk cache ----

    def _cache_get(self, name, ttl):
        try:
            p = DATA_CACHE_DIR / name
            if p.exists():
                obj = json.loads(p.read_text())
                if isinstance(obj, dict) and "ts" in obj and "data" in obj:
                    return obj["data"], (time.time() - obj["ts"]) < ttl
                return obj, False
        except Exception:
            pass
        return None, False

    def _cache_write(self, name, data):
        try:
            (DATA_CACHE_DIR / name).write_text(json.dumps({"ts": time.time(), "data": data}))
        except Exception:
            pass

    def _cache_delete(self, name):
        try:
            (DATA_CACHE_DIR / name).unlink(missing_ok=True)
        except Exception:
            pass

    # ---- auth ----

    @Slot()
    def checkLogin(self):
        def task():
            ok = self._auth.cache_handler.get_cached_token() is not None
            self.loggedInChanged.emit(ok)
        self._submit(task)

    @Slot()
    def login(self):
        def task():
            self._auth.get_access_token()
            self.loggedInChanged.emit(True)
        self._submit(task)

    @Slot()
    def startPolling(self):
        self._timer.start()
        self._sync()   # show whatever spotifyd is already playing (if anything)

    @Slot(bool)
    def setActive(self, active):
        if active:
            if not self._timer.isActive():
                self._timer.start()
            self._sync()   # re-anchor on refocus so the bar doesn't jump
        else:
            self._timer.stop()

    # ---- library / browse ----

    @Slot()
    def loadPlaylists(self):
        self._submit(self._playlists_task)

    @Slot()
    def refreshPlaylists(self):
        self._submit(self._playlists_task, True)

    def _playlists_task(self, force=False):
        cached, fresh = self._cache_get("playlists.json", TTL_PLAYLISTS)
        if cached is not None:
            self.playlistsLoaded.emit(self._apply_pins(cached))
            if fresh and not force:
                return
        out = []
        res = self._sp.current_user_playlists(limit=50)
        while res:
            for p in res["items"]:
                if not p or not p.get("id"):
                    continue
                out.append({
                    "id":    p["id"],
                    "uri":   p.get("uri", ""),
                    "name":  p.get("name", "Untitled"),
                    "image": _img(p.get("images")),
                    "count": (p.get("tracks") or {}).get("total", 0),
                    "owner": (p.get("owner") or {}).get("display_name", ""),
                })
            res = self._sp.next(res) if res.get("next") else None
        if out != cached:
            self.playlistsLoaded.emit(self._apply_pins(out))
        self._cache_write("playlists.json", out)  # cache the raw (unpinned) order

    # ---- pinning (local only — Spotify's API doesn't expose its pin feature) ----

    def _load_pinned(self):
        try:
            p = DATA_CACHE_DIR / "pinned.json"
            if p.exists():
                v = json.loads(p.read_text())
                if isinstance(v, list):
                    return v
        except Exception:
            pass
        return []

    def _apply_pins(self, playlists):
        """Tag each playlist with `pinned` and float pinned ones to the top,
        in pin order; everything else keeps its original order (stable sort)."""
        pinned = self._load_pinned()
        rank = {pid: i for i, pid in enumerate(pinned)}
        decorated = [{**p, "pinned": p["id"] in rank} for p in playlists]
        decorated.sort(key=lambda p: rank.get(p["id"], len(pinned)))
        return decorated

    @Slot(str)
    def togglePin(self, playlist_id):
        pinned = self._load_pinned()
        if playlist_id in pinned:
            pinned.remove(playlist_id)
            msg = "Unpinned"
        else:
            pinned.insert(0, playlist_id)
            msg = "Pinned"
        try:
            (DATA_CACHE_DIR / "pinned.json").write_text(json.dumps(pinned))
        except Exception:
            pass
        self.toast.emit(msg)
        self._submit(self._playlists_task)  # re-emit from cache with new order

    @Slot(str)
    def createPlaylist(self, name):
        self._submit(self._create_playlist_task, name)

    def _create_playlist_task(self, name):
        name = name.strip()
        if not name:
            return
        if not self._user_id:
            self._user_id = self._sp.current_user()["id"]
        self._sp.user_playlist_create(self._user_id, name, public=False)
        self._cache_delete("playlists.json")
        self.toast.emit(f"Created “{name}”")
        self._playlists_task(force=True)  # already on the worker thread

    @Slot(str, str, str)
    def openPlaylist(self, playlist_id, name, context_uri):
        self._submit(self._tracks_task, playlist_id, name, context_uri)

    @Slot(str, str, str)
    def refreshPlaylist(self, playlist_id, name, context_uri):
        self._submit(self._tracks_task, playlist_id, name, context_uri, True)

    def _tracks_task(self, playlist_id, name, context_uri, force=False):
        key = f"tracks/{playlist_id}.json"
        cached, fresh = self._cache_get(key, TTL_TRACKS)
        if cached is not None:
            self.tracksLoaded.emit(cached, name)
            if fresh and not force:
                return
        raw = []
        try:
            res = self._sp.playlist_items(playlist_id, limit=100, additional_types=["track"])
            while res:
                raw += res["items"]
                res = self._sp.next(res) if res.get("next") else None
        except SpotifyException as e:
            if e.http_status in (403, 404):
                if cached is None:
                    self.tracksLoaded.emit([], name)
                    self.toast.emit("Spotify won't share this playlist's tracks — "
                                    "it's one of their editorial/algorithmic playlists.")
                return
            raise
        tracks = [(r.get("track") or r.get("item")) for r in raw]
        tracks = [t for t in tracks if t and t.get("id")]
        liked  = self._saved_contains([t["id"] for t in tracks])
        out    = [self._track_dict(t, lk, context_uri) for t, lk in zip(tracks, liked)]
        if out != cached:
            self.tracksLoaded.emit(out, name)
        self._cache_write(key, out)

    @Slot(str)
    def search(self, query):
        self._submit(self._search_task, query)

    @Slot(str)
    def refreshSearch(self, query):
        self._submit(self._search_task, query, True)

    def _search_task(self, query, force=False):
        q = query.strip()
        if not q:
            self.searchLoaded.emit([])
            return
        key = "search/" + hashlib.md5(q.lower().encode()).hexdigest() + ".json"
        cached, fresh = self._cache_get(key, TTL_SEARCH)
        if cached is not None and fresh and not force:
            self.searchLoaded.emit(cached)
            return
        tracks = []
        for offset in (0, 10, 20, 30):
            res   = self._sp.search(q=q, type="track", limit=10, offset=offset)
            items = res["tracks"]["items"]
            tracks += [t for t in items if t.get("id")]
            if len(items) < 10:
                break
        ids   = [t["id"] for t in tracks]
        liked = dict(zip(ids, self._saved_contains(ids)))
        out   = [self._track_dict(t, liked.get(t["id"], False), "") for t in tracks]
        self.searchLoaded.emit(out)
        self._cache_write(key, out)

    def _saved_contains(self, ids):
        out = []
        for i in range(0, len(ids), 50):
            out += self._sp.current_user_saved_tracks_contains(ids[i:i + 50])
        return out

    def _track_dict(self, t, liked, context_uri):
        album = t.get("album") or {}
        return {
            "id":         t["id"],
            "uri":        t["uri"],
            "name":       t["name"],
            "artist":     ", ".join(a["name"] for a in t.get("artists", [])),
            "album":      album.get("name", ""),
            "image":      _img(album.get("images"), smallest=True),
            "durationMs": t.get("duration_ms", 0),
            "liked":      bool(liked),
            "contextUri": context_uri,
        }

    # ---- playback ----
    # Play/pause/skip/seek go through MPRIS (local D-Bus, no network, no rate limits).
    # Playing a specific track still uses start_playback() so playlist context is preserved —
    # that call is user-triggered (rare) so it will never cause rate-limit issues.

    def _spotifyd_device(self):
        """Return spotifyd's Spotify Connect device ID, queried once per session."""
        if self._spotifyd_device_id:
            return self._spotifyd_device_id
        devs = self._sp.devices().get("devices", [])
        # prefer devices named "frostify" or "spotifyd" (both are us); fall back to any Computer
        for d in devs:
            if d.get("name", "").lower() in ("frostify", "spotifyd"):
                self._spotifyd_device_id = d["id"]
                return d["id"]
        for d in devs:
            if d.get("type", "").lower() == "computer":
                self._spotifyd_device_id = d["id"]
                return d["id"]
        return devs[0]["id"] if devs else None

    @Slot(str, str)
    def playTrack(self, uri, context_uri):
        self._submit(self._play_task, uri, context_uri)

    def _play_task(self, uri, context_uri):
        dev = self._spotifyd_device()
        if not dev:
            self.error.emit("spotifyd device not found — is spotifyd running?")
            return
        if context_uri:
            self._sp.start_playback(device_id=dev, context_uri=context_uri, offset={"uri": uri})
        else:
            self._sp.start_playback(device_id=dev, uris=[uri])

    @Slot()
    def togglePlay(self):
        self._control("PlayPause")

    @Slot()
    def nextTrack(self):
        self._control("Next")

    @Slot()
    def prevTrack(self):
        self._control("Previous")

    @Slot(int)
    def seek(self, ms):
        # SetPosition(o trackId, x position_us) — the trackid is a D-Bus object path,
        # which QDBusInterface.call() would send as a plain string and spotifyd rejects.
        # busctl lets us specify the 'ox' signature explicitly.
        if not self._np_track_path or not self._rebind():
            return
        try:
            subprocess.run(
                ["busctl", "--user", "call", self._service, _MPRIS_PATH, _PLAYER_IFACE,
                 "SetPosition", "ox", self._np_track_path, str(max(0, ms) * 1000)],
                capture_output=True, timeout=2,
            )
        except Exception:
            pass
        QTimer.singleShot(150, self._sync)

    @Slot(str, bool)
    def toggleLike(self, track_id, like):
        def task():
            if like:
                self._sp.current_user_saved_tracks_add([track_id])
            else:
                self._sp.current_user_saved_tracks_delete([track_id])
            if track_id == self._np_id:
                self._np_liked = like
                snap = self._local_np
                if snap:
                    data = {**snap, "liked": like}
                    self._local_np = data
                    self.nowPlaying.emit(data)
            self.toast.emit("Liked" if like else "Removed from liked")
        self._submit(task)

    @Slot(str, str)
    def addToPlaylist(self, track_uri, playlist_id):
        def task():
            self._sp.playlist_add_items(playlist_id, [track_uri])
            self._cache_delete(f"tracks/{playlist_id}.json")
            self.toast.emit("Added to playlist")
        self._submit(task)

    @Slot()
    def loadDevices(self):
        pass  # spotifyd is the device; picker not needed

    @Slot(str)
    def transferPlayback(self, device_id):
        pass
