# -*- coding: utf-8 -*-
"""作业 / 课堂活动 (api/homework.py) and 课件 auto-completion (main.process_job)."""
import unittest
from unittest import mock

import main
from api import homework, manual
from api.base import StudyResult

# The 作业 list exactly as seen on a real account (ids and enc shortened).
WORK_LIST = """
<div>2026机电2班</div><ul class="bottomList">
<li onclick="goTask(this);" data="https://mooc1.chaoxing.com/mooc-ans/mooc2/work/task?courseId=1&amp;classId=2&amp;cpi=3&amp;workId=11&amp;answerId=21&amp;enc=aa" aria-label="基础练习一 ; 已完成" role="link">
  <div class="tag work-icon icon-zy-g"></div><div class="right-content"><p class="overHidden2 fl">基础练习一</p><p class="status fl">已完成</p></div></li>
<li onclick="goTask(this);" data="https://mooc1.chaoxing.com/mooc-ans/mooc2/work/task?courseId=1&amp;classId=2&amp;cpi=3&amp;workId=12&amp;answerId=22&amp;enc=bb" aria-label="基础练习二 ; 未交" role="link">
  <div class="right-content"><p class="overHidden2 fl">基础练习二</p><p class="status fl">未交</p></div></li>
<li data="https://mooc1.chaoxing.com/mooc-ans/mooc2/work/task?courseId=1&amp;classId=2&amp;cpi=3&amp;workId=13&amp;answerId=23&amp;enc=cc" aria-label="第三次作业 ; 已截止">
  <p class="overHidden2 fl">第三次作业</p><p class="status fl">已截止</p></li>
</ul>"""

WORK_PAGE = """
<form id="submitForm" action="/mooc-ans/work/addStudentWorkNew">
  <input type="hidden" name="courseId" value="1"><input type="hidden" name="classId" value="2">
  <input type="hidden" name="cpi" value="3"><input type="hidden" name="workRelationId" value="12">
  <input type="hidden" name="workAnswerId" value="22"><input type="hidden" name="enc_work" value="ee">
  <input type="hidden" name="totalQuestionNum" value="4"><input type="hidden" name="pyFlag" value="">
  <input type="hidden" name="answerwqbid" value="">
  <div class="questionLi" data="101" typename="单选题">
    <h3 class="mark_name">1. (单选题, 25分) C 语言程序的入口函数是</h3>
    <div class="stem_answer">
      <div class="answerBg"><span class="num_option" data="A">A</span><div class="answer_p">start</div></div>
      <div class="answerBg"><span class="num_option" data="B">B</span><div class="answer_p">main</div></div>
    </div>
    <input type="hidden" name="answer101" id="answer101" value=""><input type="hidden" name="answertype101" value="0">
  </div>
  <div class="questionLi" data="102" typename="多选题">
    <h3 class="mark_name">2. (多选题) 下列是 C 关键字的是</h3>
    <div class="answerBg"><span class="num_option" data="A">A</span><div class="answer_p">int</div></div>
    <div class="answerBg"><span class="num_option" data="B">B</span><div class="answer_p">var</div></div>
    <div class="answerBg"><span class="num_option" data="C">C</span><div class="answer_p">return</div></div>
    <input type="hidden" name="answer102" value=""><input type="hidden" name="answertype102" value="1">
  </div>
  <div class="questionLi" data="103" typename="判断题">
    <h3 class="mark_name">3. (判断题) C 语言区分大小写</h3>
    <input type="hidden" name="answer103" value=""><input type="hidden" name="answertype103" value="3">
  </div>
  <div class="questionLi" data="104" typename="填空题">
    <h3 class="mark_name">4. (填空题) 整型关键字是____，字符型关键字是____</h3>
    <input type="hidden" name="tiankongsize104" value="2"><input type="hidden" name="answertype104" value="2">
  </div>
</form>"""


class ListTest(unittest.TestCase):
    def test_list_and_states(self):
        items = homework.parse_work_list(WORK_LIST)
        self.assertEqual([h.title for h in items], ["基础练习一", "基础练习二", "第三次作业"])
        self.assertEqual([h.todo for h in items], [False, True, False])
        self.assertEqual(items[1].params["workId"], "12")
        self.assertTrue(items[2].closed)

    def test_empty_list(self):
        self.assertEqual(homework.parse_work_list("<div>暂无作业</div>"), [])

    def test_course_page_fields(self):
        fields = homework.parse_course_page('<input type="hidden" id="workEnc" value="e18f"><input id="cpi" value="595">')
        self.assertEqual((fields["workEnc"], fields["cpi"]), ("e18f", "595"))


class PageTest(unittest.TestCase):
    def test_questions_like_a_chapter_test(self):
        page = homework.parse_work_page(WORK_PAGE)
        qs = page["questions"]
        self.assertEqual([q["type"] for q in qs], ["single", "multiple", "judgement", "completion"])
        self.assertEqual(qs[0]["title"], "C 语言程序的入口函数是")
        self.assertEqual(qs[0]["options"], "A start\nB main")
        self.assertEqual(qs[1]["options"].splitlines()[2], "C return")
        self.assertEqual(qs[3]["blanks"], 2)
        self.assertEqual(page["form"]["workAnswerId"], "22")
        self.assertNotIn("answer101", page["form"])

    def test_form_submit_and_save(self):
        page = homework.parse_work_page(WORK_PAGE)
        answers = {"101": "B", "102": "AC", "103": "true", "104": "int；char"}
        for q in page["questions"]:
            q["answerField"][f"answer{q['id']}"] = answers[q["id"]]
        form = homework.build_form(page, submit=True)
        self.assertEqual(form["pyFlag"], "")
        self.assertEqual(form["answerwqbid"], "101,102,103,104,")
        self.assertEqual((form["answer101"], form["answertype102"]), ("B", "1"))
        self.assertEqual((form["answerEditor1041"], form["answerEditor1042"]), ("int", "char"))
        self.assertEqual(homework.build_form(page, submit=False)["pyFlag"], "1")

    def test_page_without_questions(self):
        self.assertEqual(homework.parse_work_page("<html>待批阅</html>")["questions"], [])


class RunTest(unittest.TestCase):
    def setUp(self):
        manual.reset()

    def _run(self, page_html, post_json, submit=True):
        cx = mock.Mock()
        cx.kwargs = {}
        cx._fill_answers.side_effect = lambda qs, html, delay: (
            [q["answerField"].__setitem__(f"answer{q['id']}", "A") for q in qs], (len(qs), len(qs)))[1]
        cx._post_work_form.return_value = mock.Mock(status_code=200, json=lambda: post_json)
        session = mock.Mock()
        session.get.side_effect = lambda url, params=None: mock.Mock(
            status_code=200, text={homework.COURSE_PAGE: '<input id="workEnc" value="e">',
                                   homework.WORK_LIST: WORK_LIST}.get(url, page_html))
        with mock.patch("api.base.SessionManager.get_session", return_value=session), \
                mock.patch.object(homework.time, "sleep"), mock.patch("api.base._emit_work_preview"), \
                mock.patch.object(manual, "print"), mock.patch.object(manual.logger, "warning"):
            counts = homework.run_homework(cx, {"courseId": "1", "clazzId": "2", "cpi": "3", "title": "C语言"}, submit)
        return counts, cx

    def test_only_unfinished_homework_is_answered_and_submitted(self):
        counts, cx = self._run(WORK_PAGE, {"status": True, "msg": "提交成功"})
        self.assertEqual(counts, {"submitted": 1, "saved": 0, "skipped": 0, "failed": 0})
        form = cx._post_work_form.call_args.args[1]
        self.assertEqual(form["pyFlag"], "")

    def test_submit_switched_off_saves(self):
        counts, cx = self._run(WORK_PAGE, {"status": True, "msg": "保存成功"}, submit=False)
        self.assertEqual(counts["saved"], 1)
        self.assertEqual(cx._post_work_form.call_args.args[1]["pyFlag"], "1")

    def test_failure_is_reported_not_raised(self):
        counts, _ = self._run(WORK_PAGE, {"status": False, "msg": "作业已截止"})
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(manual.items()[0]["name"], "基础练习二")


class ActivitiesTest(unittest.TestCase):
    def setUp(self):
        manual.reset()

    def test_open_quiz_and_task_are_announced(self):
        active = [
            {"activeType": 42, "status": 1, "id": 1, "nameOne": "随堂练习", "nameFour": "剩余:5分钟"},
            {"activeType": 42, "status": 2, "id": 2, "nameOne": "随堂练习"},           # ended
            {"activeType": 35, "status": 1, "id": 3, "nameOne": "语法练习3", "nameFour": "剩余:4天"},
            {"activeType": 2, "status": 1, "id": 4, "nameOne": "签到"},                 # not ours
        ]
        session = mock.Mock()
        session.get.return_value = mock.Mock(json=lambda: {"data": {"activeList": active}})
        with mock.patch("api.base.SessionManager.get_session", return_value=session), \
                mock.patch.object(manual, "print"), mock.patch.object(manual.logger, "warning"):
            found = homework.watch_activities(mock.Mock(), {"courseId": "1", "clazzId": "2", "title": "人工智能"})
        self.assertEqual(found, 2)
        self.assertEqual([i["kind"] for i in manual.items()], ["随堂练习（正在进行，请尽快完成）", "课堂任务（进行中）"])
        self.assertEqual(manual.items()[0]["name"], "随堂练习（剩余:5分钟）")


class DocumentsTest(unittest.TestCase):
    def setUp(self):
        manual.reset()

    def test_documents_are_completed(self):
        cx = mock.Mock()
        cx.study_document.return_value = StudyResult.SUCCESS
        result = main.process_job(cx, {"title": "c"}, {"type": "document", "jobid": "d", "name": "第一章课件"}, {}, 1.0, {})
        self.assertEqual(result, StudyResult.SUCCESS)
        cx.study_document.assert_called_once()
        self.assertEqual(manual.items(), [])

    def test_failed_document_goes_to_the_manual_list(self):
        cx = mock.Mock()
        cx.study_document.return_value = StudyResult.ERROR
        with mock.patch.object(manual, "print"), mock.patch.object(manual.logger, "warning"):
            result = main.process_job(cx, {"title": "c"}, {"type": "document", "jobid": "d", "name": "教案"}, {}, 1.0, {"title": "1.1"})
            manual.confirm_all()
        self.assertEqual(result, StudyResult.SUCCESS)               # not retried
        self.assertEqual(manual.items()[0]["name"], "教案")

    def test_switched_off_documents_are_listed(self):
        cx = mock.Mock()
        with mock.patch.object(main, "AUTO_DOCUMENTS", False), mock.patch.object(manual, "print"), \
                mock.patch.object(manual.logger, "warning"):
            main.process_job(cx, {"title": "c"}, {"type": "document", "jobid": "d", "name": "课件"}, {}, 1.0, {})
        cx.study_document.assert_not_called()


class SettingsTest(unittest.TestCase):
    def test_auto_group(self):
        from ui import advanced

        group = next(g for g in advanced.GROUPS if g["id"] == "auto")
        ids = [f["id"] for f in group["fields"]]
        self.assertEqual(ids, ["common.auto_documents", "common.auto_live", "common.auto_homework", "common.homework_submit",
                               "common.watch_activities"])
        self.assertTrue(all(f["default"] == "true" for f in group["fields"]))


if __name__ == "__main__":
    unittest.main()
