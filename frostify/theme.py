import re
import subprocess
import tomllib
from pathlib import Path

# dark frosted palette (tokyo-night-ish), yazi vibe. #AARRGGBB strings.
# These are the *defaults*. If the active theme (the folder of whatever wallpaper
# awww is currently showing) drops a config.toml with accent colors, the
# _apply_active_theme() pass below re-tints the palette to match it — same toml
# the quickshell bar/clock read, so frostify follows the rest of the rice.
THEME = {
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


def _active_theme_dir():
    """Folder of the wallpaper awww is currently showing — the same resolution
    the quickshell ThemeConfig uses (awww query -> dirname of the image).
    None if awww isn't running/answering."""
    try:
        out = subprocess.run(
            ["awww", "query"], capture_output=True, text=True, timeout=2
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"image:\s*(.+)", out)  # first monitor; matches awww's "image: /path"
    if not m:
        return None
    return Path(m.group(1).strip()).parent


def _apply_active_theme(theme):
    d = _active_theme_dir()
    if d is None:
        return
    cfg = d / "config.toml"
    if not cfg.exists():
        return
    try:
        data = tomllib.loads(cfg.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return

    def col(key):
        v = data.get(key)
        return v if isinstance(v, str) and v.startswith("#") else None

    accent = col("accent")
    if accent and _rgba(accent):
        theme["accent"]     = _rgba(accent)
        theme["sel"]        = _rgba(accent)
        theme["selDim"]     = _rgba(accent, "3a")
        theme["accentSoft"] = _rgba(accent, "33")

    accent2 = col("accent2")          # secondary hue -> playlist/"folder" color
    if accent2 and _rgba(accent2):
        theme["teal"] = _rgba(accent2)

    green = col("hue_green")          # sizes / durations
    if green and _rgba(green):
        theme["green"] = _rgba(green)

    fg = col("fg")
    if fg and _rgba(fg):
        theme["text"]    = _rgba(fg)
        theme["subtext"] = _rgba(fg, "aa")   # same hue, dimmed

    bg = col("bg")
    if bg and _rgba(bg):
        theme["bg"]      = _rgba(bg, "66")   # stay glassy so Hyprland's blur shows through
        theme["selText"] = _rgba(bg)         # dark base reads well on the bright accent pill


_apply_active_theme(THEME)
