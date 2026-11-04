"""Bridge between the Android app (Kotlin, via Chaquopy) and the shared task code.

The desktop app runs ``main.py`` in a subprocess and parses its stdout with
``ui/output_parser.py``. Android has no subprocess for Python, so the worker
service calls :func:`run` instead: stdout / stderr are replaced by a stream that
feeds the same parser, and every parsed event is handed to Kotlin as one JSON
string. ``input()`` (course choice, Y/n question) blocks until Kotlin calls
:func:`answer`. Pause / continue reuse ``api/pause.py`` (a flag file).
"""

from __future__ import annotations

import builtins
import configparser
import dataclasses
import io
import json
import os
import queue
import sys
import threading
import time
import traceback

_answers: "queue.Queue[str]" = queue.Queue()

BASIC_FIELDS = [
    {"id": "common.username", "label": "手机号", "type": "text", "default": ""},
    {"id": "common.password", "label": "密码", "type": "secret", "default": ""},
    {"id": "common.course_list", "label": "课程 ID", "type": "text", "default": "",
     "hint": "多个用英文逗号隔开；留空则开始时选择"},
    {"id": "common.speed", "label": "视频倍速", "type": "number", "default": "1",
     "min": 1, "max": 2, "step": 0.25, "decimals": 2, "suffix": "x"},
    {"id": "common.jobs", "label": "同时进行的章节", "type": "number", "default": "1",
     "min": 1, "max": 8, "step": 1, "decimals": 0, "suffix": "个"},
    {"id": "common.retry_interval", "label": "重试等待", "type": "number", "default": "5",
     "min": 1, "max": 120, "step": 1, "decimals": 0, "suffix": "秒"},
    {"id": "common.notopen_action", "label": "章节未开放时", "type": "choice", "default": "retry",
     "options": [{"value": "retry", "label": "等待后重试"}, {"value": "continue", "label": "跳过"}]},
]
_PLACEHOLDERS = {"xxx", "xxxxxx", "xxx,xxx,xxx"}


def setup(files_dir: str) -> None:
    """Data files are opened relative to sys._MEIPASS (see api/cxsecret_font.resource_path)."""
    sys._MEIPASS = files_dir  # type: ignore[attr-defined]


# ---------------------------------------------------------------- settings

def _read_config(config_path: str, template_path: str) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path, encoding="utf-8")
    elif os.path.exists(template_path):
        config.read(template_path, encoding="utf-8")
    return config


# The phone only uses the model companies' cloud APIs (ui/cloudmodels.PROVIDERS): no 本机模型
# detection, no free-form endpoint and no proxy. The endpoint is set by picking a company.
_DROP_TYPES = {"localmodels"}
_DROP_IDS = {"tiku.endpoint", "tiku.http_proxy"}
_HINTS = {
    "tiku.key": "在所选服务商的控制台创建",
}
_LABELS = {
    "aiprovider": "模型服务商",
}


def _cloud_endpoints() -> list[str]:
    from ui import cloudmodels

    return [p["endpoint"] for p in cloudmodels.PROVIDERS]


def settings_schema() -> str:
    from ui import advanced, cloudmodels

    groups = []
    for group in advanced.GROUPS:
        fields = []
        for f in group["fields"]:
            if f["type"] in _DROP_TYPES or f["id"] in _DROP_IDS:
                continue
            if f["id"] in _HINTS:
                f = {**f, "hint": _HINTS[f["id"]]}
            if f["type"] in _LABELS:
                f = {**f, "label": _LABELS[f["type"]]}
            fields.append(f)
        groups.append({**group, "fields": fields})
    providers = [{"name": p["name"], "endpoint": p["endpoint"]} for p in cloudmodels.PROVIDERS]
    return json.dumps({"basic": BASIC_FIELDS, "groups": groups, "aiProviders": providers},
                      ensure_ascii=False)


def load_settings(config_path: str, template_path: str) -> str:
    from ui import advanced

    config = _read_config(config_path, template_path)
    values = advanced.read_values(config)
    for f in BASIC_FIELDS:
        section, key = f["id"].split(".", 1)
        raw = config.get(section, key, fallback=f["default"]).strip()
        values[f["id"]] = "" if raw.lower() in _PLACEHOLDERS else raw
    return json.dumps(values, ensure_ascii=False)


def save_settings(config_path: str, template_path: str, values_json: str) -> None:
    from ui import advanced

    values = json.loads(values_json)
    values["tiku.http_proxy"] = ""  # no proxy setting on the phone
    config = _read_config(config_path, template_path)
    advanced.write_values(config, {k: advanced.normalize(k, v) for k, v in values.items()})
    for f in BASIC_FIELDS:
        section, key = f["id"].split(".", 1)
        if not config.has_section(section):
            config.add_section(section)
        config[section][key] = str(values.get(f["id"], f["default"])).strip()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    tmp = config_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        config.write(fp)
    os.replace(tmp, config_path)


def setup_problem(values_json: str) -> str:
    """Empty string when the run can start, otherwise what is missing."""
    from ui import advanced

    values = json.loads(values_json)
    if not values.get("common.username") or not values.get("common.password"):
        return "还没有填写手机号和密码"
    picked = [p.strip() for p in str(values.get("tiku.provider", "")).split(",")]
    if "AI" in picked:
        if str(values.get("tiku.endpoint", "")).strip() not in _cloud_endpoints():
            return "答题方式用到了 AI，请先选择模型服务商"
        if not str(values.get("tiku.key", "")).strip():
            return "答题方式用到了 AI，但还没填写 API Key"
    return advanced.answer_setup_problem(values)


def list_models(endpoint: str, key: str, proxy: str) -> str:
    from ui import cloudmodels

    try:
        return json.dumps({"ok": True, "models": cloudmodels.list_models(endpoint, key, proxy)},
                          ensure_ascii=False)
    except Exception as exc:  # shown to the user as is
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


# ---------------------------------------------------------------- running

def answer(text: str) -> None:
    _answers.put(text)


class _ParsedStream(io.TextIOBase):
    """Text written by the task code -> OutputParser events -> sink.emit(json)."""

    encoding = "utf-8"

    def __init__(self, parser, sink):
        super().__init__()
        self._parser = parser
        self._sink = sink
        self._lock = threading.Lock()
        self._last_progress: dict[str, float] = {}

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False

    def write(self, text: str) -> int:
        with self._lock:
            for event in self._parser.feed(text):
                self._emit(event)
        return len(text)

    def flush(self) -> None:
        pass

    def close_parser(self) -> None:
        with self._lock:
            for event in self._parser.feed("", final=True):
                self._emit(event)

    def _emit(self, event) -> None:
        kind = type(event).__name__.removesuffix("Event").lower()
        payload = {"type": kind, **dataclasses.asdict(event)}
        if kind == "progress":  # tqdm redraws often; ~2 updates a second is plenty for the UI
            now = time.monotonic()
            if payload["percent"] < 100 and now - self._last_progress.get(payload["name"], 0) < 0.5:
                return
            self._last_progress[payload["name"]] = now
        try:
            self._sink.emit(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass  # the UI side must never break the task


def run(config_path: str, data_dir: str, pause_file: str, sink) -> int:
    """Run main.main() with the given config; blocks until the run ends. Returns an exit code."""
    from ui.output_parser import OutputParser

    os.makedirs(data_dir, exist_ok=True)
    os.chdir(data_dir)
    os.environ["CHAOXING_DESKTOP_PREVIEW"] = "1"
    os.environ["CHAOXING_PAUSE_FILE"] = pause_file
    os.environ["PYTHONUNBUFFERED"] = "1"

    stream = _ParsedStream(OutputParser(), sink)
    sys.stdout = sys.stderr = stream  # before importing main: api/logger.py captures sys.stderr

    def _input(prompt: str = "") -> str:
        print(prompt, end="", flush=True)
        reply = _answers.get()
        print(flush=True)  # ends the prompt line, like pressing Enter in a console
        return reply

    builtins.input = _input
    sys.argv = ["main.py", "-c", config_path]
    code = 0
    try:
        import main

        main.main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException as exc:  # main() logs it already; keep a trace for unexpected ones
        print(f"错误: {type(exc).__name__}: {exc}", flush=True)
        print(traceback.format_exc(), flush=True)
        code = 1
    finally:
        try:
            from loguru import logger

            logger.complete()  # the console sink uses enqueue=True
        except Exception:
            pass
        stream.close_parser()
    return code
