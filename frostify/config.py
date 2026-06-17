import os
import tomllib
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "frostify"
CONFIG_FILE = CONFIG_DIR / "config.toml"
CACHE_FILE = CONFIG_DIR / ".cache"
DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"

_CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "frostify"
DATA_CACHE_DIR = _CACHE_HOME / "data"     # playlists.json, tracks/<id>.json
IMG_CACHE_DIR = _CACHE_HOME / "images"    # album art (HTTP disk cache)
LOG_FILE = _CACHE_HOME / "frostify.log"   # tee'd stdout/stderr (see main.py)


class ConfigError(Exception):
    pass


_HELP = f"""frostify isn't configured yet.

1. Make a Spotify app at https://developer.spotify.com/dashboard
   - Redirect URI: {DEFAULT_REDIRECT}
   - copy the Client ID
2. Create {CONFIG_FILE} with:

   [spotify]
   client_id = "your-client-id-here"
   redirect_uri = "{DEFAULT_REDIRECT}"

(there's a config.example.toml in the repo you can copy)"""


def load_config():
    if not CONFIG_FILE.exists():
        raise ConfigError(_HELP)
    data = tomllib.loads(CONFIG_FILE.read_text())
    sp = data.get("spotify", {})
    client_id = sp.get("client_id", "")
    redirect = sp.get("redirect_uri", DEFAULT_REDIRECT)
    if not client_id or client_id.lower().startswith("paste") or client_id == "your-client-id-here":
        raise ConfigError(_HELP)
    return client_id, redirect
