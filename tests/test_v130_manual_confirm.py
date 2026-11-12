# -*- coding: utf-8 -*-
"""Reminders become popups only after the run looked again (1.3.0): "可能需要手动，正在确认" first;
the chapter is reloaded, the login renewed, what can be retried is retried; only what is still
there is announced."""
import contextlib
import io
import json
import unittest
from unittest import mock

import main
from api import manual
from api.base import StudyResult
from main import ChapterTask, JobProcessor
from ui.output_parser import ManualTaskEvent, OutputParser

COURSE = {"title": "高数", "courseId": "c", "clazzId": "z", "cpi": "i"}
POINT = {"id": "p1", "title": "9.1 阅读", "has_finished": False}


def events(text):
    return [json.loads(line[len(manual.PREFIX):]) for line in text.splitlines() if line.startswith(manual.PREFIX)]


class SettleTest(unittest.TestCase):
    def setUp(self):
        manual.reset()
        self.sent = []
        manual.set_notifier(mock.Mock(send=self.sent.append))
        self.cx = mock.Mock()
        self.cx.login.return_value = {"status": True, "msg": "ok"}
        self.task = ChapterTask(index=0, point=POINT, course=COURSE)
        config = {"speed": 1.0, "jobs": 1, "notopen_action": "retry", "retry_interval": 0, "use_cookies": "false"}
        self.processor = JobProcessor(self.cx, [self.task], config)

    def tearDown(self):
        manual.set_notifier(None)
        manual.reset()

    def settle(self, job_lists, job, process_job=None):
        """Report ``job`` and settle; get_job_list answers with job_lists in turn (the last one repeats)."""
        answers = list(job_lists)
        self.cx.get_job_list.side_effect = lambda c, p: ((answers.pop(0) if len(answers) > 1 else answers[0]), {})
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(main, "logger"), mock.patch.object(manual, "logger"), \
                mock.patch.object(main, "process_job", process_job or mock.Mock(return_value=StudyResult.SUCCESS)):
            manual.report(COURSE, POINT, job)
            self.processor._settle_manual(self.task)
        return events(out.getvalue())

    def test_gone_after_reload_no_reminder(self):
        job = {"type": "read", "jobid": "r", "name": "纲要"}
        found = self.settle([[]], job)
        self.assertEqual([(e.get("checking", False), e.get("resolved", False)) for e in found], [(True, False), (False, True)])
        self.assertEqual(manual.items(), [])
        self.assertEqual(self.sent, [])
        self.assertEqual(self.cx.login.call_count, 0)        # the reload was enough

    def test_gone_after_logging_in_again(self):
        job = {"type": "read", "jobid": "r", "name": "纲要"}
        found = self.settle([[job], []], job)
        self.assertEqual(self.cx.login.call_count, 1)
        self.assertTrue(found[-1].get("resolved"))
        self.assertEqual(manual.items(), [])

    def test_still_there_is_announced_once(self):
        job = {"type": "read", "jobid": "r", "name": "纲要"}
        found = self.settle([[job]], job)
        self.assertEqual([e.get("checking", False) for e in found], [True, False])
        self.assertFalse(found[-1].get("resolved", False))
        self.assertEqual([i["name"] for i in manual.items()], ["纲要"])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(manual.pending(), {})

    def test_what_the_program_can_do_is_tried_again(self):
        job = {"type": "document", "jobid": "d", "name": "教案"}
        retried = mock.Mock(return_value=StudyResult.SUCCESS)
        found = self.settle([[job], [job], []], job, retried)        # reload, after login, after the retry
        self.assertEqual(retried.call_count, 1)
        self.assertTrue(found[-1].get("resolved"))
        self.assertEqual(self.sent, [])

    def test_content_the_program_cannot_do_is_not_retried(self):
        job = {"type": "read", "jobid": "r", "name": "纲要"}
        retried = mock.Mock()
        self.settle([[job]], job, retried)
        retried.assert_not_called()

    def test_login_is_renewed_at_most_every_ten_minutes(self):
        job = {"type": "read", "jobid": "r", "name": "纲要"}
        self.settle([[job]], job)
        other = {"type": "read", "jobid": "r2", "name": "第二篇"}
        self.settle([[other]], other)
        self.assertEqual(self.cx.login.call_count, 1)
        self.assertEqual(len(manual.items()), 2)

    def test_a_failing_reload_still_announces(self):
        job = {"type": "read", "jobid": "r", "name": "纲要"}
        self.cx.get_job_list.side_effect = RuntimeError("HTTP 500")
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(main, "logger"), mock.patch.object(manual, "logger"):
            manual.report(COURSE, POINT, job)
            self.processor._settle_manual(self.task)
        self.assertEqual(len(manual.items()), 1)

    def test_urgent_reminders_skip_the_check(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(manual, "logger"):
            manual.report(COURSE, {"id": "active", "title": "课堂活动"},
                          {"type": "other", "card_type": "quiz-open", "jobid": "1", "name": "随堂练习"}, urgent=True)
        found = events(out.getvalue())
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0].get("checking", False))
        self.assertEqual(len(self.sent), 1)

    def test_nothing_stays_pending_at_the_end(self):
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(manual, "logger"):
            manual.report(COURSE, POINT, {"type": "read", "jobid": "r", "name": "纲要"})
            self.assertEqual(manual.summary(), "")
            manual.confirm_all()
        self.assertIn("有 1 项内容需要手动完成", manual.summary())


class AppTest(unittest.TestCase):
    def test_parser_reads_the_checking_flag(self):
        line = manual.PREFIX + json.dumps({"course": "c", "chapter": "1", "kind": "阅读", "name": "n", "checking": True})
        (event,) = OutputParser().feed(line + "\n")
        self.assertIsInstance(event, ManualTaskEvent)
        self.assertTrue(event.checking)
        self.assertFalse(event.resolved)

    def test_checking_is_not_listed_and_opens_no_popup(self):
        from ui.controller import AppController

        me = mock.Mock()
        me._manual_tasks = []
        AppController._on_manual_task(me, ManualTaskEvent("c", "1", "阅读", "纲要", checking=True))
        self.assertEqual(me._manual_tasks, [])
        me.manualPopupRequested.emit.assert_not_called()
        me.manualTasksChanged.emit.assert_not_called()
        self.assertIn("正在确认中", me.toast.emit.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
