# -*- coding: utf-8 -*-
"""Completion rate: the second pass over chapters 学习通 does not show as finished, and the report."""
import unittest
from unittest import mock

import main


def points(*finished):
    return {"points": [{"id": str(i), "title": f"{i + 1}.1", "has_finished": f} for i, f in enumerate(finished)]}


class UnfinishedChaptersTest(unittest.TestCase):
    def test_left_and_stats(self):
        cx = mock.Mock()
        cx.get_course_point.side_effect = [points(True, False, True), RuntimeError("HTTP 502"), points(True)]
        courses = [{"title": "高数", "courseId": "1", "clazzId": "1", "cpi": "1"},
                   {"title": "英语", "courseId": "2", "clazzId": "2", "cpi": "2"},
                   {"title": "C语言", "courseId": "3", "clazzId": "3", "cpi": "3"}]
        left, stats = main.unfinished_chapters(cx, courses)
        self.assertEqual([(t.course["title"], t.point["title"]) for t in left], [("高数", "2.1")])
        self.assertEqual(stats, {"高数": (2, 3), "C语言": (1, 1)})          # unreadable course left out

    def test_report(self):
        self.assertEqual(main.completion_report({"高数": (30, 32), "C语言": (12, 12)}),
                         "完成情况：高数 30/32 章、C语言 12/12 章（共 95%）")
        self.assertEqual(main.completion_report({}), "")


if __name__ == "__main__":
    unittest.main()
