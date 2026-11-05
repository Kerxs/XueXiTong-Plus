"""Task points this program does not complete: reported to the user for manual completion.

Automated: videos (and audio) and 章节检测 (quizzes). Everything else — documents, reading,
live streams, questionnaires, discussions, links … — is announced instead:

* a log line and an ``__CX_MANUAL_TASK__`` event line (the desktop and phone apps list it,
  and show a popup when no push service is configured);
* a push through the configured notification service (本机通知 on the phone by default);
* one summary at the end of the run.
"""

from __future__ import annotations

import json
import threading

from api.logger import logger

PREFIX = "__CX_MANUAL_TASK__"

KIND_LABELS = {
    "document": "文档 / 课件",
    "read": "阅读",
    "live": "直播",
    "questionnaire": "问卷",
    "survey": "问卷",
    "insertsurvey": "问卷",
    "vote": "投票",
    "bbs": "讨论",
    "insertbbs": "讨论",
    "topic": "讨论",
    "hyperlink": "链接",
    "insertbook": "图书",
    "insertimage": "图片",
    "work": "作业",
}

_lock = threading.Lock()
_seen: set[str] = set()
_items: list[dict] = []
_notifier = None


def set_notifier(notifier) -> None:
    """The run's NotificationService (main.main sets it once notifications are configured)."""
    global _notifier
    _notifier = notifier


def reset() -> None:
    with _lock:
        _seen.clear()
        _items.clear()


def kind_label(job: dict) -> str:
    kind = str(job.get("card_type") or job.get("type") or "").lower()
    if kind in KIND_LABELS:
        return KIND_LABELS[kind]
    for key, label in KIND_LABELS.items():
        if key in kind:
            return label
    return f"其他内容（{kind}）" if kind and kind != "other" else "其他内容"


def report(course: dict, point: dict, job: dict) -> None:
    """Announce one task point that needs the user (once per task point per run)."""
    key = f"{course.get('courseId', '')}/{point.get('id', point.get('title', ''))}/{job.get('jobid', '')}/{job.get('type')}"
    item = {
        "course": str(course.get("title", "")),
        "chapter": str(point.get("title", "")),
        "kind": kind_label(job),
        "name": str(job.get("name") or job.get("title") or "").strip(),
    }
    with _lock:
        if key in _seen:
            return
        _seen.add(key)
        _items.append(item)
    what = f"{item['kind']}「{item['name']}」" if item["name"] else item["kind"]
    logger.warning(f"需要手动完成：{what}（{item['course']} / {item['chapter']}），本程序只自动完成视频和章节检测")
    print(PREFIX + json.dumps(item, ensure_ascii=False), flush=True)
    if _notifier is not None:
        try:
            _notifier.send(f"chaoxing : 需要手动完成：{what}\n{item['course']} / {item['chapter']}")
        except Exception as exc:  # a push must never stop the run
            logger.debug(f"手动任务通知发送失败: {exc}")


def items() -> list[dict]:
    with _lock:
        # Return snapshots so callers cannot mutate the run's stored summary.
        return [item.copy() for item in _items]


def summary() -> str:
    """One-line summary for the end of the run ("" when nothing needs the user)."""
    found = items()
    if not found:
        return ""
    kinds: dict[str, int] = {}
    for item in found:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    detail = "、".join(f"{k} {n} 项" for k, n in kinds.items())
    return f"有 {len(found)} 项内容需要手动完成（{detail}），请到学习通完成"
