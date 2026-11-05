# -*- mode: python ; coding: utf-8 -*-
# 学习通PLUS: GUI (学习通PLUS.exe) and task worker (chaoxing-worker.exe) in ONE folder,
# sharing a single _internal directory. Build: python -m PyInstaller packaging\app.spec
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(Path(SPECPATH)))
from prune import prune  # noqa: E402

import PySide6  # noqa: E402

PYSIDE = Path(PySide6.__file__).resolve().parent
ICON = str(ROOT / "assets" / "learning_plus.ico")

gui = Analysis(
    [str(ROOT / "gui.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "config_template.ini"), "."),
        (str(ROOT / "ui" / "qml"), "ui/qml"),
        (str(ROOT / "assets" / "learning_plus.png"), "assets"),
        (str(PYSIDE / "qml"), "PySide6/qml"),
    ],
    binaries=[(str(PYSIDE / "plugins" / "webview" / "qtwebview_webview2.dll"), "PySide6/plugins/webview")],
    hiddenimports=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickControls2", "PySide6.QtWebView",
                   "PySide6.QtWidgets", "PySide6.QtNetwork", "ui.uninstall", "ui.tray",
                   "ui.videoproxy"],
    # QtWidgets stays: the tray icon and its menu are widgets.
    excludes=["tkinter", "PySide6.QtOpenGLWidgets"],
    noarchive=False,
)

worker = Analysis(
    [str(ROOT / "worker.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "resource" / "font_map_table.json"), "resource")],
    hiddenimports=["api.captcha", "ddddocr"],
    # cv2: replaced by packaging/stubs/cv2 below (ddddocr's text OCR never uses OpenCV).
    excludes=["tkinter", "PySide6", "shiboken6", "matplotlib", "IPython", "pytest", "cv2"],
    noarchive=False,
)

# ddddocr's default OCR model (the only one DdddOcr() loads).
import ddddocr  # noqa: E402

worker.datas.append(("ddddocr/common_old.onnx", str(Path(ddddocr.__file__).parent / "common_old.onnx"), "DATA"))

for analysis in (gui, worker):
    analysis.binaries, dropped_bin = prune(analysis.binaries)
    analysis.datas, dropped_dat = prune(analysis.datas)
    print(f"prune: dropped {dropped_bin} binaries, {dropped_dat} data files")

# Plain-file cv2 stand-in in _internal/cv2 (found on sys.path at run time).
worker.datas.append(("cv2/__init__.py", str(ROOT / "packaging" / "stubs" / "cv2" / "__init__.py"), "DATA"))

gui_exe = EXE(
    PYZ(gui.pure),
    gui.scripts,
    [],
    exclude_binaries=True,
    name="学习通PLUS",
    icon=ICON,
    console=False,
    upx=False,
)
worker_exe = EXE(
    PYZ(worker.pure),
    worker.scripts,
    [],
    exclude_binaries=True,
    name="chaoxing-worker",
    icon=ICON,
    console=True,
    upx=False,
)
COLLECT(
    gui_exe,
    worker_exe,
    gui.binaries,
    gui.datas,
    worker.binaries,
    worker.datas,
    name="学习通PLUS",
    upx=False,
)
