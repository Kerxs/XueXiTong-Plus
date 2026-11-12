# -*- coding: utf-8 -*-
"""A config.ini written by 1.2.9 keeps working in 1.3.0: nothing the user set is lost, new options
get their defaults, and settings the app does not know are left in the file."""
import configparser
import tempfile
import unittest
from pathlib import Path
from unittest import mock

OLD = """[common]
use_cookies = false
username = 13800000000
password = old-plain-password
course_list = 2151141,189191
speed = 1.5
jobs = 3
notopen_action = continue
retry_interval = 8
auto_documents = false
auto_homework = true
homework_submit = false
watch_activities = true
telemetry = false
some_future_option = keep-me

[tiku]
provider = AI
endpoint = https://api.deepseek.com/v1
key = sk-old-key
model = deepseek-chat
submit = true
cover_rate = 0.8
min_interval_seconds = 3
http_proxy =

[notification]
provider = Bark
url = https://api.day.app/abc

[my_own_section]
note = left alone
"""


class OldConfigTest(unittest.TestCase):
    def setUp(self):
        from PySide6.QtCore import QCoreApplication, QSettings
        import ui.controller as ctl

        self.ctl_module = ctl
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        self.config = data / "config.ini"
        self.config.write_text(OLD, encoding="utf-8")
        self.patches = [mock.patch.object(ctl, "DATA_DIR", data), mock.patch.object(ctl, "CONFIG_PATH", self.config)]
        for p in self.patches:
            p.start()
        QCoreApplication.setOrganizationName("ChaoxingDesktopOldConfigTest")
        QSettings().clear()
        QSettings().setValue("telemetry/asked", "true")      # the one-time switch to "on" has its own test
        self.c = ctl.AppController()

    def tearDown(self):
        self.c.shutdown()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_values_are_read_as_the_user_left_them(self):
        c = self.c
        self.assertEqual((c.username, c.password), ("13800000000", "old-plain-password"))
        self.assertEqual(c.property("courseList") if c.property("courseList") is not None else c._values["course_list"],
                         "2151141,189191")
        self.assertEqual((c.jobs, c._values["notopen_action"], c._values["retry_interval"]), (3, "continue", 8.0))
        adv = c._advanced
        self.assertEqual((adv["common.auto_documents"], adv["common.homework_submit"]), ("false", "false"))
        self.assertEqual((adv["tiku.provider"], adv["tiku.model"], adv["tiku.cover_rate"]), ("AI", "deepseek-chat", "0.8"))
        self.assertEqual((adv["notification.provider"], adv["notification.url"]), ("Bark", "https://api.day.app/abc"))
        self.assertFalse(c.telemetryEnabled)                   # an explicit "false" stays off once asked

    def test_new_options_get_their_defaults(self):
        adv = self.c._advanced
        self.assertEqual(adv["common.auto_live"], "true")
        self.assertEqual(adv["tiku.ai_batch"], "5")
        self.assertEqual(adv["tiku.image_mode"], "auto")

    def test_saving_keeps_everything_and_encrypts_the_secrets(self):
        from core import secret

        self.c.setAdvanced("common.auto_live", "false")
        self.assertTrue(self.c.saveConfig())
        text = self.config.read_text(encoding="utf-8")
        raw = configparser.ConfigParser(interpolation=None)
        raw.read_string(text)
        self.assertEqual(raw["common"]["some_future_option"], "keep-me")       # unknown key
        self.assertEqual(raw["my_own_section"]["note"], "left alone")          # unknown section
        self.assertEqual(raw["common"]["auto_live"], "false")
        self.assertEqual(raw["common"]["jobs"], "3")
        if secret.available():
            for plain in ("old-plain-password", "sk-old-key", "13800000000", "api.day.app/abc"):
                self.assertNotIn(plain, text)
        read = secret.read_config(self.config)
        self.assertEqual((read["common"]["password"], read["tiku"]["key"]), ("old-plain-password", "sk-old-key"))

    def test_the_task_process_reads_it_too(self):
        import main

        with mock.patch.object(main.sys, "argv", ["main.py", "-c", str(self.config)]):
            common, tiku, notification, _path = main.init_config()
        self.assertEqual(common["username"], "13800000000")
        self.assertEqual(int(common["jobs"]), 3)
        self.assertEqual(tiku["provider"], "AI")
        self.assertEqual(main.str_to_bool(common.get("telemetry", True)), False)
        self.assertEqual(main.str_to_bool(common.get("auto_live", True)), True)   # not in the file: default on


if __name__ == "__main__":
    unittest.main()
