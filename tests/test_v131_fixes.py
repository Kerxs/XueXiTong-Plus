# -*- coding: utf-8 -*-
"""Fixes found through the statistics of the first week of 1.3.x: the 识别课程 timer crash, and a
chapter's failure being counted once per retry."""
import unittest
from unittest import mock

import main
from api.base import StudyResult
from main import ChapterResult, ChapterTask, JobProcessor


class CourseTimeoutTest(unittest.TestCase):
    def controller(self):
        from ui.controller import AppController
        return AppController.__new__(AppController)

    def test_a_finished_and_deleted_process_is_not_touched(self):
        c = self.controller()
        gone = mock.Mock()
        gone.state.side_effect = RuntimeError("Internal C++ object (PySide6.QtCore.QProcess) already deleted.")
        c._course_process = None                 # 识别课程 finished long ago
        c._course_timeout(gone)                  # no exception
        gone.state.assert_not_called()

    def test_a_deleted_process_still_registered_does_not_raise(self):
        c = self.controller()
        gone = mock.Mock()
        gone.state.side_effect = RuntimeError("already deleted")
        c._course_process = gone
        c._course_timeout(gone)

    def test_a_process_still_running_is_ended(self):
        from PySide6.QtCore import QProcess
        c = self.controller()
        running = mock.Mock()
        running.state.return_value = QProcess.ProcessState.Running
        c._course_process = running
        c._course_timeout(running)
        running.kill.assert_called_once()


class FailureCountTest(unittest.TestCase):
    def run_chapter(self, results):
        counted = []
        cx = mock.Mock()
        jobs = [{"type": "workid", "jobid": "w"}, {"type": "video", "jobid": "v"}]
        cx.get_job_list.return_value = (jobs, {})
        point = {"id": "p", "title": "1.1", "has_finished": False}
        with mock.patch.object(main, "process_job", side_effect=results), \
                mock.patch.object(main.telemetry, "count", side_effect=lambda k, n=1: counted.append(k)), \
                mock.patch.object(main, "logger"):
            outcome = main.process_chapter(cx, {"title": "c", "courseId": "1"}, point, 1.0)
        return outcome, counted, point

    def test_a_failed_attempt_is_a_retry_not_a_failure(self):
        outcome, counted, point = self.run_chapter([StudyResult.ERROR, StudyResult.SUCCESS])
        self.assertEqual(outcome, ChapterResult.ERROR)
        self.assertIn("workid.retry", counted)
        self.assertNotIn("workid.fail", counted)
        self.assertIn("video.ok", counted)
        self.assertEqual(point["_failed_kinds"], ["workid"])

    def test_given_up_chapter_counts_its_failure_once(self):
        counted = []
        task = ChapterTask(index=0, point={"id": "p", "title": "1.1", "_failed_kinds": ["workid"]},
                           course={"title": "c"})
        with mock.patch.object(main.telemetry, "count", side_effect=lambda k, n=1: counted.append(k)):
            JobProcessor._count_failed(task)
        self.assertEqual(counted, ["workid.fail"])

    def test_retry_is_an_allowed_statistics_name(self):
        from api import telemetry
        self.assertTrue(telemetry._KEY.match("workid.retry"))


if __name__ == "__main__":
    unittest.main()
