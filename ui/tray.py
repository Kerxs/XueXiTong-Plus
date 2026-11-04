# -*- coding: utf-8 -*-
"""Background mode: system tray icon + single instance.

Closing the main window hides it to the tray (tasks keep running); the tray menu
shows the window, starts/stops a run, or quits. Launching the app again while it is
already running brings the existing window to the front instead of a second copy.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

SERVER_NAME = "xxtplus-gui-" + (os.environ.get("USERNAME") or "user")


def activate_running_instance() -> bool:
    """If another copy is running, ask it to show its window and return True."""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


class Tray(QObject):
    showRequested = Signal()
    quitRequested = Signal()
    toggleRunRequested = Signal()
    closeToTrayChanged = Signal()

    def __init__(self, app, controller, icon_path: Path, parent=None) -> None:
        super().__init__(parent or app)
        self._settings = QSettings()
        self._controller = controller
        self._available = QSystemTrayIcon.isSystemTrayAvailable()

        # Single instance: later launches connect here and ask us to show the window.
        self._server = QLocalServer(self)
        QLocalServer.removeServer(SERVER_NAME)
        self._server.newConnection.connect(self._on_connection)
        self._server.listen(SERVER_NAME)

        self._icon = QSystemTrayIcon(QIcon(str(icon_path)), self)
        menu = QMenu()
        self._menu = menu
        self._show_action = menu.addAction("显示主窗口")
        self._show_action.triggered.connect(self.showRequested)
        menu.addSeparator()
        self._run_action = menu.addAction("开始运行")
        self._run_action.triggered.connect(self.toggleRunRequested)
        menu.addSeparator()
        quit_action = menu.addAction("退出 学习通 PLUS")
        quit_action.triggered.connect(self.quitRequested)
        self._icon.setContextMenu(menu)
        self._icon.activated.connect(self._on_activated)
        controller.runStateChanged.connect(self._sync)
        self._sync()
        if self._available:
            self._icon.show()

    def _on_connection(self) -> None:
        # Any connection is a "show yourself" request. (Acting on readyRead could miss data
        # that arrived before the handler was attached.)
        conn = self._server.nextPendingConnection()
        if conn is not None:
            conn.disconnected.connect(conn.deleteLater)
        self.showRequested.emit()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.showRequested.emit()

    def _sync(self) -> None:
        running = self._controller.running
        self._run_action.setText("停止任务" if running else "开始运行")
        self._icon.setToolTip(f"学习通 PLUS · {self._controller.status}")

    available = Property(bool, lambda self: self._available, constant=True)

    # What closing the window does: "ask" (dialog, default), "tray" (keep running in the
    # background) or "quit". Older versions stored a yes/no ui/closeToTray; someone who had
    # turned it off keeps "quit", everyone else is asked once and can tick "以后都这样".
    CLOSE_ACTIONS = ("ask", "tray", "quit")

    def _get_close_action(self) -> str:
        value = str(self._settings.value("ui/closeAction", "") or "")
        if value not in self.CLOSE_ACTIONS:
            value = "quit" if str(self._settings.value("ui/closeToTray", "")).lower() == "false" else "ask"
        if value == "tray" and not self._available:
            return "quit"                       # no system tray: nothing to hide to
        return value

    def _set_close_action(self, value: str) -> None:
        if value not in self.CLOSE_ACTIONS:
            return
        self._settings.setValue("ui/closeAction", value)
        self.closeToTrayChanged.emit()

    closeAction = Property(str, _get_close_action, _set_close_action, notify=closeToTrayChanged)
    # Kept for older QML: true when closing hides to the tray.
    closeToTray = Property(bool, lambda self: self._get_close_action() == "tray", notify=closeToTrayChanged)

    @Slot(str, str)
    def notify(self, title: str, message: str) -> None:
        if self._available:
            self._icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    @Slot()
    def hintOnce(self) -> None:
        """First time the window is hidden, tell the user where the app went."""
        if str(self._settings.value("ui/trayHintShown", "false")).lower() == "true":
            return
        self._settings.setValue("ui/trayHintShown", "true")
        self.notify("学习通 PLUS 仍在后台运行", "任务会继续进行。点击托盘图标可以重新打开窗口，右键可退出。")

    def shutdown(self) -> None:
        self._icon.hide()
        self._server.close()
