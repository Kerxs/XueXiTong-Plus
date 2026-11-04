# -*- coding: utf-8 -*-
"""Startup sequence: show the splash first, then load the real app behind it.

Each step does actual work (config, runtime checks, asynchronous QML compile and
incubation of the main window) and reports progress to ``Splash.qml``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QTimer, QUrl, Signal, Slot, qCritical
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine, QQmlIncubator

APP_NAME = "学习通PLUS"          # identity (QSettings location) — do not change
DISPLAY_NAME = "学习通 PLUS"     # shown to users
ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
QML_DIR = ROOT_DIR / "ui" / "qml"


class _Incubator(QQmlIncubator):
    def __init__(self, on_status, mode=QQmlIncubator.IncubationMode.Asynchronous) -> None:
        super().__init__(mode)
        self._on_status = on_status

    def statusChanged(self, status) -> None:  # noqa: N802 - Qt override
        self._on_status(status)


class StartupLoader(QObject):
    statusChanged = Signal()
    loadedChanged = Signal()
    ready = Signal(QObject)

    def __init__(self, app, engine: QQmlApplicationEngine) -> None:
        super().__init__(app)
        self._app = app
        self._engine = engine
        self._status = "正在启动"
        self._progress = 0.0
        self._loaded = False
        self._warnings: list[str] = []
        self.controller = None
        self.tray = None
        self.main_window: QObject | None = None
        self._component: QQmlComponent | None = None
        self._incubator: _Incubator | None = None
        self._splash_done = False
        self._sync_create = False
        self._splash_shown = False

    # ----- properties read by Splash.qml ---------------------------------
    status = Property(str, lambda self: self._status, notify=statusChanged)
    progress = Property(float, lambda self: self._progress, notify=statusChanged)
    loaded = Property(bool, lambda self: self._loaded, notify=loadedChanged)
    appName = Property(str, lambda self: DISPLAY_NAME, constant=True)
    iconUrl = Property(QUrl, lambda self: QUrl.fromLocalFile(str(ROOT_DIR / "assets" / "learning_plus.png")), constant=True)
    # Main.qml flies the splash logo from the screen centre to the nav-pane brand only after a splash.
    splashShown = Property(bool, lambda self: self._splash_shown, constant=True)

    def _step(self, text: str, progress: float) -> None:
        self._status = text
        self._progress = progress
        self.statusChanged.emit()

    # ----- sequence ------------------------------------------------------
    def start(self) -> None:
        self._engine.rootContext().setContextProperty("startup", self)
        # "启动动画" off in settings: no splash; the window opens once loading is done.
        if str(QSettings().value("ui/splash", "true")).lower() != "true":
            self._splash_done = True
            self._sync_create = True
            QTimer.singleShot(0, self._load_config)
            return
        self._splash_shown = True
        self._engine.load(QUrl.fromLocalFile(str(QML_DIR / "Splash.qml")))
        splash = self._engine.rootObjects()[-1] if self._engine.rootObjects() else None
        if splash is not None:
            # Let async incubation run between splash frames.
            controller = splash.incubationController()
            if controller is not None:
                self._engine.setIncubationController(controller)
            splash.finished.connect(self._on_splash_finished)
        # Give the splash a frame to appear before doing any work.
        QTimer.singleShot(120, self._load_config)

    def _load_config(self) -> None:
        self._step("读取配置", 0.15)
        from ui.controller import AppController  # deferred: imports models/parser

        self.controller = AppController(self._app)
        self._engine.rootContext().setContextProperty("controller", self.controller)
        # Background mode: tray icon + single-instance server (closing the window hides it).
        from ui.tray import Tray

        self.tray = Tray(self._app, self.controller, ROOT_DIR / "assets" / "learning_plus.png")
        self.tray.showRequested.connect(self.show_main)
        self._engine.rootContext().setContextProperty("tray", self.tray)
        QTimer.singleShot(0, self._check_runtime)

    def _check_runtime(self) -> None:
        self._step("检查运行组件", 0.3)
        from ui.controller import BUNDLE_DIR

        if getattr(sys, "frozen", False):
            worker = BUNDLE_DIR / "chaoxing-worker.exe"
        else:
            worker = BUNDLE_DIR / "worker.py"
        if not worker.exists():
            self._warnings.append(f"找不到任务运行组件：{worker}")
        if not (ROOT_DIR / "config_template.ini").exists():
            self._warnings.append("缺少配置模板 config_template.ini")
        QTimer.singleShot(0, self._compile_ui)

    def _compile_ui(self) -> None:
        self._step("加载界面", 0.45)
        self._component = QQmlComponent(self._engine)
        self._component.statusChanged.connect(self._on_component_status)
        self._component.loadUrl(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")), QQmlComponent.CompilationMode.Asynchronous)
        if self._component.isReady() or self._component.isError():
            self._on_component_status(self._component.status())

    def _on_component_status(self, status) -> None:
        if status == QQmlComponent.Status.Ready:
            self._component.statusChanged.disconnect(self._on_component_status)
            QTimer.singleShot(0, self._create_window)
        elif status == QQmlComponent.Status.Error:
            self._fail(self._component.errorString())

    def _create_window(self) -> None:
        self._step("创建主窗口", 0.7)
        # Async incubation needs the splash window's incubation controller; without a splash, create synchronously.
        mode = QQmlIncubator.IncubationMode.Synchronous if self._sync_create else QQmlIncubator.IncubationMode.Asynchronous
        self._incubator = _Incubator(self._on_incubator_status, mode)
        self._component.create(self._incubator, self._engine.rootContext())
        self._on_incubator_status(self._incubator.status())

    def _on_incubator_status(self, status) -> None:
        if status == QQmlIncubator.Status.Ready and self.main_window is None:
            self.main_window = self._incubator.object()
            QQmlEngine.setObjectOwnership(self.main_window, QQmlEngine.ObjectOwnership.CppOwnership)
            QTimer.singleShot(0, self._finish)
        elif status == QQmlIncubator.Status.Error:
            self._fail("\n".join(e.toString() for e in self._incubator.errors()))

    def _finish(self) -> None:
        self._step("准备就绪", 1.0)
        self._loaded = True
        self.loadedChanged.emit()
        self.ready.emit(self.main_window)
        if self._splash_done:
            self._reveal()

    def _fail(self, message: str) -> None:
        qCritical(f"界面加载失败: {message}")
        self._step("界面加载失败", 1.0)
        QTimer.singleShot(1500, lambda: self._app.exit(1))

    @Slot()
    def _on_splash_finished(self) -> None:
        self._splash_done = True
        if self._loaded:
            self._reveal()

    @Slot()
    def show_main(self) -> None:
        """Bring the main window back (tray click, or the app was launched again)."""
        window = self.main_window
        if window is None or not self._loaded:
            return
        window.showNormal()
        window.raise_()
        window.requestActivate()

    def _reveal(self) -> None:
        window = self.main_window
        if window is None:
            return
        window.setProperty("visible", True)
        window.raise_()
        window.requestActivate()
        for message in self._warnings:
            self.controller.toast.emit(message, "warning")
