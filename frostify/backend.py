import json
import traceback
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .auth import make_auth, make_client
from .config import DATA_CACHE_DIR


def _img(images, smallest=False):
    if not images:
        return ""
    return images[-1]["url"] if smallest else images[0]["url"]


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
        # one worker so spotipy's requests session is never touched concurrently
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._auth = make_auth()
        self._sp = make_client(self._auth)
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(lambda: self._submit(self._now_playing_task))
        (DATA_CACHE_DIR / "tracks").mkdir(parents=True, exist_ok=True)

    # ---- disk cache (show stale instantly, refresh in background) ----
    def _cache_read(self, name):
        try:
            p = DATA_CACHE_DIR / name
            if p.exists():
                return json.loads(p.read_text())
        except Exception:
            pass
        return None

    def _cache_write(self, name, data):
        try:
            (DATA_CACHE_DIR / name).write_text(json.dumps(data))
        except Exception:
            pass

    # ---- threading helpers ----
    def _submit(self, fn, *args):
        self._pool.submit(self._guard, fn, *args)

    def _guard(self, fn, *args):
        try:
            fn(*args)
        except Exception as e:  # surface anything to the UI instead of dying silently
            traceback.print_exc()
            self.error.emit(str(e))

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
            self._auth.get_access_token()  # opens browser + tiny local server, then caches
            self.loggedInChanged.emit(True)
        self._submit(task)

    @Slot()
    def startPolling(self):
        # called from QML (main thread) after login, so the timer starts in the right thread
        self._timer.start()
        self._submit(self._now_playing_task)

    # ---- library / browse ----
    @Slot()
    def loadPlaylists(self):
        self._submit(self._playlists_task)

    def _playlists_task(self):
        cached = self._cache_read("playlists.json")
        if cached:
            self.playlistsLoaded.emit(cached)
        out = []
        res = self._sp.current_user_playlists(limit=50)
        while res:
            for p in res["items"]:
                if not p or not p.get("id"):
                    continue
                out.append({
                    "id": p["id"],
                    "uri": p.get("uri", ""),
                    "name": p.get("name", "Untitled"),
                    "image": _img(p.get("images")),
                    "count": (p.get("tracks") or {}).get("total", 0),
                    "owner": (p.get("owner") or {}).get("display_name", ""),
                })
            res = self._sp.next(res) if res.get("next") else None
        if out != cached:
            self.playlistsLoaded.emit(out)
            self._cache_write("playlists.json", out)

    @Slot(str, str, str)
    def openPlaylist(self, playlist_id, name, context_uri):
        self._submit(self._tracks_task, playlist_id, name, context_uri)

    def _tracks_task(self, playlist_id, name, context_uri):
        key = f"tracks/{playlist_id}.json"
        cached = self._cache_read(key)
        if cached:
            self.tracksLoaded.emit(cached, name)
        raw = []
        res = self._sp.playlist_items(playlist_id, limit=100, additional_types=["track"])
        while res:
            raw += res["items"]
            res = self._sp.next(res) if res.get("next") else None
        # some API/spotipy versions return the track under "item" instead of "track"
        tracks = [(r.get("track") or r.get("item")) for r in raw]
        tracks = [t for t in tracks if t and t.get("id")]
        liked = self._saved_contains([t["id"] for t in tracks])
        out = [self._track_dict(t, lk, context_uri) for t, lk in zip(tracks, liked)]
        if out != cached:
            self.tracksLoaded.emit(out, name)
            self._cache_write(key, out)

    @Slot(str)
    def search(self, query):
        self._submit(self._search_task, query)

    def _search_task(self, query):
        if not query.strip():
            self.searchLoaded.emit([])
            return
        res = self._sp.search(q=query, type="track", limit=30)
        tracks = [t for t in res["tracks"]["items"] if t.get("id")]
        liked = dict(zip([t["id"] for t in tracks], self._saved_contains([t["id"] for t in tracks])))
        out = [self._track_dict(t, liked.get(t["id"], False), "") for t in tracks]
        self.searchLoaded.emit(out)

    def _saved_contains(self, ids):
        out = []
        for i in range(0, len(ids), 50):
            out += self._sp.current_user_saved_tracks_contains(ids[i:i + 50])
        return out

    def _track_dict(self, t, liked, context_uri):
        album = t.get("album") or {}
        return {
            "id": t["id"],
            "uri": t["uri"],
            "name": t["name"],
            "artist": ", ".join(a["name"] for a in t.get("artists", [])),
            "album": album.get("name", ""),
            "image": _img(album.get("images"), smallest=True),
            "durationMs": t.get("duration_ms", 0),
            "liked": bool(liked),
            "contextUri": context_uri,
        }

    # ---- playback ----
    def _device_id(self):
        pb = self._sp.current_playback()
        if pb and pb.get("device"):
            return pb["device"]["id"]
        devs = self._sp.devices().get("devices", [])
        return devs[0]["id"] if devs else None

    @Slot(str, str)
    def playTrack(self, uri, context_uri):
        self._submit(self._play_task, uri, context_uri)

    def _play_task(self, uri, context_uri):
        dev = self._device_id()
        if not dev:
            self.error.emit("No Spotify device found — open the Spotify app and play any song once.")
            return
        if context_uri:
            self._sp.start_playback(device_id=dev, context_uri=context_uri, offset={"uri": uri})
        else:
            self._sp.start_playback(device_id=dev, uris=[uri])
        self._submit(self._now_playing_task)

    @Slot()
    def togglePlay(self):
        def task():
            pb = self._sp.current_playback()
            if pb and pb.get("is_playing"):
                self._sp.pause_playback()
            else:
                self._sp.start_playback()
            self._submit(self._now_playing_task)
        self._submit(task)

    @Slot()
    def nextTrack(self):
        self._submit(lambda: (self._sp.next_track(), self._submit(self._now_playing_task)))

    @Slot()
    def prevTrack(self):
        self._submit(lambda: (self._sp.previous_track(), self._submit(self._now_playing_task)))

    @Slot(int)
    def seek(self, ms):
        self._submit(lambda: self._sp.seek_track(max(0, ms)))

    @Slot(str, bool)
    def toggleLike(self, track_id, like):
        def task():
            if like:
                self._sp.current_user_saved_tracks_add([track_id])
            else:
                self._sp.current_user_saved_tracks_delete([track_id])
            self.toast.emit("Liked" if like else "Removed from liked")
        self._submit(task)

    @Slot(str, str)
    def addToPlaylist(self, track_uri, playlist_id):
        def task():
            self._sp.playlist_add_items(playlist_id, [track_uri])
            self.toast.emit("Added to playlist")
        self._submit(task)

    def _now_playing_task(self):
        pb = self._sp.current_playback()
        if not pb or not pb.get("item"):
            self.nowPlaying.emit({"active": False})
            return
        t = pb["item"]
        album = t.get("album") or {}
        liked = self._saved_contains([t["id"]])[0] if t.get("id") else False
        self.nowPlaying.emit({
            "active": True,
            "isPlaying": pb.get("is_playing", False),
            "id": t.get("id", ""),
            "uri": t.get("uri", ""),
            "name": t.get("name", ""),
            "artist": ", ".join(a["name"] for a in t.get("artists", [])),
            "album": album.get("name", ""),
            "image": _img(album.get("images")),
            "progressMs": pb.get("progress_ms", 0),
            "durationMs": t.get("duration_ms", 0),
            "liked": bool(liked),
        })
