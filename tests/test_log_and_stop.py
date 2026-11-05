# -*- coding: utf-8 -*-
"""Error logs carry no personal request parameters; 停止 ends as 已停止, not as an error."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from api.base import _safe_url


class SafeUrlTest(unittest.TestCase):
    def test_video_report_address_loses_ids_and_query(self):
        url = ("https://mooc1.chaoxing.com/mooc-ans/multimedia/log/a/595065080/1897f745291d941e5d7b25f6c82203ed"
               "?clazzId=158395099&playingTime=1356&userid=488746998&enc=086293a9bbabd25d0b1f01d5e6a4ad5d&rt=0.9")
        safe = _safe_url(url)
        self.assertEqual(safe, "https://mooc1.chaoxing.com/mooc-ans/multimedia/log/a/*/*")
        for secret in ("595065080", "1897f745", "488746998", "086293a9", "userid", "enc="):
            self.assertNotIn(secret, safe)

    def test_plain_address_kept(self):
        self.assertEqual(_safe_url("https://mobilelearn.chaoxing.com/newsign/preSign?uid=1"),
                         "https://mobilelearn.chaoxing.com/newsign/preSign")


class StopIsNotAnErrorTest(unittest.TestCase):
    def setUp(self):
        from PySide6.QtCore import QCoreApplication, QSettings
        import ui.controller as ctl

        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        self.patches = [mock.patch.object(ctl, "DATA_DIR", data), mock.patch.object(ctl, "CONFIG_PATH", data / "config.ini")]
        for p in self.patches:
            p.start()
        QCoreApplication.setOrganizationName("ChaoxingDesktopStopTest")
        QSettings().clear()
        self.ctl = ctl.AppController()
        self.logs = []
        self.ctl._log = lambda level, message, *a: self.logs.append((level, message))

    def tearDown(self):
        self.ctl.shutdown()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _finish(self, code, stopping):
        self.ctl._process = None
        self.ctl._stopping = stopping
        self.ctl._on_finished(code, None)

    def test_user_stop(self):
        self._finish(62097, True)
        self.assertEqual((self.ctl.property("status"), self.ctl.property("statusKind")), ("已停止", "idle"))
        self.assertFalse([m for lvl, m in self.logs if lvl == "ERROR"])

    def test_crash_still_reported(self):
        self._finish(62097, False)
        self.assertEqual(self.ctl.property("statusKind"), "error")
        self.assertTrue([m for lvl, m in self.logs if lvl == "ERROR" and "62097" in m])

    def test_normal_end(self):
        self._finish(0, False)
        self.assertEqual(self.ctl.property("statusKind"), "done")


if __name__ == "__main__":
    unittest.main()
