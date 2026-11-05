# -*- coding: utf-8 -*-
"""Anonymous usage statistics and one-click feedback (设置 → 数据与隐私, off by default).

Only counts under fixed category names are kept (``video.ok``, ``captcha.restart`` …): no account,
password, course or chapter names, questions, addresses or log text. While the switch is off
nothing is written.

Feedback never uploads anything by itself and the app holds no GitHub token: ``feedback_url()``
builds a prefilled ``github.com/…/issues/new`` page from the counts, the user reads it in the
browser and presses 提交 there.
"""

from __future__ import annotations

import json
import os
import platform
import threading
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote

REPO = "Kerxs/XueXiTong-Plus"
STATS_FILE = "stats.json"
MAX_BODY = 6000          # GitHub's prefilled issue URL gets unreliable beyond ~8 KB

# Category → label in the feedback text (anything else is shown by its key).
LABELS = {
    "runs": "运行次数",
    "video.ok": "视频完成", "video.fail": "视频失败", "video.unconfirmed": "视频看完但平台暂未确认",
    "workid.ok": "章节检测完成", "workid.fail": "章节检测失败", "work.graded_skip": "章节检测已批阅（跳过）",
    "document.ok": "课件完成", "document.fail": "课件失败",
    "other.manual": "需要手动完成的内容",
    "homework.submitted": "作业已提交", "homework.saved": "作业只保存", "homework.skipped": "作业已交过",
    "homework.failed": "作业未能完成",
    "captcha.seen": "遇到验证码", "captcha.restart": "因验证码重新开始", "relogin": "重新登录",
    "chapter.retry": "章节重试", "run.stopped": "运行被停止（有原因）", "network.wait": "等待网络恢复",
    "chapters.done": "已完成章节", "chapters.total": "章节总数",
}

_lock = threading.Lock()
_counts: Counter = Counter()
_enabled = False
_folder: Path | None = None


def configure(enabled: bool, folder: str | os.PathLike | None = None) -> None:
    """Called once per run (main.main): counting is a no-op unless the user switched it on."""
    global _enabled, _folder
    with _lock:
        _enabled = bool(enabled)
        _folder = Path(folder) if folder else Path.cwd()
        _counts.clear()


def count(key: str, n: int = 1) -> None:
    if not _enabled or not n:
        return
    with _lock:
        _counts[key] += n


def path(folder=None) -> Path:
    return Path(folder or _folder or Path.cwd()) / STATS_FILE


def load(folder=None) -> dict:
    try:
        data = json.loads(path(folder).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save() -> None:
    """Merge this run's counts into stats.json (only when enabled)."""
    if not _enabled:
        return
    with _lock:
        run = dict(_counts)
        _counts.clear()
    data = load()
    counts = Counter(data.get("counts") or {})
    counts.update(run)
    counts["runs"] += 1
    data.update({
        "version": os.environ.get("XXTPLUS_VERSION", data.get("version", "")),
        "platform": _platform(),
        "since": data.get("since") or time.strftime("%Y-%m-%d"),
        "updated": time.strftime("%Y-%m-%d"),
        "counts": dict(counts),
    })
    try:
        path().write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def clear(folder=None) -> None:
    try:
        path(folder).unlink()
    except OSError:
        pass


def _platform() -> str:
    if "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ:
        return "Android"
    return f"{platform.system()} {platform.release()}".strip()


def summary(stats: dict | None = None) -> str:
    """The feedback text (Markdown): only the counts."""
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
