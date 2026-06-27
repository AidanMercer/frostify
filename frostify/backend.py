import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface
from spotipy.exceptions import SpotifyException

from .auth import make_auth, make_client
from .config import DATA_CACHE_DIR, LOG_FILE

TTL_PLAYLISTS = 1800
TTL_TRACKS = 900
TTL_SEARCH = 3600

LIKED_ID = "liked"       # sentinel id for the Liked Songs pseudo-playlist
RECENT_ID = "recent"     # sentinel id for the Recent Searches pseudo-playlist
DESKTOP_ID = "desktop"   # sentinel id for the local Desktop stash pseudo-playlist
RECENT_MAX = 100         # how many recently-searched tracks to keep

_MPRIS_PATH = "/org/mpris/MediaPlayer2"
_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
_SYNC_EVERY = 2   # re-read spotifyd every N timer ticks; interpolate in between


def _img(images, smallest=False):
    if not images:
        return ""
    return images[-1]["url"] if smallest else images[0]["url"]


def _fmt_dur(seconds):
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}h {s % 3600 // 60}m"
    if s >= 60:
        return f"{s // 60}m {s % 60}s"
    return f"{s}s"


def _json_val(node):
    """Unwrap busctl --json `{"type","data"}` nodes into plain values."""
    if isinstance(node, dict):
        if len(node) == 2 and "type" in node and "data" in node:
            return _json_val(node["data"])
        return {k: _json_val(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_json_val(v) for v in node]
    return node


class RateLimited(Exception):
    """Raised in place of an API call while a 429 cooldown is active, so a task
    can still serve cache and then unwind quietly instead of hitting Spotify."""


class _Guarded:
    """Wraps the spotipy client: every API call first checks the backend's
    rate-limit cooldown and raises RateLimited rather than touching the network.
    Lets tasks emit cached data before the (suppressed) live fetch."""

    def __init__(self, sp, backend):
        self._sp = sp
        self._backend = backend

    def __getattr__(self, name):
        attr = getattr(self._sp, name)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            if self._backend._rl_remaining() > 0:
                raise RateLimited()
            return attr(*args, **kwargs)
        return wrapped


class Backend(QObject):
    loggedInChanged = Signal(bool)
    playlistsLoaded = Signal(list)
    tracksLoaded = Signal(list, str)
    searchLoaded = Signal(list)
    nowPlaying = Signal("QVariant")
    error = Signal(str)
    toast = Signal(str)

    def __init__(self):
        super().__init__()
        # single worker so spotipy's session is never touched concurrently
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._auth = make_auth()

        # rate-limit circuit breaker: once Spotify 429s us, suppress all further
        # requests until this monotonic deadline instead of hammering (which only
        # makes Spotify extend the ban). Protected by a lock because the deadline
        # is read on the worker thread and written there too, but the toast
        # throttle is touched from the same thread only. _Guarded raises
        # RateLimited at each call site so tasks can still serve cache first.
        self._rl_until = 0.0
        self._rl_lock = threading.Lock()
        self._rl_toast_at = 0.0
        self._sp = _Guarded(make_client(self._auth), self)

        self._np_id = None
        self._np_liked = False
        self._np_track_path = ""       # mpris:trackid, needed for SetPosition
        self._local_np = None
        self._np_playing_since = 0.0   # monotonic anchor for interpolating progress
        self._np_duration_ms = 0
        self._spotifyd_device_id = None
        self._user_id = None
        self._liked_total = None
        self._tick = 0
        self._track_index = {}         # uri -> track dict, for tracks we might record as recent
        self._search_seq = 0           # bumped per search; stale queued searches drop themselves
        self._liked_cache = {}         # track id -> bool; populated from every fetch that
                                       # already knows liked state, so now-playing changes
                                       # don't re-hit the API for tracks we just saw
        self._recent = None            # in-memory mirrors of the small sidebar json files,
        self._pinned = None            # loaded once and kept in sync on write so the sidebar
        self._played = None            # doesn't re-read/parse disk on every emit
        self._desktop = None           # local Desktop stash (full track dicts, newest first)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        # QtDBus is used to send commands; reads go through busctl --json since
        # PySide6 can't demarshal MPRIS's a{sv} metadata maps.
        self._bus = QDBusConnection.sessionBus()
        self._service = ""
        self._player = None

        for sub in ("tracks", "search"):
            (DATA_CACHE_DIR / sub).mkdir(parents=True, exist_ok=True)

    # ---- spotifyd playback over D-Bus ----

    def _rebind(self):
        # spotifyd only claims its MPRIS name while it's the active device, and the
        # name carries a per-process suffix, so look it up fresh each time.
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
        if self._rebind():
            self._player.call(method, *args)
        QTimer.singleShot(150, self._sync)  # let spotifyd settle, then refresh the UI

    def _read_state(self):
        if not self._rebind():
            return {"active": False}
        cmd = ["busctl", "--user", "--json=short", "get-property",
               self._service, _MPRIS_PATH, _PLAYER_IFACE,
               "PlaybackStatus", "Metadata", "Position", "Volume"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        except Exception:
            return {"active": False}
        if res.returncode != 0:
            self._service = ""  # gone — rediscover next time
            return {"active": False}

        vals = {}
        for name, line in zip(("PlaybackStatus", "Metadata", "Position", "Volume"),
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
        try:
            volume = max(0, min(100, int(round(float(vals.get("Volume") or 0.0) * 100))))
        except (ValueError, TypeError):
            volume = 0

        # bare track id from the url ("spotify:track:X") or trackid path ("/spotify/track/X")
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
            "volume":     volume,
            "liked":      False,
        }

    def _sync(self):
        data = self._read_state()
        if data.get("active"):
            tid = data.get("id", "")
            if tid and tid == self._np_id:
                data["liked"] = self._np_liked        # already know it for this track
            elif tid:
                self._np_id = tid
                self._submit(self._check_liked_task, tid)
        else:
            self._np_id = None
        self._local_np = data
        self.nowPlaying.emit(data)

    def _check_liked_task(self, tid):
        if tid in self._liked_cache:
            liked = self._liked_cache[tid]          # seen this session — no API call
        else:
            try:
                liked = self._sp.current_user_saved_tracks_contains([tid])[0] if tid else False
            except SpotifyException as e:
                if e.http_status == 429:
                    raise      # let _guard trip the cooldown instead of hiding it
                liked = False
            except Exception:
                liked = False
            if tid:
                self._liked_cache[tid] = liked
        self._np_liked = liked
        snap = self._local_np
        if snap and snap.get("id") == tid:
            data = {**snap, "liked": liked}
            self._local_np = data
            self.nowPlaying.emit(data)

    def _on_tick(self):
        self._tick += 1
        if self._tick % _SYNC_EVERY == 0:
            self._sync()
            return
        snap = self._local_np
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
        except RateLimited:
            # cooldown is active; the task already served whatever it had cached,
            # then its live fetch was suppressed. Nudge the user, throttled, so we
            # don't toast on every queued action during a long ban.
            now = time.monotonic()
            if now - self._rl_toast_at > 5:
                self._rl_toast_at = now
                self.toast.emit(
                    f"Spotify rate limit — try again in {_fmt_dur(self._rl_remaining())}")
        except SpotifyException as e:
            if e.http_status == 429:
                self._enter_cooldown(e)
                return
            print(f"[error] Spotify HTTP {e.http_status} (code {e.code}): {e.msg}",
                  file=sys.stderr, flush=True)
            traceback.print_exc()
            self.error.emit(str(e))
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            traceback.print_exc()
            self.error.emit(str(e))

    def _rl_remaining(self):
        with self._rl_lock:
            return max(0.0, self._rl_until - time.monotonic())

    def _enter_cooldown(self, exc):
        # honour Spotify's Retry-After exactly — that's the value that lets the
        # ban actually expire. Fall back to a short backoff when it's missing.
        try:
            retry_after = int((exc.headers or {}).get("Retry-After", 0))
        except (TypeError, ValueError):
            retry_after = 0
        cooldown = max(5, retry_after)
        with self._rl_lock:
            self._rl_until = time.monotonic() + cooldown
        self._rl_toast_at = time.monotonic()
        print(f"[rate-limit] backing off {cooldown}s (Retry-After: {retry_after}s)",
              file=sys.stderr, flush=True)
        self.toast.emit(f"Spotify rate limit — pausing for {_fmt_dur(cooldown)}")

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

    def _read_json(self, name, typ, default):
        try:
            p = DATA_CACHE_DIR / name
            if p.exists():
                v = json.loads(p.read_text())
                if isinstance(v, typ):
                    return v
        except Exception:
            pass
        return default

    def _write_json(self, name, data):
        try:
            (DATA_CACHE_DIR / name).write_text(json.dumps(data))
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

    @Slot()
    def openLogs(self):
        # live-tail the log in whatever terminal is around. detached so closing the
        # terminal (or frostify) doesn't take the other down.
        tail = ["sh", "-c", 'exec tail -n 500 -f "$1"', "_", str(LOG_FILE)]
        term = os.environ.get("TERMINAL")
        attempts = []
        if term:
            attempts.append([term, "-e", *tail])
        attempts += [
            ["kitty", *tail],
            ["foot", *tail],
            ["alacritty", "-e", *tail],
            ["wezterm", "start", "--", *tail],
            ["xterm", "-e", *tail],
        ]
        for cmd in attempts:
            try:
                subprocess.Popen(cmd, start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except (FileNotFoundError, OSError):
                continue
        self.error.emit("Couldn't find a terminal to show logs in.")

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
        try:   # refresh the liked count for the sidebar (cheap, total only)
            self._liked_total = self._sp.current_user_saved_tracks(limit=1).get("total", 0)
        except Exception:
            pass
        # cache only the real playlists; Liked/Recent are injected at display time
        # by _apply_pins so they always show regardless of cache freshness.
        if out != cached:
            self.playlistsLoaded.emit(self._apply_pins(out))
        self._cache_write("playlists.json", out)

    def _uid(self):
        if not self._user_id:
            self._user_id = self._sp.current_user()["id"]
        return self._user_id

    def _liked_entry(self):
        # Liked Songs isn't a real playlist. Kept cheap (no network) since this runs
        # on every sidebar emit; the collection context for playback is resolved when
        # the list is opened, in _tracks_task. _liked_total is refreshed in the bg.
        return {
            "id":    LIKED_ID,
            "uri":   "",
            "name":  "Liked Songs",
            "image": "",
            "count": self._liked_total or 0,
            "owner": "you",
            "pinned": False,
        }

    def _recent_entry(self):
        return {
            "id":    RECENT_ID,
            "uri":   "",                 # no context — recent tracks play one-off
            "name":  "Recent Searches",
            "image": "",
            "count": len(self._load_recent()),
            "owner": "you",
            "pinned": False,
        }

    def _desktop_entry(self):
        return {
            "id":    DESKTOP_ID,
            "uri":   "",                 # local stash — tracks play one-off, no context
            "name":  "Desktop",
            "image": "",
            "count": len(self._load_desktop()),
            "owner": "you",
            "pinned": False,
        }

    # ---- desktop stash (local, hand-curated with the 'd' key; newest first) ----

    def _load_desktop(self):
        if self._desktop is None:
            self._desktop = self._read_json("desktop.json", list, [])
        return self._desktop

    @Slot("QVariant")
    def addToDesktop(self, track):
        self._submit(self._desktop_toggle_task, dict(track) if track else {})

    def _desktop_toggle_task(self, track):
        tid = track.get("id")
        if not tid:
            return
        items = self._load_desktop()
        if any(t.get("id") == tid for t in items):
            items = [t for t in items if t.get("id") != tid]
            msg = "Removed from Desktop"
        else:
            # store a one-off copy (no playlist context) so it plays standalone
            items = [{**track, "contextUri": ""}] + items
            msg = "Added to Desktop"
        self._desktop = items
        self._write_json("desktop.json", items)
        self.toast.emit(msg)
        self.tracksLoaded.emit(items, "Desktop")  # refresh the view only if Desktop is open
        self._index_tracks(items)
        self._playlists_task()                    # refresh the sidebar count/order

    # ---- recent searches (local history of searched tracks, newest first) ----

    def _load_recent(self):
        if self._recent is None:
            self._recent = self._read_json("recent.json", list, [])
        return self._recent

    def _index_tracks(self, tracks):
        # remember search results by uri so we can record a track as "recent" only
        # if the user actually plays it (not just because it showed up in results)
        for t in tracks:
            if t.get("uri"):
                self._track_index[t["uri"]] = t

    def _record_recent(self, tracks):
        tracks = [t for t in tracks if t.get("id")]
        if not tracks:
            return
        fresh = {t["id"] for t in tracks}
        merged = tracks + [t for t in self._load_recent() if t.get("id") not in fresh]
        self._recent = merged[:RECENT_MAX]
        self._write_json("recent.json", self._recent)

    # ---- pinning (local only — Spotify has no pin API) ----

    def _load_pinned(self):
        if self._pinned is None:
            self._pinned = self._read_json("pinned.json", list, [])
        return self._pinned

    def _apply_pins(self, playlists):
        # order: Recent Searches, Liked Songs, then pinned (pin order), then the rest by
        # most recently played, then whatever order Spotify gave us for the never-played.
        # The two special rows are injected here so they show regardless of cache state;
        # we strip any that an older cache baked into the list so they don't double up.
        real = [p for p in playlists if p["id"] not in (RECENT_ID, DESKTOP_ID, LIKED_ID)]
        pinned = self._load_pinned()
        rank = {pid: i for i, pid in enumerate(pinned)}
        played = self._load_played()
        special = {RECENT_ID: 0, DESKTOP_ID: 1, LIKED_ID: 2}
        decorated = [self._recent_entry(), self._desktop_entry(), self._liked_entry()] \
            + [{**p, "pinned": p["id"] in rank} for p in real]

        def key(item):
            i, p = item
            pid = p["id"]
            if pid in special:
                return (0, special[pid], 0.0, i)
            if pid in rank:
                return (1, rank[pid], 0.0, i)
            return (2, 0, -played.get(pid, 0), i)  # recent first; 0 (never) keeps Spotify order

        return [p for _, p in sorted(enumerate(decorated), key=key)]

    # ---- last-played tracking (local — drives the recency sort above) ----

    def _load_played(self):
        if self._played is None:
            self._played = self._read_json("played.json", dict, {})
        return self._played

    def _record_played(self, playlist_id):
        # returns True if this changes which playlist is most-recent (i.e. the
        # sidebar order would actually shift), so the caller can skip a needless re-emit.
        if not playlist_id:
            return False
        played = self._load_played()
        was_top = bool(played) and max(played, key=played.get) == playlist_id
        played[playlist_id] = time.time()
        self._write_json("played.json", played)
        return not was_top

    @Slot(str)
    def togglePin(self, playlist_id):
        pinned = self._load_pinned()
        if playlist_id in pinned:
            pinned.remove(playlist_id)
            msg = "Unpinned"
        else:
            pinned.insert(0, playlist_id)
            msg = "Pinned"
        self._write_json("pinned.json", pinned)
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
        if playlist_id == RECENT_ID:
            recent = self._load_recent()
            self.tracksLoaded.emit(recent, name)   # purely local, no fetch
            self._index_tracks(recent)             # replaying one re-bumps it to the top
            return
        if playlist_id == DESKTOP_ID:
            items = self._load_desktop()
            self.tracksLoaded.emit(items, name)    # purely local, no fetch
            self._index_tracks(items)
            return
        if playlist_id == LIKED_ID:
            # collection context so a played track keeps the rest of liked as the queue
            context_uri = f"spotify:user:{self._uid()}:collection"
            raw = []
            res = self._sp.current_user_saved_tracks(limit=50)
            while res:
                raw += res["items"]
                res = self._sp.next(res) if res.get("next") else None
            tracks = [r.get("track") for r in raw]
            tracks = [t for t in tracks if t and t.get("id")]
            out = [self._track_dict(t, True, context_uri) for t in tracks]  # all liked by definition
            self._liked_cache.update({t["id"]: True for t in tracks})
            self._liked_total = len(out)
            if out != cached:
                self.tracksLoaded.emit(out, name)
            self._cache_write(key, out)
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
        self._liked_cache.update(liked)
        out    = [self._track_dict(t, liked.get(t["id"], False), context_uri) for t in tracks]
        if out != cached:
            self.tracksLoaded.emit(out, name)
        self._cache_write(key, out)

    @Slot(str)
    def search(self, query):
        self._search_seq += 1
        self._submit(self._search_task, query, False, self._search_seq)

    @Slot(str)
    def refreshSearch(self, query):
        self._search_seq += 1
        self._submit(self._search_task, query, True, self._search_seq)

    def _search_task(self, query, force, seq):
        # a newer keystroke already superseded this one — don't bother the API
        # for results that would be thrown away (and would flicker the UI).
        if seq != self._search_seq:
            return
        q = query.strip()
        if not q:
            self.searchLoaded.emit([])
            return
        key = "search/" + hashlib.md5(q.lower().encode()).hexdigest() + ".json"
        cached, fresh = self._cache_get(key, TTL_SEARCH)
        if cached is not None and fresh and not force:
            self.searchLoaded.emit(cached)
            self._index_tracks(cached)
            return
        # Spotify capped /search limit at 10 (Feb 2026 changelog; 50 now 400s
        # "Invalid limit"). Dedup by id since the API can still echo a track
        # more than once.
        res    = self._sp.search(q=q, type="track", limit=10)
        items  = (res.get("tracks") or {}).get("items") or []
        tracks = list({t["id"]: t for t in items if t.get("id")}.values())
        liked  = self._saved_contains([t["id"] for t in tracks])
        self._liked_cache.update(liked)
        out   = [self._track_dict(t, liked.get(t["id"], False), "") for t in tracks]
        self.searchLoaded.emit(out)
        self._cache_write(key, out)
        self._index_tracks(out)

    def _saved_contains(self, ids):
        # Returns {id: bool}. Dedup first: search pages and playlists routinely
        # repeat track ids, and every duplicate would otherwise cost another slot
        # in a 429-prone request. This spotipy hits the unified
        # me/library/contains endpoint, which rejects 50 uris at once
        # ("Too many uris requested") — chunk the unique ids by 20.
        uniq = list(dict.fromkeys(i for i in ids if i))
        liked = {}
        for i in range(0, len(uniq), 20):
            chunk = uniq[i:i + 20]
            liked.update(zip(chunk, self._sp.current_user_saved_tracks_contains(chunk)))
        return liked

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
    # Transport runs over MPRIS; starting a specific track needs start_playback()
    # so the playlist context carries over.

    def _spotifyd_device(self):
        if self._spotifyd_device_id:
            return self._spotifyd_device_id
        devs = self._sp.devices().get("devices", [])
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
        try:
            self._start_playback(dev, uri, context_uri)
        except SpotifyException as e:
            # a cached device id that 404s means spotifyd restarted with a new id —
            # drop it, re-resolve once, and retry so playback doesn't silently die.
            if e.http_status != 404 or not self._spotifyd_device_id:
                raise
            self._spotifyd_device_id = None
            dev = self._spotifyd_device()
            if not dev:
                self.error.emit("spotifyd device not found — is spotifyd running?")
                return
            self._start_playback(dev, uri, context_uri)
        if not context_uri:
            # a one-off play (no playlist context) means it came from search — record it
            t = self._track_index.get(uri)
            if t:
                self._record_recent([t])
        if context_uri.startswith("spotify:playlist:"):
            if self._record_played(context_uri.rsplit(":", 1)[-1]):
                self._playlists_task()  # already on the worker thread; re-emit so the sidebar reorders live

    def _start_playback(self, dev, uri, context_uri):
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
        # via busctl so the trackid goes as an object path ('o'), not a string
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

    @Slot(int)
    def setVolume(self, pct):
        # Sets spotifyd's own MPRIS volume (its Spotify Connect device level), which
        # only attenuates spotifyd's audio — not the system mixer. Runs on the worker
        # so the (fast, local) busctl call is off the GUI thread and the child is reaped.
        self._submit(self._set_volume_task, max(0, min(100, int(pct))))

    def _set_volume_task(self, pct):
        svc = self._service          # populated by the regular sync's _rebind
        if not svc:
            return
        try:
            subprocess.run(
                ["busctl", "--user", "set-property", svc, _MPRIS_PATH, _PLAYER_IFACE,
                 "Volume", "d", f"{pct / 100:.4f}"],
                capture_output=True, timeout=2,
            )
        except Exception:
            return
        # optimistic echo so the slider settles on the new value without waiting for
        # the next poll (which is up to _SYNC_EVERY seconds away).
        snap = self._local_np
        if snap and snap.get("active"):
            data = {**snap, "volume": pct}
            self._local_np = data
            self.nowPlaying.emit(data)

    @Slot(str, bool)
    def toggleLike(self, track_id, like):
        def task():
            if like:
                self._sp.current_user_saved_tracks_add([track_id])
            else:
                self._sp.current_user_saved_tracks_delete([track_id])
            self._liked_cache[track_id] = like
            self._cache_delete(f"tracks/{LIKED_ID}.json")  # the liked list changed
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
            if playlist_id == LIKED_ID:
                # "add to Liked Songs" == save the track
                self._sp.current_user_saved_tracks_add([track_uri.rsplit(":", 1)[-1]])
                self._liked_cache[track_uri.rsplit(":", 1)[-1]] = True
                self.toast.emit("Added to Liked Songs")
            else:
                self._sp.playlist_add_items(playlist_id, [track_uri])
                self.toast.emit("Added to playlist")
            self._cache_delete(f"tracks/{playlist_id}.json")
        self._submit(task)
