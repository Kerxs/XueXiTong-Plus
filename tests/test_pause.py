import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from api import pause


class PauseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flag = Path(self.tmp.name) / "pause.flag"
        self.env = mock.patch.dict(os.environ, {pause.ENV: str(self.flag)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_not_paused_returns_at_once(self):
        started = time.monotonic()
        self.assertEqual(pause.wait_if_paused(), 0.0)
        self.assertLess(time.monotonic() - started, 0.1)

    def test_waits_until_resumed_and_reports_the_pause(self):
        self.flag.write_text("paused")
        threading.Timer(1.2, self.flag.unlink).start()
        waited = pause.wait_if_paused()
        self.assertGreaterEqual(waited, 1.0)
        self.assertLess(waited, 2.5)

    def test_video_time_excludes_the_pause(self):
        # The study_video loop: last_iter += wait_if_paused(); dt = (now - last_iter) * speed
        last_iter = time.time()
        self.flag.write_text("paused")
        threading.Timer(1.0, self.flag.unlink).start()
        last_iter += pause.wait_if_paused()
        dt = time.time() - last_iter
        self.assertLess(dt, 0.6)          # not the ~1 s spent paused

    def test_without_the_env_var_nothing_happens(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.flag.write_text("paused")
            self.assertFalse(pause.is_paused())
            self.assertEqual(pause.wait_if_paused(), 0.0)


class JobProcessorPauseTest(unittest.TestCase):
    """Paused runs must not keep re-reading chapters (the 章节未开放 retry loop spammed the log)."""

    def test_retry_loop_stops_while_paused(self):
        import main

        reads = []

        class FakeLimiter:
            def limit_rate(self, **kwargs):
                pass

        class FakeChaoxing:
            rate_limiter = FakeLimiter()

            def get_job_list(self, course, point):
                reads.append(time.monotonic())
                return [], {"notOpen": True}          # never opens: retried forever

        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / "pause.flag"
            with mock.patch.dict(os.environ, {pause.ENV: str(flag)}):
                task = main.ChapterTask(index=0, point={"title": "3.6", "has_finished": False}, course={"title": "c"})
                proc = main.JobProcessor(FakeChaoxing(), [task], {"jobs": 1, "speed": 1, "notopen_action": "retry",
                                                                 "retry_interval": 0.1})
                proc.max_tries = 10 ** 6
                threading.Thread(target=proc.run, daemon=True).start()
                time.sleep(0.6)
                self.assertGreater(len(reads), 1)       # retrying while running
                flag.write_text("paused")
                time.sleep(0.4)                         # let in-flight work reach a checkpoint
                during = len(reads)
                time.sleep(1.5)
                self.assertLessEqual(len(reads) - during, 0, "chapters were read while paused")
                flag.unlink()
                time.sleep(0.6)
                self.assertGreater(len(reads), during)  # resumes after 继续

if __name__ == "__main__":
    unittest.main()
