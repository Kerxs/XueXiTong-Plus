# -*- coding: utf-8 -*-
"""Windows install bookkeeping shared by the installer and the in-app uninstaller.

Per-user install: files under %LOCALAPPDATA%\\Programs\\学习通PLUS, an entry in
HKCU\\...\\Uninstall, and .lnk shortcuts on the desktop / Start menu.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "学习通PLUS"
APP_EXE = "学习通PLUS.exe"
WORKER_EXE = "chaoxing-worker.exe"
PUBLISHER = "学习通PLUS"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\XueXiTongPlus"
# Written into every install folder; the uninstaller refuses to delete a folder without it.
MARKER = ".xxtplus-install"

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / APP_NAME


def data_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "ChaoxingDesktop"


from core.account import ACCOUNT_FILES, LOG_PATTERNS  # noqa: E402,F401  (kept for existing imports)


def clear_account_data(folder: Path | None = None) -> None:
    """Blank the account, password and cookies login in config.ini and delete cookies files."""
    from core import account  # shared with the Android app

    account.clear_account_data(folder or data_dir())


def log_files(folder: Path | None = None) -> list[Path]:
    from core import account

    return account.log_files(folder or data_dir())


def clear_ui_settings() -> None:
    """Remove the QSettings tree (theme, window size, onboarding state) from HKCU."""
    import winreg

    def delete_tree(root, path):
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
                while True:
                    try:
                        child = winreg.EnumKey(key, 0)
                    except OSError:
                        break
                    delete_tree(root, path + "\\" + child)
            winreg.DeleteKey(root, path)
        except OSError:
            pass

    delete_tree(winreg.HKEY_CURRENT_USER, r"Software\ChaoxingDesktop")


def desktop_shortcut() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop" / f"{APP_NAME}.lnk"


def start_menu_shortcut() -> Path:
    return (Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / f"{APP_NAME}.lnk")


def _powershell(script: str) -> None:
    """Run a PowerShell snippet without a console window (UTF-16 encoded, so no quoting issues)."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        check=True, creationflags=CREATE_NO_WINDOW, capture_output=True, timeout=60,
    )


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_shortcut(link: Path, target: Path, description: str = APP_NAME) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    _powershell(
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + _ps_quote(str(link)) + ");"
        "$s.TargetPath = " + _ps_quote(str(target)) + ";"
        "$s.WorkingDirectory = " + _ps_quote(str(target.parent)) + ";"
        "$s.IconLocation = " + _ps_quote(f"{target},0") + ";"
        "$s.Description = " + _ps_quote(description) + ";"
        "$s.Save()"
    )


def read_installed() -> dict | None:
    """Return {'version', 'location'} of an existing install, or None."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            version = winreg.QueryValueEx(key, "DisplayVersion")[0]
            location = winreg.QueryValueEx(key, "InstallLocation")[0]
    except OSError:
        return None
    return {"version": str(version), "location": str(location)}


def register(install_dir: Path, version: str, size_bytes: int) -> None:
    import winreg

    exe = install_dir / APP_EXE
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_WRITE) as key:
        values = {
            "DisplayName": APP_NAME,
            "DisplayVersion": version,
            "Publisher": PUBLISHER,
            "DisplayIcon": f"\"{exe}\",0",
            "InstallLocation": str(install_dir),
            "UninstallString": f"\"{exe}\" --uninstall",
            "QuietUninstallString": f"\"{exe}\" --uninstall --quiet",
            "Comments": "基于开源项目 Samueli924/chaoxing，遵循 GPL-3.0 协议",
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, max(1, size_bytes // 1024))
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def unregister() -> None:
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass


def running_app_processes(install_dir: Path | None = None) -> list[str]:
    """Names of 学习通PLUS processes that are running (other than this one)."""
    names = []
    for image in (APP_EXE, WORKER_EXE):
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
                capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15,
            ).stdout.decode("mbcs", errors="replace")
        except (OSError, subprocess.SubprocessError):
            continue
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) > 1 and parts[0].lower() == image.lower() and parts[1] != str(os.getpid()):
                names.append(image)
    return names


def schedule_folder_removal(folder: Path) -> None:
    """Delete `folder` a moment after this process exits (it may contain the running exe)."""
    # A plain command-line string: a list would get its inner quotes escaped as \" , which cmd
    # does not understand. cwd is moved out of the folder so it is not held open.
    subprocess.Popen(
        f'cmd /d /c "ping 127.0.0.1 -n 3 >nul & rmdir /s /q "{folder}""',
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True, cwd=str(Path(folder).parent),
    )
