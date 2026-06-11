# frostify

A small, frosted-white-glass Spotify GUI for Hyprland. Your own front-end — browse
playlists, search, like songs, add to playlists, and control playback — while the
official Spotify app sits in the background doing the actual audio.

Built with **PySide6 + QML**: Python (via [spotipy](https://spotipy.readthedocs.io))
handles auth and all the Spotify Web API calls; QML draws the UI. The glass look comes
from a translucent window + Hyprland's blur.

## How it works

- **Metadata + control** go through the Spotify Web API (search, playlists, library, play/pause/skip).
- **Audio** is played by whatever Spotify client is running (the desktop app, or `spotifyd`).
  frostify just tells that device what to do — so keep Spotify open in the background.
- Controlling playback (clicking a song to play it) needs **Spotify Premium**. Browsing,
  searching, liking and editing playlists work on free accounts too.

## Setup

### 1. Install dependencies (Arch)

```bash
sudo pacman -S pyside6
paru -S python-spotipy
```

### 2. Make a Spotify app

1. Go to <https://developer.spotify.com/dashboard> → **Create app**.
2. Set the **Redirect URI** to exactly: `http://127.0.0.1:8888/callback`
3. Copy the **Client ID** (no client secret needed — frostify uses the PKCE flow).

### 3. Configure

```bash
mkdir -p ~/.config/frostify
cp config.example.toml ~/.config/frostify/config.toml
# then edit ~/.config/frostify/config.toml and paste your Client ID
```

### 4. Log in (one time)

```bash
./run.sh --login
```

This opens your browser to authorize the app, then caches a refresh token at
`~/.config/frostify/.cache`. You won't have to do it again.

### 5. Run

```bash
./run.sh
```

Make sure the Spotify desktop app is open and has played at least one song, so there's
an active device for frostify to control.

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
    backend.py         QObject bridge — all spotipy calls, run on a worker thread
    auth.py            spotipy PKCE auth + scopes
    config.py          reads ~/.config/frostify/config.toml
    theme.py           the frosted-glass palette (exposed to QML as `Theme`)
    qml/               the UI
      Main.qml         window, layout, signal wiring
      Sidebar.qml      playlist list
      ContentView.qml  track list (playlist or search results)
      TrackRow.qml     one track: play / like / add-to-playlist
      NowPlayingBar.qml transport controls + progress
      IconButton.qml   reusable round glyph button
      Toast.qml        little confirmation/error popup
```
