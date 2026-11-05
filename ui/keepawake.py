# -*- coding: utf-8 -*-
"""Keep Windows from going to sleep while a run is active.

A laptop left alone sleeps after 15-30 minutes and the run stalls (no network, no reports).
SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) keeps the system awake; the screen
may still turn off (no ES_DISPLAY_REQUIRED). It applies to the calling thread, so call
hold() / release() from the same (UI) thread. Closing the lid still follows the power settings.
"""

from __future__ import annotations

import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

_held = False


def _set(flags: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))
    except (AttributeError, OSError):
        return False


def hold() -> bool:
    """Keep the system awake until release(). Returns True when Windows accepted it."""
    global _held
    _held = _set(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) or _held
    return _held


def release() -> None:
    global _held
    if _held:
        _set(ES_CONTINUOUS)
    _held = False


def held() -> bool:
    return _held
