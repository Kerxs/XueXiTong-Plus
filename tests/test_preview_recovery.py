# -*- coding: utf-8 -*-
"""Desktop video preview recovery: the proxy reports refused / unreachable addresses and page
failures; the app then asks the task for a fresh address (at most once per PREVIEW_REFRESH_SECONDS)."""
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from ui.videoproxy import VideoProxy


class Expired(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_error(403)


class ProxyReportsTest(unittest.TestCase):
    def setUp(self):
        self.reports = []
        self.proxy = VideoProxy(allowed_hosts=("127.0.0.1",), on_problem=lambda u, s, r="": self.reports.append((u, s)))

    def tearDown(self):
        self.proxy.stop()

    def test_refused_address_is_reported(self):
        cdn = ThreadingHTTPServer(("127.0.0.1", 0), Expired)
        threading.Thread(target=cdn.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{cdn.server_address[1]}/v.mp4"
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(self.proxy.register(url), timeout=10)
            self.assertEqual(ctx.exception.code, 403)          # still forwarded to the page
            self.assertEqual(self.reports, [(url, 403)])
        finally:
            cdn.shutdown()

    def test_unreachable_is_tried_twice_then_reported(self):
        url = "http://127.0.0.1:9/v.mp4"                       # nothing listens there
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.proxy.register(url), timeout=30)
        self.assertEqual(ctx.exception.code, 502)
        self.assertEqual(self.reports, [(url, 502)])

    def test_page_failure_endpoint(self):
        url = "http://127.0.0.1:9/v.mp4"
        local = self.proxy.register(url)
        with urllib.request.urlopen(local.replace("/v/", "/f/"), timeout=5) as resp:
            self.assertEqual(resp.status, 204)
        self.assertEqual(self.reports, [(url, 0)])


class Good(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = b"video-bytes"
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BackupAddressTest(unittest.TestCase):
    """Several addresses for one video: the first that answers is used, and remembered."""

    def setUp(self):
        self.servers = []
        self.reports = []
        self.proxy = VideoProxy(allowed_hosts=("127.0.0.1",),
                                on_problem=lambda u, s, r="": self.reports.append((u, s, r)))

    def tearDown(self):
        self.proxy.stop()
        for server in self.servers:
            server.shutdown()

    def _serve(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}/v.mp4"

    def test_refused_first_address_falls_back_to_the_next(self):
        bad, good = self._serve(Expired), self._serve(Good)
        local = self.proxy.register([bad, good])
        with urllib.request.urlopen(local, timeout=10) as resp:
            self.assertEqual(resp.read(), b"video-bytes")
        self.assertEqual(self.reports, [])                          # a backup worked: nothing to report
        self.assertEqual(self.proxy._lookup(local[local.index("/v/"):])[0], good)   # remembered first

    def test_all_failing_reports_the_reason(self):
        local = self.proxy.register(["http://127.0.0.1:9/a.mp4", "http://127.0.0.1:9/b.mp4"])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(local, timeout=60)
        self.assertEqual(ctx.exception.code, 502)
        url, status, reason = self.reports[0]
        self.assertEqual((url, status), ("http://127.0.0.1:9/a.mp4", 502))
        self.assertIn("URLError", reason)                           # the reason is in the log line

    def test_second_way_used_when_the_first_fails(self):
        good = self._serve(Good)
        local = self.proxy.register([good])
        with mock.patch.object(self.proxy, "_open_system", side_effect=OSError("ssl handshake")):
            with urllib.request.urlopen(local, timeout=10) as resp:
                self.assertEqual(resp.read(), b"video-bytes")


class ControllerRefreshTest(unittest.TestCase):
    def setUp(self):
        from PySide6.QtCore import QCoreApplication, QSettings
        import ui.controller as ctl

        self.mod = ctl
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        self.flag = data / "preview_refresh.flag"
        self.patches = [mock.patch.object(ctl, "DATA_DIR", data), mock.patch.object(ctl, "CONFIG_PATH", data / "config.ini"),
                        mock.patch.object(ctl, "PREVIEW_REFRESH_FILE", self.flag)]
        for p in self.patches:
            p.start()
        QCoreApplication.setOrganizationName("ChaoxingDesktopPreviewTest")
        QSettings().clear()
        self.ctl = ctl.AppController()
        self.logs = []
        self.ctl._log = lambda level, message, *a: self.logs.append((level, message))
        self.ctl._process = mock.Mock()
        self.ctl._video_source = "https://s1.cldisk.com/a.mp4"
        self.ctl._videos["a.mp4"] = {"title": "a.mp4", "html": "", "page": "", "pos": -1.0,
                                     "sources": ["https://s1.cldisk.com/a.mp4"]}

    def tearDown(self):
        self.ctl._process = None
        self.ctl.shutdown()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_refused_asks_for_a_fresh_address_once(self):
        self.ctl._on_preview_problem("https://s1.cldisk.com/a.mp4", 403)
        self.assertTrue(self.flag.exists())
        self.assertTrue(any("HTTP 403" in m for _, m in self.logs))
        self.flag.unlink()
        self.ctl._on_preview_problem("https://s1.cldisk.com/a.mp4", 403)     # within 90 s: no second request
        self.assertFalse(self.flag.exists())
        self.assertEqual(len(self.logs), 1)                                   # and no repeated log line
        self.ctl._preview_refreshed_at = time.monotonic() - self.mod.PREVIEW_REFRESH_SECONDS - 1
        self.ctl._on_preview_problem("https://s1.cldisk.com/a.mp4", 0)       # page gave up: ask again
        self.assertTrue(self.flag.exists())

    def test_network_trouble_only_logs(self):
        self.ctl._on_preview_problem("https://s1.cldisk.com/a.mp4", 502)
        self.assertFalse(self.flag.exists())
        self.assertTrue(any("都暂时连不上" in m for _, m in self.logs))

    def test_old_video_or_no_run_is_ignored(self):
        self.ctl._on_preview_problem("https://s1.cldisk.com/old.mp4", 403)
        self.ctl._process = None
        self.ctl._on_preview_problem("https://s1.cldisk.com/a.mp4", 403)
        self.assertFalse(self.flag.exists())
        self.assertEqual(self.logs, [])


class WorkerRefreshTest(unittest.TestCase):
    def test_flag_is_consumed_once(self):
        import os
        from api.base import Chaoxing

        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / "preview_refresh.flag"
            with mock.patch.dict(os.environ, {"CHAOXING_PREVIEW_REFRESH_FILE": str(flag)}):
                self.assertFalse(Chaoxing._preview_refresh_requested())
                flag.write_text("refresh")
                self.assertTrue(Chaoxing._preview_refresh_requested())
                self.assertFalse(flag.exists())
                self.assertFalse(Chaoxing._preview_refresh_requested())


class ManualAnswersInTheAppsTest(unittest.TestCase):
    """The apps have no console to type answers into: TikuManual would wait forever."""

    def test_skipped_in_the_apps(self):
        import os
        from api.answer import DummyTiku, Tiku

        with mock.patch.dict(os.environ, {"CHAOXING_DESKTOP_PREVIEW": "1"}):
            tiku = Tiku.get_tiku_from_config({"provider": "TikuManual"}, config_path="none.ini")
        self.assertIsInstance(tiku, DummyTiku)

    def test_still_available_on_the_command_line(self):
        import os
        from api.answer import Tiku, TikuManual

        env = {k: v for k, v in os.environ.items() if k != "CHAOXING_DESKTOP_PREVIEW"}
        with mock.patch.dict(os.environ, env, clear=True):
            tiku = Tiku.get_tiku_from_config({"provider": "TikuManual"}, config_path="none.ini")
        self.assertIsInstance(tiku, TikuManual)


if __name__ == "__main__":
    unittest.main()
