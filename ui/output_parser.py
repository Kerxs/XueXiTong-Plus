# -*- coding: utf-8 -*-
"""Turn the worker's merged stdout/stderr stream into structured UI events.

The worker is the unchanged command line runner, so everything here is derived
from its existing output: loguru lines, tqdm progress bars, ``print`` output and
the ``__CX_VIDEO_PREVIEW__`` / ``__CX_WORK_PREVIEW__`` preview lines.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

VIDEO_PREVIEW_PREFIX = "__CX_VIDEO_PREVIEW__"
WORK_PREVIEW_PREFIX = "__CX_WORK_PREVIEW__"
MANUAL_TASK_PREFIX = "__CX_MANUAL_TASK__"   # api/manual.py

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
LOGURU_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} (?P<clock>\d{2}:\d{2}:\d{2})\.\d{3})\s*\|\s*"
    r"(?P<level>[A-Z]+)\s*\|\s*(?P<source>\S+)\s+-\s(?P<message>.*)$"
)
TQDM_RE = re.compile(r"^(?P<name>.+?):\s*(?P<percent>\d{1,3})%\|.*\|\s*(?P<done>[^\s/]+)/(?P<total>\S+)\s*$")
COURSE_RE = re.compile(r"^ID:\s*(?P<course_id>\S+)\s+班级ID:\s*(?P<clazz_id>\S+)\s+课程名:\s*(?P<title>.*)$")
COURSE_PROMPT = "请输入想要学习的课程列表"
YES_NO_RE = re.compile(r"\(Y/n\)\s*:?\s*$", re.IGNORECASE)

LEVELS = ("TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")

# Markers already logged by main.py / api/base.py, mapped to dashboard fields.
ACTIVITY_MARKERS = {
    "开始学习课程:": "course",
    "正在读取课程章节:": "course",
    "当前章节:": "chapter",
    "开始任务:": "task_started",
    "任务完成:": "task_finished",
}


@dataclass
class LogEvent:
    level: str
    message: str
    time: str = ""


@dataclass
class ActivityEvent:
    kind: str  # course | chapter | task_started | task_finished
    value: str


@dataclass
class ProgressEvent:
    name: str
    percent: int
    done: str
    total: str


@dataclass
class VideoPreviewEvent:
    source: str
    title: str
    valid: bool = True
    sources: list = field(default_factory=list)   # every usable address, best first (source = sources[0])


@dataclass
class WorkPreviewEvent:
    phase: str
    data: dict[str, Any] = field(default_factory=dict)
    valid: bool = True


@dataclass
class ManualTaskEvent:
    """A task point the program does not do (document, reading, survey …): the user must."""

    course: str
    chapter: str
    kind: str
    name: str


@dataclass
class CourseListEvent:
    courses: list[dict[str, str]]


@dataclass
class PromptEvent:
    """The worker is blocked on ``input()`` with a yes/no question."""

    text: str


class StreamDecoder:
    """Bytes from the worker -> text.

    Incremental, so a character split across two reads is not garbled. Expects UTF-8;
    if the bytes are not valid UTF-8 (an older packaged worker writes the system code
    page, GBK on Chinese Windows) it switches to GB18030 for the rest of the stream.
    """

    def __init__(self) -> None:
        import codecs

        self._codecs = codecs
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.encoding = "utf-8"

    def decode(self, data: bytes, final: bool = False) -> str:
        if self.encoding == "utf-8":
            try:
                return self._decoder.decode(data, final)
            except UnicodeDecodeError:
                pending = self._decoder.getstate()[0]
                self.encoding = "gb18030"
                self._decoder = self._codecs.getincrementaldecoder("gb18030")("replace")
                data = pending + data
        return self._decoder.decode(data, final)


def clock_seconds(text: str) -> float | None:
    """Seconds from a progress counter: "MM:SS" / "HH:MM:SS" (the worker's video bars) or a number."""
    text = text.strip()
    try:
        if ":" in text:
            seconds = 0.0
            for part in text.split(":"):
                seconds = seconds * 60 + float(part)
            return seconds
        return float(text)
    except ValueError:
        return None


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _activity_from_message(message: str) -> ActivityEvent | None:
    for marker, kind in ACTIVITY_MARKERS.items():
        if marker in message:
            value = message.split(marker, 1)[1].strip()
            if kind == "task_started":
                # "开始任务: 名称, 总时长: 120s, 已进行: 0s"
                value = value.split(", 总时长:", 1)[0].strip()
            return ActivityEvent(kind, value)
    return None


def _parse_json(payload: str) -> dict[str, Any] | None:
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class OutputParser:
    """Stateful line splitter and classifier for the worker output stream."""

    def __init__(self) -> None:
        self._buffer = ""
        self._last_level = "INFO"
        self._courses: list[dict[str, str]] = []
        self._prompt_reported = ""

    def feed(self, chunk: str, final: bool = False) -> list[object]:
        pending = self._buffer + chunk
        parts = re.split(r"\r\n|\r|\n", pending)
        self._buffer = "" if final else parts.pop()
        events: list[object] = []
        for part in parts:
            events.extend(self.parse_line(part))

        # input() prompts without a trailing newline stay in the buffer.
        tail = strip_ansi(self._buffer).strip()
        if tail and YES_NO_RE.search(tail) and tail != self._prompt_reported:
            self._prompt_reported = tail
            events.append(PromptEvent(tail))
        return events

    def parse_line(self, raw: str) -> list[object]:
        line = strip_ansi(raw).strip()
        if not line:
            return []

        # A yes/no prompt has no newline, so the next output line is glued to it.
        if self._prompt_reported and line.startswith(self._prompt_reported):
            prompt = self._prompt_reported
            self._prompt_reported = ""
            rest = line[len(prompt):].strip()
            return [LogEvent("WARNING", prompt), *(self.parse_line(rest) if rest else [])]

        # tqdm redraws its bar with a leading carriage return and no line end, so a preview line printed
        # while a video is running arrives glued behind the bar ("...| 06:22/12:44__CX_...").
        # Split there, or the quiz / video event is lost as an ordinary log line.
        for prefix in (VIDEO_PREVIEW_PREFIX, WORK_PREVIEW_PREFIX, MANUAL_TASK_PREFIX):
            at = line.find(prefix)
            if at > 0:
                return [*self.parse_line(line[:at]), *self.parse_line(line[at:])]

        if line.startswith(MANUAL_TASK_PREFIX):
            data = _parse_json(line.removeprefix(MANUAL_TASK_PREFIX))
            if data is None:
                return []
            return [ManualTaskEvent(str(data.get("course", "")), str(data.get("chapter", "")),
                                    str(data.get("kind", "其他内容")), str(data.get("name", "")))]

        if line.startswith(VIDEO_PREVIEW_PREFIX):
            data = _parse_json(line.removeprefix(VIDEO_PREVIEW_PREFIX))
            if data is None:
                return [VideoPreviewEvent("", "", valid=False)]
            source = str(data.get("source", "") or "")
            sources = [str(s) for s in (data.get("sources") or []) if isinstance(s, str) and s]
            if source and source not in sources:
                sources.insert(0, source)
            return [VideoPreviewEvent(source or (sources[0] if sources else ""), str(data.get("title", "") or "学习通视频"),
                                      sources=sources)]

        if line.startswith(WORK_PREVIEW_PREFIX):
            data = _parse_json(line.removeprefix(WORK_PREVIEW_PREFIX))
            if data is None:
                return [WorkPreviewEvent("", valid=False)]
            return [WorkPreviewEvent(str(data.get("phase", "")), data)]

        progress = TQDM_RE.match(line)
        if progress:
            return [ProgressEvent(
                progress["name"].strip(),
                min(100, int(progress["percent"])),
                progress["done"],
                progress["total"],
            )]

        course = COURSE_RE.match(line)
        if course:
            self._courses.append({
                "courseId": course["course_id"],
                "clazzId": course["clazz_id"],
                "title": course["title"].strip(),
            })
            return []

        if COURSE_PROMPT in line:
            courses, self._courses = self._courses, []
            return [CourseListEvent(courses)]

        if set(line) <= {"*"} or line.startswith("*" * 10 + "课程列表") or line.startswith("提示: 同一 courseId"):
            return []

        match = LOGURU_RE.match(line)
        if match:
            level = match["level"] if match["level"] in LEVELS else "INFO"
            self._last_level = level
            message = match["message"]
            events: list[object] = [LogEvent(level, message, match["clock"])]
        else:
            # Continuation lines (tracebacks, multi-line messages) keep the last level.
            message = line
            events = [LogEvent(self._last_level, message)]

        activity = _activity_from_message(message)
        if activity:
            events.append(activity)
        return events
