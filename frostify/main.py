import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication, QSurfaceFormat
from PySide6.QtQml import QQmlApplicationEngine

from . import config
from .theme import THEME


def main():
    if "--login" in sys.argv:
        from .auth import make_auth
        try:
            make_auth().get_access_token()
        except config.ConfigError as e:
            print(e)
            sys.exit(1)
        print(f"Logged in. Token cached at {config.CACHE_FILE}")
        return

    try:
        config.load_config()
    except config.ConfigError as e:
        print(e)
        sys.exit(1)

    # ask for an alpha channel so the window can actually be translucent (Hyprland blurs behind it)
    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QGuiApplication(sys.argv)
    app.setApplicationName("frostify")
    app.setDesktopFileName("frostify")  # becomes the Wayland app_id Hyprland sees

    from .backend import Backend
    backend = Backend()

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("backend", backend)
    ctx.setContextProperty("Theme", THEME)

    qml = Path(__file__).parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects():
        sys.exit(1)
    sys.exit(app.exec())
