# -*- coding: utf-8 -*-
"""Chapter content: quizzes without questions, unreadable chapters, text-only chapters and other content."""
import unittest
from unittest import mock

import main
from api import decode, manual
from api.base import Chaoxing, StudyResult, classify_empty_work_page


class EmptyQuizPageTest(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(classify_empty_work_page(200, "<div>作业状态：待批阅</div>"), "submitted")
        self.assertEqual(classify_empty_work_page(200, "本次成绩 80 分"), "submitted")
        self.assertEqual(classify_empty_work_page(200, "该测验已截止"), "closed")
        self.assertEqual(classify_empty_work_page(200, "未到开始时间"), "closed")
        self.assertEqual(classify_empty_work_page(200, "<form></form>"), "empty")
        self.assertEqual(classify_empty_work_page(500, "已截止"), "")      # a real error stays an error

    def test_page_without_a_form_has_no_questions(self):
        info = decode.decode_questions_info("<html><body>已截止</body></html>")
        self.assertEqual(info["questions"], [])


class StudyWorkWithoutQuestionsTest(unittest.TestCase):
    def _study(self, status, text):
        cx = Chaoxing.__new__(Chaoxing)
        cx.tiku = mock.Mock(DISABLE=False)
        cx.kwargs = {}
        session = mock.Mock()
        session.get.return_value = mock.Mock(status_code=status, text=text)
        job = {"jobid": "work-1", "enc": "e", "name": "第一章测验"}
        info = {"knowledgeid": "k", "ktoken": "t", "cpi": "c"}
        with mock.patch("api.base.SessionManager.get_session", return_value=session), \
                mock.patch("tenacity.nap.time.sleep"):
            return cx.study_work({"clazzId": "z", "courseId": "c"}, job, info), job

    def test_submitted_counts_as_done(self):
        result, _ = self._study(200, "<html>待批阅</html>")
        self.assertEqual(result, StudyResult.SUCCESS)

    def test_closed_or_empty_needs_the_user_but_is_no_failure(self):
        result, job = self._study(200, "<html>已截止</html>")
        self.assertEqual((result, job["work_problem"]), (StudyResult.NEEDS_USER, "closed"))
        self.assertFalse(result.is_failure())
        result, job = self._study(200, "<html><form></form></html>")
        self.assertEqual((result, job["work_problem"]), (StudyResult.NEEDS_USER, "empty"))

    def test_server_error_is_still_an_error(self):
        result, _ = self._study(500, "Internal Server Error")
        self.assertEqual(result, StudyResult.ERROR)


class ProcessJobQuizTest(unittest.TestCase):
    def setUp(self):
        manual.reset()

    def test_quiz_needing_the_user_is_reported_not_retried(self):
        cx = mock.Mock()

        def study_work(course, job, info):
            job["work_problem"] = "empty"
            return StudyResult.NEEDS_USER

        cx.study_work.side_effect = study_work
        with mock.patch.object(manual, "print"), mock.patch.object(manual.logger, "warning"):
            result = main.process_job(cx, {"title": "高数", "courseId": "1"}, {"type": "workid", "jobid": "w", "name": "测验"},
                                      {}, 1.0, {"id": "p", "title": "1.1"})
            self.assertEqual(manual.items(), [])        # only "正在确认" so far
            manual.confirm_all()
        self.assertEqual(result, StudyResult.SUCCESS)
        self.assertEqual(manual.items()[0]["kind"], "章节检测（没有读到题目）")


class ChapterReadingTest(unittest.TestCase):
    def test_http_error_is_an_error_not_an_empty_chapter(self):
        cx = Chaoxing.__new__(Chaoxing)
        cx.rate_limiter = mock.Mock()
        cx.study_emptypage = mock.Mock()
        session = mock.Mock()
        session.get.return_value = mock.Mock(status_code=502, text="Bad Gateway")
        with mock.patch("api.base.SessionManager.get_session", return_value=session):
            with self.assertRaisesRegex(RuntimeError, "HTTP 502"):
                cx.get_job_list({"clazzId": "z", "courseId": "c", "cpi": "i"}, {"id": "p", "title": "1.1"})
        cx.study_emptypage.assert_not_called()          # not visited as if it had nothing to do


class OtherContentNamesTest(unittest.TestCase):
    def test_kind_from_card_fields(self):
        job = decode._process_other_task({"type": "", "property": {"module": "insertsurvey", "title": "课程反馈"}}, "")
        self.assertEqual(manual.kind_label(job), "问卷")
        job = decode._process_other_task({"type": "insertbbs", "property": {"title": "讨论一"}}, "insertbbs")
        self.assertEqual(manual.kind_label(job), "讨论")
        job = decode._process_other_task({"type": "inserttext", "property": {}}, "inserttext")
        self.assertEqual(manual.kind_label(job), "文字内容")
        job = decode._process_other_task({"type": "mystery", "property": {}}, "mystery")
        self.assertEqual(manual.kind_label(job), "其他内容（mystery）")


if __name__ == "__main__":
    unittest.main()
