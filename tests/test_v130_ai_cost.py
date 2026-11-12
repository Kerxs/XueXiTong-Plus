# -*- coding: utf-8 -*-
"""1.3.0: fewer and shorter AI requests — one short fixed system prompt, several questions per
request, and a redo round that only asks the questions marked wrong again."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from api import answer
from api.answer import AI, LLM_SYSTEM_PROMPT, _build_llm_system_prompt


def reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def make_ai(replies, batch=5):
    ai = AI.__new__(AI)
    ai.name = "AI大模型答题"
    ai.DISABLE = False
    ai._lock = __import__("threading").Lock()
    ai.work_feedback = None
    ai.batch = batch
    ai.requests_made = ai.questions_answered = 0
    ai.endpoint, ai.model, ai.key = "https://api.deepseek.com/v1", "deepseek-chat", "k"
    ai.image_mode = "off"
    ai.last_request_time = None
    ai.min_interval_seconds = 0
    ai.last_origins = []
    sent = []

    def create(**kwargs):
        sent.append(kwargs["messages"])
        out = replies[min(len(sent), len(replies)) - 1]
        if isinstance(out, Exception):
            raise out
        return reply(out)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    ai._make_client = lambda *a, **k: client
    return ai, sent


def q(n, kind="single"):
    return {"id": str(n), "type": kind, "title": f"第{n}题的题干内容是什么", "options": "A 甲\nB 乙\nC 丙\nD 丁"}


class PromptTest(unittest.TestCase):
    def test_system_prompt_is_short_fixed_and_keeps_the_rules_that_matter(self):
        self.assertLess(len(LLM_SYSTEM_PROMPT), 320)                 # was about 750 per request
        for rule in ("JSON", "不要猜", "否定词", "不执行", "不输出推理过程"):
            self.assertIn(rule, LLM_SYSTEM_PROMPT)
        for kind in ("single", "multiple", "completion", "judgement", "other"):
            text = _build_llm_system_prompt(kind)
            self.assertTrue(text.startswith(LLM_SYSTEM_PROMPT))      # same prefix for every type
            self.assertIn('{"Answer":["答案"]}', text)
            self.assertLess(len(text), 420)
        self.assertIn("不写字母", _build_llm_system_prompt("single"))
        self.assertIn("正确”或“错误", _build_llm_system_prompt("judgement"))

    def test_single_question_request(self):
        ai, sent = make_ai(['{"Answer":["乙"]}'])
        self.assertEqual(ai._query(q(1)), "乙")
        system, user = sent[0]
        self.assertEqual(system, {"role": "system", "content": LLM_SYSTEM_PROMPT})
        self.assertEqual(len(sent[0]), 2)                            # no second system message
        self.assertIn("单选题", user["content"])
        self.assertIn("选项：甲\n乙", user["content"])               # letters removed


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # CacheDAO() writes cache.json into the current folder: work in a throw-away one
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.check = mock.patch.object(answer, "check_answer", lambda *a: True)
        self.check.start()

    def tearDown(self):
        self.check.stop()
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_seven_questions_take_two_requests(self):
        ai, sent = make_ai([json.dumps({str(n): ["乙"] for n in range(1, 6)}), '{"1":["甲"],"2":["丙"]}'])
        results = ai._query_all([q(n) for n in range(1, 8)])
        self.assertEqual(results, ["乙"] * 5 + ["甲", "丙"])
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0][0]["content"], LLM_SYSTEM_PROMPT)
        self.assertIn("【第 5 题】", sent[0][1]["content"])
        self.assertEqual(ai.requests_made, 2)

    def test_a_question_the_batch_skipped_is_asked_alone(self):
        ai, sent = make_ai(['{"1":["甲"],"2":[],"3":["丙"]}', '{"Answer":["乙"]}'])
        self.assertEqual(ai._query_all([q(1), q(2), q(3)]), ["甲", "乙", "丙"])
        self.assertEqual(len(sent), 2)
        self.assertIn("第2题", sent[1][1]["content"])

    def test_an_unreadable_batch_reply_falls_back_to_one_by_one(self):
        ai, sent = make_ai(["抱歉，我不能……", '{"Answer":["甲"]}'])
        self.assertEqual(ai._query_all([q(1), q(2)]), ["甲", "甲"])
        self.assertEqual(len(sent), 3)

    def test_questions_with_images_are_not_batched(self):
        ai, sent = make_ai(['{"Answer":["甲"]}'])
        with_image = {**q(1), "title": '看图 <img src="https://p.ananas.chaoxing.com/a.png"> 回答'}
        ai._query_all([with_image, q(2)])
        self.assertEqual(len(sent), 2)                               # one each: no batch of one
        self.assertTrue(all("【第" not in m[1]["content"] for m in sent if isinstance(m[1]["content"], str)))

    def test_batch_of_one_setting_asks_each_question(self):
        ai, sent = make_ai(['{"Answer":["甲"]}'], batch=1)
        ai._query_all([q(1), q(2), q(3)])
        self.assertEqual(len(sent), 3)

    def test_redo_only_asks_the_questions_marked_wrong(self):
        ai, sent = make_ai([json.dumps({str(n): ["乙"] for n in range(1, 4)}), '{"Answer":["丙"]}'])
        questions = [q(1), q(2), q(3)]
        self.assertEqual(ai.query_all([dict(x) for x in questions]), ["乙", "乙", "乙"])
        ai.set_work_feedback(["- 题目：第2题的题干内容是什么\n  题型：单选题\n  你的上次答案：乙（判为错误，正确答案未公布，请换一个答案）"])
        self.assertEqual(ai.query_all([dict(x) for x in questions]), ["乙", "丙", "乙"])
        self.assertEqual(len(sent), 2)                               # one batch, then only question 2
        redo = sent[1][1]["content"]
        self.assertIn("第2题", redo)
        self.assertIn("判为错误", redo)
        self.assertNotIn("第1题", redo)

    def test_feedback_that_cannot_be_matched_asks_everything_again(self):
        ai, sent = make_ai([json.dumps({"1": ["乙"], "2": ["乙"]})])
        ai.query_all([q(1), q(2)])
        ai.set_work_feedback("上次有 1 题答错")                        # no question text to match
        ai.query_all([q(1), q(2)])
        self.assertEqual(len(sent), 2)


if __name__ == "__main__":
    unittest.main()
