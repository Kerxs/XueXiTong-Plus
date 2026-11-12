# -*- mode: python ; coding: utf-8 -*-
# Setup program stub (one file). build_windows.ps1 appends the release zip to it.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(Path(SPECPATH)))
from prune import prune  # noqa: E402

setup = Analysis(
    [str(ROOT / "installer" / "setup.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "ui" / "qml"), "ui/qml"),
        (str(ROOT / "installer" / "qml"), "installer/qml"),
        (str(ROOT / "assets" / "learning_plus.png"), "assets"),
    ],
    # lzma / tarfile: the appended payload is a solid .tar.xz stream (installer/payload.py).
    hiddenimports=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickControls2", "lzma", "tarfile",
                   "installer.payload"],
    excludes=["tkinter", "PySide6.QtWebView", "PySide6.QtWebEngineCore", "PySide6.QtWidgets",
              "numpy", "PIL"],
    noarchive=False,
)
# The installer uses QtQuick.Dialogs (FolderDialog); keep it here.
setup.binaries, dropped_bin = prune(setup.binaries, keep_dialogs=True)
setup.datas, dropped_dat = prune(setup.datas, keep_dialogs=True)
print(f"prune: dropped {dropped_bin} binaries, {dropped_dat} data files")

# What the setup program unpacks into its own folder when it runs, with hashes: the payload does
# not store a release file again that is here with the same content (installer/payload.py).
import hashlib  # noqa: E402
import json  # noqa: E402

manifest = {}
for dest, src, _kind in list(setup.binaries) + list(setup.datas):
    try:
        manifest[dest.replace("\\", "/")] = hashlib.sha256(Path(src).read_bytes()).hexdigest()
    except OSError:
        pass
(ROOT / ".build").mkdir(exist_ok=True)
(ROOT / ".build" / "setup-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
print(f"setup manifest: {len(manifest)} files")

EXE(
    PYZ(setup.pure),
    setup.scripts,
    setup.binaries,
    setup.datas,
    [],
    name="setup-stub",
    icon=str(ROOT / "assets" / "learning_plus.ico"),
    console=False,
    upx=False,
)
