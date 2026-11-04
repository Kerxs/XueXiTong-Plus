# -*- coding: utf-8 -*-
"""Video speed is fixed at 1x; videos that complete at 90% report as soon as 90% is reached."""
import unittest
from unittest import mock

from api.base import Chaoxing, StudyResult


class RequiredRatioTest(unittest.TestCase):
    def test_ratio_from_job_property_and_otherinfo(self):
        self.assertEqual(Chaoxing.required_watch_ratio({"rt": "0.9"}), 0.9)
        self.assertEqual(Chaoxing.required_watch_ratio({"rt": "1"}), 1.0)
        self.assertEqual(Chaoxing.required_watch_ratio({"rt": "", "otherinfo": "nodeId_1-rt_d"}), 0.9)
        self.assertEqual(Chaoxing.required_watch_ratio({"rt": "", "otherinfo": "nodeId_1-rt_1"}), 1.0)
        self.assertEqual(Chaoxing.required_watch_ratio({"rt": "", "otherinfo": ""}), 1.0)   # unknown: watch it all
        self.assertEqual(Chaoxing.required_watch_ratio({"rt": "abc"}), 1.0)
        self.assertEqual(Chaoxing.required_watch_ratio({"rt": "0.1"}), 1.0)                 # implausible value


class StudyVideoStopsAtRequiredShareTest(unittest.TestCase):
    """study_video with a fake clock: a 0.9 video is reported at 90% and ends when the platform passes it."""

    def _run(self, rt, duration=100):
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
            if _isdrag == 4:          # the opening report: not passed yet
                return False, 200
            return playing >= dur * float(rt), 200

        cx.video_progress_log = progress
        cx._close_pbar_safe = lambda pbar: None
        job = {"name": "1.1 视频", "jobid": "j", "rt": rt, "otherinfo": "", "playTime": 0}
        with mock.patch("api.base.time.time", fake_time), mock.patch("api.base.time.sleep", fake_sleep), \
                mock.patch("api.base.random.uniform", lambda a, b: 85), \
                mock.patch("api.base.pause.wait_if_paused", lambda: 0.0), \
                mock.patch("api.base.tqdm"):
            result = cx.study_video({"title": "c"}, job, {}, _speed=1.0)
        return result, reports

    def test_ninety_percent_video_ends_at_ninety(self):
        result, reports = self._run("0.9")
        self.assertEqual(result, StudyResult.SUCCESS)
        last_playing = reports[-1][0]
        self.assertGreaterEqual(last_playing, 90)
        self.assertLess(last_playing, 95)   # reported right at 90%, not at the next 85 s report / the end

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
