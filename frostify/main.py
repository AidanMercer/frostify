import sys
from pathlib import Path

from PySide6.QtCore import QUrl, qInstallMessageHandler
from PySide6.QtGui import QFont, QGuiApplication, QSurfaceFormat
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache
from PySide6.QtQml import QQmlApplicationEngine, QQmlNetworkAccessManagerFactory

from . import config
from .theme import THEME


def _qt_message_handler(mode, ctx, msg):
    loc = f" ({ctx.file}:{ctx.line})" if ctx.file else ""
    print(f"[qml] {msg}{loc}", file=sys.stderr, flush=True)


class _CachingNAMFactory(QQmlNetworkAccessManagerFactory):
    """Gives QML Images a persistent on-disk HTTP cache so album art doesn't
    re-download every launch."""
    def create(self, parent):
        nam = QNetworkAccessManager(parent)
        cache = QNetworkDiskCache(nam)
        config.IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.setCacheDirectory(str(config.IMG_CACHE_DIR))
        cache.setMaximumCacheSize(256 * 1024 * 1024)
        nam.setCache(cache)
        return nam


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

    qInstallMessageHandler(_qt_message_handler)

    app = QGuiApplication(sys.argv)
    app.setApplicationName("frostify")
    app.setDesktopFileName("frostify")  # becomes the Wayland app_id Hyprland sees
    app.setFont(QFont(THEME["font"]))   # monospace everywhere, yazi-style

    from .backend import Backend
    backend = Backend()

    engine = QQmlApplicationEngine()
    engine._nam_factory = _CachingNAMFactory()  # keep a ref so it isn't GC'd
    engine.setNetworkAccessManagerFactory(engine._nam_factory)
    ctx = engine.rootContext()
    ctx.setContextProperty("backend", backend)
    ctx.setContextProperty("Theme", THEME)

    qml = Path(__file__).parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects():
        sys.exit(1)
    sys.exit(app.exec())
