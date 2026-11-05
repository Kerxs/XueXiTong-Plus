# -*- coding: utf-8 -*-
"""1.2.9: captcha restart, already-graded tests, faster completion check, anonymous stats + feedback."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import main
from api import manual, telemetry
from api.base import Chaoxing, StudyResult, is_graded_work_page
from api.exceptions import CaptchaBlocked
from main import ChapterResult, ChapterTask, JobProcessor


class CaptchaRestartTest(unittest.TestCase):
    def setUp(self):
        manual.reset()

    def _run(self, outcomes, login_ok=True):
        cx = mock.Mock()
        cx.login.return_value = {"status": login_ok, "msg": "ok" if login_ok else "密码错误"}
        course = {"title": "民俗", "courseId": "c", "clazzId": "z", "cpi": "i"}
        task = ChapterTask(index=0, point={"id": "p", "title": "6.4", "has_finished": False}, course=course)
        p = JobProcessor(cx, [task], {"speed": 1.0, "jobs": 1, "notopen_action": "retry", "retry_interval": 0})
        calls = []

        def chapter(*a):
            calls.append(1)
            out = outcomes[min(len(calls), len(outcomes)) - 1]
            if isinstance(out, Exception):
                raise out
            return out

        with mock.patch.object(main, "process_chapter", chapter), mock.patch.object(main.time, "sleep"), \
                mock.patch.object(manual, "print"), mock.patch.object(manual.logger, "warning"):
            try:
                p.run()
                stopped = None
            except main.RunStopped as e:
                stopped = str(e)
        return p, task, cx, calls, stopped

    def test_cooldown_relogin_and_start_over_without_counting_a_try(self):
        p, task, cx, calls, stopped = self._run([CaptchaBlocked("6.4.mp4"), ChapterResult.SUCCESS])
        self.assertIsNone(stopped)
        self.assertEqual(len(calls), 2)
        self.assertEqual(cx.login.call_count, 1)
        self.assertEqual(task.tries, 0)
        self.assertEqual(p._captcha_restarts, 1)

    def test_after_three_restarts_the_video_is_left_for_the_user(self):
        p, task, cx, calls, stopped = self._run([CaptchaBlocked("6.4.mp4")] * 5)
        self.assertIsNone(stopped)
        self.assertEqual(len(calls), main.MAX_CAPTCHA_RESTARTS + 1)
        self.assertEqual(manual.items()[0]["kind"], "视频需要验证（请到学习通打开播放一下）")

    def test_login_failure_stops_with_the_reason(self):
        _, _, _, _, stopped = self._run([CaptchaBlocked("x")], login_ok=False)
        self.assertIn("重新登录失败：密码错误", stopped)


# One question of a real 已批阅 page (selectWorkQuestionYiPiYue), shortened.
GRADED = ('<div class="TiMu newTiMu singleQuesId" data="1"><div class="Zy_TItle"><span class="newZy_TItle">【单选题】</span>题</div>'
          '<div class="newAnswerBx"><div class="myAnswerBx"><span class="answerFont">我的答案：</span><div class="fl answerCon">C</div>'
          '<div class="CorrectOrNot"><span class="marking_dui"></span></div></div></div></div>')
FILLABLE = '<form><div class="TiMu singleQuesId" data="1"></div><input type="hidden" name="answer1" value=""></form>'


class GradedTest(unittest.TestCase):
    def test_detection(self):
        self.assertTrue(is_graded_work_page("https://mooc1.chaoxing.com/mooc-ans/work/selectWorkQuestionYiPiYue?x=1", ""))
        self.assertTrue(is_graded_work_page("https://mooc1.chaoxing.com/mooc-ans/api/work", GRADED))
        self.assertFalse(is_graded_work_page("https://mooc1.chaoxing.com/mooc-ans/api/work", FILLABLE))
        self.assertFalse(is_graded_work_page(mock.Mock(), mock.Mock()))

    def test_study_work_does_not_submit_a_graded_test(self):
        cx = Chaoxing.__new__(Chaoxing)
        cx.tiku = mock.Mock(DISABLE=False)
        cx.kwargs = {}
        cx._post_work_form = mock.Mock()
        session = mock.Mock()
        session.get.return_value = mock.Mock(status_code=200, text=GRADED,
                                             url="https://mooc1.chaoxing.com/mooc-ans/work/selectWorkQuestionYiPiYue?a=1")
        with mock.patch("api.base.SessionManager.get_session", return_value=session):
            result = cx.study_work({"clazzId": "z", "courseId": "c"}, {"jobid": "work-1", "enc": "e", "name": "6.4"},
                                   {"knowledgeid": "k", "ktoken": "t", "cpi": "i"})
        self.assertEqual(result, StudyResult.SUCCESS)
        cx._post_work_form.assert_not_called()


class CardConfirmTest(unittest.TestCase):
    def test_card_passed(self):
        cx = Chaoxing.__new__(Chaoxing)
        page = 'var mArg = {"attachments":[{"jobid":"v1","isPassed":true},{"jobid":"v2"}]};'
        session = mock.Mock()
        session.get.return_value = mock.Mock(text=page)
        course = {"clazzId": "z", "courseId": "c", "cpi": "i"}
        with mock.patch("api.base.SessionManager.get_session", return_value=session):
            self.assertTrue(cx._card_passed(course, {"jobid": "v1", "card_num": "1", "knowledgeid": "k"}))
            self.assertFalse(cx._card_passed(course, {"jobid": "v2", "card_num": "1", "knowledgeid": "k"}))
            self.assertFalse(cx._card_passed(course, {"jobid": "v1"}))          # unknown card: no request
        self.assertEqual(session.get.call_args.kwargs["params"]["num"], "1")


class TelemetryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        telemetry.configure(False, self.dir)
        self.tmp.cleanup()

    def test_off_writes_nothing(self):
        telemetry.configure(False, self.dir)
        telemetry.count("video.ok")
        telemetry.save()
        self.assertFalse((self.dir / telemetry.STATS_FILE).exists())

    def test_counts_merge_and_contain_no_names(self):
        for _ in range(2):
            telemetry.configure(True, self.dir)
            telemetry.count("video.ok", 3)
            telemetry.count("captcha.restart")
            telemetry.save()
        data = json.loads((self.dir / telemetry.STATS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(data["counts"], {"video.ok": 6, "captcha.restart": 2, "runs": 2})
        self.assertEqual(set(data), {"version", "platform", "since", "updated", "counts"})

    def test_feedback_text_and_link(self):
        telemetry.configure(True, self.dir)
        telemetry.count("video.ok", 5)
        telemetry.count("chapters.done", 9)
        telemetry.count("chapters.total", 10)
        telemetry.save()
        text = telemetry.summary(telemetry.load(self.dir))
        self.assertIn("| 视频完成 | 5 |", text)
        self.assertIn("章节完成率：90%", text)
        url = telemetry.feedback_url(text)
        self.assertTrue(url.startswith("https://github.com/Kerxs/XueXiTong-Plus/issues/new?"))
        self.assertEqual(parse_qs(urlsplit(url).query)["body"][0], text)
        self.assertLess(len(telemetry.feedback_url("x" * 20000)), 60000)

    def test_nothing_to_send(self):
        self.assertEqual(telemetry.summary({}), "")


if __name__ == "__main__":
    unittest.main()
