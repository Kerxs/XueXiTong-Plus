# -*- coding: utf-8 -*-
"""学习通PLUS setup program (QML UI in installer/qml/Setup.qml).

The files to install are appended to the end of the built setup exe (installer/payload.py: one
solid .tar.xz stream; the Qt and Python files the setup program carries itself are copied from
its own folder instead of being stored twice). For development pass
``--payload path\\to\\XueXiTong-Plus-Windows-<ver>.zip``.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Property, QObject, QThread, QUrl, Signal, Slot, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QFont, QGuiApplication, QIcon  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402

from installer.payload import Payload  # noqa: E402
from ui import runtime_deps, winsetup  # noqa: E402
from ui.controller import APP_VERSION as VERSION  # noqa: E402
ZIP_ROOT = winsetup.APP_NAME + "/"


def payload_path(argv: list[str]) -> Path:
    if "--payload" in argv:
        return Path(argv[argv.index("--payload") + 1])
    return Path(sys.executable)


class InstallWorker(QThread):
    progressed = Signal(float, str)
    failed = Signal(str)
    warned = Signal(str)
    succeeded = Signal()

    def __init__(self, payload: Path, target: Path, desktop: bool, start_menu: bool,
                 install_deps: bool = True) -> None:
        super().__init__()
        self.payload = payload
        self.target = target
        self.desktop = desktop
        self.start_menu = start_menu
        self.install_deps = install_deps

    def run(self) -> None:
        try:
            self._install()
        except Exception as exc:  # surfaced on the error page
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.succeeded.emit()

    def _install(self) -> None:
        target = self.target
        self.progressed.emit(0.0, "检查运行中的程序")
        running = winsetup.running_app_processes()
        if running:
            raise RuntimeError("学习通 PLUS 正在运行，请先关闭程序（包括正在运行的任务）后重试。")

        target.mkdir(parents=True, exist_ok=True)
        # Remove the previous version's files so nothing stale is left behind.
        if (target / winsetup.MARKER).exists() or (target / winsetup.APP_EXE).exists():
            self.progressed.emit(0.02, "移除旧版本文件")
            internal = target / "_internal"
            if internal.exists():
                shutil.rmtree(internal)

        payload = Payload(self.payload, ZIP_ROOT)
        total = payload.size or 1
        # Files the setup program carries itself (its own Qt and Python) are copied from its folder.
        payload.extract(target, lambda fraction, rel: self.progressed.emit(0.05 + 0.75 * fraction, rel),
                        shared_root=getattr(sys, "_MEIPASS", None))

        # A missing runtime does not fail the install: the app still runs, only the
        # video preview needs WebView2. The finish page reports what went wrong.
        if self.install_deps and not runtime_deps.webview2_version():
            work = Path(tempfile.gettempdir()) / "xxtplus-setup"
            problem = runtime_deps.install_webview2(
                work, lambda text, value: self.progressed.emit(0.80 + 0.12 * value, text))
            if problem:
                self.warned.emit(problem)

        self.progressed.emit(0.93, "创建快捷方式")
        exe = target / winsetup.APP_EXE
        if self.start_menu:
            winsetup.create_shortcut(winsetup.start_menu_shortcut(), exe)
        if self.desktop:
            winsetup.create_shortcut(winsetup.desktop_shortcut(), exe)

        self.progressed.emit(0.97, "写入卸载信息")
        (target / winsetup.MARKER).write_text(VERSION, encoding="utf-8")
        winsetup.register(target, VERSION, total)
        self.progressed.emit(1.0, "安装完成")


class Installer(QObject):
    stateChanged = Signal()
    progressChanged = Signal()

    def __init__(self, payload: Path, parent=None) -> None:
        super().__init__(parent)
        self._payload = payload
        self._state = "idle"      # idle | installing | done | error
        self._progress = 0.0
        self._current = ""
        self._error = ""
        self._worker: InstallWorker | None = None
        self._warning = ""
        self._webview2 = runtime_deps.webview2_version()
        self._installed = winsetup.read_installed()
        self._size_mb = 0
        self._payload_ok = False
        info = Payload(payload, ZIP_ROOT)
        self._payload_ok = info.ok
        self._size_mb = round(info.size / 1024 / 1024)

    version = Property(str, lambda self: VERSION, constant=True)
    appName = Property(str, lambda self: winsetup.DISPLAY_NAME, constant=True)
    iconUrl = Property(QUrl, lambda self: QUrl.fromLocalFile(str(ROOT / "assets" / "learning_plus.png")), constant=True)
    requiredMb = Property(int, lambda self: self._size_mb, constant=True)
    payloadOk = Property(bool, lambda self: self._payload_ok, constant=True)
    installedVersion = Property(str, lambda self: (self._installed or {}).get("version", ""), constant=True)
    defaultDir = Property(str, lambda self: (self._installed or {}).get("location") or str(winsetup.default_install_dir()), constant=True)
    state = Property(str, lambda self: self._state, notify=stateChanged)
    errorText = Property(str, lambda self: self._error, notify=stateChanged)
    progress = Property(float, lambda self: self._progress, notify=progressChanged)
    currentFile = Property(str, lambda self: self._current, notify=progressChanged)
    # Runtime components (see ui/runtime_deps.py).
    webview2Version = Property(str, lambda self: self._webview2, constant=True)
    webview2Name = Property(str, lambda self: runtime_deps.WEBVIEW2_NAME, constant=True)
    webview2Page = Property(str, lambda self: runtime_deps.WEBVIEW2_PAGE, constant=True)
    warningText = Property(str, lambda self: self._warning, notify=stateChanged)

    @Slot(str, result=str)
    def normalizeDir(self, value: str) -> str:
        """Turn a picked folder URL/path into a path; append the app folder name if missing."""
        path = QUrl(value).toLocalFile() if value.startswith("file:") else value
        path = path.strip().strip('"')
        if not path:
            return ""
        p = Path(path)
        if p.name != winsetup.APP_NAME:
            p = p / winsetup.APP_NAME
        return str(p)

    @Slot(str, result=str)
    def freeSpaceText(self, folder: str) -> str:
        probe = Path(folder)
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        try:
            free = shutil.disk_usage(probe).free
        except OSError:
            return ""
        return f"{free / 1024 ** 3:.1f} GB 可用"

    @Slot(str, bool, bool, bool)
    def install(self, folder: str, desktop: bool, start_menu: bool, install_deps: bool) -> None:
        if self._state == "installing":
            return
        self._state = "installing"
        self._error = ""
        self._warning = ""
        self._progress = 0.0
        self.stateChanged.emit()
        self._worker = InstallWorker(self._payload, Path(folder), desktop, start_menu, install_deps)
        self._worker.progressed.connect(self._on_progress)
        self._worker.failed.connect(self._on_failed)
        self._worker.warned.connect(self._on_warned)
        self._worker.succeeded.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, value: float, current: str) -> None:
        self._progress = value
        self._current = current
        self.progressChanged.emit()

    def _on_failed(self, message: str) -> None:
        self._state = "error"
        self._error = message
        self.stateChanged.emit()

    def _on_warned(self, message: str) -> None:
        self._warning = message

    @Slot(str)
    def openUrl(self, url: str) -> None:
        os.startfile(url)  # noqa: S606 - fixed Microsoft page

    def _on_done(self) -> None:
        self._state = "done"
        self.stateChanged.emit()

    @Slot(str)
    def launch(self, folder: str) -> None:
        exe = Path(folder) / winsetup.APP_EXE
        if exe.exists():
            os.startfile(str(exe))  # noqa: S606 - starting the app we just installed


def _install_log() -> None:
    """Qt/QML messages go to %TEMP%\\xxtplus-setup.log (the packaged setup has no console)."""
    try:
        log = open(Path(os.environ.get("TEMP", ".")) / "xxtplus-setup.log", "w", encoding="utf-8")
    except OSError:
        return

    def handler(_mode, _context, message):
        log.write(message + "\n")
        log.flush()

    qInstallMessageHandler(handler)


def silent_install(argv: list[str]) -> int:
    """``--silent [--dir PATH] [--no-shortcuts] [--no-deps]``: install without UI; exit code 0 on success."""
    target = Path(argv[argv.index("--dir") + 1]) if "--dir" in argv else winsetup.default_install_dir()
    shortcuts = "--no-shortcuts" not in argv
    worker = InstallWorker(payload_path(argv), target, shortcuts, shortcuts, "--no-deps" not in argv)
    errors: list[str] = []
    worker.failed.connect(errors.append)
    worker.run()
    return 1 if errors else 0


def extract_only(argv: list[str]) -> int:
    """``--extract PATH``: only unpack the program's files into PATH — no registry entry, no
    shortcuts, no check for a running copy. For a portable copy, and to verify a built setup
    program without touching the installed one."""
    target = Path(argv[argv.index("--extract") + 1])
    try:
        Payload(payload_path(argv), ZIP_ROOT).extract(target, shared_root=getattr(sys, "_MEIPASS", None))
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    _install_log()
    if "--extract" in sys.argv:
        raise SystemExit(extract_only(sys.argv))
    if "--silent" in sys.argv:
        raise SystemExit(silent_install(sys.argv))
    QGuiApplication.setApplicationName(f"{winsetup.APP_NAME} 安装程序")
    app = QGuiApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ROOT / "assets" / "learning_plus.png")))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    QQuickStyle.setStyle("Basic")

    installer = Installer(payload_path(sys.argv), app)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("installer", installer)
    engine.load(QUrl.fromLocalFile(str(ROOT / "installer" / "qml" / "Setup.qml")))
    if not engine.rootObjects():
        raise SystemExit(1)
    code = app.exec()
    if installer._worker is not None:
        installer._worker.wait(5000)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
