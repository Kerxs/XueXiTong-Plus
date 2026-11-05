# -*- coding: utf-8 -*-
"""看图答题 (api/images.py + api/answer.AI): direct recognition, conversion to text, fallbacks."""
import unittest
from types import SimpleNamespace
from unittest import mock

from api import images

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def session_with(data=PNG, status=200):
    s = mock.Mock()
    s.get.return_value = SimpleNamespace(status_code=status, content=data, headers={"Content-Type": "image/png"})
    return s


class ImageHelpersTest(unittest.TestCase):
    def setUp(self):
        images._transcribed.clear()

    def test_urls_from_title_and_options(self):
        q = {"title": '求面积 <img src="https://p.ananas.chaoxing.com/a.png">',
             "options": 'A <img src="//p.ananas.chaoxing.com/b.png">\nB 12\nC <img src="https://p.ananas.chaoxing.com/a.png">'}
        self.assertEqual(images.image_urls(q), ["https://p.ananas.chaoxing.com/a.png", "https://p.ananas.chaoxing.com/b.png"])
        self.assertEqual(images.text_only('题 <img src="x.png"> 完'), "题 [图片] 完")

    def test_direct_content_parts(self):
        q = {"title": '如图 <img src="https://p.ananas.chaoxing.com/a.png">', "options": ""}
        content, n = images.user_content("题目：" + q["title"], q, session_with())
        self.assertEqual(n, 1)
        self.assertEqual(content[0]["type"], "text")
        self.assertNotIn("<img", content[0]["text"])
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(session_with().get.call_args, None)       # (fresh mock: nothing called)

    def test_download_failure_falls_back_to_text(self):
        q = {"title": '如图 <img src="https://p.ananas.chaoxing.com/a.png">', "options": ""}
        content, n = images.user_content("题目：" + q["title"], q, session_with(status=403))
        self.assertEqual((content, n), ("题目：如图 [图片]", 0))

    def test_transcription_replaces_images_and_is_cached(self):
        asked = []

        def ask(content):
            asked.append(content)
            return "$x^2+1=5$"

        s = session_with()
        text, done = images.with_transcriptions('解方程 <img src="https://p/a.png"> 与 <img src="https://p/a.png">', ask, s)
        self.assertEqual(done, 2)
        self.assertEqual(text, "解方程 【图片内容：$x^2+1=5$】 与 【图片内容：$x^2+1=5$】")
        self.assertEqual(len(asked), 1)                           # same picture: converted once
        self.assertIn("LaTeX", asked[0][0]["text"])


class AIModesTest(unittest.TestCase):
    """AI._query_locked with a fake client: which messages each mode sends."""

    def setUp(self):
        from api.answer import AI

        images._transcribed.clear()
        AI._vision_refused.clear()
        self.AI = AI

    def _ai(self, mode, refuse_images=False):
        ai = self.AI.__new__(self.AI)
        ai.endpoint, ai.key, ai.model, ai.http_proxy = "https://api.deepseek.com/v1", "k", "deepseek-chat", ""
        ai.image_mode = mode
        ai.vision_endpoint = ai.vision_key = ""
        ai.vision_model = "qwen-vl-max"
        ai.min_interval_seconds = 0
        ai.last_request_time = 0
        ai._work_feedback = None
        ai.name = "AI"
        sent = []

        def create(**kwargs):
            sent.append(kwargs)
            user = kwargs["messages"][-1]["content"]
            if isinstance(user, list) and any(p.get("type") == "image_url" for p in user):
                if refuse_images and kwargs["model"] == "deepseek-chat":
                    import openai
                    raise openai.BadRequestError("image_url is not supported", response=mock.Mock(status_code=400), body=None)
                if kwargs["model"] == "qwen-vl-max":
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="一个直角三角形，两直角边 3 和 4"))])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"Answer":["5"]}'))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        ai._make_client = lambda *a, **k: client
        ai._wait_for_interval = lambda: None
        ai._completion_kwargs = lambda **kw: kw
        ai._build_work_feedback_text = lambda: ""
        return ai, sent

    q = {"type": "completion", "title": '斜边长是多少？<img src="https://p.ananas.chaoxing.com/t.png">', "options": ""}

    def _answer(self, ai):
        with mock.patch("api.images.data_url", return_value="data:image/png;base64,AAAA"):
            return ai._query_locked(dict(self.q))

    def test_direct(self):
        ai, sent = self._ai("direct")
        self.assertEqual(self._answer(ai), "5")
        self.assertEqual(sent[0]["messages"][-1]["content"][1]["type"], "image_url")

    def test_transcribe(self):
        ai, sent = self._ai("transcribe")
        self.assertEqual(self._answer(ai), "5")
        self.assertEqual(sent[0]["model"], "qwen-vl-max")                     # image → text first
        final = sent[1]["messages"][-1]["content"]
        self.assertIsInstance(final, str)                                     # the answer model gets text only
        self.assertIn("【图片内容：一个直角三角形，两直角边 3 和 4】", final)

    def test_auto_switches_to_text_when_images_are_refused(self):
        ai, sent = self._ai("auto", refuse_images=True)
        self.assertEqual(self._answer(ai), "5")
        self.assertIn(("https://api.deepseek.com/v1", "deepseek-chat"), self.AI._vision_refused)
        self.assertIn("【图片内容：", sent[-1]["messages"][-1]["content"])
        sent.clear()
        self._answer(ai)                    # next question: no new image attempt; the picture's text is cached
        self.assertEqual(len(sent), 1)
        self.assertIsInstance(sent[0]["messages"][-1]["content"], str)
        self.assertIn("【图片内容：", sent[0]["messages"][-1]["content"])

    def test_off(self):
        ai, sent = self._ai("off")
        self._answer(ai)
        self.assertEqual(len(sent), 1)
        self.assertIn("[图片]", sent[0]["messages"][-1]["content"])


class OptionImagesTest(unittest.TestCase):
    def test_chapter_test_option_keeps_its_image(self):
        from bs4 import BeautifulSoup
        from api.decode import _extract_choices

        li = BeautifulSoup('<li aria-label="A"><img src="https://p.ananas.chaoxing.com/o.png"></li>', "lxml").li
        self.assertEqual(_extract_choices(li), 'A <img src="https://p.ananas.chaoxing.com/o.png">')


class SettingsTest(unittest.TestCase):
    def test_fields_and_secret(self):
        from core import secret
        from ui import advanced

        ids = [f["id"] for g in advanced.GROUPS for f in g["fields"]]
        for field in ("tiku.image_mode", "tiku.vision_model", "tiku.vision_endpoint", "tiku.vision_key"):
            self.assertIn(field, ids)
        self.assertTrue(secret.is_secret("tiku", "vision_key"))


if __name__ == "__main__":
    unittest.main()
