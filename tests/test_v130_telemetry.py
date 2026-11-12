# -*- coding: utf-8 -*-
"""1.3.0 telemetry: only whitelisted numbers, scrubbed crashes, a bounded queue, uploads that never
get in the way, and switching it off deletes what was waiting. Plus watching live streams."""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from api import telemetry
from api.live_process import LiveProcessor, LiveResult, live_minutes


class Collector:
    """A local stand-in for the Cloudflare Worker."""

    def __init__(self, status=200):
        self.reports, self.status = [], status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if outer.status == 200:
                    outer.reports.append(json.loads(body))
                self.send_response(outer.status)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/report"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TelemetryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = mock.patch.dict("os.environ", {"XXTPLUS_VERSION": "1.3.0", "XXTPLUS_TELEMETRY_URL": ""})
        self.env.start()

    def tearDown(self):
        thread = telemetry._upload_thread
        if thread is not None:
            thread.join(5)
        telemetry.configure(False, self.dir)
        self.env.stop()
        self.tmp.cleanup()

    def queue(self, process="worker"):
        try:
            return json.loads((self.dir / telemetry.QUEUE_FILE.format(process)).read_text(encoding="utf-8"))
        except OSError:
            return []

    def test_only_whitelisted_names_are_kept(self):
        telemetry.configure(True, self.dir)
        telemetry.count("video.ok", 2)
        telemetry.count("高等数学 第一章")                   # a course name passed by mistake
        telemetry.count("video.13800138000")                # too long for a category: dropped
        telemetry.count("user.name")                        # unknown group
        telemetry.timing("task.video", 12.5)
        telemetry.timing("secret.path", 1)
        telemetry.gauge("cfg.jobs", 2)
        telemetry.save()
        report = self.queue()[0]
        self.assertEqual(report["counts"], {"video.ok": 2, "runs": 1})
        self.assertEqual(report["timings"], {"task.video": [12500, 1]})
        self.assertEqual(report["gauges"]["cfg.jobs"], 2)
        self.assertEqual(set(report), {"v", "kind", "id", "app", "os", "proc", "day", "counts", "timings", "gauges"})
        self.assertRegex(report["id"], r"^[0-9a-f]{32}$")
        self.assertEqual(report["app"], "1.3.0")

    def test_off_writes_nothing_and_deletes_what_was_waiting(self):
        telemetry.configure(True, self.dir)
        telemetry.count("video.ok")
        telemetry.save()
        self.assertTrue(self.queue())
        telemetry.configure(False, self.dir)                # the switch is turned off
        self.assertEqual(list(self.dir.iterdir()), [])
        telemetry.count("video.ok")
        telemetry.save()
        telemetry.record_crash(ValueError("x"))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_crash_is_scrubbed(self):
        from api.logger import register_secret

        register_secret("hunter2-password")
        telemetry.configure(True, self.dir)
        try:
            raise RuntimeError(r"登录失败 hunter2-password 用户 13800138000 张三 C:\Users\zhangsan\AppData\x.ini "
                               "https://mooc1.chaoxing.com/a?uid=123456789 a@b.com")
        except RuntimeError as exc:
            telemetry.record_crash(exc, "worker.crash")
        crash = self.queue()[0]["crash"]
        text = json.dumps(crash, ensure_ascii=False)
        for leaked in ("hunter2", "13800138000", "张三", "zhangsan", "chaoxing.com", "123456789", "a@b.com", "登录失败"):
            self.assertNotIn(leaked, text)
        self.assertEqual(crash["type"], "RuntimeError")
        self.assertTrue(all(":" in f and "\\" not in f and not f.startswith("/") for f in crash["frames"]))
        self.assertEqual(self.queue()[0]["counts"], {"worker.crash": 1})

    def test_frames_outside_the_program_are_left_out(self):
        self.assertEqual(telemetry._frame_name(r"D:\Claude\学习通PLUS\api\base.py"), "api/base.py")
        self.assertEqual(telemetry._frame_name("/data/app/files/chaquopy/AssetFinder/app/main.py"), "main.py")
        self.assertEqual(telemetry._frame_name(r"C:\Users\zhangsan\Python\Lib\site-packages\requests\api.py"), "")
        self.assertEqual(telemetry._frame_name(r"C:\Users\zhangsan\secret.py"), "")

    def test_queue_is_bounded(self):
        telemetry.configure(True, self.dir)
        for _ in range(telemetry.MAX_QUEUE + 20):
            telemetry.count("video.ok")
            telemetry.save()
        self.assertEqual(len(self.queue()), telemetry.MAX_QUEUE)
        self.assertEqual(telemetry.pending(self.dir), telemetry.MAX_QUEUE)

    def test_no_address_means_nothing_is_uploaded(self):
        self.assertEqual(telemetry.upload_url(), "")            # from source: never, whatever is built in
        with mock.patch.object(telemetry.sys, "frozen", True, create=True):
            self.assertEqual(telemetry.upload_url(), telemetry.TELEMETRY_URL)   # the packaged app: the collector
            with mock.patch.object(telemetry, "TELEMETRY_URL", ""):
                self.assertEqual(telemetry.upload_url(), "")    # a build without an address: local only
            with mock.patch.dict("os.environ", {"XXTPLUS_TELEMETRY_URL": "off"}):
                self.assertEqual(telemetry.upload_url(), "")
        self.assertTrue(telemetry.TELEMETRY_URL == "" or telemetry.TELEMETRY_URL.startswith("https://"))
        with mock.patch.dict("os.environ", {"XXTPLUS_TELEMETRY_URL": "http://example.com/v1/report"}):
            self.assertEqual(telemetry.upload_url(), "")    # plain http to another host: refused
        with mock.patch.dict("os.environ", {"XXTPLUS_TELEMETRY_URL": "https://t.example.com/v1/report"}):
            self.assertEqual(telemetry.upload_url(), "https://t.example.com/v1/report")

    def test_upload_sends_the_queue_and_empties_it(self):
        collector = Collector()
        try:
            with mock.patch.dict("os.environ", {"XXTPLUS_TELEMETRY_URL": collector.url}):
                telemetry.configure(True, self.dir)
                telemetry.count("video.ok", 3)
                telemetry.save()
                telemetry.flush(wait=5)
            self.assertEqual(collector.reports[0]["counts"]["video.ok"], 3)
            self.assertEqual(self.queue(), [])
        finally:
            collector.close()

    def test_server_down_keeps_the_reports_and_the_run_goes_on(self):
        collector = Collector(status=500)
        try:
            with mock.patch.dict("os.environ", {"XXTPLUS_TELEMETRY_URL": collector.url}):
                telemetry.configure(True, self.dir)
                telemetry.count("video.ok")
                telemetry.save()                             # must not raise
                telemetry.flush(wait=5)
                self.assertEqual(len(self.queue()), 1)
                collector.status = 200                       # the server is back: the next run sends both
                telemetry.count("video.ok")
                telemetry.save()
                telemetry.flush(wait=5)
            self.assertEqual(len(collector.reports), 2)
            self.assertEqual(self.queue(), [])
        finally:
            collector.close()

    def test_unreachable_server_does_not_raise(self):
        with mock.patch.dict("os.environ", {"XXTPLUS_TELEMETRY_URL": "http://127.0.0.1:9/v1/report"}):
            telemetry.configure(True, self.dir)
            telemetry.count("video.ok")
            telemetry.save()
            telemetry.flush(wait=5)
        self.assertEqual(len(self.queue()), 1)

    def test_clear_gives_a_new_install_id(self):
        telemetry.configure(True, self.dir)
        first = telemetry.install_id()
        self.assertEqual(telemetry.install_id(), first)
        telemetry.clear(self.dir)
        self.assertNotEqual(telemetry.install_id(), first)

    def test_default_is_on_for_the_task_and_the_settings(self):
        from ui import advanced

        field = next(f for g in advanced.GROUPS for f in g["fields"] if f.get("key") == "telemetry")
        self.assertEqual(field["default"], "true")
        self.assertIn('common_config.get("telemetry", True)', Path("main.py").read_text(encoding="utf-8"))


class FakeLive:
    name = "第一次直播"

    def __init__(self, status, reports=None):
        self.status, self.reports, self.sent = status, list(reports or []), 0

    def get_status(self):
        return self.status

    def do_finish(self):
        self.sent += 1
        return self.reports.pop(0) if self.reports else True


class LiveTest(unittest.TestCase):
    def run_live(self, live, **kwargs):
        with mock.patch("api.live_process.tqdm"), mock.patch("api.live_process.pause.wait_if_paused", lambda: 0.0), \
                mock.patch("api.live_process.logger"):
            return LiveProcessor.run_live(live, sleep=lambda s: None, **kwargs)

    def test_length(self):
        self.assertEqual(live_minutes({"temp": {"data": {"duration": 125}}}), 3)
        with mock.patch("api.live_process.logger"):
            self.assertEqual(live_minutes({}), 30)
            self.assertEqual(live_minutes({"temp": None}), 30)

    def test_watched_minute_by_minute(self):
        live = FakeLive({"temp": {"data": {"duration": 180}}})
        self.assertEqual(self.run_live(live), LiveResult.DONE)
        self.assertEqual(live.sent, 3)
        self.assertTrue(live.started)

    def test_no_status_is_left_to_the_user(self):
        live = FakeLive(None)
        self.assertEqual(self.run_live(live), LiveResult.UNAVAILABLE)
        self.assertEqual(live.sent, 0)
        self.assertFalse(getattr(live, "started", False))

    def test_refused_reports_stop_instead_of_pretending(self):
        live = FakeLive({"temp": {"data": {"duration": 600}}}, reports=[True, False, False, False])
        self.assertEqual(self.run_live(live), LiveResult.UNAVAILABLE)
        self.assertEqual(live.sent, 4)

    def test_stops_early_when_the_platform_shows_it_finished(self):
        live = FakeLive({"temp": {"data": {"duration": 3600}}})
        self.assertEqual(self.run_live(live, passed=lambda: True), LiveResult.DONE)
        self.assertEqual(live.sent, 5)

    def test_live_is_automated_and_can_be_switched_off(self):
        import main

        self.assertTrue(main._automated({"type": "live"}))
        with mock.patch.object(main, "AUTO_LIVE", False):
            self.assertFalse(main._automated({"type": "live"}))


if __name__ == "__main__":
    unittest.main()
