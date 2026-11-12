# -*- coding: utf-8 -*-
"""Setting up AI with less to learn: only models that can answer are listed, one tiny test request,
rarely needed options folded away, the legacy 硅基流动 entry only for whoever uses it."""
import io
import json
import unittest
import urllib.error
from unittest import mock

from ui import advanced, cloudmodels


class ChatModelsTest(unittest.TestCase):
    def test_non_chat_models_are_left_out(self):
        models = ["qwen3.7-text-embedding", "qwen3.7-text-rerank", "qwen-plus", "deepseek-chat", "cosyvoice-v2",
                  "qwen-vl-max", "wanx2.1-t2i-turbo", "glm-4-flash", "whisper-1", "text-embedding-3-small", "gpt-4o"]
        keep, hidden = cloudmodels.chat_models(models)
        self.assertEqual(keep, ["qwen-plus", "deepseek-chat", "qwen-vl-max", "glm-4-flash", "gpt-4o"])
        self.assertEqual(hidden, 6)


class TestChatTest(unittest.TestCase):
    def answer(self, payload=None, error=None):
        opener = mock.Mock()
        if error is not None:
            opener.open.side_effect = error
        else:
            resp = mock.MagicMock()
            resp.__enter__.return_value.read.return_value = json.dumps(payload).encode()
            opener.open.return_value = resp
        with mock.patch.object(cloudmodels, "_opener", return_value=opener):
            return cloudmodels.test_chat("https://api.example.com/v1", "sk-x", "m")

    def test_answer_is_ok(self):
        self.assertEqual(self.answer({"choices": [{"message": {"content": "2"}}]}), "")

    def test_reasons(self):
        def http(code, body=b'{"error":{"message":"bad"}}'):
            return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(body))
        self.assertIn("API Key", self.answer(error=http(401)))
        self.assertIn("余额", self.answer(error=http(402)))
        self.assertIn("模型", self.answer(error=http(404)))
        self.assertIn("bad", self.answer(error=http(400)))
        self.assertIn("连不上", self.answer(error=urllib.error.URLError("refused")))
        self.assertIn("没有返回", self.answer({"choices": []}))

    def test_missing_inputs_are_said_before_any_request(self):
        self.assertIn("服务商", cloudmodels.test_chat("", "k", "m"))
        self.assertIn("模型", cloudmodels.test_chat("https://a/v1", "k", ""))
        self.assertIn("API Key", cloudmodels.test_chat("https://a/v1", "", "m"))


class FieldsTest(unittest.TestCase):
    def fields(self):
        return {f["id"] if f["key"] else f["type"]: f for g in advanced.GROUPS for f in g["fields"]}

    def test_rarely_needed_options_are_folded(self):
        f = self.fields()
        for fid in ("tiku.image_mode", "tiku.vision_model", "tiku.http_proxy", "tiku.ai_batch", "localmodels"):
            self.assertTrue(f[fid].get("more"), fid)
        for fid in ("tiku.key", "tiku.model", "backupproviders", "aitest"):
            self.assertFalse(f[fid].get("more"), fid)
        self.assertIn("more", advanced.DISPLAY_ONLY)

    def test_address_only_for_unknown_services(self):
        show = self.fields()["tiku.endpoint"]["show"]
        self.assertIn({"key": "tiku.endpoint", "unlisted": True}, show)

    def test_siliconflow_is_legacy(self):
        options = {o["value"]: o for o in advanced.TIKU_PROVIDERS}
        self.assertTrue(options["SiliconFlow"].get("legacy"))
        self.assertEqual(options["AI"]["label"], "AI 大模型")

    def test_values_are_unchanged(self):
        # display-only rows store nothing; the stored fields and their defaults stay as they were
        ids = [f["id"] for f in advanced.fields()]
        for fid in ("tiku.endpoint", "tiku.key", "tiku.model", "tiku.image_mode", "tiku.ai_batch"):
            self.assertIn(fid, ids)


class PhoneBridgeTest(unittest.TestCase):
    def bridge(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "android/app/src/main/python/xxtplus_android.py"
        spec = importlib.util.spec_from_file_location("xxtplus_android_simple", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_list_models_hides_non_chat(self):
        bridge = self.bridge()
        with mock.patch.object(cloudmodels, "list_models", return_value=["a-embedding", "deepseek-chat"]):
            result = json.loads(bridge.list_models("https://a/v1", "k", ""))
        self.assertEqual((result["models"], result["hidden"]), (["deepseek-chat"], 1))

    def test_test_ai(self):
        bridge = self.bridge()
        with mock.patch.object(cloudmodels, "test_chat", return_value=""):
            self.assertEqual(bridge.test_ai("https://a/v1", "k", "m"), "")

    def test_schema_has_the_new_rows(self):
        schema = json.loads(self.bridge().settings_schema())
        types = [f["type"] for g in schema["groups"] for f in g["fields"]]
        self.assertIn("more", types)
        self.assertIn("aitest", types)


if __name__ == "__main__":
    unittest.main()
