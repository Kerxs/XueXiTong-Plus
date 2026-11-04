import unittest

from ui.controller import build_work_view

QUESTIONS = [
    {"index": 1, "type": "single", "title": "越剧的发源地是（）。", "options": "A 浙江嵊州\nB 上海", "answer": "", "source": ""},
    {"index": 2, "type": "judgement", "title": "越剧被称为中国歌剧。", "options": "对\n错", "answer": "", "source": ""},
]


class WorkViewTest(unittest.TestCase):
    def test_questions_before_answers(self):
        view = build_work_view({"phase": "questions", "title": "测验", "questions": QUESTIONS}, pending=True)
        self.assertTrue(view["pending"])
        self.assertEqual(len(view["questions"]), 2)
        self.assertTrue(all(q["pending"] for q in view["questions"]))
        self.assertFalse(any(o["selected"] for q in view["questions"] for o in q["options"]))
        self.assertEqual([o["text"] for o in view["questions"][0]["options"]], ["A 浙江嵊州", "B 上海"])

    def test_filled_view_is_not_pending(self):
        filled = [dict(q, answer="A", source="cover") for q in QUESTIONS[:1]]
        view = build_work_view({"phase": "filled", "cover_rate": 100, "questions": filled})
        self.assertFalse(view["pending"])
        self.assertFalse(view["questions"][0]["pending"])
        self.assertTrue(view["questions"][0]["options"][0]["selected"])


if __name__ == "__main__":
    unittest.main()
