# -*- coding: utf-8 -*-
"""Online update: check the latest GitHub Release, download the setup exe, run it.

The setup program upgrades an existing install in place, so "update" is simply:
download the release's setup exe, verify it, start it, quit this app.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, QThread, QTimer, Signal, Slot

REPO = "Kerxs/XueXiTong-Plus"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
# Any "...Setup...exe" asset. GitHub strips non-ASCII from asset names, so this must not
# depend on the Chinese product name (releases use XueXiTong-Plus-Setup-<ver>.exe).
ASSET_RE = re.compile(r"(?i)^[\w.\-]*setup[\w.\-]*\.exe$")
TIMEOUT = 15


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' / '1.2' -> (1, 2, 3) / (1, 2, 0); anything unparsable -> (0,)."""
    numbers = re.findall(r"\d+", text or "")[:3]
    if not numbers:
        return (0,)
    return tuple(int(n) for n in numbers + ["0"] * (3 - len(numbers)))


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def trusted_download(url: str) -> bool:
    """Only this project's release downloads on github.com, over https."""
    return str(url).startswith(f"https://github.com/{REPO}/releases/download/")


def pick_asset(release: dict) -> dict | None:
    for asset in release.get("assets") or []:
        if ASSET_RE.match(asset.get("name", "")):
            return asset
    return None


def _request(url: str, accept: str = "application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "XueXiTong-Plus-Updater"})
    return urllib.request.urlopen(req, timeout=TIMEOUT)  # noqa: S310 - fixed https URLs


class _CheckWorker(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def run(self) -> None:
        try:
            with _request(LATEST_API) as resp:
                self.done.emit(json.loads(resp.read().decode("utf-8")))
        except Exception as exc:  # network errors are shown, never raised
            self.failed.emit(_describe(exc))


class _DownloadWorker(QThread):
    progressed = Signal(float)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, name: str, size: int, digest: str) -> None:
        super().__init__()
        self.url, self.name, self.size, self.digest = url, name, size, digest
        self.cancelled = False

    def run(self) -> None:
        if not trusted_download(self.url) or not ASSET_RE.match(self.name) or Path(self.name).name != self.name:
            self.failed.emit("更新地址不是本项目的发布下载地址，已取消")
            return
        target = Path(tempfile.gettempdir()) / "xxtplus-update" / self.name
        partial = target.with_suffix(".part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            sha = hashlib.sha256()
            got = 0
            with _request(self.url, accept="application/octet-stream") as resp, open(partial, "wb") as out:
                total = self.size or int(resp.headers.get("Content-Length") or 0)
                while True:
                    if self.cancelled:
                        raise RuntimeError("已取消下载")
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    sha.update(chunk)
                    got += len(chunk)
                    if total:
                        self.progressed.emit(min(1.0, got / total))
            if self.size and got != self.size:
                raise RuntimeError(f"下载不完整（{got} / {self.size} 字节）")
            # GitHub publishes "sha256:<hex>" for every release asset. No checksum, no install:
            # a setup program is about to be run.
            if not self.digest.startswith("sha256:"):
                raise RuntimeError("发布信息里没有校验值，不自动安装。请到发布页手动下载")
            if sha.hexdigest() != self.digest.split(":", 1)[1].lower():
                raise RuntimeError("文件校验失败（SHA-256 不一致），已丢弃下载")
            partial.replace(target)
            self.done.emit(str(target))
        except Exception as exc:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            self.failed.emit(_describe(exc))


def _describe(exc: Exception) -> str:
    text = str(exc)
    if "404" in text:
        return "还没有发布任何版本"
    if "timed out" in text or "urlopen error" in text:
        return "无法连接到 GitHub，请检查网络后重试"
    return text or type(exc).__name__


class Updater(QObject):
    stateChanged = Signal()
    progressChanged = Signal()
    updateAvailable = Signal()
    autoCheckChanged = Signal()

    def __init__(self, current_version: str, parent=None) -> None:
        super().__init__(parent)
        self._current = current_version
        self._settings = QSettings()
        self._state = "idle"  # idle | checking | latest | available | downloading | ready | error
        self._error = ""
        self._latest = ""
        self._notes = ""
        self._asset: dict | None = None
        self._progress = 0.0
        self._file = ""
        self._silent = False
        self._worker: QThread | None = None

    def _set(self, state: str, error: str = "") -> None:
        self._state = state
        self._error = error
        self.stateChanged.emit()

    state = Property(str, lambda self: self._state, notify=stateChanged)
    errorText = Property(str, lambda self: self._error, notify=stateChanged)
    latestVersion = Property(str, lambda self: self._latest, notify=stateChanged)
    releaseNotes = Property(str, lambda self: self._notes, notify=stateChanged)
    downloadMb = Property(int, lambda self: round((self._asset or {}).get("size", 0) / 2**20), notify=stateChanged)
    progress = Property(float, lambda self: self._progress, notify=progressChanged)
    releasesPage = Property(str, lambda self: RELEASES_PAGE, constant=True)

    def _get_auto(self) -> bool:
        return str(self._settings.value("update/autoCheck", "true")).lower() == "true"

    def _set_auto(self, value: bool) -> None:
        self._settings.setValue("update/autoCheck", "true" if value else "false")
        self.autoCheckChanged.emit()

    autoCheck = Property(bool, _get_auto, _set_auto, notify=autoCheckChanged)

    @Slot()
    def checkOnStartup(self) -> None:
        # Only packaged builds check automatically (XXTPLUS_UPDATE_CHECK=1 forces it for testing).
        if (self._get_auto() and getattr(sys, "frozen", False)) or os.environ.get("XXTPLUS_UPDATE_CHECK") == "1":
            # Give the main window a moment; a silent check only speaks up when there is an update.
            QTimer.singleShot(4000, lambda: self.check(True))

    @Slot(bool)
    def check(self, silent: bool = False) -> None:
        if self._state in ("checking", "downloading"):
            return
        self._silent = silent
        self._set("checking")
        worker = _CheckWorker()
        worker.done.connect(self._on_release)
        worker.failed.connect(lambda msg: self._set("idle" if self._silent else "error", msg))
        self._start(worker)

    def _on_release(self, release: dict) -> None:
        tag = str(release.get("tag_name") or release.get("name") or "")
        self._latest = tag.lstrip("vV")
        self._notes = str(release.get("body") or "").strip()
        self._asset = pick_asset(release)
        if not is_newer(self._latest, self._current):
            self._set("idle" if self._silent else "latest")
            return
        if self._asset is None:
            self._set("idle" if self._silent else "error", f"新版本 {self._latest} 没有可下载的安装程序")
            return
        self._set("available")
        self.updateAvailable.emit()

    @Slot()
    def download(self) -> None:
        if self._state != "available" or not self._asset:
            return
        self._progress = 0.0
        self.progressChanged.emit()
        self._set("downloading")
        worker = _DownloadWorker(
            self._asset["browser_download_url"], self._asset["name"],
            int(self._asset.get("size") or 0), str(self._asset.get("digest") or ""),
        )
        worker.progressed.connect(self._on_progress)
        worker.done.connect(self._on_downloaded)
        worker.failed.connect(lambda msg: self._set("error", msg))
        self._start(worker)

    @Slot()
    def cancel(self) -> None:
        try:
            if isinstance(self._worker, _DownloadWorker) and self._worker.isRunning():
                self._worker.cancelled = True
        except RuntimeError:        # the thread object was already deleted
            self._worker = None

    def _on_progress(self, value: float) -> None:
        self._progress = value
        self.progressChanged.emit()

    def _on_downloaded(self, path: str) -> None:
        self._file = path
        self._set("ready")

    @Slot(result=bool)
    def installAndQuit(self) -> bool:
        """Start the downloaded setup program; the caller then closes the app."""
        if self._state != "ready" or not Path(self._file).exists():
            return False
        os.startfile(self._file)  # noqa: S606 - the setup exe we just downloaded and verified
        return True

    def _start(self, worker: QThread) -> None:
        self._worker = worker
        # Drop our reference before Qt deletes the finished thread object; touching a
        # deleted QThread (e.g. in shutdown() on exit) raises "Internal C++ object already deleted".
        worker.finished.connect(lambda: self._forget(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _forget(self, worker: QThread) -> None:
        if self._worker is worker:
            self._worker = None

    def shutdown(self) -> None:
        worker = self._worker
        if worker is None:
            return
        try:
            running = worker.isRunning()
        except RuntimeError:        # already deleted by Qt
            self._worker = None
            return
        if running:
            self.cancel()
            worker.wait(3000)
