import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

from PySide6.QtCore import (Property, QFileSystemWatcher, QObject, QTimer,
                            QUrl, Signal)

THEMES_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "themes"
_AWWW_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "awww"

# dark frosted palette (tokyo-night-ish), yazi vibe. #AARRGGBB strings.
# These are the *defaults* — used verbatim when no rice theme resolves. When one
# does, _build_theme() re-derives most keys from the theme's config.toml tokens
# (layered over themes/default/config.toml, same as the quickshell loaders) so
# frostify follows the rest of the rice, light themes included.
_BASE = {
    "bg":          "#661f2335",   # window base, ~40% dark navy (blur shows through)
    "glassSoft":   "#14ffffff",   # hover
    "sel":         "#ff7aa2f7",   # selection pill, active pane (periwinkle)
    "selText":     "#ff1a1b26",   # text on active pill (dark)
    "selDim":      "#3a7aa2f7",   # cursor pill when pane is inactive
    "border":      "#30ffffff",
    "divider":     "#1affffff",
    "badge":       "#33ffffff",   # status-bar badge backing

    "text":        "#ffc0caf5",   # light
    "subtext":     "#ff7e87b0",
    "teal":        "#ff7dcfff",   # playlist / "folder" color
    "green":       "#ff9ece6a",   # sizes / durations
    "accent":      "#ff7aa2f7",
    "accentSoft":  "#337aa2f7",

    "errorBg":     "#e6db4b4b",
    "toastBg":     "#ee2a2e42",

    "radius":    16,
    "radiusSm":  10,
    "radiusXs":  7,
    "pad":       12,

    "font":      "Adwaita Mono",
}

# mirrors themes/default/config.toml + the shell's ThemeTokens.js — fallback if
# even the default toml is missing
_TOKEN_FALLBACK = {
    "accent":      "#a8b5e8",
    "accent2":     "#c8a5e8",
    "accent3":     "#e8919b",
    "accent_warn": "#e8c89b",
    "accent_dim":  "#3b3f51",
    "text":        "#e6e6f0",
    "glass":       "#0f0f14",
    "font_mono":   "monospace",
}


def _rgba(hex_color, alpha="ff"):
    """The theme tomls store opaque "#rrggbb"; frostify/QML want "#aarrggbb".
    Prefix the alpha. Passes 8-digit values through, expands #rgb shorthand.
    Returns None for anything we don't recognise so the caller keeps its default."""
    h = hex_color.lstrip("#")
    if len(h) == 8:
        return "#" + h
    if len(h) == 6:
        return "#" + alpha + h
    if len(h) == 3:
        return "#" + alpha + "".join(c * 2 for c in h)
    return None


def _focused_monitor():
    """Name of the focused Hyprland monitor, "" if unknowable — monitors can
    show different themes, and frostify should match the one being looked at."""
    try:
        out = subprocess.run(
            ["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=2
        ).stdout
        for m in json.loads(out):
            if m.get("focused"):
                return m.get("name", "")
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return ""


def _active_theme_dir():
    """Folder of the wallpaper awww is showing on the focused monitor — the
    same resolution the quickshell loaders use (awww query -> dirname of the
    image), first monitor as fallback. FROSTIFY_THEME overrides it (a theme
    name, or a path) for testing themes headlessly. None if nothing resolves."""
    override = os.environ.get("FROSTIFY_THEME", "").strip()
    if override:
        p = Path(override).expanduser() if "/" in override else THEMES_DIR / override
        return p if p.is_dir() else None
    try:
        out = subprocess.run(
            ["awww", "query"], capture_output=True, text=True, timeout=2
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    lines = out.splitlines()
    mon = _focused_monitor()
    picked = next((l for l in lines if mon and f"{mon}:" in l), None)
    m = re.search(r"image:\s*(.+)", picked if picked is not None else out)
    if not m:
        return None
    d = Path(m.group(1).strip()).parent
    return d if d.is_dir() else None


def _read_tokens(theme_dir):
    """Theme config.toml layered over default/config.toml layered over the
    builtin fallback — flat keys, last write wins (same as the shell)."""
    tokens = dict(_TOKEN_FALLBACK)
    layers = [THEMES_DIR / "default" / "config.toml"]
    if theme_dir is not None:
        layers.append(theme_dir / "config.toml")
    for f in layers:
        try:
            tokens.update(tomllib.loads(f.read_text()))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return tokens


def _build_theme(tokens):
    """Re-derive frostify's palette from the rice tokens. The chrome hairlines
    (border/divider/hover) come from `text` instead of hardcoded white so light
    themes (shiro, guts) stay legible."""
    theme = dict(_BASE)

    def col(key):
        v = tokens.get(key)
        return v if isinstance(v, str) and v.startswith("#") and _rgba(v) else None

    accent = col("accent")
    if accent:
        theme["accent"]     = _rgba(accent)
        theme["sel"]        = _rgba(accent)
        theme["selDim"]     = _rgba(accent, "3a")
        theme["accentSoft"] = _rgba(accent, "33")

    accent2 = col("accent2")          # secondary hue -> playlist/"folder" color
    if accent2:
        theme["teal"] = _rgba(accent2)

    accent3 = col("accent3")          # danger -> error toast
    if accent3:
        theme["errorBg"] = _rgba(accent3, "e6")

    green = col("hue_green")          # sizes / durations
    if green:
        theme["green"] = _rgba(green)

    fg = col("fg") or col("text")
    if fg:
        theme["text"]    = _rgba(fg)
        theme["subtext"] = _rgba(fg, "aa")   # same hue, dimmed

    txt = col("text") or col("fg")    # hairlines follow the ink, not white
    if txt:
        theme["border"]    = _rgba(txt, "30")
        theme["divider"]   = _rgba(txt, "1a")
        theme["glassSoft"] = _rgba(txt, "14")
        theme["badge"]     = _rgba(txt, "33")

    bg = col("bg")
    if bg:
        theme["bg"]      = _rgba(bg, "66")   # stay glassy so Hyprland's blur shows through
        theme["selText"] = _rgba(bg)         # base color reads well on the bright accent pill

    glass = col("glass") or bg
    if glass:
        theme["toastBg"] = _rgba(glass, "ee")

    font = tokens.get("font_mono")
    if isinstance(font, str) and font:
        theme["font"] = font

    return theme


class ThemeManager(QObject):
    """Follows the active rice theme (~/.config/themes/<x>) live.

    - palette: config.toml tokens -> the Theme dict all the QML binds to
    - chrome slot: the theme's optional frostify.qml (same slot grammar as the
      shell's popup.qml — pal/host injection, backdrop/overlay Components)
    - watches ~/.cache/awww (touched on every wallpaper switch) plus the active
      theme's config.toml / frostify.qml, so switching themes or editing them
      re-skins frostify while it runs. themeChanged fires after each rebuild.
    """
    themeChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dir = None
        self._theme = dict(_BASE)
        self._pal = {}
        self._source = ""
        self._wants_pal = False
        self._wants_host = False
        self._nonce = 0
        self._snapshot = None

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._poke)
        self._watcher.fileChanged.connect(self._poke)
        # theme switches touch several files in a burst — coalesce them
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._refresh)

        self._refresh(first=True)

    # -- QML-facing state (Rice context property) --
    @Property(str, notify=themeChanged)
    def source(self):
        """file:// URL of the theme's frostify.qml with a ?v= nonce (hot reload),
        or "" when the theme ships none."""
        return self._source

    @Property(bool, notify=themeChanged)
    def wantsPal(self):
        return self._wants_pal

    @Property(bool, notify=themeChanged)
    def wantsHost(self):
        return self._wants_host

    @Property("QVariantMap", notify=themeChanged)
    def pal(self):
        return self._pal

    @Property(str, notify=themeChanged)
    def themeDir(self):
        return str(self._dir) if self._dir else ""

    @Property(str, notify=themeChanged)
    def name(self):
        return self._dir.name if self._dir else ""

    def theme_dict(self):
        return self._theme

    # -- plumbing --
    def _poke(self, _path):
        self._debounce.start()

    def _refresh(self, first=False):
        d = _active_theme_dir()
        tokens = _read_tokens(d)

        qml = (d / "frostify.qml") if d else None
        qml_stat = None
        qml_text = ""
        if qml is not None and qml.is_file():
            try:
                st = qml.stat()
                qml_stat = (st.st_mtime_ns, st.st_size)
                qml_text = qml.read_text()
            except OSError:
                qml_stat = None

        snapshot = (str(d) if d else "", tuple(sorted(
            (k, str(v)) for k, v in tokens.items())), qml_stat)
        self._rewatch(d)
        if snapshot == self._snapshot:
            return
        self._snapshot = snapshot

        self._dir = d
        self._theme = _build_theme(tokens)
        self._pal = {
            "neon":     tokens.get("accent", _TOKEN_FALLBACK["accent"]),
            "cyan":     tokens.get("accent2", _TOKEN_FALLBACK["accent2"]),
            "magenta":  tokens.get("accent3", _TOKEN_FALLBACK["accent3"]),
            "amber":    tokens.get("accent_warn", _TOKEN_FALLBACK["accent_warn"]),
            "dim":      tokens.get("accent_dim", _TOKEN_FALLBACK["accent_dim"]),
            "text":     tokens.get("text", _TOKEN_FALLBACK["text"]),
            "glass":    tokens.get("glass", _TOKEN_FALLBACK["glass"]),
            "fontMono": tokens.get("font_mono", _TOKEN_FALLBACK["font_mono"]),
            "uiScale":  1.0,
            "themeDir": str(d) if d else "",
        }

        if qml_stat is not None:
            # same handshake as the shell's loaders: grep the file for the
            # literal property declarations to decide what to inject
            self._wants_pal = "property var pal" in qml_text
            self._wants_host = "property var host" in qml_text
            self._nonce += 1
            self._source = QUrl.fromLocalFile(str(qml)).toString() + f"?v={self._nonce}"
        else:
            self._wants_pal = self._wants_host = False
            self._source = ""

        print(f"[theme] {self._dir.name if self._dir else '(defaults)'}"
              f"  chrome={'frostify.qml' if self._source else 'none'}", flush=True)
        if not first:
            self.themeChanged.emit()

    def _rewatch(self, d):
        """(Re-)arm the watcher. Dir watches catch atomic-replace saves and new
        files; file watches catch in-place edits. Stale paths are pruned by
        QFileSystemWatcher itself when they vanish; re-adding dupes is a no-op."""
        want = [_AWWW_CACHE] + [p for p in _AWWW_CACHE.glob("*") if p.is_dir()]
        want += [THEMES_DIR / "default" / "config.toml"]
        if d is not None:
            want += [d, d / "config.toml", d / "frostify.qml"]
        have = set(self._watcher.directories()) | set(self._watcher.files())
        missing = [str(p) for p in want if p.exists() and str(p) not in have]
        if missing:
            self._watcher.addPaths(missing)
