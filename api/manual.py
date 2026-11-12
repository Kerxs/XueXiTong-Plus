"""Task points this program does not complete: reported to the user for manual completion.

Automated: videos (and audio) and 章节检测 (quizzes). Everything else — documents, reading,
live streams, questionnaires, discussions, links … — is announced instead:

* a log line and an ``__CX_MANUAL_TASK__`` event line (the desktop and phone apps list it,
  and show a popup when no push service is configured);
* a push through the configured notification service (本机通知 on the phone by default);
* one summary at the end of the run.

Two steps, so that few reminders become popups: ``report`` only says "可能需要手动，正在确认"
(the event carries ``"checking": true``: the apps list it quietly). The run then looks again — the
chapter is read once more, after logging in again when that does not help, and what can be retried
is retried (main.JobProcessor._settle_manual). What is gone by then is taken back (``dismiss``);
only what is still there is announced for real (``confirm``: popup / push). ``urgent`` reminders
(a quiz that is open right now, a captcha that stayed) skip the first step.
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
    "homework": "作业",
    "exam": "考试",
    "test": "测验",
    "quiz": "测验",
    "insertdoc": "文档 / 课件",
    "insertpdf": "文档 / 课件",
    "insertppt": "文档 / 课件",
    "text": "文字内容",
    "inserttext": "文字内容",
    "richtext": "文字内容",
    "link": "链接",
    "insertlink": "链接",
    "flash": "动画",
    "insertflash": "动画",
    "audio": "音频",
    "insertaudio": "音频",
    "signin": "签到",
    "sign": "签到",
    "evaluation": "评价",
    "insertevaluation": "评价",
    "workid-closed": "章节检测（已截止或未到作答时间）",
    "quiz-open": "随堂练习（正在进行，请尽快完成）",
    "captcha": "视频需要验证（请到学习通打开播放一下）",
    "task-open": "课堂任务（进行中）",
    "workid-empty": "章节检测（没有读到题目）",
}

_lock = threading.Lock()
_seen: set[str] = set()
_items: list[dict] = []            # confirmed: these need the user
_pending: dict[str, dict] = {}     # key -> {"item", "course", "point", "job"}: being looked at again
_notifier = None


def set_notifier(notifier) -> None:
    """The run's NotificationService (main.main sets it once notifications are configured)."""
    global _notifier
    _notifier = notifier


def reset() -> None:
    with _lock:
        _seen.clear()
        _items.clear()
        _pending.clear()


def kind_label(job: dict) -> str:
    if job.get("file_label"):           # documents: "PDF", "PPT 课件", "Word 文档" …
        return str(job["file_label"])
    kind = str(job.get("card_type") or job.get("type") or "").lower()
    if kind in KIND_LABELS:
        return KIND_LABELS[kind]
    for key, label in KIND_LABELS.items():
        if key in kind:
            return label
    return f"其他内容（{kind}）" if kind and kind != "other" else "其他内容"


def _what(item: dict) -> str:
    return f"{item['kind']}「{item['name']}」" if item["name"] else item["kind"]


def _emit(item: dict, **flags) -> None:
    print(PREFIX + json.dumps({**item, **flags}, ensure_ascii=False), flush=True)


def report(course: dict, point: dict, job: dict, urgent: bool = False) -> None:
    """One task point that may need the user (once per task point per run). Not announced yet:
    the run looks again first (see the module text); ``urgent`` announces it right away."""
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
        _pending[key] = {"item": item, "course": course, "point": point, "job": job}
    if urgent:
        confirm(key)
        return
    logger.info(f"可能需要手动完成，正在确认：{_what(item)}（{item['course']} / {item['chapter']}）")
    _emit(item, checking=True)


def pending(course: dict | None = None, point: dict | None = None) -> dict[str, dict]:
    """What is being looked at again: key -> {"item", "course", "point", "job"} (for one chapter
    when ``course`` and ``point`` are given)."""
    with _lock:
        found = dict(_pending)
    if course is None:
        return found
    return {k: e for k, e in found.items()
            if e["course"].get("courseId") == course.get("courseId") and e["point"].get("id") == (point or {}).get("id")}


def confirm(key: str) -> None:
    """Still there after looking again: the user has to do it. Popup / push / summary."""
    with _lock:
        entry = _pending.pop(key, None)
        if entry is None:
            return
        _items.append(entry["item"])
    item = entry["item"]
    what = _what(item)
    logger.warning(f"需要手动完成：{what}（{item['course']} / {item['chapter']}），程序无法自动完成")
    _emit(item)
    if _notifier is not None:
        try:
            _notifier.send(f"chaoxing : 需要手动完成：{what}\n{item['course']} / {item['chapter']}")
        except Exception as exc:  # a push must never stop the run
            logger.debug(f"手动任务通知发送失败: {exc}")


def confirm_all() -> None:
    """End of the run: whatever was not looked at again is announced as it is."""
    for key in list(pending()):
        confirm(key)


def dismiss(key: str) -> None:
    """Gone after looking again (学习通 shows it finished, or the retry did it): no reminder."""
    with _lock:
        entry = _pending.pop(key, None)
    if entry is None:
        return
    item = entry["item"]
    logger.info(f"确认完毕，不需要手动处理：{_what(item)}")
    _emit(item, resolved=True)


def resolve(course: dict, name: str) -> None:
    """The task was done after all (e.g. a video that needed a captcha went through on a later try):
    take its reminder back, so the app removes it and closes its popup."""
    course_title, name = str(course.get("title", "")), str(name or "").strip()
    if not name:
        return
    with _lock:
        gone = [i for i in _items if i["course"] == course_title and i["name"] == name]
        for item in gone:
            _items.remove(item)
        for key, entry in list(_pending.items()):
            if entry["item"]["course"] == course_title and entry["item"]["name"] == name:
                gone.append(_pending.pop(key)["item"])
    for item in gone:
        logger.info(f"已自动完成，不再需要手动处理：{item['kind']}「{item['name']}」")
        print(PREFIX + json.dumps({**item, "resolved": True}, ensure_ascii=False), flush=True)


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
