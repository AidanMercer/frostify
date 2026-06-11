# frostify

A small, frosted-white-glass Spotify GUI for Hyprland. Your own front-end — browse
playlists, search, like songs, add to playlists, and control playback — with audio
played locally by [`spotifyd`](https://github.com/Spotifyd/spotifyd).

Built with **PySide6 + QML**: Python handles auth and the Spotify Web API (search,
playlists, library); QML draws the UI. The glass look comes from a translucent window
+ Hyprland's blur.

## How it works

- **Playback** runs through `spotifyd`, a lightweight Spotify daemon. frostify controls
  it locally over **D-Bus (MPRIS)** — play/pause, skip, seek, and now-playing all happen
  with no network calls, so you never hit Spotify's API rate limits.
- **Search, playlists and library** use the Spotify Web API. These are cached and only
  fetched when you ask, so traffic stays tiny.
- Playback needs **Spotify Premium** (spotifyd's requirement). Browsing, searching,
  liking and editing playlists work on free accounts too.

## Setup

### 1. Install dependencies (Arch)

```bash
sudo pacman -S pyside6 spotifyd
paru -S python-spotipy
```

> On other distros: install `spotifyd` from your package manager (or
> [cargo](https://github.com/Spotifyd/spotifyd)), plus PySide6 and spotipy via `pip`.

### 2. Configure spotifyd

Create `~/.config/spotifyd/spotifyd.conf`:

```ini
[global]
device_name = "frostify"
device_type = "computer"
bitrate = 320
backend = "pulseaudio"   # or "alsa" / "pipewire" to match your audio setup
# required — lets frostify control playback over D-Bus instead of the Web API:
use_mpris = true
dbus_type = "session"
```

Then start it (and enable it so it's always running):

```bash
systemctl --user enable --now spotifyd
```

The first time, log spotifyd into your Spotify account — run `spotifyd --no-daemon`
once and authorize via the Spotify app (Connect → "frostify"), or follow spotifyd's
[OAuth setup](https://docs.spotifyd.rs/).

### 3. Make a Spotify app (for search/library)

1. Go to <https://developer.spotify.com/dashboard> → **Create app**.
2. Set the **Redirect URI** to exactly: `http://127.0.0.1:8888/callback`
3. Copy the **Client ID** (no client secret needed — frostify uses the PKCE flow).

### 4. Configure frostify

```bash
mkdir -p ~/.config/frostify
cp config.example.toml ~/.config/frostify/config.toml
# then edit ~/.config/frostify/config.toml and paste your Client ID
```

### 5. Log in (one time)

```bash
./run.sh --login
```

This opens your browser to authorize the app, then caches a refresh token at
`~/.config/frostify/.cache`. You won't have to do it again.

### 6. Run

```bash
./run.sh
```

Press play on any track in frostify — that hands playback to `spotifyd`, and from then
on the now-playing bar and all transport controls run locally over D-Bus.

> **Note:** `spotifyd` only exposes its D-Bus controls while it's the active playback
> device. So on a fresh launch the now-playing bar is empty until you play something
> through frostify; after that it stays live for the whole session.

## Frosted look on Hyprland (optional)

Blur is automatic for the translucent window. To make it float at a nice size, add these
to your Hyprland config (the app's `class` is `frostify`):

```
windowrulev2 = float, class:^(frostify)$
windowrulev2 = size 1100 720, class:^(frostify)$
windowrulev2 = center, class:^(frostify)$
```

## Layout

```
frostify/
  frostify/            python package
    main.py            entry point: builds the QML engine, wires backend + theme
    backend.py         QObject bridge — Web API on a worker thread, playback over D-Bus
    auth.py            spotipy PKCE auth + scopes
    config.py          reads ~/.config/frostify/config.toml
    theme.py           the frosted-glass palette (exposed to QML as `Theme`)
    qml/               the UI
      Main.qml         window, layout, signal wiring
      Sidebar.qml      playlist list
      ContentView.qml  track list (playlist or search results)
      PreviewPane.qml  details for the selected playlist / track
      StatusBar.qml    transport controls + progress
      IconButton.qml   reusable round glyph button
      Toast.qml        little confirmation/error popup
```
