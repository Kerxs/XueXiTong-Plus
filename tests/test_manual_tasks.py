# -*- coding: utf-8 -*-
"""Only video and 章节检测 are automated; other content is reported (push, or a popup without one)."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
from api import decode, manual
from api.base import StudyResult
from ui.output_parser import ManualTaskEvent, OutputParser


class DecodeTest(unittest.TestCase):
    def test_unknown_card_types_are_kept_not_dropped(self):
        cards = [
            {"type": "questionnaire", "job": True, "jobid": "q1", "property": {"title": "课程满意度调查"}},
            {"type": "insertbbs", "job": True, "jobid": "b1", "property": {"name": "第一章讨论"}},
            {"type": "document", "job": True, "jobid": "d1", "property": {"name": "第一章课件.pptx"}},
        ]
        jobs = decode._process_attachment_cards(cards)
        self.assertEqual([j["type"] for j in jobs], ["other", "other", "document"])
        self.assertEqual(jobs[0]["name"], "课程满意度调查")
        self.assertEqual(jobs[1]["card_type"], "insertbbs")
        self.assertEqual(jobs[2]["name"], "第一章课件.pptx")


class ReportTest(unittest.TestCase):
    def setUp(self):
        main.logger.remove()
        manual.reset()
        self.sent = []
        manual.set_notifier(mock.Mock(send=self.sent.append))

    def tearDown(self):
        manual.set_notifier(None)
        manual.reset()

    def test_non_automated_jobs_are_reported_once_and_not_retried(self):
        course, point = {"title": "大学物理", "courseId": "1"}, {"title": "1.2 刚体", "id": "p"}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for job in ({"type": "read", "jobid": "r", "title": "拓展阅读"},
                        {"type": "other", "card_type": "questionnaire", "jobid": "q", "name": "问卷"},
                        {"type": "read", "jobid": "r", "title": "拓展阅读"}):        # same one again
                self.assertEqual(main.process_job(None, course, job, {}, 1.0, point), StudyResult.SUCCESS)
        events = [json.loads(l[len(manual.PREFIX):]) for l in out.getvalue().splitlines() if l.startswith(manual.PREFIX)]
        self.assertEqual([e["kind"] for e in events], ["阅读", "问卷"])
        self.assertEqual(len(self.sent), 2)
        self.assertIn("需要手动完成：阅读「拓展阅读」", self.sent[0])
        self.assertIn("有 2 项内容需要手动完成", manual.summary())

    def test_video_and_quiz_still_automated(self):
        cx = mock.Mock()
        cx.study_video.return_value = StudyResult.SUCCESS
        cx.study_work.return_value = StudyResult.SUCCESS
        main.process_job(cx, {"title": "c"}, {"type": "video", "jobid": "v", "name": "v"}, {}, 1.0, {})
        main.process_job(cx, {"title": "c"}, {"type": "workid", "jobid": "w"}, {}, 1.0, {})
        cx.study_video.assert_called_once()
        cx.study_work.assert_called_once()
        self.assertEqual(manual.items(), [])

    def test_labels(self):
        self.assertEqual(manual.kind_label({"type": "document"}), "文档 / 课件")
        self.assertEqual(manual.kind_label({"type": "live"}), "直播")
        self.assertEqual(manual.kind_label({"type": "other", "card_type": "insertsurvey"}), "问卷")
        self.assertEqual(manual.kind_label({"type": "other", "card_type": "zzz"}), "其他内容（zzz）")


class ParserTest(unittest.TestCase):
    def test_event_line_and_glued_behind_progress_bar(self):
        payload = json.dumps({"course": "c", "chapter": "1.1", "kind": "阅读", "name": "n"}, ensure_ascii=False)
        events = OutputParser().feed("\r1.1 v.mp4:  50%|█████     | 00:20/00:40" + manual.PREFIX + payload + "\n")
        found = [e for e in events if isinstance(e, ManualTaskEvent)]
        self.assertEqual(found, [ManualTaskEvent("c", "1.1", "阅读", "n")])


class DesktopPopupTest(unittest.TestCase):
    """No push service -> popup in the window; with one -> a toast (the worker pushed already)."""

    def setUp(self):
        from PySide6.QtCore import QCoreApplication, QSettings
        import ui.controller as ctl

        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        self.patches = [mock.patch.object(ctl, "DATA_DIR", data), mock.patch.object(ctl, "CONFIG_PATH", data / "config.ini")]
        for p in self.patches:
            p.start()
        QCoreApplication.setOrganizationName("ChaoxingDesktopManualTest")
        QSettings().clear()
        self.ctl = ctl.AppController()

    def tearDown(self):
        self.ctl.shutdown()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_popup_without_push_and_toast_with_push(self):
        popups, toasts = [], []
        self.ctl.manualPopupRequested.connect(lambda: popups.append(1))
        self.ctl.toast.connect(lambda m, k: toasts.append(m))
        self.ctl._advanced["notification.provider"] = ""
        self.ctl._on_manual_task(ManualTaskEvent("c", "1.1", "阅读", "a"))
        self.ctl._on_manual_task(ManualTaskEvent("c", "1.1", "阅读", "a"))   # duplicate ignored
        self.assertEqual((len(popups), len(self.ctl.manualTasks)), (1, 1))
        self.ctl._advanced.update({"notification.provider": "ServerChan", "notification.url": "https://x/y.send"})
        self.ctl._on_manual_task(ManualTaskEvent("c", "1.2", "问卷", "b"))
        self.assertEqual(len(popups), 1)
        self.assertTrue(any("已推送" in t for t in toasts))


class AndroidBridgeEventTest(unittest.TestCase):
    def test_manual_task_reaches_the_phone_as_an_event(self):
        import importlib
        import sys
        import types

        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "android" / "app" / "src" / "main" / "python"))
        try:
            bridge = importlib.import_module("xxtplus_android")
        finally:
            sys.path.pop(0)
        fake = types.ModuleType("main")
        fake.main = lambda: print(manual.PREFIX + json.dumps({"course": "c", "chapter": "1.1", "kind": "问卷", "name": "调查"},
                                                             ensure_ascii=False), flush=True)
        events = []
        saved = sys.modules.get("main"), sys.stdout, sys.stderr, sys.argv[:]
        sys.modules["main"] = fake
        cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    bridge.run(str(Path(tmp) / "c.ini"), tmp, str(Path(tmp) / "p"),
                               mock.Mock(emit=lambda s: events.append(json.loads(s))))
                finally:
                    os.chdir(cwd)   # run() chdirs into tmp: leave it before the folder is removed
        finally:
            sys.modules["main"], sys.stdout, sys.stderr, sys.argv[:] = saved[0] or main, saved[1], saved[2], saved[3]
        task = next(e for e in events if e["type"] == "manualtask")
        self.assertEqual((task["kind"], task["name"]), ("问卷", "调查"))


if __name__ == "__main__":
    unittest.main()
