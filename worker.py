# -*- coding: utf-8 -*-
"""Console entry point used by the GUI subprocess."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _utf8_streams() -> None:
    """The GUI reads our output as UTF-8. The packaged exe ignores PYTHONUTF8 and would
    otherwise write in the system code page (GBK on Chinese Windows) -> garbled log."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


COURSES_PREFIX = "__CX_COURSES__"


def list_courses(config_path: Path, data_dir: Path) -> int:
    """Log in with the saved account and print the course list as one JSON line.

    Used by the GUI's "识别课程" button; no question bank, no tasks.
    """
    import json

    data_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(data_dir)
    from core.courses import list_courses as read_courses  # shared with the Android app

    payload = read_courses(config_path)
    code = 0 if payload.get("ok") else int(payload.pop("code", 1))
    print(COURSES_PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)
    return code


def run_worker(argv: list[str]) -> int:
    _utf8_streams()
    if len(argv) == 4 and argv[1] == "--list-courses":
        return list_courses(Path(argv[2]).resolve(), Path(argv[3]).resolve())
    if len(argv) != 4 or argv[1] != "--worker":
        print("用法: chaoxing-worker.exe --worker <config.ini> <data-directory>")
        return 2

    config_path = Path(argv[2]).resolve()
    data_dir = Path(argv[3]).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(data_dir)
    sys.argv = ["main.py", "-c", str(config_path)]

    import main

    main.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_worker(sys.argv))
