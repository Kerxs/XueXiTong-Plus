# -*- coding: utf-8 -*-
"""Desktop front end for the Chaoxing study task runner (Qt Quick / QML)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QtMsgType, qInfo, qInstallMessageHandler
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWebView import QtWebView

from ui.startup import APP_NAME, ROOT_DIR, StartupLoader

if os.name == "nt":
    LOG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "ChaoxingDesktop"
else:
    LOG_DIR = Path.home() / ".config" / "chaoxing-desktop"
GUI_LOG = LOG_DIR / "gui.log"
_LEVELS = {
    QtMsgType.QtDebugMsg: "DEBUG",
    QtMsgType.QtInfoMsg: "INFO",
    QtMsgType.QtWarningMsg: "WARNING",
    QtMsgType.QtCriticalMsg: "ERROR",
    QtMsgType.QtFatalMsg: "FATAL",
}


def _install_log() -> None:
    """Keep Qt/QML messages from the last run in gui.log (the packaged exe has no console)."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = GUI_LOG.open("w", encoding="utf-8")
    except OSError:
        return

    def handler(mode, context, message):
        line = f"{time.strftime('%H:%M:%S')} {_LEVELS.get(mode, 'INFO'):<7} {message}"
        log.write(line + "\n")
        log.flush()
        if sys.stderr is not None and not isinstance(sys.stderr, _LogStream):
            print(line, file=sys.stderr)

    qInstallMessageHandler(handler)

    # The packaged GUI has no console: send Python tracebacks to the same log.
    class _LogStream:
        def write(self, text):
            if text.strip():
                log.write(text if text.endswith("\n") else text + "\n")
                log.flush()

        def flush(self):
            log.flush()

    if sys.stderr is None:
        sys.stderr = _LogStream()

    def excepthook(kind, value, tb):
        import traceback

        log.write("".join(traceback.format_exception(kind, value, tb)))
        log.flush()
        try:        # anonymous crash statistics (when switched on): type and code location only
            from api import telemetry

            telemetry.record_crash(value, "app.crash")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = excepthook


def _quietly(fn, *args) -> None:
    try:
        fn(*args)
    except Exception as exc:  # bookkeeping only: never disturb the app
        qInfo(f"{fn.__name__} failed: {type(exc).__name__}: {exc}")


def main() -> None:
    _install_log()
    os.environ["QT_WEBVIEW_PLUGIN"] = "native"
    QGuiApplication.setApplicationName(APP_NAME)
    # Interface preferences live in the registry under this name. Tests and measurements set
    # CHAOXING_DESKTOP_SETTINGS_ORG so they never read or write the real user's preferences
    # (APPDATA alone does not isolate them).
    QGuiApplication.setOrganizationName(os.environ.get("CHAOXING_DESKTOP_SETTINGS_ORG") or "ChaoxingDesktop")
    QtWebView.initialize()
    # QApplication (not QGuiApplication): the tray icon and its menu are widgets.
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ROOT_DIR / "assets" / "learning_plus.png")))
    app.setFont(QFont("Microsoft YaHei UI", 10))

    QQuickStyle.setStyle(os.environ.get("CHAOXING_DESKTOP_STYLE", "FluentWinUI3"))
    QQuickStyle.setFallbackStyle("Basic")
    qInfo(f"frozen={getattr(sys, 'frozen', False)} root={ROOT_DIR} style={QQuickStyle.name()}")

    engine = QQmlApplicationEngine()
    embedded_qml_dir = ROOT_DIR / "PySide6" / "qml"
    if embedded_qml_dir.exists():
        engine.addImportPath(str(embedded_qml_dir))

    from ui import winsetup

    # 卸载学习通PLUS.exe in the install folder, or the older 学习通PLUS.exe --uninstall.
    if "--uninstall" in sys.argv or winsetup.launched_as_uninstaller():
        from ui.uninstall import quiet_uninstall, run_uninstaller

        if "--quiet" in sys.argv:
            raise SystemExit(quiet_uninstall())

        run_uninstaller(app, engine)
        exit_code = app.exec()
        del engine
        raise SystemExit(exit_code)

    # Already running (perhaps hidden in the tray)? Bring that window up instead.
    from ui.tray import activate_running_instance

    if activate_running_instance():
        raise SystemExit(0)
    # Closing the window hides it to the tray; the app quits explicitly (tray menu / 退出).
    app.setQuitOnLastWindowClosed(False)

    if getattr(sys, "frozen", False) and sys.platform == "win32":
        # An installed copy whose 应用和功能 entry went missing (or is from an older version)
        # writes it again, so it can always be uninstalled from Windows settings too.
        import threading

        def repair() -> None:
            from ui.controller import APP_VERSION   # imported off the UI thread, after the splash starts

            winsetup.ensure_registered(Path(sys.executable).resolve().parent, APP_VERSION)

        threading.Thread(target=lambda: _quietly(repair), name="ensure-registered", daemon=True).start()

    # Splash first; config, runtime checks and the main window load behind it.
    startup = StartupLoader(app, engine)
    startup.start()
    exit_code = app.exec()
    if startup.controller is not None:
        startup.controller.shutdown()
    if startup.tray is not None:
        startup.tray.shutdown()
    del engine
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
