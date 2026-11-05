# -*- coding: utf-8 -*-
"""Video speed is fixed at 1x, and every video is watched to the end (the 90% shortcut no longer works)."""
import unittest
from unittest import mock

from api.base import Chaoxing, StudyResult


class StudyVideoWatchesToTheEndTest(unittest.TestCase):
    """study_video with a fake clock and a platform that passes a video only at its end."""

    def _run(self, rt, duration=100, start=0, passes=None):
        reports = []
        clock = {"t": 1000.0}

        def fake_time():
            return clock["t"]

        def fake_sleep(seconds):
            clock["t"] += max(seconds, 1.0)

        cx = Chaoxing.__new__(Chaoxing)
        cx._refresh_video_status = lambda *a, **k: {"dtoken": "d", "duration": duration}

        def progress(_s, _c, _j, _ji, _d, dur, playing, _type, headers=None, _isdrag=3):
            reports.append((playing, _isdrag))
            if passes is not None:
                return passes(reports, dur), 200
            return playing >= dur, 200

        cx.video_progress_log = progress
        cx._close_pbar_safe = lambda pbar: None
        job = {"name": "1.1 视频", "jobid": "j", "rt": rt, "otherinfo": "", "playTime": start * 1000}
        # A private fake clock for api.base only: patching time.time / time.sleep themselves would let
        # background threads left by other tests (sleeping in the same process) move this clock.
        import time as real_time
        from types import SimpleNamespace
        fake_clock = SimpleNamespace(**{k: getattr(real_time, k) for k in dir(real_time) if not k.startswith("_")})
        fake_clock.time, fake_clock.sleep = fake_time, fake_sleep
        with mock.patch("api.base.time", fake_clock), \
                mock.patch("api.base.random.uniform", lambda a, b: 85), \
                mock.patch("api.base.pause.wait_if_paused", lambda: 0.0), \
                mock.patch("api.base.tqdm"):
            result = cx.study_video({"title": "c"}, job, {}, _speed=1.0)
        return result, reports

    def test_rt_point_nine_is_not_cut_short(self):
        result, reports = self._run("0.9")
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(reports[-1][0], 100)
        self.assertFalse([p for p, _ in reports if 86 <= p < 100])   # no extra report at 90%

    def test_opening_report_is_the_recorded_position_not_the_end(self):
        # No "watched it all" claim at second 0: the first report is where the platform says we are.
        _, reports = self._run("1")
        self.assertEqual(reports[0], (0, 3))
        _, reports = self._run("1", start=40)
        self.assertEqual(reports[0], (40, 3))
        self.assertNotIn(4, [drag for _, drag in reports])
        # ... and the next report waits for real watching time instead of repeating that position.
        self.assertGreater(reports[1][0], 40)

    def test_recorded_progress_at_the_end_completes_at_once(self):
        result, reports = self._run("0.9", start=100)
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(reports, [(100, 3)])

    def test_recorded_end_not_accepted_rewatches_from_the_start(self):
        # "开始任务: …, 总时长: 1356s, 已进行: 1356s" and the platform does not pass it: it wants the
        # video really watched. It used to report "at the end" 8 times and fail every retry.
        def passes(reports, dur):
            rewatched = any(p == 0 for p, _ in reports[1:])
            return rewatched and reports[-1][0] >= dur

        result, reports = self._run("1", duration=1356, start=1356, passes=passes)
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(reports[0][0], 1356)            # the recorded position, as before
        self.assertEqual(reports[1][0], 0)               # then from the start
        self.assertTrue(any(0 < p < 1356 for p, _ in reports))   # normal progress reports while watching
        self.assertEqual(reports[-1][0], 1356)

    def test_full_video_still_watched_to_the_end(self):
        result, reports = self._run("1")
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(reports[-1][0], 100)


class SpeedFixedTest(unittest.TestCase):
    def test_android_settings_force_speed_one(self):
        import importlib
        import json
        import sys
        import tempfile
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "android" / "app" / "src" / "main" / "python"))
        try:
            bridge = importlib.import_module("xxtplus_android")
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = str(Path(tmp) / "config.ini")
            values = json.loads(bridge.load_settings(cfg, str(root / "config_template.ini")))
            values["common.speed"] = "2"
            bridge.save_settings(cfg, str(root / "config_template.ini"), json.dumps(values))
            self.assertEqual(json.loads(bridge.load_settings(cfg, ""))["common.speed"], "1")


if __name__ == "__main__":
    unittest.main()
