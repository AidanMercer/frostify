#!/usr/bin/env bash
# focus frostify if it's already open, otherwise launch it
if hyprctl clients -j | grep -q '"class": "frostify"'; then
    hyprctl dispatch focuswindow class:frostify
else
    cd "$(dirname "$0")" && setsid -f python -m frostify >/dev/null 2>&1
fi
