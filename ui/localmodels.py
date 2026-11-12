# -*- coding: utf-8 -*-
"""Find OpenAI-compatible model servers running on this computer.

Used by 高级选项 → 答题来源 → 自动检测本机模型: llama.cpp, Ollama, LM Studio, vLLM and
similar all answer GET /v1/models. Candidates are the usual default ports, the ports the
app already knows about, and every TCP port this machine is listening on (netstat), so a
server on an unusual port is found too. Only 127.0.0.1 is asked, without any proxy.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePath

# Default ports of common local model servers.
KNOWN_PORTS = {
    8080: "llama.cpp",
    11434: "Ollama",
    1234: "LM Studio",
    8000: "vLLM",
    5000: "text-generation-webui",
    5001: "KoboldCpp",
}
MAX_PORTS = 200
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# A listening socket has remote address 0.0.0.0:0 / [::]:0; the state column is localized
# and not always reported, so it is not used.
_LISTEN_RE = re.compile(r"^\s*TCP\s+(?:127\.0\.0\.1|0\.0\.0\.0|\[::1?\]):(\d+)\s+(?:0\.0\.0\.0:0|\[::\]:0)\s", re.MULTILINE)
_PS_LISTENERS = ("Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.RemotePort -eq 0 -and "
                 "@('127.0.0.1','0.0.0.0','::','::1') -contains $_.LocalAddress } | "
                 "Select-Object -ExpandProperty LocalPort -Unique")


def _run(args: list[str], timeout: float = 10) -> str:
    try:
        from ui import winsetup

        args = [winsetup.system_exe(args[0]), *args[1:]]         # Windows' own netstat / powershell
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def listening_ports() -> list[int]:
    """TCP ports listening on loopback / all interfaces.

    netstat does not list every socket on every machine (seen: a llama-server that only
    Get-NetTCPConnection reported), so both are asked and the results merged.
    """
    if sys.platform != "win32":
        return []
    ports = {int(p) for p in _LISTEN_RE.findall(_run(["netstat", "-ano", "-p", "TCP"]))}
    ports |= {int(p) for p in _LISTEN_RE.findall(_run(["netstat", "-ano", "-p", "TCPv6"]))}
    for line in _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_LISTENERS], timeout=20).split():
        if line.isdigit():
            ports.add(int(line))
    return sorted(ports)


def model_ids(payload: dict) -> list[str]:
    """Model names from a /v1/models response (OpenAI "data" or llama.cpp / Ollama "models")."""
    items = payload.get("data") or payload.get("models") or []
    names = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            name = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def display_model(name: str) -> str:
    """llama.cpp reports the model file path; the file name (without .gguf) reads better and works as the model."""
    if ("\\" in name or "/" in name) and name.lower().endswith(".gguf"):
        return PurePath(name.replace("\\", "/")).stem
    return name


def probe(port: int, timeout: float = 0.8) -> list[str] | None:
    """Model names served on 127.0.0.1:port, or None if it is not a model server."""
    try:
        with _NO_PROXY.open(f"http://127.0.0.1:{port}/v1/models", timeout=timeout) as resp:  # noqa: S310 - loopback only
            data = json.loads(resp.read(512 * 1024).decode("utf-8", errors="replace") or "{}")
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    names = [display_model(n) for n in model_ids(data)]
    return names or None


def detect(extra_ports=(), scan_listening: bool = True) -> list[dict]:
    """[{endpoint, port, server, models}] for every local server that lists models."""
    ports: list[int] = []
    for port in [*extra_ports, *KNOWN_PORTS, *(listening_ports() if scan_listening else [])]:
        if isinstance(port, int) and 0 < port < 65536 and port not in ports:
            ports.append(port)
    ports = ports[:MAX_PORTS]
    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(probe, ports))
    found = []
    for port, models in zip(ports, results):
        if models:
            found.append({
                "endpoint": f"http://127.0.0.1:{port}/v1",
                "port": port,
                "server": KNOWN_PORTS.get(port, ""),
                "models": models,
            })
    return found


def port_of(url: str) -> int | None:
    match = re.match(r"^\s*https?://(?:127\.0\.0\.1|localhost|\[::1\]):(\d+)", url or "", re.IGNORECASE)
    return int(match.group(1)) if match else None
