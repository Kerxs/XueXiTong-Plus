import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication, QEventLoop, QSettings, QTimer

app = QCoreApplication.instance() or QCoreApplication([])
HERE = Path(__file__).resolve().parent


def wait_for(cond, seconds=20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        loop = QEventLoop()
        QTimer.singleShot(50, loop.quit)
        loop.exec()
    return cond()


class WorkerListModeTestCase(unittest.TestCase):
    """worker.py --list-courses, with the Chaoxing client stubbed (no network)."""

    def _run(self, config_text, login_state=None, courses=None):
        import worker

        class FakeChaoxing:
            def __init__(self, account=None, **_):
                self.account = account

            def login(self, login_with_cookies=False):
                return login_state or {"status": True, "msg": ""}

            def get_course_list(self):
                return courses or []

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.ini"
            cfg.write_text(config_text, encoding="utf-8")
            out = io.StringIO()
            cwd = os.getcwd()
            try:
                with mock.patch("api.base.Chaoxing", FakeChaoxing), contextlib.redirect_stdout(out):
                    code = worker.list_courses(cfg, Path(tmp) / "data")
            finally:
                os.chdir(cwd)
        lines = [l for l in out.getvalue().splitlines() if l.startswith(worker.COURSES_PREFIX)]
        self.assertEqual(len(lines), 1, out.getvalue())
        return code, json.loads(lines[0][len(worker.COURSES_PREFIX):])

    def test_lists_courses(self):
        code, payload = self._run(
            "[common]\nusername = 13800000000\npassword = x\n",
            courses=[{"courseId": "1", "clazzId": "2", "cpi": "3", "title": "高等数学", "teacher": "赵", "desc": ""}])
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "courses": [
            {"courseId": "1", "clazzId": "2", "title": "高等数学", "teacher": "赵", "desc": ""}]})

    def test_login_failure_and_missing_account(self):
        code, payload = self._run("[common]\nusername = 1\npassword = x\n", login_state={"status": False, "msg": "密码错误"})
        self.assertEqual((code, payload["ok"]), (1, False))
        self.assertIn("密码错误", payload["error"])
        code, payload = self._run("[common]\nusername = xxx\npassword = xxx\n")
        self.assertEqual((code, payload["error"]), (3, "还没有填写账号和密码"))


class ControllerCourseDetectTestCase(unittest.TestCase):
    """AppController.detectCourses end to end with a fake worker process."""

    def setUp(self):
        import ui.controller as ctl

        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        # Never touch the real %APPDATA%\ChaoxingDesktop.
        self.patches = [mock.patch.object(ctl, "DATA_DIR", data), mock.patch.object(ctl, "CONFIG_PATH", data / "config.ini")]
        for p in self.patches:
            p.start()
        QCoreApplication.setOrganizationName("ChaoxingDesktopCourseTest")
        QSettings().clear()
        (data / "config.ini").write_text("[common]\nusername = 13800000000\npassword = test\ncourse_list = \n", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"CHAOXING_DESKTOP_FAKE_WORKER": str(HERE / "fake_course_worker.py")})
        self.env.start()
        self.ctl = ctl.AppController()

    def tearDown(self):
        self.ctl.shutdown()
        self.env.stop()
        for p in self.patches:
            p.stop()
        QSettings().clear()
        self.tmp.cleanup()

    def test_detect_choose_and_context(self):
        detected = []
        self.ctl.coursesDetected.connect(lambda c: detected.append(c))
        self.ctl.detectCourses()
        self.assertEqual(self.ctl.courseDetectState, "running")
        self.assertTrue(wait_for(lambda: self.ctl.courseDetectState != "running"))
        self.assertEqual(self.ctl.courseDetectState, "done", self.ctl.courseDetectError)
        self.assertEqual([c["title"] for c in detected[0]], ["大学物理（上）", "马克思主义基本原理", "计算机网络"])
        self.assertEqual(len(self.ctl.knownCourses), 3)

        self.ctl.chooseCourses(["189191", "2151141", "189191", ""])
        self.assertEqual(self.ctl.courseList, "189191,2151141")
        self.assertEqual(self.ctl.selected_course_names(), ["马克思主义基本原理", "大学物理（上）"])

        # Known courses survive a restart (QSettings).
        import ui.controller as ctl

        again = ctl.AppController()
        self.assertEqual(len(again.knownCourses), 3)
        again.shutdown()

    def test_detect_reports_login_error(self):
        with mock.patch.dict(os.environ, {"FAKE_COURSES_FAIL": "1"}):
            self.ctl.detectCourses()
            self.assertTrue(wait_for(lambda: self.ctl.courseDetectState != "running"))
        self.assertEqual(self.ctl.courseDetectState, "error")
        self.assertIn("密码错误", self.ctl.courseDetectError)

    def test_requires_account(self):
        toasts = []
        self.ctl.toast.connect(lambda m, k: toasts.append(m))
        self.ctl.username = ""
        self.ctl.detectCourses()
        self.assertEqual(self.ctl.courseDetectState, "idle")
        self.assertTrue(any("账号" in t for t in toasts))


if __name__ == "__main__":
    unittest.main()
