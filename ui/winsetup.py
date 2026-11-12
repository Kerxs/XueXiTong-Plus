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

APP_NAME = "学习通PLUS"          # identity: install folder, shortcut files, exe — do not change
DISPLAY_NAME = "学习通 PLUS"     # what users see (window titles, Apps & features, …)
APP_EXE = "学习通PLUS.exe"
WORKER_EXE = "chaoxing-worker.exe"
# The uninstaller in the install folder, like other Windows programs have. It is a copy of
# APP_EXE (same PyInstaller launcher, same _internal) that starts in uninstall mode because of
# its name; ``学习通PLUS.exe --uninstall`` keeps working.
UNINSTALL_EXE = "卸载学习通PLUS.exe"
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


def system_exe(name: str) -> str:
    """Full path of one of Windows' own programs ("powershell", "tasklist", "cmd", "netstat").

    Started by bare name, Windows looks in the folder of the running exe first — for the setup
    program that is the Downloads folder, where a file someone else put there under the same name
    would be run instead. A full path under %SystemRoot% leaves nothing to look up."""
    root = Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows") / "System32"
    known = {
        "powershell": root / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        "cmd": root / "cmd.exe",
        "tasklist": root / "tasklist.exe",
        "netstat": root / "NETSTAT.EXE",
        "ping": root / "PING.EXE",
    }
    path = known[name]
    return str(path) if path.exists() or sys.platform != "win32" else name


def _powershell(script: str) -> None:
    """Run a PowerShell snippet without a console window (UTF-16 encoded, so no quoting issues)."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        [system_exe("powershell"), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        check=True, creationflags=CREATE_NO_WINDOW, capture_output=True, timeout=60,
    )


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_shortcut(link: Path, target: Path, description: str = DISPLAY_NAME) -> None:
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


def launched_as_uninstaller(executable: str | None = None) -> bool:
    """True when this process is the uninstaller copy (卸载学习通PLUS.exe)."""
    name = Path(executable or sys.executable).name.lower()
    return name == UNINSTALL_EXE.lower()


def uninstall_commands(install_dir: Path) -> tuple[str, str]:
    """(UninstallString, QuietUninstallString): the uninstaller in the folder, else the app exe."""
    uninstaller = install_dir / UNINSTALL_EXE
    if uninstaller.exists():
        return f"\"{uninstaller}\"", f"\"{uninstaller}\" --quiet"
    exe = install_dir / APP_EXE
    return f"\"{exe}\" --uninstall", f"\"{exe}\" --uninstall --quiet"


def folder_size(folder: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def ensure_registered(install_dir: Path, version: str) -> bool:
    """Write the 应用和功能 entry again if an installed copy lost it (or it points elsewhere / is old).

    Only for folders the installer created (MARKER). Returns True when the entry was written.
    """
    if sys.platform != "win32" or not (install_dir / MARKER).exists():
        return False
    info = read_installed()
    current = uninstall_commands(install_dir)[0]
    same_place = info and os.path.normcase(os.path.normpath(info["location"])) == os.path.normcase(os.path.normpath(install_dir))
    if same_place and info["version"] == version and _uninstall_string() == current:
        return False
    register(install_dir, version, folder_size(install_dir))
    return True


def _uninstall_string() -> str:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return str(winreg.QueryValueEx(key, "UninstallString")[0])
    except OSError:
        return ""


def register(install_dir: Path, version: str, size_bytes: int) -> None:
    import winreg

    exe = install_dir / APP_EXE
    uninstall, quiet = uninstall_commands(install_dir)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_WRITE) as key:
        values = {
            "DisplayName": DISPLAY_NAME,
            "DisplayVersion": version,
            "Publisher": PUBLISHER,
            "DisplayIcon": f"\"{exe}\",0",
            "InstallLocation": str(install_dir),
            "UninstallString": uninstall,
            "QuietUninstallString": quiet,
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
                [system_exe("tasklist"), "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
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
    # A folder name cannot contain a double quote, but % would be expanded by cmd: refuse those
    # (the folder is then simply left behind; the uninstaller says what to delete by hand).
    if "%" in str(folder) or '"' in str(folder):
        return
    subprocess.Popen(
        f'"{system_exe("cmd")}" /d /c ""{system_exe("ping")}" 127.0.0.1 -n 3 >nul & rmdir /s /q "{folder}""',
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True, cwd=str(Path(folder).parent),
    )
