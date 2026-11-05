# -*- coding: utf-8 -*-
"""Chapter-test results where 正确答案 is hidden: the right / wrong mark decides (real page, Nov 2026)."""
import unittest

from api.base import _parse_work_record_detail

# One question of a real submitted 章节检测 (selectWorkQuestionYiPiYue): no 正确答案, only the mark.
RIGHT = """<div class="TiMu newTiMu ans-cc singleQuesId" data="406802986" id="question406802986"> <div class="Zy_TItle clearfix">
<i class="fl">1</i> <div class="clearfix font-cxsecret fontLabel qtContent"><span class="newZy_TItle">【单选题】</span>()是高雅文化的基础。</div> </div>
<div class="newAnswerBx"> <div class="myAnswerBx marBot16"> <div class="myAnswer"> <span class="answerFont fl">我的答案：</span>
<div class="fl answerCon"> C </div> <p class="clear"></p> </div> <div class="answerScore"> <div class="CorrectOrNot fl">
<span class="marking_dui"></span> </div> <div class="fr newAnswerScore"><span class="scoreNum">25.0</span>分</div> </div> </div></div> </div>"""

WRONG = RIGHT.replace('data="406802986"', 'data="406802987"').replace("> C <", "> A <").replace("marking_dui", "marking_cuo")


class MarksTest(unittest.TestCase):
    def test_right_and_wrong_marks_without_correct_answer(self):
        detail = _parse_work_record_detail(RIGHT + WRONG)
        self.assertEqual([(q["my_answer"], q["correct"], q["parse_ok"]) for q in detail],
                         [("C", True, True), ("A", False, True)])
        self.assertEqual(detail[0]["type_label"], "【单选题】")

    def test_check_result_uses_marks(self):
        from unittest import mock
        from api.base import Chaoxing

        cx = Chaoxing.__new__(Chaoxing)
        session = mock.Mock()
        record_list = mock.Mock(text="")
        with mock.patch("api.base._parse_work_record_list", return_value=[(1, 25.0)]), \
                mock.patch("api.base._parse_work_record_detail", return_value=_parse_work_record_detail(RIGHT + WRONG)):
            session.get.return_value = record_list
            info = cx._check_work_result(session, {"courseId": "1", "clazzId": "2", "cpi": "3"},
                                         {"jobid": "work-9"}, {}, {"workAnswerId": "5"})
        self.assertEqual(info["unknown"], 0)                 # used to be 2 ("答案字段未能解析")
        self.assertFalse(info["all_correct"])
        self.assertEqual(len(info["feedback"]), 1)
        self.assertIn("判为错误，正确答案未公布", info["feedback"][0])


if __name__ == "__main__":
    unittest.main()
