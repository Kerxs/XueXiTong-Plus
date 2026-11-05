# -*- coding: utf-8 -*-
"""Audio vs video comes from the task card; a known type is not retried as the other one."""
import unittest
from unittest import mock

import main
from api import decode
from api.base import StudyResult


class MediaTypeFromCardTest(unittest.TestCase):
    def test_player_module_wins(self):
        self.assertEqual(decode.media_type({"property": {"module": "insertaudio", "name": "a.mp4"}}), "Audio")
        self.assertEqual(decode.media_type({"property": {"module": "insertvideo", "name": "a.mp3"}}), "Video")

    def test_file_name(self):
        self.assertEqual(decode.media_type({"property": {"name": "民俗资源与旅游3.5.mp4"}}), "Video")
        self.assertEqual(decode.media_type({"property": {"name": "第一讲 导论.MP3"}}), "Audio")
        self.assertEqual(decode.media_type({"property": {"name": "听力.m4a"}}), "Audio")

    def test_unknown(self):
        self.assertEqual(decode.media_type({"property": {"name": "第一讲"}}), "")
        self.assertEqual(decode.media_type({}), "")

    def test_video_job_carries_it(self):
        job = decode._process_video_task({"mid": "m", "jobid": "j", "property": {"name": "1.1.mp4"}})
        self.assertEqual(job["media"], "Video")


class ProcessJobUsesKnownTypeTest(unittest.TestCase):
    def _types(self, media, results):
        cx = mock.Mock()
        cx.study_video.side_effect = results
        job = {"type": "video", "jobid": "v", "name": "v", "media": media}
        result = main.process_job(cx, {"title": "c"}, job, {}, 1.0, {})
        return result, [c.kwargs["_type"] for c in cx.study_video.call_args_list]

    def test_known_video_is_not_retried_as_audio(self):
        result, types = self._types("Video", [StudyResult.ERROR])
        self.assertEqual(types, ["Video"])
        self.assertEqual(result, StudyResult.ERROR)

    def test_known_audio_goes_straight_to_audio(self):
        result, types = self._types("Audio", [StudyResult.SUCCESS])
        self.assertEqual(types, ["Audio"])
        self.assertEqual(result, StudyResult.SUCCESS)

    def test_unknown_keeps_the_old_fallback(self):
        result, types = self._types("", [StudyResult.ERROR, StudyResult.SUCCESS])
        self.assertEqual(types, ["Video", "Audio"])
        self.assertEqual(result, StudyResult.SUCCESS)


if __name__ == "__main__":
    unittest.main()
