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
    {"id": "common.use_cookies", "label": "使用 cookies 登录", "type": "switch", "default": "false",
     "hint": "开启后用导入的 cookies.txt 登录，账号密码不参与登录"},
    {"id": "common.username", "label": "手机号", "type": "text", "default": "",
     "show": {"key": "common.use_cookies", "on": False}},
    {"id": "common.password", "label": "密码", "type": "secret", "default": "",
     "show": {"key": "common.use_cookies", "on": False}},
    {"id": "common.course_list", "label": "课程 ID", "type": "text", "default": "",
     "hint": "多个用英文逗号隔开；留空则开始时选择"},
    # 倍速已失效：不再提供设置，保存时固定写 1（main.py 也会强制 1 倍速）
    {"id": "common.speed", "label": "视频倍速", "type": "hidden", "default": "1"},
    {"id": "common.jobs", "label": "同时进行的章节", "type": "number", "default": "1",
     "min": 1, "max": 8, "step": 1, "decimals": 0, "suffix": "个"},
    {"id": "common.retry_interval", "label": "重试等待", "type": "number", "default": "5",
     "min": 1, "max": 120, "step": 1, "decimals": 0, "suffix": "秒"},
    {"id": "common.notopen_action", "label": "章节未开放时", "type": "choice", "default": "retry",
     "options": [{"value": "retry", "label": "等待后重试"}, {"value": "continue", "label": "跳过"}]},
]
_PLACEHOLDERS = {"xxx", "xxxxxx", "xxx,xxx,xxx"}


_data_dir = ""


def setup(files_dir: str, data_dir: str = "", data_key: str = "") -> None:
    """Data files are opened relative to sys._MEIPASS (see api/cxsecret_font.resource_path).

    data_key: hex key from the Android Keystore (DataKey.kt) that encrypts the account, password,
    API keys and saved cookies (core/secret.py). Empty: they stay plain text, as before.
    """
    global _data_dir
    from core import secret

    if data_key:
        os.environ[secret.KEY_ENV] = data_key
    sys._MEIPASS = files_dir  # type: ignore[attr-defined]
    _data_dir = data_dir or os.path.join(files_dir, "data")
    os.makedirs(_data_dir, exist_ok=True)


# ---------------------------------------------------------------- 数据与隐私 (core/account.py, shared)

def data_stats() -> str:
    from core import account

    return json.dumps({"logSize": account.log_size_text(_data_dir), "hasCookies": account.has_cookies(_data_dir)})


def clear_logs() -> int:
    from core import account

    removed = 0
    for path in account.log_files(_data_dir):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def clear_account_data(config_path: str) -> None:
    """Blank the account, password and cookies login in config.ini and delete cookies files."""
    from core import account

    account.clear_account_data(_data_dir, config_path)


def reset_config(config_path: str, template_path: str) -> None:
    """Restore config.ini from the template but keep the account fields (desktop resetConfig)."""
    keep = {k: v for k, v in json.loads(load_settings(config_path, template_path)).items()
            if k in ("common.username", "common.password", "common.use_cookies")}
    try:
        os.remove(config_path)
    except FileNotFoundError:
        pass
    values = json.loads(load_settings(config_path, template_path))
    values.update(keep)
    save_settings(config_path, template_path, json.dumps(values))


# ---------------------------------------------------------------- 识别课程 (worker.py --list-courses)

def list_courses(config_path: str) -> str:
    """Log in with the saved account and return the course list (core/courses.py, shared)."""
    os.chdir(_data_dir)
    try:
        from core.courses import list_courses as read_courses

        payload = read_courses(config_path)
    except Exception as exc:  # e.g. the task code itself cannot be imported
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    payload.pop("code", None)
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------- settings

def _read_config(config_path: str, template_path: str) -> configparser.ConfigParser:
    from core import secret

    if os.path.exists(config_path):
        try:
            secret.migrate(config_path)   # plain text from older versions -> encrypted
        except OSError:
            pass
        return secret.read_config(config_path)
    config = configparser.ConfigParser(interpolation=None)
    if os.path.exists(template_path):
        config.read(template_path, encoding="utf-8")
    return config


# The phone only uses the model companies' cloud APIs (ui/cloudmodels.PROVIDERS): no 本机模型
# detection, no free-form endpoint and no proxy. The endpoint is set by picking a company.
_DROP_TYPES = {"localmodels", "hidden"}   # hidden: stored only (自定义服务商, edited by aiprovider)
_DROP_IDS = {"tiku.endpoint", "tiku.http_proxy", "tiku.vision_endpoint", "tiku.vision_key"}
_HINTS = {
    "tiku.key": "在所选服务商的控制台创建",
    "tiku.url": "自建 TikuAdapter 服务的地址（手机要能访问到），例如 http://192.168.1.10:8060/adapter-service/search",
}
_LABELS = {
    "aiprovider": "模型服务商",
}


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
            if f["id"] == "notification.provider":
                # 本机通知 = Android's own notification shade (api.notification.Local).
                f = {**f, "options": [{"value": "Local", "label": "本机通知"}, *f["options"]],
                     "hint": "本机通知：直接显示在手机通知栏，不需要第三方服务"}
            elif f["section"] == "notification" and f.get("show"):
                show = f["show"] if isinstance(f["show"], list) else [f["show"]]
                f = {**f, "show": [*show, {"key": "notification.provider", "ne": "Local"}]}
            fields.append(f)
        groups.append({**group, "fields": fields})
    return json.dumps({"basic": BASIC_FIELDS, "groups": groups, "aiProviders": cloudmodels.public_providers(),
                       "aiRegions": cloudmodels.REGIONS},
                      ensure_ascii=False)


def load_settings(config_path: str, template_path: str) -> str:
    from ui import advanced

    config = _read_config(config_path, template_path)
    values = advanced.read_values(config)
    for f in BASIC_FIELDS:
        section, key = f["id"].split(".", 1)
        raw = config.get(section, key, fallback=f["default"]).strip()
        values[f["id"]] = "" if raw.lower() in _PLACEHOLDERS else raw
    # The template's provider is ServerChan with no address, i.e. not set up: on the phone
    # the natural default is the system notification.
    if values.get("notification.provider") == "ServerChan" and not values.get("notification.url"):
        values["notification.provider"] = "Local"
    return json.dumps(values, ensure_ascii=False)


def save_settings(config_path: str, template_path: str, values_json: str) -> None:
    from ui import advanced

    values = json.loads(values_json)
    values["tiku.http_proxy"] = ""  # no proxy setting on the phone
    values["common.speed"] = "1"    # 倍速已失效
    config = _read_config(config_path, template_path)
    advanced.write_values(config, {k: advanced.normalize(k, v) for k, v in values.items()})
    for f in BASIC_FIELDS:
        section, key = f["id"].split(".", 1)
        if not config.has_section(section):
            config.add_section(section)
        config[section][key] = str(values.get(f["id"], f["default"])).strip()
    from core import secret

    secret.write_config(config, config_path)   # account, password, keys encrypted


def setup_problem(values_json: str) -> str:
    """Why 开始运行 cannot start ("" = can start): the same rule as the desktop (core/settings.py)."""
    from core import settings

    return settings.start_problem(json.loads(values_json), _data_dir, cloud_only=True)


def guide_problem(values_json: str) -> str:
    """The guide's 答题来源 step (also needs the 题库 token / address), as on the desktop."""
    from core import settings

    return settings.guide_problem(json.loads(values_json), cloud_only=True)


def add_custom_provider(saved: str, name: str, endpoint: str) -> str:
    """自定义服务商 on the phone: https only, no 本机 services. {"ok", "error", "value", "endpoint"}."""
    from ui import cloudmodels

    problem = cloudmodels.custom_problem(name, endpoint, saved, cloud_only=True)
    if problem:
        return json.dumps({"ok": False, "error": problem}, ensure_ascii=False)
    value = cloudmodels.dump_custom(cloudmodels.add_custom(saved, name, endpoint))
    return json.dumps({"ok": True, "value": value, "endpoint": cloudmodels.normalize_endpoint(endpoint)},
                      ensure_ascii=False)


def remove_custom_provider(saved: str, endpoint: str) -> str:
    from ui import cloudmodels

    return cloudmodels.dump_custom(cloudmodels.remove_custom(saved, endpoint))


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
    # The video preview asks for a fresh address by creating this file (PreviewPlayer, api/base.py).
    refresh = os.path.join(data_dir, "preview_refresh.flag")
    try:
        os.remove(refresh)
    except OSError:
        pass
    os.environ["CHAOXING_PREVIEW_REFRESH_FILE"] = refresh
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
        from api import notification

        # 本机通知: messages the task sends (finished / error) become Android notifications.
        def _notify(message: str) -> None:
            sink.emit(json.dumps({"type": "notify", "text": message}, ensure_ascii=False))

        notification.set_local_handler(_notify)
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
