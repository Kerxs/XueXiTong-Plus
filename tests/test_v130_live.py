# -*- coding: utf-8 -*-
"""Live streams (1.3.0): when one counts as finished, the progress moving every second and what
the preview is told. From a real run: two replays were watched in full, 学习通 showed both chapters
as finished, and the app still said 待确认 because the live card was never matched."""
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

import main
from api.base import Chaoxing
from api.live_process import LiveProcessor, LiveResult, preview_sources
from ui.output_parser import OutputParser, VideoPreviewEvent


class SameCardTest(unittest.TestCase):
    def test_video_card_matches_by_jobid(self):
        self.assertTrue(Chaoxing._same_card({"jobid": "a1"}, {"jobid": "a1"}))
        self.assertFalse(Chaoxing._same_card({"jobid": "a2"}, {"jobid": "a1"}))

    def test_live_card_without_top_level_jobid(self):
        # decode gives the job the card's id when the card has no jobid; the real one is property._jobid
        card = {"id": 77, "property": {"_jobid": "live-9", "liveId": 555}, "isPassed": True}
        self.assertTrue(Chaoxing._same_card(card, {"jobid": "77", "property": {"_jobid": "live-9"}}))
        self.assertTrue(Chaoxing._same_card({"jobid": "live-9"}, {"jobid": "77", "property": {"_jobid": "live-9"}}))
        self.assertTrue(Chaoxing._same_card({"property": {"liveId": 555}}, {"jobid": "x", "liveId": "555"}))
        self.assertFalse(Chaoxing._same_card({"property": {"liveId": 556}}, {"jobid": "x", "liveId": "555"}))

    def test_empty_ids_never_match(self):
        self.assertFalse(Chaoxing._same_card({"jobid": ""}, {"jobid": ""}))
        self.assertFalse(Chaoxing._same_card({}, {"type": "live"}))


class CardStateTest(unittest.TestCase):
    COURSE = {"clazzId": "1", "courseId": "2", "cpi": "3"}

    def state(self, cards, job):
        page = "<script>mArg = " + json.dumps({"attachments": cards}) + ";</script>"
        session = mock.Mock()
        session.get.return_value = mock.Mock(text=page)
        with mock.patch("api.base.SessionManager.get_session", return_value=session):
            return Chaoxing.__new__(Chaoxing)._card_state(self.COURSE, job)

    def test_passed_not_passed_and_unknown(self):
        job = {"jobid": "77", "card_num": 0, "knowledgeid": "9", "property": {"_jobid": "live-9"}}
        self.assertIs(self.state([{"property": {"_jobid": "live-9"}, "isPassed": True}], job), True)
        self.assertIs(self.state([{"property": {"_jobid": "live-9"}}], job), False)
        self.assertIsNone(self.state([{"jobid": "other", "isPassed": True}], job))
        self.assertIsNone(Chaoxing.__new__(Chaoxing)._card_state(self.COURSE, {"jobid": "77"}))


class LiveConfirmedTest(unittest.TestCase):
    def confirmed(self, states, accepted=True):
        chaoxing = mock.Mock()
        chaoxing._card_state.side_effect = states
        live = mock.Mock(all_accepted=accepted)
        waits = []
        with mock.patch.object(main, "logger"):
            result = main.live_confirmed(chaoxing, {}, {"name": "直播"}, live, sleep=waits.append)
        return result, waits, chaoxing._card_state.call_count

    def test_shown_as_passed(self):
        self.assertEqual(self.confirmed([True]), (True, [], 1))

    def test_shown_a_little_later(self):
        self.assertEqual(self.confirmed([False, False, True]), (True, [5, 10], 3))

    def test_card_not_found_counts_when_every_report_was_accepted(self):
        self.assertEqual(self.confirmed([None]), (True, [], 1))
        self.assertEqual(self.confirmed([None], accepted=False)[0], False)

    def test_still_not_passed_stays_pending(self):
        self.assertEqual(self.confirmed([False, False, False]), (False, [5, 10], 3))


class FakeLive:
    name = "第一次直播"

    def __init__(self, status, reports=None):
        self.status, self.reports, self.sent = status, list(reports or []), 0

    def get_status(self):
        return self.status

    def do_finish(self):
        self.sent += 1
        return self.reports.pop(0) if self.reports else True


class LiveRunTest(unittest.TestCase):
    def run_live(self, live):
        bar = mock.Mock()
        seen = []
        bar.refresh.side_effect = lambda: seen.append(bar.n)
        with mock.patch("api.live_process.tqdm", return_value=bar), \
                mock.patch("api.live_process.pause.wait_if_paused", lambda: 0.0), mock.patch("api.live_process.logger"):
            result = LiveProcessor.run_live(live, sleep=lambda s: None)
        return result, seen

    def test_progress_moves_every_second(self):
        result, seen = self.run_live(FakeLive({"temp": {"data": {"duration": 120}}}))
        self.assertEqual(result, LiveResult.DONE)
        self.assertEqual(seen[:5], [1, 2, 3, 4, 5])
        self.assertEqual(seen[-1], 120)

    def test_all_accepted_is_recorded(self):
        live = FakeLive({"temp": {"data": {"duration": 180}}})
        self.run_live(live)
        self.assertTrue(live.all_accepted)
        live = FakeLive({"temp": {"data": {"duration": 180}}}, reports=[True, False, True])
        self.run_live(live)
        self.assertFalse(live.all_accepted)


class LivePreviewTest(unittest.TestCase):
    def test_only_mp4_on_chaoxing_hosts(self):
        status = {"temp": {"data": {"duration": 60, "a": "http://s1.cldisk.com/x/replay.mp4?k=1",
                                    "b": "https://zhibo.chaoxing.com/live/a.m3u8",
                                    "c": ["https://s2.cldisk.com/y/replay.mp4", "https://evil.example/x.mp4"]}}}
        self.assertEqual(preview_sources(status),
                         ["https://s2.cldisk.com/y/replay.mp4", "http://s1.cldisk.com/x/replay.mp4?k=1"])
        self.assertEqual(preview_sources({"temp": None}), [])

    def event(self, status):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CHAOXING_DESKTOP_PREVIEW": "1"}), redirect_stdout(out), \
                mock.patch("api.live_process.tqdm"), mock.patch("api.live_process.pause.wait_if_paused", lambda: 0.0), \
                mock.patch("api.live_process.logger"):
            LiveProcessor.run_live(FakeLive(status), sleep=lambda s: None)
        events = [e for line in out.getvalue().splitlines() for e in OutputParser().feed(line + "\n")]
        return [e for e in events if isinstance(e, VideoPreviewEvent)]

    def test_stream_without_a_picture_says_so(self):
        events = self.event({"temp": {"data": {"duration": 60}}})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "")
        self.assertEqual(events[0].title, "第一次直播")
        self.assertIn("直播观看中", events[0].message)

    def test_replay_address_is_previewed(self):
        events = self.event({"temp": {"data": {"duration": 60, "url": "https://s1.cldisk.com/r.mp4"}}})
        self.assertEqual(events[0].source, "https://s1.cldisk.com/r.mp4")
        self.assertEqual(events[0].message, "")


if __name__ == "__main__":
    unittest.main()
