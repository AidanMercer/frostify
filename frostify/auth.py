import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE

from .config import CACHE_FILE, CONFIG_DIR, load_config

# everything the GUI needs: read+edit playlists, read+edit library, read+control playback
SCOPES = " ".join([
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-library-read",
    "user-library-modify",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-read-private",
])


def make_auth(open_browser=True):
    client_id, redirect = load_config()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return SpotifyPKCE(
        client_id=client_id,
        redirect_uri=redirect,
        scope=SCOPES,
        open_browser=open_browser,
        cache_handler=CacheFileHandler(cache_path=str(CACHE_FILE)),
    )


def make_client(auth=None):
    auth = auth or make_auth()
    # retries=0: never let spotipy sleep on a 429 Retry-After (it can be hours)
    # and freeze the worker thread — we surface and back off ourselves instead.
    return spotipy.Spotify(auth_manager=auth, retries=0, requests_timeout=10)


def has_cached_token(auth):
    return auth.cache_handler.get_cached_token() is not None
