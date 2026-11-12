"""Network loss handling shared by the desktop worker and the Android app.

When the connection drops (Wi-Fi switching, mobile data off, screen-off power saving),
requests fail. Instead of spending a chapter's retries on that, the task waits here until
the 学习通 server is reachable again, then carries on where it was.
"""

from __future__ import annotations

import socket
import threading
import time

import requests

from api import pause
from api.logger import logger

PROBE_HOSTS = (("mooc1.chaoxing.com", 443), ("passport2.chaoxing.com", 443))
_lock = threading.Lock()


def is_network_error(exc: BaseException) -> bool:
    """Connection-level failures (not HTTP error statuses or parsing problems)."""
    if isinstance(exc, (requests.ConnectionError, requests.Timeout, ConnectionError, TimeoutError, socket.gaierror)):
        return True
    cause = exc.__cause__ or exc.__context__
    return cause is not None and cause is not exc and is_network_error(cause)


def online(timeout: float = 5.0) -> bool:
    for host, port in PROBE_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def reset_connections() -> None:
    """Forget the connections that were open before an outage or a network change: they are dead,
    and each would otherwise cost a timeout before it is replaced."""
    try:
        from api.base import SessionManager

        SessionManager.reset_connections()
    except Exception:  # noqa: BLE001 - never in the way of the task
        pass


def wait_for_network(sleep=time.sleep, check=online, max_interval: float = 30.0) -> float:
    """Block until the server is reachable; returns the seconds waited (0 if it already is).

    Only one thread probes at a time; the others wait for its result. Pausing is honoured.
    """
    with _lock:
        if check():
            return 0.0
        logger.warning("网络连接中断，等待网络恢复后继续…")
        from api import telemetry

        telemetry.count("network.wait")
        started = time.monotonic()
        last_note = started
        interval = 3.0
        while True:
            pause.wait_if_paused()
            sleep(interval)
            if check():
                waited = time.monotonic() - started
                logger.info(f"网络已恢复（中断约 {waited:.0f} 秒），继续任务")
                reset_connections()
                return waited
            # A line every few minutes: the user sees it is still waiting, and the desktop app's
            # hang check (no output for a long time) does not mistake an outage for a hang.
            if time.monotonic() - last_note >= 300:
                last_note = time.monotonic()
                logger.warning(f"仍在等待网络恢复（已等待约 {(last_note - started) / 60:.0f} 分钟）")
            interval = min(max_interval, interval * 1.6)
