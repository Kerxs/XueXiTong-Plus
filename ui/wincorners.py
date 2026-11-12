"""Rounded corners for the app's own frameless windows.

Windows 11 rounds the corners of ordinary windows itself; a frameless window (the app draws its own
title bar) is left square unless it asks. Windows 10 has no rounded windows: the call fails there
and the window stays square, which is how every window looks on that system.
"""
import sys

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
RADIUS = 8          # what Windows 11 uses for DWMWCP_ROUND, in device-independent pixels


def set_rounded(hwnd: int, rounded: bool) -> bool:
    """Ask Windows to round (or square, e.g. while the window fills the screen) the window's corners.
    True when Windows accepted it."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        value = ctypes.c_int(DWMWCP_ROUND if rounded else DWMWCP_DONOTROUND)
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        dwm.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.restype = ctypes.c_long
        return dwm(wintypes.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(value), ctypes.sizeof(value)) == 0
    except Exception:  # noqa: BLE001 - cosmetic only
        return False
