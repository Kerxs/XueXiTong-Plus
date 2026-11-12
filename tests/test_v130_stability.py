# -*- coding: utf-8 -*-
"""1.3.0 stage 1: result lines for every video ending, one end report + read-only confirmation,
chapters that are not open wait for the ones before them, popups that close themselves, log privacy."""
import json
import tempfile
import time as real_time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import main
from api import manual
from api.answer import CacheDAO
from api.base import Chaoxing, StudyResult, _mask_name
from api.exceptions import CaptchaBlocked
from main import ChapterResult, ChapterTask, JobProcessor
from ui.output_parser import ActivityEvent, ManualTaskEvent, OutputParser


def run_video(progress, card=lambda: False, duration=100, start=0):
    """study_video with a fake clock. Returns (result, reports, card reads, log lines)."""
    clock = {"t": 1000.0}
    reports, cards, lines = [], [], []
    cx = Chaoxing.__new__(Chaoxing)
    cx._refresh_video_status = lambda *a, **k: {"dtoken": "d", "duration": duration}
    cx._close_pbar_safe = lambda pbar: None

    def log(_s, _c, _j, _ji, _d, dur, playing, _type, headers=None, _isdrag=3):
        reports.append((playing, _isdrag, clock["t"]))
        return progress(reports, dur)

    def card_passed(_course, _job):
        cards.append(clock["t"])
        return card()

    cx.video_progress_log = log
    cx._card_passed = card_passed
    fake = SimpleNamespace(**{k: getattr(real_time, k) for k in dir(real_time) if not k.startswith("_")})
    fake.time = lambda: clock["t"]
    fake.sleep = lambda s: clock.__setitem__("t", clock["t"] + max(s, 1.0))
    job = {"name": "1.1 视频", "jobid": "j", "rt": "1", "otherinfo": "", "playTime": start * 1000}
    with mock.patch("api.base.time", fake), mock.patch("api.base.random.uniform", lambda a, b: 85), \
            mock.patch("api.base.pause.wait_if_paused", lambda: 0.0), mock.patch("api.base.tqdm"), \
            mock.patch("api.base.logger") as logger:
        try:
            result = cx.study_video({"title": "c"}, job, {}, _speed=1.0)
        except CaptchaBlocked:
            result = "captcha"
        for call in logger.info.call_args_list + logger.warning.call_args_list:
            lines.append(call.args[0].format(*call.args[1:]) if len(call.args) > 1 else call.args[0])
    return result, reports, cards, lines


def result_lines(lines):
    return [line for line in lines if line.startswith(("任务完成:", "任务待确认:", "任务未完成:"))]


class ResultLineTest(unittest.TestCase):
    """The progress row stayed "进行中" because four endings wrote no "任务完成" line."""

    def test_watched_and_confirmed(self):
        result, _, _, lines = run_video(lambda r, dur: (r[-1][0] >= dur, 200))
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(result_lines(lines), ["任务完成: 1.1 视频"])

    def test_confirmed_from_the_recorded_progress(self):
        _, _, _, lines = run_video(lambda r, dur: (True, 200), start=100)
        self.assertEqual(result_lines(lines), ["任务完成: 1.1 视频"])

    def test_error(self):
        result, _, _, lines = run_video(lambda r, dur: (False, 500))
        self.assertEqual(result, StudyResult.ERROR)
        self.assertEqual(result_lines(lines), ["任务未完成: 1.1 视频"])

    def test_captcha_in_the_middle_still_ends_the_row(self):
        def progress(reports, dur):
            if len(reports) == 2:
                raise CaptchaBlocked("1.1 视频")
            return False, 200

        result, _, _, lines = run_video(progress)
        self.assertEqual(result, "captcha")                       # the chapter is started over
        self.assertEqual(result_lines(lines), ["任务未完成: 1.1 视频"])

    def test_never_confirmed_is_pending_not_failed(self):
        result, _, _, lines = run_video(lambda r, dur: (False, 200))
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(result_lines(lines), ["任务待确认: 1.1 视频"])


class EndConfirmationTest(unittest.TestCase):
    """60 of the 65 captchas in the logs came right after the third "watched it all" report."""

    def test_at_most_two_end_reports_twenty_seconds_apart(self):
        _, reports, cards, _ = run_video(lambda r, dur: (False, 200))
        ends = [t for pos, drag, t in reports if drag == 4]
        self.assertEqual(len(ends), 2)
        self.assertGreaterEqual(ends[1] - ends[0], 20)
        self.assertEqual(len(cards), 4)                           # 3 looks in between, 1 after

    def test_card_confirms_without_another_report(self):
        looks = []

        def card():
            looks.append(1)
            return len(looks) == 2

        result, reports, _, lines = run_video(lambda r, dur: (False, 200), card)
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(len([1 for _, drag, _ in reports if drag == 4]), 1)
        self.assertEqual(result_lines(lines), ["任务完成: 1.1 视频"])

    def test_captcha_on_the_end_report_does_not_restart_the_chapter(self):
        def progress(reports, dur):
            if reports[-1][1] == 4:
                raise CaptchaBlocked("1.1 视频")
            return False, 200

        result, reports, _, lines = run_video(progress)
        self.assertEqual(result, StudyResult.SUCCESS)             # not raised: nothing is watched again
        self.assertEqual(len([1 for _, drag, _ in reports if drag == 4]), 1)
        self.assertEqual(result_lines(lines), ["任务待确认: 1.1 视频"])

    def test_recorded_end_looks_at_the_card_before_reporting(self):
        result, reports, cards, _ = run_video(lambda r, dur: (False, 200), card=lambda: True, start=100)
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual([drag for _, drag, _ in reports], [3])   # no end report needed


def point(pid, locked=False, finished=False):
    return {"id": pid, "title": f"第{pid}章", "has_finished": finished, "need_unlock": locked}


class SchedulerTest(unittest.TestCase):
    COURSE = {"title": "闯关课", "courseId": "c", "clazzId": "z", "cpi": "i"}

    def _run(self, points, outcome, fresh=None, config=None, course2=None):
        cx = mock.Mock()
        state = {"points": fresh if fresh is not None else points}
        cx.get_course_point.side_effect = lambda *a: {"points": state["points"]}
        tasks = [ChapterTask(index=i, point=p, course=self.COURSE) for i, p in enumerate(points)]
        if course2:
            tasks += [ChapterTask(index=i, point=p, course=course2[0]) for i, p in enumerate(course2[1])]
        p = JobProcessor(cx, tasks, {"speed": 1.0, "jobs": 3, "notopen_action": "retry", "retry_interval": 0,
                                     **(config or {})})
        order, running, peak = [], set(), []

        def chapter(_cx, course, pt, _speed):
            running.add((course["courseId"], pt["id"]))
            peak.append(len(running))
            try:
                return outcome(course, pt, order, state)
            finally:
                order.append(pt["id"])
                running.discard((course["courseId"], pt["id"]))

        with mock.patch.object(main, "process_chapter", chapter), mock.patch.object(main.logger, "warning") as warn, \
                mock.patch.object(main.logger, "error") as err:
            p.run()
        # Only this scheduler's own lines: threads left by other tests log through the same logger.
        closed = [c for c in err.call_args_list if "章节未开启" in str(c)]
        return order, max(peak), warn, closed

    def test_locked_chapters_wait_for_the_one_before(self):
        pts = [point("1"), point("2", locked=True), point("3", locked=True)]

        def outcome(course, pt, order, state):
            # 学习通 opens the next chapter when this one is done
            nxt = {"1": "2", "2": "3"}.get(pt["id"])
            state["points"] = [point(p["id"], locked=p["id"] not in order + [pt["id"], nxt]) for p in pts]
            return ChapterResult.SUCCESS

        order, peak, warn, err = self._run(pts, outcome)
        self.assertEqual(order, ["1", "2", "3"])
        self.assertEqual(peak, 1)                 # three workers, one chapter open at a time
        self.assertEqual(err, [])

    def test_open_chapters_still_run_together(self):
        seen = []

        def outcome(course, pt, order, state):
            seen.append(pt["id"])
            real_time.sleep(0.05)
            return ChapterResult.SUCCESS

        order, peak, _, _ = self._run([point("1"), point("2"), point("3")], outcome)
        self.assertEqual(sorted(order), ["1", "2", "3"])
        self.assertGreaterEqual(peak, 2)

    def test_a_chapter_that_stays_closed_is_reported_once_for_all_after_it(self):
        pts = [point("1"), point("2", locked=True), point("3", locked=True), point("4", locked=True)]

        def outcome(course, pt, order, state):
            return ChapterResult.SUCCESS if pt["id"] == "1" else ChapterResult.NOT_OPEN

        order, _, warn, err = self._run(pts, outcome)
        self.assertEqual(set(order), {"1", "2"})                 # 3 and 4 are never tried
        text = " ".join(str(c) for c in warn.call_args_list)
        self.assertIn("本次不再逐个尝试", text)
        self.assertEqual(len(err), 1)                       # one "章节未开启" error, not three

    def test_not_open_while_earlier_chapters_run_is_not_a_try(self):
        pts = [point("1"), point("2")]                            # the list does not show 2 as locked
        tries = []

        def outcome(course, pt, order, state):
            if pt["id"] == "1":
                real_time.sleep(0.2)
                return ChapterResult.SUCCESS
            tries.append(1)
            return ChapterResult.SUCCESS if "1" in order else ChapterResult.NOT_OPEN

        order, _, _, err = self._run(pts, outcome)
        self.assertEqual(len(tries), 2)                           # once too early, once after chapter 1
        self.assertEqual(err, [])

    def test_another_course_is_not_held_back(self):
        other = ({"title": "另一门", "courseId": "d", "clazzId": "y", "cpi": "i"}, [point("9")])
        order, _, _, _ = self._run([point("1"), point("2", locked=True)],
                                   lambda course, pt, order, state: ChapterResult.SUCCESS, course2=other)
        self.assertEqual(sorted(order), ["1", "2", "9"])


class ReloginNetworkTest(unittest.TestCase):
    def test_a_dropped_connection_waits_and_logs_in_again(self):
        import requests

        cx = mock.Mock()
        cx.login.side_effect = [requests.ConnectionError("reset"), {"status": True, "msg": "ok"}]
        p = JobProcessor(cx, [], {"speed": 1.0, "jobs": 1, "notopen_action": "retry"})
        with mock.patch.object(main.net, "wait_for_network") as wait, mock.patch.object(main.time, "sleep"):
            self.assertEqual(p._relogin(force=True), "")
        wait.assert_called_once()
        self.assertEqual(cx.login.call_count, 2)

    def test_a_real_login_error_is_still_reported(self):
        cx = mock.Mock()
        cx.login.side_effect = ValueError("bad page")
        p = JobProcessor(cx, [], {"speed": 1.0, "jobs": 1, "notopen_action": "retry"})
        self.assertIn("ValueError", p._relogin(force=True))


class ParserAndModelTest(unittest.TestCase):
    def test_result_lines(self):
        parser = OutputParser()
        kinds = {}
        for text in ("任务完成: a.mp4", "任务待确认: b.mp4", "任务未完成: c.mp4"):
            for event in parser.feed(f"2026-11-10 10:00:00.000 | INFO     | api.base:study_video:1 - {text}\n"):
                if isinstance(event, ActivityEvent):
                    kinds[event.value] = event.kind
        self.assertEqual(kinds, {"a.mp4": "task_finished", "b.mp4": "task_pending", "c.mp4": "task_failed"})

    def test_manual_task_taken_back(self):
        events = OutputParser().feed('__CX_MANUAL_TASK__' + json.dumps(
            {"course": "c", "chapter": "1", "kind": "视频需要验证", "name": "a.mp4", "resolved": True}) + "\n")
        self.assertEqual(events, [ManualTaskEvent("c", "1", "视频需要验证", "a.mp4", True)])

    def test_task_model_states(self):
        from ui.models import TaskModel

        model = TaskModel()

        def row(name):
            item = model._items[model._find(name)]
            return item["state"], item["detail"], item["percent"]

        model.start("a.mp4")
        model.upsert("a.mp4", percent=100, detail="06:46 / 06:46")
        model.start("a.mp4")                                     # the chapter is tried again …
        self.assertEqual(row("a.mp4"), ("running", "进行中", 0))
        model.finish("a.mp4", "done")                            # … and 学习通 says it is done already
        self.assertEqual(row("a.mp4"), ("done", "已完成", 100))
        model.upsert("a.mp4", percent=97, detail="06:30 / 06:46")   # the bar's last redraw arrives late
        self.assertEqual(row("a.mp4"), ("done", "已完成", 100))
        model.start("b.mp4")
        model.finish("b.mp4", "pending")
        self.assertEqual(row("b.mp4")[:2], ("pending", "待确认"))
        model.start("c.mp4")
        model.finish_running()
        self.assertEqual(row("c.mp4")[:2], ("stopped", "已停止"))


class ManualResolveTest(unittest.TestCase):
    def test_reminder_is_taken_back(self):
        manual.reset()
        course, pt = {"title": "课", "courseId": "c"}, {"id": "p", "title": "1.1"}
        with mock.patch.object(manual, "print") as out, mock.patch.object(manual.logger, "warning"), \
                mock.patch.object(manual.logger, "info"):
            manual.report(course, pt, {"type": "other", "card_type": "captcha", "jobid": "a.mp4", "name": "a.mp4"})
            manual.resolve(course, "other.mp4")                  # not reported: nothing happens
            self.assertEqual(out.call_count, 1)
            manual.resolve(course, "a.mp4")
        self.assertTrue(json.loads(out.call_args.args[0].removeprefix(manual.PREFIX))["resolved"])
        self.assertEqual(manual.items(), [])


class LogPrivacyTest(unittest.TestCase):
    def test_name_is_masked(self):
        self.assertEqual(_mask_name("张三丰"), "张**")
        self.assertEqual(_mask_name("李"), "李*")
        self.assertEqual(_mask_name(""), "")

    def test_log_file_is_not_trace_and_old_files_are_removed(self):
        source = Path("api/logger.py").read_text(encoding="utf-8")
        self.assertIn("retention=_expired_logs", source)
        self.assertIn('else "DEBUG"', source)

    def test_logs_are_kept_thirty_days_and_never_more_than_the_cap(self):
        import os
        import time

        from api import logger as log

        self.assertEqual((log.LOG_DAYS, log.LOG_FILES_MAX), (30, 30))
        with tempfile.TemporaryDirectory() as tmp:
            def make(name, days_old):
                path = os.path.join(tmp, name)
                Path(path).write_text("x", encoding="utf-8")
                stamp = time.time() - days_old * 86400
                os.utime(path, (stamp, stamp))
                return path

            recent = [make(f"chaoxing.{n}.log", n) for n in range(1, 29)]     # 1 … 28 days old
            old = [make("chaoxing.old1.log", 31), make("chaoxing.old2.log", 200)]
            log._expired_logs(recent + old)
            self.assertTrue(all(os.path.exists(p) for p in recent))
            self.assertFalse(any(os.path.exists(p) for p in old))
            many = [make(f"chaoxing.m{n}.log", 0.01 * n) for n in range(40)]  # 40 files from today
            log._expired_logs(many + recent)
            left = [p for p in many + recent if os.path.exists(p)]
            self.assertEqual(len(left), log.LOG_FILES_MAX)
            self.assertTrue(all(os.path.exists(p) for p in many[:30]))        # the newest stay

    def test_cache_is_parsed_once_until_the_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            dao = CacheDAO(str(Path(tmp) / "cache.json"))
            dao.add_cache("题目", "答案")
            with mock.patch.object(CacheDAO, "_read_cache_file", wraps=dao._read_cache_file) as read:
                for _ in range(5):
                    self.assertEqual(CacheDAO(str(Path(tmp) / "cache.json")).get_cache("题目"), "答案")
                self.assertLessEqual(read.call_count, 1)
            dao.add_cache("新题", "乙")
            self.assertEqual(CacheDAO(str(Path(tmp) / "cache.json")).get_cache("新题"), "乙")


if __name__ == "__main__":
    unittest.main()
