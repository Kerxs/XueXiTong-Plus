# -*- coding: utf-8 -*-
"""1.3.0 stage 2: several videos / quizzes at once (single view with a pager, grid, off), and a
progress report that fails for a moment no longer ends the video."""
import tempfile
import time as real_time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from api.base import Chaoxing, StudyResult
from ui.output_parser import ActivityEvent, ProgressEvent, VideoPreviewEvent, WorkPreviewEvent


def video(n):
    url = f"https://s1.cldisk.com/v{n}.mp4"
    return VideoPreviewEvent(url, f"{n}.mp4", sources=[url])


def quiz(n, phase="filled"):
    return WorkPreviewEvent(phase, {"phase": phase, "title": f"检测{n}", "cover_rate": 50, "submit": True, "questions": [
        {"index": 1, "type": "single", "title": f"题{n}", "options": "A 甲\nB 乙", "answer": "A", "source": "cover"}]})


class PreviewListTest(unittest.TestCase):
    def setUp(self):
        from PySide6.QtCore import QCoreApplication, QSettings
        import ui.controller as ctl

        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        self.patches = [mock.patch.object(ctl, "DATA_DIR", data), mock.patch.object(ctl, "CONFIG_PATH", data / "config.ini"),
                        mock.patch.object(ctl, "PREVIEW_REFRESH_FILE", data / "preview_refresh.flag")]
        for p in self.patches:
            p.start()
        QCoreApplication.setOrganizationName("ChaoxingDesktopPreviewListTest")
        QSettings().clear()
        self.ctl = ctl.AppController()
        self.ctl._process = mock.Mock()

    def tearDown(self):
        self.ctl._process = None
        self.ctl.shutdown()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_two_videos_and_the_pager(self):
        c = self.ctl
        c._handle_event(video(1))
        c._handle_event(video(2))
        self.assertEqual([v["title"] for v in c.videos], ["1.mp4", "2.mp4"])
        self.assertEqual((c.videoTitle, c.videoIndex), ("1.mp4", 0))     # the one on screen stays
        c.stepVideo(1)
        self.assertEqual((c.videoTitle, c.videoIndex), ("2.mp4", 1))
        c.stepVideo(1)
        self.assertEqual(c.videoTitle, "1.mp4")                          # wraps around

    def test_each_video_keeps_its_own_position(self):
        c = self.ctl
        c._handle_event(video(1))
        c._handle_event(video(2))
        c._handle_event(ProgressEvent("2.mp4", 50, "05:00", "10:00"))
        self.assertEqual(c.videoPosition, -1.0)                          # not the one on screen
        self.assertTrue(c.videoPageFor("2.mp4").endswith("#t=300&r=1"))
        c.stepVideo(1)
        self.assertEqual(c.videoPosition, 300.0)

    def test_a_finished_video_leaves_and_the_next_one_shows(self):
        c = self.ctl
        for n in (1, 2, 3):
            c._handle_event(ActivityEvent("task_started", f"{n}.mp4"))
            c._handle_event(video(n))
        c._handle_event(ActivityEvent("task_finished", "2.mp4"))        # not on screen: nothing moves
        self.assertEqual((c.videoCount, c.videoTitle, c.videoActive), (2, "1.mp4", True))
        c._handle_event(ActivityEvent("task_pending", "1.mp4"))         # the one on screen ends
        self.assertEqual((c.videoCount, c.videoTitle, c.videoActive), (1, "3.mp4", True))
        c._handle_event(ActivityEvent("task_failed", "3.mp4"))
        self.assertEqual((c.videoCount, c.videoActive), (0, False))

    def test_quizzes_page_and_results_go_to_their_own_quiz(self):
        c = self.ctl
        c._handle_event(quiz(1, "questions"))
        c._handle_event(quiz(2, "questions"))                            # two chapters at once
        self.assertEqual((c.workCount, c.workIndex, c.work["title"]), (2, 1, "检测2"))
        c._handle_event(quiz(1))
        c._handle_event(WorkPreviewEvent("submitted", {"phase": "submitted", "title": "检测1", "msg": "ok"}))
        self.assertEqual(c.workStatus, "正在查找答案")                    # quiz 2 is on screen, unchanged
        c.stepWork(-1)
        self.assertEqual((c.work["title"], c.workStatus), ("检测1", "已提交"))
        c._handle_event(quiz(3, "questions"))                            # the user just picked one: no jump
        self.assertEqual(c.work["title"], "检测1")
        self.assertEqual(c.workCount, 3)

    def test_only_the_last_quizzes_are_kept(self):
        for n in range(1, 10):
            self.ctl._handle_event(quiz(n))
            self.ctl._handle_event(WorkPreviewEvent("submitted", {"phase": "submitted", "title": f"检测{n}"}))
        self.assertEqual(self.ctl.workCount, self.ctl.WORKS_KEPT)
        self.assertEqual(self.ctl.work["title"], "检测9")

    def test_off_registers_nothing_but_still_counts(self):
        c = self.ctl
        c._handle_event(video(1))
        c.previewMode = "off"
        self.assertEqual((c.videoCount, c.workCount), (0, 0))
        with mock.patch.object(c._video_proxy, "register") as register:
            c._handle_event(video(2))
            c._handle_event(quiz(1))
            c._handle_event(WorkPreviewEvent("submitted", {"phase": "submitted", "title": "检测1"}))
        register.assert_not_called()
        self.assertEqual((c.videoCount, c.workCount), (0, 0))
        self.assertEqual(c._completed, 1)
        c.previewMode = "grid"
        self.assertEqual(c.previewMode, "grid")
        c.previewMode = "nonsense"
        self.assertEqual(c.previewMode, "grid")


class AutoSaveTest(PreviewListTest):
    """Settings are written a moment after the last change; there is no 保存 button."""

    def test_a_change_is_saved_by_itself(self):
        import ui.controller as ctl
        from PySide6.QtTest import QTest

        c = self.ctl
        c._autosave.setInterval(30)
        logs = []
        c._log = lambda level, message, *a: logs.append(message)
        c.setAdvanced("common.auto_live", "false")
        c.username = "13800000000"
        self.assertTrue(c.dirty)
        QTest.qWait(200)
        self.assertFalse(c.dirty)
        text = ctl.CONFIG_PATH.read_text(encoding="utf-8")
        self.assertIn("auto_live = false", text)
        self.assertNotIn("13800000000", text)            # the account is stored encrypted, also when saved automatically
        self.assertEqual(logs, [])                        # no "配置已保存" line for every change

    def test_typing_is_one_save_and_closing_saves_what_is_left(self):
        from PySide6.QtTest import QTest
        from unittest import mock

        c = self.ctl
        c._autosave.setInterval(80)
        with mock.patch.object(type(c), "saveConfig", autospec=True, side_effect=type(c).saveConfig) as save:
            for text in ("1", "13", "138", "1380"):
                c.username = text
                QTest.qWait(10)
            QTest.qWait(250)
            self.assertEqual(save.call_count, 1)
            c.username = "13800"
            c.shutdown()                                  # closed before the delay ran out
            self.assertEqual(save.call_count, 2)
        self.assertFalse(c.dirty)


class ReportFailureTest(unittest.TestCase):
    """On a phone in the background a report often fails once; that used to restart the chapter."""

    def _run(self, states, online=True):
        clock = {"t": 1000.0}
        reports = []
        cx = Chaoxing.__new__(Chaoxing)
        cx._refresh_video_status = lambda *a, **k: {"dtoken": "d", "duration": 100}
        cx._close_pbar_safe = lambda pbar: None
        cx._card_passed = lambda *a: False

        def log(_s, _c, _j, _ji, _d, dur, playing, _type, headers=None, _isdrag=3):
            reports.append(playing)
            state = states[min(len(reports), len(states)) - 1]
            return (playing >= dur and state == 200), state

        cx.video_progress_log = log
        fake = SimpleNamespace(**{k: getattr(real_time, k) for k in dir(real_time) if not k.startswith("_")})
        fake.time = lambda: clock["t"]
        fake.sleep = lambda s: clock.__setitem__("t", clock["t"] + max(s, 1.0))
        waits = []
        job = {"name": "v", "jobid": "j", "rt": "1", "otherinfo": "", "playTime": 0}
        with mock.patch("api.base.time", fake), mock.patch("api.base.random.uniform", lambda a, b: 85), \
                mock.patch("api.base.pause.wait_if_paused", lambda: 0.0), mock.patch("api.base.tqdm"), \
                mock.patch("api.net.online", lambda *a, **k: online), \
                mock.patch("api.net.wait_for_network", lambda *a, **k: waits.append(1) or 5.0):
            result = cx.study_video({"title": "c"}, job, {}, _speed=1.0)
        return result, reports, waits

    def test_one_failed_report_is_tried_again(self):
        result, reports, _ = self._run([200, 0, 200])
        self.assertEqual(result, StudyResult.SUCCESS)

    def test_offline_waits_for_the_network_instead_of_failing(self):
        result, _, waits = self._run([200, 0, 0, 0, 0, 0, 200], online=False)
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(len(waits), 5)

    def test_keeps_failing_while_online_is_a_failure(self):
        result, reports, _ = self._run([200, 0])
        self.assertEqual(result, StudyResult.ERROR)
        self.assertEqual(len(reports), 1 + Chaoxing.REPORT_RETRIES)


if __name__ == "__main__":
    unittest.main()
