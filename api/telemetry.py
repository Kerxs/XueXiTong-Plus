# -*- coding: utf-8 -*-
"""Anonymous usage statistics (设置 → 数据与隐私; on by default since 1.3.0, the guide says so and
the switch turns it off).

What is kept and sent — and nothing else:
  * counts under fixed names (``video.ok``, ``captcha.restart`` …),
  * durations and sizes as numbers (how long a video task took, peak memory),
  * the app version, the system ("Windows 11", "Android 14") and a random install id that is not
    tied to the account,
  * for a crash: the exception type and where in THIS program's code it happened.
Never: account, password, cookies, tokens, course / chapter / question text, answers, AI
conversations, addresses, file contents or log lines. Names outside ``_KEY`` are dropped, so a
careless ``count(course_title)`` cannot leak anything (tests/test_v130_telemetry.py).

Telemetry never gets in the way of the task: every failure is swallowed, uploads run in their own
thread with a 10 s timeout, and when the server is down the reports wait in a small queue.
Switching it off stops everything at once and deletes what was waiting to be sent.

While ``TELEMETRY_URL`` is empty nothing is uploaded at all (statistics stay on this device).
Feedback is separate and manual: ``feedback_url()`` opens a prefilled GitHub issue the user
submits themselves; the app holds no token of any kind.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import threading
import time
import traceback
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlsplit

REPO = "Kerxs/XueXiTong-Plus"
# The collector (server/telemetry, a Cloudflare Worker). Empty: nothing is uploaded.
# Used by the released apps only (the packaged Windows build and the Android app): running from
# source — development, tests, measurements — never uploads unless XXTPLUS_TELEMETRY_URL says where.
TELEMETRY_URL = "https://xxtplus-telemetry.q26112419.workers.dev/v1/report"
STATS_FILE = "stats.json"
QUEUE_FILE = "telemetry_queue_{}.json"      # one per process kind (gui / worker): no shared writes
MAX_BODY = 6000          # GitHub's prefilled issue URL gets unreliable beyond ~8 KB
MAX_QUEUE = 50           # reports waiting to be sent
MAX_QUEUE_BYTES = 200_000
MAX_REPORT_BYTES = 16_000
UPLOAD_TIMEOUT = 10
SCHEMA = 1

# Category → label in the local summary (anything else is shown by its key).
LABELS = {
    "runs": "运行次数",
    "video.ok": "视频完成", "video.fail": "视频失败", "video.unconfirmed": "视频看完但平台暂未确认",
    "workid.ok": "章节检测完成", "workid.fail": "章节检测失败", "work.graded_skip": "章节检测已批阅（跳过）",
    "document.ok": "课件完成", "document.fail": "课件失败",
    "live.ok": "直播完成", "live.fail": "直播失败",
    "other.manual": "需要手动完成的内容",
    "homework.submitted": "作业已提交", "homework.saved": "作业只保存", "homework.skipped": "作业已交过",
    "homework.failed": "作业未能完成",
    "captcha.seen": "遇到验证码", "captcha.restart": "因验证码重新开始", "relogin": "重新登录",
    "chapter.retry": "章节重试", "run.stopped": "运行被停止（有原因）", "network.wait": "等待网络恢复",
    "chapters.done": "已完成章节", "chapters.total": "章节总数",
    "ai.requests": "AI 请求次数", "ai.questions": "交给 AI 的题目",
    "net.requests": "网络请求", "net.fail": "网络请求失败", "net.timeout": "网络请求超时",
    "app.start": "应用启动", "app.exit": "应用正常退出", "app.crash": "应用崩溃",
    "worker.crash": "任务进程异常退出", "worker.hang": "任务卡住", "worker.restart": "任务自动重新开始",
    "preview.fail": "视频预览失败",
}

# Only names like these are kept: lower-case words joined by dots, from a fixed set of groups.
_KEY = re.compile(r"^(runs|video|audio|live|workid|work|document|other|homework|captcha|relogin|chapter|chapters|run|"
                  r"network|net|ai|app|worker|preview|task|perf|cfg)(\.[a-z][a-z0-9_]{0,23}){0,3}$")

_lock = threading.Lock()
_counts: Counter = Counter()
_timings: dict[str, list[float]] = {}        # key -> [total seconds, how many]
_gauges: dict[str, float] = {}               # key -> largest value seen
_enabled = False
_folder: Path | None = None
_process = "worker"
_started = time.time()
_upload_thread: threading.Thread | None = None


def configure(enabled: bool, folder: str | os.PathLike | None = None, process: str = "worker") -> None:
    """Called once per process (main.main, the app's controller). Off: everything below is a no-op."""
    global _enabled, _folder, _process, _started
    with _lock:
        _enabled = bool(enabled)
        _folder = Path(folder) if folder else Path.cwd()
        _process = process if process in ("gui", "worker") else "worker"
        _started = time.time()
        _counts.clear()
        _timings.clear()
        _gauges.clear()
    if not _enabled:
        discard(folder)


def enabled() -> bool:
    return _enabled


def _ok(key: str) -> bool:
    return isinstance(key, str) and bool(_KEY.match(key))


def count(key: str, n: int = 1) -> None:
    if not _enabled or not n or not _ok(key):
        return
    with _lock:
        _counts[key] += int(n)


def timing(key: str, seconds: float) -> None:
    """How long something took (a video task, a request): reported as a total and a count."""
    if not _enabled or not _ok(key) or seconds < 0:
        return
    with _lock:
        slot = _timings.setdefault(key, [0.0, 0])
        slot[0] += float(seconds)
        slot[1] += 1


def gauge(key: str, value: float) -> None:
    """A size (peak memory, parallel chapters): the largest value of the run is reported."""
    if not _enabled or not _ok(key):
        return
    with _lock:
        _gauges[key] = max(_gauges.get(key, float("-inf")), float(value))


class timed:
    """``with telemetry.timed("task.video"): …`` — never raises, never changes what the block does."""

    def __init__(self, key: str):
        self.key = key

    def __enter__(self):
        self.t = time.monotonic()
        return self

    def __exit__(self, *exc):
        timing(self.key, time.monotonic() - self.t)
        return False


# ----- files ---------------------------------------------------------------------------------
def path(folder=None) -> Path:
    return Path(folder or _folder or Path.cwd()) / STATS_FILE


def _queue_path(folder=None, process: str | None = None) -> Path:
    return Path(folder or _folder or Path.cwd()) / QUEUE_FILE.format(process or _process)


def load(folder=None) -> dict:
    try:
        data = json.loads(path(folder).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(file: Path, data) -> None:
    try:
        tmp = file.with_name(file.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, file)
    except OSError:
        pass


def install_id(folder=None, create: bool = True) -> str:
    """A random id for this installation (not derived from the account or the machine)."""
    data = load(folder)
    value = str(data.get("id") or "")
    if re.fullmatch(r"[0-9a-f]{32}", value):
        return value
    if not create:
        return ""
    data["id"] = uuid.uuid4().hex
    _write(path(folder), data)
    return data["id"]


def clear(folder=None) -> None:
    """清除统计: the local numbers, what was waiting to be sent, and the install id (a new one is
    made the next time something is recorded)."""
    discard(folder)


def discard(folder=None) -> None:
    for file in (path(folder), _queue_path(folder, "gui"), _queue_path(folder, "worker")):
        try:
            file.unlink()
        except OSError:
            pass


# ----- what this process used ----------------------------------------------------------------
def _peak_memory_mb() -> float:
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (name, ctypes.c_size_t) for name in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                        "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

            info = Counters()
            info.cb = ctypes.sizeof(info)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(info), info.cb):
                return info.PeakWorkingSetSize / 1048576
            return 0.0
        with open("/proc/self/status", encoding="ascii", errors="ignore") as fp:
            for line in fp:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024
    except Exception:  # noqa: BLE001 - statistics only
        pass
    return 0.0


def _platform() -> str:
    named = os.environ.get("XXTPLUS_OS", "").strip()          # the phone app sets "Android 14"
    if named:
        return named[:40]
    if "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ:
        return "Android"
    release = platform.release()
    if sys.platform == "win32":
        try:        # Windows 11 still reports release "10": the build number tells them apart
            release = "11" if int(platform.version().split(".")[2]) >= 22000 else release
        except (IndexError, ValueError):
            pass
    return f"{platform.system()} {release}".strip()[:40]


# ----- reports ---------------------------------------------------------------------------------
def _report(kind: str, counts: dict, timings: dict | None = None, gauges: dict | None = None,
            crash: dict | None = None) -> dict:
    report = {
        "v": SCHEMA, "kind": kind, "id": install_id(), "app": os.environ.get("XXTPLUS_VERSION", "")[:20],
        "os": _platform(), "proc": _process, "day": time.strftime("%Y-%m-%d"),
        "counts": {k: int(v) for k, v in counts.items() if _ok(k) and v},
    }
    if timings:
        report["timings"] = {k: [round(v[0] * 1000), int(v[1])] for k, v in timings.items() if _ok(k) and v[1]}
    if gauges:
        report["gauges"] = {k: round(v, 1) for k, v in gauges.items() if _ok(k)}
    if crash:
        report["crash"] = crash
    return report


def _enqueue(report: dict) -> None:
    if len(json.dumps(report, ensure_ascii=False)) > MAX_REPORT_BYTES:
        return
    file = _queue_path()
    try:
        queue = json.loads(file.read_text(encoding="utf-8"))
        queue = queue if isinstance(queue, list) else []
    except (OSError, ValueError):
        queue = []
    queue.append(report)
    queue = queue[-MAX_QUEUE:]
    while len(queue) > 1 and len(json.dumps(queue, ensure_ascii=False)) > MAX_QUEUE_BYTES:
        queue.pop(0)                         # the oldest goes first
    _write(file, queue)


def save(kind: str = "run") -> None:
    """End of a run (or of the app): merge the numbers into stats.json, queue one report and try to
    send what is waiting. Never raises."""
    if not _enabled:
        return
    try:
        gauge("perf.mem_peak_mb", _peak_memory_mb())
        gauge("perf.cpu_s", time.process_time())
        gauge("perf.run_s", time.time() - _started)
        with _lock:
            run, timings, gauges = dict(_counts), {k: list(v) for k, v in _timings.items()}, dict(_gauges)
            _counts.clear()
            _timings.clear()
            _gauges.clear()
        if kind == "run":
            run["runs"] = run.get("runs", 0) + 1
        data = load()
        counts = Counter(data.get("counts") or {})
        counts.update(run)
        data.update({
            "id": install_id(),
            "version": os.environ.get("XXTPLUS_VERSION", data.get("version", "")),
            "platform": _platform(),
            "since": data.get("since") or time.strftime("%Y-%m-%d"),
            "updated": time.strftime("%Y-%m-%d"),
            "counts": dict(counts),
        })
        _write(path(), data)
        _enqueue(_report(kind, run, timings, gauges))
        flush()
    except Exception:  # noqa: BLE001 - statistics must never break the run
        pass


# ----- crashes ---------------------------------------------------------------------------------
_PROJECT_DIRS = ("api", "core", "ui", "installer", "packaging")


def _frame_name(filename: str) -> str:
    """"api/base.py" for this program's files; "" for anything else (no user paths, no library paths)."""
    parts = Path(filename).parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] in _PROJECT_DIRS and i < len(parts) - 1:
            return "/".join(parts[i:])
    name = Path(filename).name
    return name if name in ("main.py", "gui.py", "worker.py", "xxtplus_android.py") else ""


def scrub_text(text: str) -> str:
    """A message with everything that could identify someone removed: registered secrets, paths,
    addresses, long digit runs (phone numbers, ids), e-mail addresses, CJK text (names, course and
    question text)."""
    try:
        from api.logger import redact

        text = redact(str(text))
    except Exception:  # noqa: BLE001
        text = str(text)
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(r"[A-Za-z]:[\\/][^\s'\"]*|(?:/[\w.\-]+){2,}", "<path>", text)
    text = re.sub(r"\S+@\S+\.\S+", "<mail>", text)
    text = re.sub(r"\d{5,}", "<n>", text)
    text = re.sub(r"[㐀-鿿豈-﫿]+", "<文>", text)
    return text[:200]


def scrub_exception(exc: BaseException) -> dict:
    """Type, a scrubbed message and the frames inside this program: "api/base.py:study_video:1234".
    No local variables, no source lines, no frames from outside the program."""
    frames = []
    for frame in traceback.extract_tb(exc.__traceback__):
        name = _frame_name(frame.filename)
        if name:
            frames.append(f"{name}:{frame.name}:{frame.lineno}")
    return {"type": type(exc).__name__[:60], "message": scrub_text(str(exc)), "frames": frames[-12:]}


def record_crash(exc: BaseException, key: str = "app.crash") -> None:
    """Queue a crash report (sent on the next start if the process dies now)."""
    if not _enabled:
        return
    try:
        _enqueue(_report("crash", {key: 1}, crash=scrub_exception(exc)))
        data = load()
        counts = Counter(data.get("counts") or {})
        counts[key] += 1
        data["counts"] = dict(counts)
        _write(path(), data)
    except Exception:  # noqa: BLE001
        pass


# ----- upload ----------------------------------------------------------------------------------
def upload_url() -> str:
    """Where reports go ("" = nowhere). https only; plain http is accepted for 127.0.0.1 (tests)."""
    override = os.environ.get("XXTPLUS_TELEMETRY_URL", "").strip()
    if override.lower() == "off":
        return ""
    released = bool(getattr(sys, "frozen", False)) or "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ
    url = override or (TELEMETRY_URL if released else "")
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")):
        return url
    return ""


def _post(url: str, report: dict) -> bool:
    import urllib.request

    request = urllib.request.Request(
        url, data=json.dumps(report, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "XueXiTong-Plus"})
    with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT) as response:  # noqa: S310 - https, checked above
        return 200 <= response.status < 300


def _send_queue() -> None:
    url = upload_url()
    file = _queue_path()
    if not url or not _enabled:
        return
    try:
        queue = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    left = list(queue) if isinstance(queue, list) else []
    try:
        while left and _enabled:
            if not _post(url, left[0]):
                break
            left.pop(0)
    except Exception:  # noqa: BLE001 - server down, no network: the reports wait
        pass
    if not _enabled:
        return                               # switched off meanwhile: discard() already removed the file
    if left:
        _write(file, left)
    else:
        try:
            file.unlink()
        except OSError:
            pass


def flush(wait: float = 0.0) -> None:
    """Send what is waiting, in a background thread. ``wait``: seconds to give it before returning
    (the task process waits a little at its end; the app never waits)."""
    global _upload_thread
    if not _enabled or not upload_url():
        return
    with _lock:
        if _upload_thread is None or not _upload_thread.is_alive():
            _upload_thread = threading.Thread(target=_send_queue, name="telemetry-upload", daemon=True)
            _upload_thread.start()
        thread = _upload_thread
    if wait > 0:
        thread.join(wait)


def pending(folder=None) -> int:
    """Reports waiting to be sent (both processes)."""
    total = 0
    for process in ("gui", "worker"):
        try:
            data = json.loads(_queue_path(folder, process).read_text(encoding="utf-8"))
            total += len(data) if isinstance(data, list) else 0
        except (OSError, ValueError):
            pass
    return total


# ----- what the user sees ------------------------------------------------------------------------
def summary(stats: dict | None = None) -> str:
    """The local statistics as text (Markdown): only the counts."""
    stats = stats if stats is not None else load()
    counts = stats.get("counts") or {}
    if not counts:
        return ""
    lines = [
        "### 匿名使用统计",
        "",
        f"- 版本：{stats.get('version') or '未知'}　系统：{stats.get('platform') or '未知'}",
        f"- 统计时间：{stats.get('since', '?')} 至 {stats.get('updated', '?')}",
        "",
        "| 项目 | 次数 |",
        "| --- | ---: |",
    ]
    order = list(LABELS)
    for key in sorted(counts, key=lambda k: (order.index(k) if k in order else len(order), k)):
        lines.append(f"| {LABELS.get(key, key)} | {counts[key]} |")
    done, total = counts.get("chapters.done", 0), counts.get("chapters.total", 0)
    if total:
        lines += ["", f"章节完成率：{done * 100 // total}%"]
    lines += ["", "（由学习通 PLUS 生成，只含计数，不含账号、课程、题目和日志。）"]
    return "\n".join(lines)


def feedback_url(text: str, title: str = "运行反馈（匿名统计）") -> str:
    """A prefilled GitHub issue page; the user presses 提交 themselves."""
    body = text if len(text) <= MAX_BODY else text[:MAX_BODY] + "\n…（内容过长已截断）"
    return f"https://github.com/{REPO}/issues/new?title={quote(title)}&body={quote(body)}"
