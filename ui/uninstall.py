# -*- coding: utf-8 -*-
"""In-app uninstaller: ``学习通PLUS.exe --uninstall`` (registered as the UninstallString)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from ui import winsetup

ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
INSTALL_DIR = Path(sys.executable).resolve().parent


class Uninstaller(QObject):
    stateChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = "confirm"   # confirm | working | done | error
        self._error = ""
        info = winsetup.read_installed() or {}
        self._version = info.get("version", "")

    appName = Property(str, lambda self: winsetup.DISPLAY_NAME, constant=True)
    version = Property(str, lambda self: self._version, constant=True)
    installDir = Property(str, lambda self: str(INSTALL_DIR), constant=True)
    dataDir = Property(str, lambda self: str(winsetup.data_dir()), constant=True)
    iconUrl = Property(QUrl, lambda self: QUrl.fromLocalFile(str(ROOT_DIR / "assets" / "learning_plus.png")), constant=True)
    # Only folders the installer created can be removed.
    installed = Property(bool, lambda self: (INSTALL_DIR / winsetup.MARKER).exists(), constant=True)
    state = Property(str, lambda self: self._state, notify=stateChanged)
    errorText = Property(str, lambda self: self._error, notify=stateChanged)

    def _set(self, state: str, error: str = "") -> None:
        self._state = state
        self._error = error
        self.stateChanged.emit()

    @Slot(bool, bool)
    def uninstall(self, clear_account: bool, remove_all: bool) -> None:
        self._set("working")
        # Let the UI paint the working state before doing the (quick) work.
        QTimer.singleShot(400, lambda: self._run(clear_account, remove_all))

    def _run(self, clear_account: bool, remove_all: bool) -> None:
        if not (INSTALL_DIR / winsetup.MARKER).exists():
            self._set("error", "这个目录不是由安装程序创建的，已取消卸载。")
            return
        others = winsetup.running_app_processes()
        if others:
            self._set("error", "学习通 PLUS 仍在运行（包括正在运行的任务），请先关闭后再卸载。")
            return
        try:
            for link in (winsetup.desktop_shortcut(), winsetup.start_menu_shortcut()):
                if link.exists():
                    link.unlink()
            winsetup.unregister()
            if remove_all:
                if winsetup.data_dir().exists():
                    shutil.rmtree(winsetup.data_dir(), ignore_errors=True)
                winsetup.clear_ui_settings()
            elif clear_account:
                winsetup.clear_account_data()
        except OSError as exc:
            self._set("error", f"{type(exc).__name__}: {exc}")
            return
        self._set("done")

    @Slot()
    def finish(self) -> None:
        # The running exe lives in INSTALL_DIR, so delete the folder after we exit.
        if self._state == "done":
            winsetup.schedule_folder_removal(INSTALL_DIR)


def quiet_uninstall() -> int:
    """``--uninstall --quiet [--keep-account]``: no UI. Clears account data unless --keep-account."""
    uninstaller = Uninstaller()
    uninstaller._run(clear_account="--keep-account" not in sys.argv, remove_all=False)
    if uninstaller._state != "done":
        return 1
    uninstaller.finish()
    return 0


def run_uninstaller(app, engine) -> None:
    uninstaller = Uninstaller(app)
    app.aboutToQuit.connect(uninstaller.finish)
    engine.rootContext().setContextProperty("uninstaller", uninstaller)
    engine.load(QUrl.fromLocalFile(str(ROOT_DIR / "ui" / "qml" / "Uninstall.qml")))
