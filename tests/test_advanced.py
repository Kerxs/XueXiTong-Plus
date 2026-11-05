import configparser
import unittest
from pathlib import Path

from ui import advanced

TEMPLATE = Path(__file__).resolve().parent.parent / "config_template.ini"


def template() -> configparser.ConfigParser:
    config = configparser.ConfigParser(interpolation=None)
    config.read(TEMPLATE, encoding="utf-8")
    return config


class AdvancedOptionsTest(unittest.TestCase):
    def test_fields_unique_and_typed(self):
        ids = [f["id"] for f in advanced.fields()]
        self.assertEqual(len(ids), len(set(ids)))
        types = {"providers", "switch", "percent", "number", "choice", "text", "secret", "hidden"}
        for f in advanced.fields():
            self.assertIn(f["type"], types, f["id"])
            if f["type"] == "number":
                self.assertLessEqual(f["min"], f["max"])

    def test_show_conditions_point_at_fields(self):
        ids = {f["id"] for f in advanced.fields()}
        for group in advanced.GROUPS:
            for f in group["fields"]:
                if "show" in f:
                    conditions = f["show"] if isinstance(f["show"], list) else [f["show"]]
                    for condition in conditions:
                        self.assertIn(condition["key"], ids, f)

    def test_provider_options_exist_in_worker(self):
        import api.answer as answer
        import api.notification as notification
        for option in advanced.TIKU_PROVIDERS:
            self.assertTrue(hasattr(answer, option["value"]), option)
        for option in advanced.NOTIFY_PROVIDERS:
            if option["value"]:
                self.assertTrue(hasattr(notification, option["value"]), option)

    def test_template_round_trip_is_unchanged(self):
        config = template()
        before = {s: dict(config[s]) for s in config.sections()}
        before["notification"]["tg_chat_id"] = ""   # template placeholder XXXXXX is cleared
        advanced.write_values(config, advanced.read_values(config))
        self.assertEqual({s: dict(config[s]) for s in config.sections()}, before)

    def test_placeholder_reads_empty(self):
        values = advanced.read_values(template())
        self.assertEqual(values["notification.tg_chat_id"], "")
        self.assertEqual(values["tiku.provider"], "TikuAdapter")
        self.assertEqual(values["tiku.cover_rate"], "0.75")

    def test_defaults_not_added_but_changes_are(self):
        config = configparser.ConfigParser(interpolation=None)
        values = advanced.read_values(config)
        values["common.work_redo_enabled"] = "false"          # the default is on (答错后自动重做)
        advanced.write_values(config, values)
        self.assertEqual(config["common"]["work_redo_enabled"], "false")
        self.assertFalse(config.has_option("common", "work_max_retries"))   # still the default
        self.assertFalse(config.has_option("tiku", "submit"))

    def test_answer_mode(self):
        self.assertEqual(advanced.answer_mode(""), "none")
        self.assertEqual(advanced.answer_mode("TikuYanxi,TikuGo"), "tiku")
        self.assertEqual(advanced.answer_mode("AI"), "ai")
        self.assertEqual(advanced.answer_mode("TikuYanxi, SiliconFlow"), "both")

    def test_apply_answer_mode_keeps_fitting_picks(self):
        self.assertEqual(advanced.apply_answer_mode("TikuGo,AI", "tiku"), "TikuGo")
        self.assertEqual(advanced.apply_answer_mode("TikuGo,AI", "ai"), "AI")
        self.assertEqual(advanced.apply_answer_mode("TikuGo", "both"), "TikuGo,AI")        # default AI added
        self.assertEqual(advanced.apply_answer_mode("SiliconFlow", "both"), "TikuYanxi,SiliconFlow")
        self.assertEqual(advanced.apply_answer_mode("TikuGo", "ai"), "AI")
        self.assertEqual(advanced.apply_answer_mode("TikuGo,AI", "none"), "")
        for mode in ("tiku", "ai", "both"):
            self.assertEqual(advanced.answer_mode(advanced.apply_answer_mode("", mode)), mode)

    def test_order_providers_puts_tiku_first(self):
        self.assertEqual(advanced.order_providers(["AI", "TikuGo", "SiliconFlow", "TikuYanxi"]),
                         "TikuGo,TikuYanxi,AI,SiliconFlow")

    def test_ai_config_problem(self):
        ok = {"tiku.provider": "AI", "tiku.endpoint": "https://api.example.com/v1", "tiku.model": "m", "tiku.key": "k"}
        self.assertEqual(advanced.ai_config_problem(ok), "")
        self.assertEqual(advanced.ai_config_problem({"tiku.provider": "TikuYanxi"}), "")
        self.assertIn("接口地址", advanced.ai_config_problem({**ok, "tiku.endpoint": ""}))
        self.assertIn("http", advanced.ai_config_problem({**ok, "tiku.endpoint": "api.example.com/v1"}))
        self.assertIn("/chat/completions", advanced.ai_config_problem({**ok, "tiku.endpoint": "https://x/v1/chat/completions"}))
        self.assertIn("模型", advanced.ai_config_problem({**ok, "tiku.model": " "}))
        self.assertIn("API Key", advanced.ai_config_problem({**ok, "tiku.key": ""}))
        # A model server on this machine needs no key.
        self.assertEqual(advanced.ai_config_problem({**ok, "tiku.key": "", "tiku.endpoint": "http://127.0.0.1:9931/v1"}), "")
        self.assertIn("硅基流动", advanced.ai_config_problem({"tiku.provider": "SiliconFlow", "tiku.siliconflow_key": ""}))

    def test_every_worker_key_has_a_control(self):
        import re
        root = Path(__file__).resolve().parent.parent
        pattern = re.compile(r"(?:common_config|tiku_config|_conf)(?:\.get)?[\[(][\"']([a-z_]+)[\"']")
        read = set()
        for path in [root / "main.py", *(root / "api").glob("*.py")]:
            read |= set(pattern.findall(path.read_text(encoding="utf-8")))
        offered = {f["key"] for f in advanced.fields()}
        elsewhere = {  # 运行面板 / 设置页其它卡片
            "username", "password", "use_cookies", "course_list", "speed", "jobs", "notopen_action",
            "retry_interval", "add_learning_count", "target_count",
        }
        console_only = {"manual_mode_default", "manual_mode_separator"}  # 手动答题需要控制台输入
        self.assertEqual(read - offered - elsewhere - console_only, set())

    def test_like_switches_parse_false(self):
        from api.answer import TikuLike
        like = TikuLike()
        like._conf = {"likeapi_search": "false", "likeapi_vision": "false", "likeapi_retry": "false", "likeapi_retry_times": "2"}
        like.load_config()
        self.assertEqual((like._search, like._vision, like._retry, like._retry_times), (False, False, False, 2))
        like._conf = {}
        like.load_config()
        self.assertEqual((like._search, like._vision, like._retry), (False, True, True))

    def test_judgement_word_lists(self):
        from api.answer_check import check_judgement
        values = advanced.read_values(template())
        true_words = values["tiku.true_list"].split(",")
        false_words = values["tiku.false_list"].split(",")
        defaults = {f["id"]: f["default"] for f in advanced.fields()}
        self.assertEqual(values["tiku.true_list"], defaults["tiku.true_list"])     # template == 高级选项
        self.assertEqual(values["tiku.false_list"], defaults["tiku.false_list"])
        self.assertFalse({w.lower() for w in true_words} & {w.lower() for w in false_words})
        for word in true_words:
            self.assertEqual(check_judgement(word, true_words, false_words), 1, word)
            self.assertEqual(check_judgement(word.upper(), true_words, false_words), 1, word)
        for word in false_words:
            self.assertEqual(check_judgement(word, true_words, false_words), 0, word)
        # Whole-word match only: a longer answer containing "n" or "t" is not a judgement.
        self.assertEqual(check_judgement("not sure", true_words, false_words), -1)

    def test_normalize(self):
        self.assertEqual(advanced.normalize("x", True), "true")
        self.assertEqual(advanced.normalize("x", False), "false")
        self.assertEqual(advanced.normalize("x", ["TikuYanxi", " AI ", ""]), "TikuYanxi,AI")
        self.assertEqual(advanced.normalize("x", 0.85), "0.85")
        self.assertEqual(advanced.normalize("x", "abc"), "abc")


if __name__ == "__main__":
    unittest.main()
