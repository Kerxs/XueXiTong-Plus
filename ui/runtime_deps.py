# -*- coding: utf-8 -*-
"""External runtime components the app needs, and installing them from the vendor.

The MSVC runtime ships inside the package. The one thing that must be on the machine is
the Microsoft Edge WebView2 Runtime (the video preview is a WebView2). Windows 11 has it;
Windows 10 may not. The setup program checks for it and, if it is missing, downloads
Microsoft's Evergreen bootstrapper from go.microsoft.com, checks that the file carries a
valid Microsoft Authenticode signature, and runs it silently (per-user when not elevated).
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable

WEBVIEW2_NAME = "Microsoft Edge WebView2 运行时"
# Evergreen bootstrapper (~2 MB; it downloads the matching runtime itself).
WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_PAGE = "https://developer.microsoft.com/microsoft-edge/webview2/"
WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_CLIENT_KEYS = (
    ("HKLM", rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT}"),
    ("HKLM", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT}"),
    ("HKCU", rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT}"),
)
USER_AGENT = "XueXiTong-Plus-Setup"


def webview2_version() -> str:
    """Installed WebView2 Runtime version, or "" when it is not installed."""
    if sys.platform != "win32":
        return ""
    import winreg

    roots = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}
    for root, path in _CLIENT_KEYS:
        try:
            with winreg.OpenKey(roots[root], path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        # Microsoft documents "" and 0.0.0.0 as "not installed" (left over after removal).
        if isinstance(version, str) and version.strip() not in ("", "0.0.0.0"):
            return version.strip()
    return ""


def download(url: str, dest: Path, progress: Callable[[float], None] | None = None, timeout: float = 30) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as resp, open(partial, "wb") as out:  # noqa: S310 - fixed Microsoft URL
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(64 * 1024):
            out.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    partial.replace(dest)
    return dest


def is_microsoft_signed(path: Path) -> bool:
    """True when the file has a valid Authenticode signature issued to Microsoft Corporation."""
    script = (
        "$s = Get-AuthenticodeSignature -LiteralPath $env:XXT_SIG_FILE; "
        "if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'O=Microsoft Corporation') { 'ok' } else { 'bad' }"
    )
    from ui import winsetup

    try:
        result = subprocess.run(
            [winsetup.system_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "XXT_SIG_FILE": str(path)},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip() == "ok"


def run_webview2_installer(path: Path, timeout: float = 900) -> int:
    """Run the bootstrapper silently; it downloads and installs the runtime. Returns its exit code."""
    result = subprocess.run([str(path), "/silent", "/install"], timeout=timeout,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.returncode


def install_webview2(work_dir: Path, progress: Callable[[str, float], None] | None = None) -> str:
    """Download, verify and install the WebView2 Runtime. Returns "" on success, else a message."""
    report = progress or (lambda _text, _value: None)
    target = work_dir / "MicrosoftEdgeWebview2Setup.exe"
    try:
        report("从微软官网下载 " + WEBVIEW2_NAME, 0.0)
        download(WEBVIEW2_URL, target, lambda f: report("从微软官网下载 " + WEBVIEW2_NAME, 0.3 * f))
    except OSError as exc:
        return f"下载 {WEBVIEW2_NAME} 失败（{type(exc).__name__}）。可以稍后从微软官网手动安装。"
    try:
        report("校验安装程序签名", 0.32)
        if not is_microsoft_signed(target):
            return f"下载的 {WEBVIEW2_NAME} 安装程序签名无效，已放弃安装。可以稍后从微软官网手动安装。"
        report("正在安装 " + WEBVIEW2_NAME + "（可能需要几分钟）", 0.35)
        try:
            code = run_webview2_installer(target)
        except (OSError, subprocess.SubprocessError) as exc:
            return f"{WEBVIEW2_NAME} 安装失败（{type(exc).__name__}）。可以稍后从微软官网手动安装。"
        if not webview2_version():
            return f"{WEBVIEW2_NAME} 安装没有完成（返回码 {code}）。可以稍后从微软官网手动安装。"
        report(WEBVIEW2_NAME + " 已安装", 1.0)
        return ""
    finally:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass

