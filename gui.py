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

    sys.excepthook = excepthook


def main() -> None:
    _install_log()
    os.environ["QT_WEBVIEW_PLUGIN"] = "native"
    QGuiApplication.setApplicationName(APP_NAME)
    QGuiApplication.setOrganizationName("ChaoxingDesktop")
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

    if "--uninstall" in sys.argv:
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
