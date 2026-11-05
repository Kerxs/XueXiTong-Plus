# -*- coding: utf-8 -*-
"""A chapter that fails 5 times: log in again, read the chapter again, try 5 more times; then stop and say why."""
import unittest
from unittest import mock

import main
from main import ChapterResult, ChapterTask, JobProcessor, RunStopped


def make_processor(login_results):
    cx = mock.Mock()
    cx.login.side_effect = login_results
    cx.get_course_point.return_value = {"points": [{"id": "p1", "title": "1.1 新", "has_finished": False}]}
    course = {"title": "高等数学", "courseId": "c", "clazzId": "z", "cpi": "i"}
    task = ChapterTask(index=0, point={"id": "p1", "title": "1.1", "has_finished": False}, course=course)
    config = {"speed": 1.0, "jobs": 1, "notopen_action": "retry", "retry_interval": 0, "use_cookies": "false"}
    return JobProcessor(cx, [task], config), cx, task


class RetryReloginTest(unittest.TestCase):
    def _run(self, outcomes, login_results):
        processor, cx, task = make_processor(login_results)
        calls = []

        def chapter(_cx, _course, point, _speed):
            calls.append(point["title"])
            outcome = outcomes[len(calls) - 1] if len(calls) <= len(outcomes) else outcomes[-1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(main, "process_chapter", chapter), mock.patch.object(main.time, "sleep"):
            try:
                processor.run()
                stopped = None
            except RunStopped as e:
                stopped = str(e)
        return stopped, calls, cx, task

    def test_works_after_logging_in_again(self):
        outcomes = [ChapterResult.ERROR] * 5 + [ChapterResult.SUCCESS]
        stopped, calls, cx, task = self._run(outcomes, [{"status": True, "msg": "ok"}])
        self.assertIsNone(stopped)
        self.assertEqual(len(calls), 6)
        self.assertEqual(cx.login.call_count, 1)
        self.assertEqual(calls[-1], "1.1 新")          # the chapter was read again after the login
        self.assertTrue(task.relogged)

    def test_still_failing_after_login_stops_with_reason(self):
        outcomes = [ChapterResult.ERROR] * 4 + [RuntimeError("接口返回异常")]
        stopped, calls, cx, _ = self._run(outcomes, [{"status": True, "msg": "ok"}])
        self.assertEqual(len(calls), 10)
        self.assertEqual(cx.login.call_count, 1)
        self.assertIn("高等数学 - 1.1 新", stopped)
        self.assertIn("重新登录后又重试 5 次仍然失败", stopped)
        self.assertIn("RuntimeError: 接口返回异常", stopped)

    def test_login_failure_stops_with_its_reason(self):
        stopped, calls, cx, _ = self._run([ChapterResult.ERROR], [{"status": False, "msg": "密码错误"}])
        self.assertEqual(len(calls), 5)
        self.assertIn("重新登录失败：密码错误", stopped)

    def test_main_reports_the_stop_without_a_traceback(self):
        logged = []
        with mock.patch.object(main, "init_config", side_effect=RunStopped("章节“x”…已停止运行。")), \
                mock.patch.object(main.logger, "error", lambda msg, *a: logged.append(msg)):
            with self.assertRaises(SystemExit) as exit_:
                main.main()
        self.assertEqual(exit_.exception.code, 1)
        self.assertEqual(logged, ["章节“x”…已停止运行。"])


if __name__ == "__main__":
    unittest.main()
