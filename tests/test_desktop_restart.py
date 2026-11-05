# -*- coding: utf-8 -*-
"""Desktop stability: restart the task after an unexpected exit or a hang; never after a deliberate stop."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


class DesktopRestartTest(unittest.TestCase):
    def setUp(self):
        from PySide6.QtCore import QCoreApplication, QSettings
        import ui.controller as ctl

        self.mod = ctl
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        self.patches = [mock.patch.object(ctl, "DATA_DIR", data), mock.patch.object(ctl, "CONFIG_PATH", data / "config.ini")]
        for p in self.patches:
            p.start()
        QCoreApplication.setOrganizationName("ChaoxingDesktopRestartTest")
        QSettings().clear()
        self.ctl = ctl.AppController()
        self.logs = []
        self.ctl._log = lambda level, message, *a: self.logs.append((level, message))
        self.ctl._launched_at = time.monotonic()

    def tearDown(self):
        self.ctl._restart_pending = False
        self.ctl.shutdown()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _finish(self, code, stopping=False):
        self.ctl._process = None
        self.ctl._stopping = stopping
        self.ctl._on_finished(code, None)

    def _state(self):
        return self.ctl.property("status"), self.ctl.property("running")

    def test_unexpected_exit_restarts(self):
        self._finish(1)
        self.assertTrue(self.ctl._restart_pending)
        self.assertEqual(self._state(), ("即将重新开始", True))     # 停止 stays available
        self.assertEqual(self.ctl._restarts, 1)
        self.assertTrue(any("自动重新开始（第 1/3 次）" in m for _, m in self.logs))

    def test_crash_code_restarts_too(self):
        self._finish(-1073741819)   # 0xC0000005 access violation
        self.assertTrue(self.ctl._restart_pending)

    def test_deliberate_stop_is_not_restarted(self):
        self._finish(self.mod.EXIT_STOPPED)
        self.assertFalse(self.ctl._restart_pending)
        self.assertEqual(self._state(), ("已退出", False))
        self.assertIn(("ERROR", "任务已停止，原因见上方日志。"), self.logs)

    def test_user_stop_and_success_are_not_restarted(self):
        self._finish(62097, stopping=True)
        self.assertFalse(self.ctl._restart_pending)
        self._finish(0)
        self.assertFalse(self.ctl._restart_pending)
        self.assertEqual(self.ctl.property("status"), "已完成")

    def test_gives_up_after_three(self):
        for _ in range(3):
            self._finish(1)
            self.ctl._restart_pending = False
        self._finish(1)
        self.assertFalse(self.ctl._restart_pending)
        self.assertEqual(self._state(), ("已退出", False))
        self.assertTrue(any("连续 3 次意外退出" in m for _, m in self.logs))

    def test_count_starts_over_after_a_long_good_stretch(self):
        self.ctl._restarts = 3
        self.ctl._launched_at = time.monotonic() - self.mod.RESTART_RESET_SECONDS - 1
        self._finish(1)
        self.assertTrue(self.ctl._restart_pending)
        self.assertEqual(self.ctl._restarts, 1)

    def test_stop_cancels_a_pending_restart(self):
        self._finish(1)
        self.ctl.stopRun()
        self.assertFalse(self.ctl._restart_pending)
        self.assertEqual(self._state(), ("已停止", False))
        self.ctl._restart()                  # the timer firing later does nothing
        self.assertIsNone(self.ctl._process)

    def test_hang_check(self):
        proc = mock.Mock()
        self.ctl._process = proc
        self.ctl._last_output = time.monotonic() - self.mod.HANG_SECONDS - 5
        self.ctl._waiting_input = True       # waiting for the user is not a hang
        self.ctl._check_hang()
        proc.kill.assert_not_called()
        self.ctl._waiting_input = False
        self.ctl._paused = True              # nor is a pause
        self.ctl._check_hang()
        proc.kill.assert_not_called()
        self.ctl._paused = False
        self.ctl._check_hang()
        proc.kill.assert_called_once()
        self.assertTrue(self.ctl._hung)
        self.ctl._process = None

    def test_restarted_worker_gets_the_same_answers(self):
        from ui.output_parser import CourseListEvent, PromptEvent

        written = []
        self.ctl._write_stdin = written.append
        asked = []
        self.ctl.courseSelectionRequested.connect(lambda c: asked.append(c))
        self.ctl._handle_event(CourseListEvent([{"id": "1", "title": "a"}]))
        self.assertEqual((written, len(asked)), ([], 1))       # first run: the user is asked
        self.ctl.submitCourses(["1", "2"])
        self.ctl.answerPrompt(True)
        written.clear()
        self.ctl._handle_event(CourseListEvent([{"id": "1", "title": "a"}]))
        self.ctl._handle_event(PromptEvent("继续？"))
        self.assertEqual(written, ["1,2", "y"])                  # after a restart: answered again
        self.assertEqual(len(asked), 1)


class KeepAwakeTest(unittest.TestCase):
    def test_hold_and_release(self):
        from ui import keepawake

        with mock.patch.object(keepawake, "_set", return_value=True) as set_:
            self.assertTrue(keepawake.hold())
            self.assertEqual(set_.call_args.args[0], keepawake.ES_CONTINUOUS | keepawake.ES_SYSTEM_REQUIRED)
            keepawake.release()
            self.assertEqual(set_.call_args.args[0], keepawake.ES_CONTINUOUS)
            self.assertFalse(keepawake.held())


class NetworkWaitNoteTest(unittest.TestCase):
    def test_a_line_every_few_minutes(self):
        from api import net

        clock = {"t": 0.0}
        checks = iter([False] + [False] * 40 + [True])
        notes = []
        with mock.patch.object(net.time, "monotonic", lambda: clock["t"]), \
                mock.patch.object(net.logger, "warning", lambda m, *a: notes.append(m)), \
                mock.patch.object(net.pause, "wait_if_paused", lambda: 0.0):
            def sleep(s):
                clock["t"] += s
            net.wait_for_network(sleep=sleep, check=lambda: next(checks))
        self.assertTrue(any("仍在等待网络恢复" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
