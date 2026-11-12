# -*- coding: utf-8 -*-
"""Watching a live-stream task point (直播): the watch time is reported once a minute, in real
time, until the stream's length is reached.

The task used to be handed straight to "需要手动完成", so a live stream was never watched. When it
is watched now it shows up like a video (开始任务 / progress / 任务完成), honours pause, and when
学习通 does not accept the reports it stops and reminds the user instead of pretending it worked.

Checked against two real replays (59 and 42 minutes): every saveTimePc answered @success and
学习通 showed both chapters as finished afterwards.
"""
import json
import os
import time
from urllib.parse import urlsplit
from enum import Enum

from tqdm import tqdm

from api import pause
from api.live import Live
from api.logger import logger

REPORT_EVERY = 59          # seconds between two watch-time reports, like the page
DEFAULT_MINUTES = 30       # when the stream does not state its length
MAX_FAILURES = 3           # reports that may fail in a row


class LiveResult(Enum):
    DONE = 0               # watched for the stream's length
    UNAVAILABLE = 1        # no status / the reports are not accepted: the user has to look
    STOPPED = 2


def live_minutes(status: dict) -> int:
    """The stream's length in minutes, rounded up (DEFAULT_MINUTES when it is not stated)."""
    try:
        seconds = float(((status.get("temp") or {}).get("data") or {}).get("duration") or 0)
    except (TypeError, ValueError, AttributeError):
        seconds = 0
    if seconds <= 0:
        logger.warning(f"无法获取直播总时长，按 {DEFAULT_MINUTES} 分钟处理")
        return DEFAULT_MINUTES
    return max(1, (int(seconds) + 59) // 60)


def preview_sources(status) -> list:
    """Addresses in the stream's status that the app's preview can play: mp4 files on 学习通's own
    hosts (a replay). A stream that is only offered as HLS (.m3u8) has none: the preview's <video>
    cannot play that."""
    found = []

    def walk(value, depth=0):
        if depth > 6:
            return
        if isinstance(value, dict):
            for item in value.values():
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value[:50]:
                walk(item, depth + 1)
        elif isinstance(value, str) and value.startswith(("http://", "https://")) and value not in found:
            try:
                parts = urlsplit(value)
            except ValueError:
                return
            host = (parts.hostname or "").lower()
            if parts.path.lower().endswith(".mp4") and host.endswith((".chaoxing.com", ".cldisk.com")):
                found.append(value)

    walk(status)
    return sorted(found, key=lambda url: not url.startswith("https://"))


def emit_preview(live, status) -> None:
    """Tell the app what to show for this stream (__CX_VIDEO_PREVIEW__): the replay when there is a
    playable address, otherwise a line saying that the stream is being watched without a picture."""
    if os.environ.get("CHAOXING_DESKTOP_PREVIEW") != "1":
        return
    try:
        sources = preview_sources(status)
        event = {"source": sources[0] if sources else "", "sources": sources, "title": live.name, "live": True}
        if not sources:
            event["message"] = "直播观看中（这场直播没有可预览的画面）"
        print("__CX_VIDEO_PREVIEW__" + json.dumps(event, ensure_ascii=False), flush=True)
    except Exception:  # noqa: BLE001 - the preview never gets in the way of the task
        pass


class LiveProcessor:
    @staticmethod
    def run_live(live: Live, speed: float = 1.0, passed=None, sleep=time.sleep) -> LiveResult:
        """Report the watch time minute by minute. ``passed``: a callable that says whether 学习通
        already shows the task point as finished (checked every few minutes: no need to go on then).
        ``speed`` is ignored: like videos, live streams are watched at 1x."""
        status = live.get_status()
        if not status:
            logger.warning(f"读不到直播「{live.name}」的状态（可能还没开始、已结束或没有回放）")
            return LiveResult.UNAVAILABLE
        minutes = live_minutes(status)
        total = minutes * 60
        live.started = True
        live.all_accepted = False
        logger.info(f"开始任务: {live.name}, 总时长: {total}s, 已进行: 0s")
        emit_preview(live, status)
        failures = 0
        refused = 0
        bar = None
        try:
            bar = tqdm(total=total, initial=0, desc=live.name, unit_scale=True,
                       bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}', leave=False)
            for minute in range(minutes):
                pause.wait_if_paused()
                if live.do_finish():
                    failures = 0
                else:
                    failures += 1
                    refused += 1
                    if failures >= MAX_FAILURES:
                        logger.warning(f"直播「{live.name}」的观看时长连续 {failures} 次没有提交成功，停止观看")
                        return LiveResult.UNAVAILABLE
                    logger.warning(f"直播观看时长提交失败，下一分钟再试（第 {failures} 次）")
                if passed is not None and minute % 5 == 4 and passed():
                    logger.info(f"学习通已显示直播「{live.name}」完成")
                    return LiveResult.DONE
                # one minute of watching, in small steps so the bar moves and a pause is noticed
                for second in range(REPORT_EVERY):
                    sleep(1)
                    pause.wait_if_paused()
                    bar.n = min(total, minute * 60 + second + 1)      # every second, like a video
                    bar.refresh()
            bar.n = total
            bar.refresh()
            live.all_accepted = refused == 0
        finally:
            if bar is not None:
                try:
                    bar.leave = False
                    bar.close()
                except Exception:  # noqa: BLE001
                    pass
        return LiveResult.DONE
