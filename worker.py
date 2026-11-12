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


def selftest() -> int:
    """``chaoxing-worker.exe --selftest``: load every heavy component the task needs and use it once
    (no network, no account). Run after each change to what is packaged: a library that was cut
    away shows up here instead of in the middle of a user's run."""
    import io
    import json

    results: dict[str, str] = {}

    def check(name, fn):
        try:
            results[name] = str(fn())
        except Exception as exc:  # noqa: BLE001
            results[name] = f"FAILED {type(exc).__name__}: {exc}"

    def ocr():
        from PIL import Image, ImageDraw, ImageFont

        from api.captcha import ocr_init

        image = Image.new("RGB", (120, 44), "white")
        try:
            font = ImageFont.truetype("arial.ttf", 30)
        except OSError:
            font = ImageFont.load_default()
        ImageDraw.Draw(image).text((12, 4), "7K3M", fill="black", font=font)
        data = io.BytesIO()
        image.save(data, "PNG")
        text = ocr_init().classification(data.getvalue())
        if len(text) < 3:
            raise RuntimeError(f"read {text!r}")
        return f"ok ({text})"

    def ai_client():
        import openai

        from api.answer import AI

        client = openai.OpenAI(base_url="https://example.invalid/v1", api_key="x", timeout=1, max_retries=0)
        if not hasattr(client.chat.completions, "create") or not issubclass(openai.RateLimitError, Exception):
            raise RuntimeError("client incomplete")
        return f"ok ({'slim' if 'stand-in' in (openai.__doc__ or '') else 'sdk'}, {AI.__name__})"

    def html():
        from bs4 import BeautifulSoup

        return "ok" if BeautifulSoup("<p class='a'>x</p>", "lxml").select_one("p.a").text == "x" else "wrong"

    def fonts():
        from api.font_decoder import FontDecoder  # noqa: F401
        import fontTools.ttLib  # noqa: F401

        return "ok"

    def crypto():
        import ssl

        import pyaes  # noqa: F401
        import requests  # noqa: F401

        from core import secret

        return "ok" if ssl.OPENSSL_VERSION and secret.reveal(secret.protect("秘密")) == "秘密" else "wrong"

    def task():
        import main  # noqa: F401
        from api import homework, images, live_process, telemetry  # noqa: F401

        return "ok"

    for name, fn in (("ocr", ocr), ("ai_client", ai_client), ("html", html), ("fonts", fonts),
                     ("crypto", crypto), ("task", task)):
        check(name, fn)
    print("__CX_SELFTEST__" + json.dumps(results, ensure_ascii=False), flush=True)
    return 0 if all(v.startswith("ok") for v in results.values()) else 1


def run_worker(argv: list[str]) -> int:
    _utf8_streams()
    if len(argv) == 2 and argv[1] == "--selftest":
        return selftest()
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
