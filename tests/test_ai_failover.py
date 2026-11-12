# -*- coding: utf-8 -*-
"""Several AI services in order (Issue #1): the primary first, then the backups; a service that
fails is skipped for a while and the next one answers."""
import configparser
import json
import unittest
from unittest import mock

import httpx
import openai

from api.answer import AI
from core import aiproviders, secret


def status_error(cls, code):
    try:
        return cls("boom", response=httpx.Response(code, request=httpx.Request("POST", "https://x/v1")), body=None)
    except TypeError:                       # the slim client on the phone / in the package
        return cls("boom", code)


PRIMARY = {"endpoint": "https://a.example/v1", "key": "ka", "model": "m-a"}
BACKUP1 = {"endpoint": "https://b.example/v1", "key": "kb", "model": "m-b"}
BACKUP2 = {"endpoint": "https://c.example/v1", "key": "kc", "model": "m-c"}


class CoreTest(unittest.TestCase):
    def test_profiles_primary_then_backups_without_duplicates(self):
        conf = {**PRIMARY, "backup_providers": json.dumps([BACKUP1, PRIMARY, BACKUP2])}
        self.assertEqual([p["model"] for p in aiproviders.profiles(conf)], ["m-a", "m-b", "m-c"])

    def test_old_config_without_backups(self):
        self.assertEqual(aiproviders.profiles(PRIMARY), [PRIMARY])
        self.assertEqual(aiproviders.profiles({**PRIMARY, "backup_providers": "not json"}), [PRIMARY])

    def test_editing(self):
        text = aiproviders.dump(aiproviders.save("", -1, "https://b.example/v1/", " kb ", "m-b"))
        self.assertEqual(aiproviders.parse(text), [BACKUP1])
        text = aiproviders.dump(aiproviders.save(text, -1, **{"endpoint": BACKUP2["endpoint"], "key": "kc", "model": "m-c"}))
        text = aiproviders.dump(aiproviders.move(text, 1, -1))
        self.assertEqual([e["model"] for e in aiproviders.parse(text)], ["m-c", "m-b"])
        primary, rest = aiproviders.promote(text, 1, PRIMARY)
        self.assertEqual(primary, BACKUP1)
        self.assertEqual([e["model"] for e in rest], ["m-c", "m-a"])
        self.assertEqual(aiproviders.parse(aiproviders.dump(aiproviders.remove(text, 0))), [BACKUP1])

    def test_problems(self):
        self.assertEqual(aiproviders.problem(**BACKUP1), "")
        self.assertIn("模型", aiproviders.problem("https://b/v1", "k", ""))
        self.assertIn("API Key", aiproviders.problem("https://b/v1", "", "m"))
        self.assertEqual(aiproviders.problem("http://127.0.0.1:8080/v1", "", "m"), "")
        self.assertIn("https", aiproviders.problem("http://127.0.0.1:8080/v1", "", "m", cloud_only=True))
        self.assertIn("备用服务商 2", aiproviders.list_problem(json.dumps([BACKUP1, {"endpoint": "https://x/v1", "key": "k"}])))

    def test_backups_are_encrypted_with_the_other_secrets(self):
        self.assertTrue(secret.is_secret("tiku", "backup_providers"))

    def test_settings_check_reports_a_broken_backup(self):
        from ui import advanced

        values = {"tiku.provider": "AI", "tiku.endpoint": PRIMARY["endpoint"], "tiku.key": "ka", "tiku.model": "m-a",
                  "tiku.backup_providers": json.dumps([{"endpoint": "https://b/v1", "key": "", "model": "m"}])}
        self.assertIn("备用服务商 1", advanced.ai_config_problem(values))
        values["tiku.backup_providers"] = json.dumps([BACKUP1])
        self.assertEqual(advanced.ai_config_problem(values), "")
        self.assertIn("tiku.backup_providers", [f["id"] for f in advanced.fields()])


class FailoverTest(unittest.TestCase):
    def setUp(self):
        AI._down.clear()
        self.ai = AI.__new__(AI)
        self.ai.name = "AI大模型答题"
        self.ai.http_proxy = ""
        self.ai.profiles = [PRIMARY, BACKUP1, BACKUP2]
        self.ai._use(PRIMARY)
        self.logs = mock.patch("api.answer.logger").start()
        self.addCleanup(mock.patch.stopall)

    def run_with(self, outcomes):
        """outcomes: model -> exception to raise or value to return."""
        used = []

        def call():
            used.append(self.ai.model)
            outcome = outcomes[self.ai.model]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return self.ai._failover(call), used

    def test_primary_answers(self):
        self.assertEqual(self.run_with({"m-a": "A"}), ("A", ["m-a"]))

    def test_switches_on_service_errors(self):
        for error in (openai.APIConnectionError(request=httpx.Request("POST", "https://a/v1"))
                      if "request" in openai.APIConnectionError.__init__.__code__.co_varnames
                      else openai.APIConnectionError("down"),
                      status_error(openai.RateLimitError, 429),
                      status_error(openai.InternalServerError, 503),
                      status_error(openai.AuthenticationError, 401),
                      ValueError("未填写 API Key（设置 → 高级选项 → 答题来源）")):
            AI._down.clear()
            result, used = self.run_with({"m-a": error, "m-b": "B"})
            self.assertEqual((result, used), ("B", ["m-a", "m-b"]), type(error).__name__)

    def test_a_refused_question_does_not_switch(self):
        with self.assertRaises(openai.BadRequestError):
            self.run_with({"m-a": status_error(openai.BadRequestError, 400), "m-b": "B"})

    def test_failed_service_is_skipped_next_time(self):
        self.run_with({"m-a": status_error(openai.RateLimitError, 429), "m-b": "B"})
        result, used = self.run_with({"m-a": "A", "m-b": "B"})
        self.assertEqual(used, ["m-b"])                       # m-a waits RETRY_AFTER seconds
        with mock.patch("api.answer.time.time", return_value=10 ** 12):
            self.assertEqual(self.run_with({"m-a": "A"})[1], ["m-a"])     # … then it is tried first again

    def test_wrong_key_is_skipped_for_the_run(self):
        self.run_with({"m-a": status_error(openai.AuthenticationError, 401), "m-b": "B"})
        with mock.patch("api.answer.time.time", return_value=10 ** 12):
            self.assertEqual(self.run_with({"m-a": "A", "m-b": "B"})[1], ["m-b"])

    def test_all_fail_raises_the_last_error(self):
        err = status_error(openai.InternalServerError, 500)
        with self.assertRaises(openai.InternalServerError):
            self.run_with({"m-a": err, "m-b": err, "m-c": err})

    def test_all_down_are_still_tried(self):
        err = status_error(openai.InternalServerError, 500)
        with self.assertRaises(openai.InternalServerError):
            self.run_with({"m-a": err, "m-b": err, "m-c": err})
        self.assertEqual(self.run_with({"m-a": "A", "m-b": "B", "m-c": "C"}), ("A", ["m-a"]))

    def test_one_service_behaves_as_before(self):
        self.ai.profiles = [PRIMARY]
        err = status_error(openai.RateLimitError, 429)
        with self.assertRaises(openai.RateLimitError):
            self.run_with({"m-a": err})

    def test_query_uses_the_backup_end_to_end(self):
        self.ai._lock = __import__("threading").Lock()
        calls = []

        def query_locked(q):
            calls.append(self.ai.model)
            if self.ai.model == "m-a":
                raise status_error(openai.InternalServerError, 502)
            return "答案"

        with mock.patch.object(self.ai, "_query_locked", query_locked):
            self.assertEqual(self.ai._query({"title": "t", "type": "single", "options": "A x"}), "答案")
        self.assertEqual(calls, ["m-a", "m-b"])

    def test_connection_check_passes_when_a_backup_works(self):
        with mock.patch.object(self.ai, "_check_one", side_effect=[False, True, True]):
            self.assertTrue(self.ai.check_llm_connection())
        self.assertEqual(self.ai.model, "m-a")
        with mock.patch.object(self.ai, "_check_one", return_value=False):
            self.assertFalse(self.ai.check_llm_connection())


class ConfigTest(unittest.TestCase):
    def test_init_reads_the_list(self):
        conf = configparser.ConfigParser()
        conf["tiku"] = {**PRIMARY, "backup_providers": json.dumps([BACKUP1]), "http_proxy": "",
                        "min_interval_seconds": "0"}
        ai = AI.__new__(AI)
        ai._conf = conf["tiku"]
        with mock.patch("api.answer.logger"):
            ai._init_tiku()
        self.assertEqual([p["model"] for p in ai.profiles], ["m-a", "m-b"])
        self.assertEqual(ai.model, "m-a")


class PhoneTest(unittest.TestCase):
    def test_phone_start_check_requires_https_backups(self):
        from core import settings

        values = {"tiku.provider": "AI", "tiku.endpoint": "https://api.deepseek.com/v1", "tiku.key": "k",
                  "tiku.model": "deepseek-chat",
                  "tiku.backup_providers": json.dumps([{"endpoint": "http://192.168.1.2:8000/v1", "key": "k", "model": "m"}])}
        self.assertIn("https", settings._cloud_problem(values))
        values["tiku.backup_providers"] = json.dumps([BACKUP1])
        self.assertEqual(settings._cloud_problem(values), "")

    def test_phone_schema_has_the_control_and_keeps_the_value(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "android/app/src/main/python/xxtplus_android.py"
        spec = importlib.util.spec_from_file_location("xxtplus_android_backup", path)
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        schema = json.loads(bridge.settings_schema())
        types = [f["type"] for g in schema["groups"] for f in g["fields"]]
        self.assertIn("backupproviders", types)
        from ui import advanced
        self.assertIn("tiku.backup_providers", [f["id"] for f in advanced.fields()])   # loaded and saved with the rest


if __name__ == "__main__":
    unittest.main()
