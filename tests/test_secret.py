# -*- coding: utf-8 -*-
"""Account data at rest is encrypted (core/secret.py): config.ini secrets and saved cookies."""
import configparser
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import secret

KEY = "11" * 32


class KeyBackendTest(unittest.TestCase):
    """The Android path (data key from the Keystore via XXTPLUS_DATA_KEY); runs everywhere."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {secret.KEY_ENV: KEY})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_round_trip_and_random_nonce(self):
        a, b = secret.protect("p@ss%word"), secret.protect("p@ss%word")
        self.assertTrue(a.startswith(secret.PREFIX))
        self.assertNotEqual(a, b)
        self.assertNotIn("p@ss", a)
        self.assertEqual(secret.unprotect(a), "p@ss%word")

    def test_wrong_key_or_tampering_reads_as_empty(self):
        value = secret.protect("secret")
        with mock.patch.dict(os.environ, {secret.KEY_ENV: "22" * 32}):
            with self.assertRaises(secret.SecretError):
                secret.unprotect(value)
            self.assertEqual(secret.reveal(value), "")
        damaged = value[:-4] + ("AAAA" if not value.endswith("AAAA") else "BBBB")
        self.assertEqual(secret.reveal(damaged), "")

    def test_plain_and_empty_unchanged(self):
        self.assertEqual(secret.unprotect("plain"), "plain")
        self.assertEqual(secret.protect(""), "")


class ConfigFileTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {secret.KEY_ENV: KEY})
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.ini"
        self.path.write_text(
            "[common]\nusername = 13800000000\npassword = pa%ss\nspeed = 1\n"
            "[tiku]\nprovider = AI\nkey = sk-abc\ntokens = t1,t2\nendpoint = https://api.deepseek.com/v1\n"
            "[notification]\nprovider = Bark\nurl = https://api.day.app/KEY123\n", encoding="utf-8")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_migrate_encrypts_only_secrets(self):
        self.assertTrue(secret.needs_migration(self.path))
        self.assertTrue(secret.migrate(self.path))
        text = self.path.read_text(encoding="utf-8")
        for plain in ("13800000000", "pa%ss", "sk-abc", "t1,t2", "KEY123"):
            self.assertNotIn(plain, text)
        for kept in ("speed = 1", "provider = AI", "https://api.deepseek.com/v1"):
            self.assertIn(kept, text)
        self.assertFalse(secret.needs_migration(self.path))
        config = secret.read_config(self.path)
        self.assertEqual(config["common"]["password"], "pa%ss")
        self.assertEqual(config["tiku"]["key"], "sk-abc")
        self.assertEqual(config["notification"]["url"], "https://api.day.app/KEY123")

    def test_task_code_reads_decrypted_values(self):
        secret.migrate(self.path)
        import main

        common, tiku, notification = main.load_config_from_file(str(self.path))
        self.assertEqual((common["username"], common["password"]), ("13800000000", "pa%ss"))
        self.assertEqual(tiku["key"], "sk-abc")
        self.assertEqual(notification["url"], "https://api.day.app/KEY123")

    def test_unreadable_value_becomes_empty(self):
        secret.migrate(self.path)
        with mock.patch.dict(os.environ, {secret.KEY_ENV: "33" * 32}):
            config = configparser.ConfigParser(interpolation=None)
            config.read(self.path, encoding="utf-8")
            self.assertEqual(secret.decrypt_config(config)[:1], ["common.username"])
            self.assertEqual(config["common"]["password"], "")

    def test_template_placeholder_not_encrypted(self):
        self.path.write_text("[common]\nusername = xxx\npassword = xxx\n", encoding="utf-8")
        self.assertFalse(secret.needs_migration(self.path))


class CookiesTest(unittest.TestCase):
    def test_saved_encrypted_and_plain_import_converted(self):
        from api import cookies
        from api.config import GlobalConst as gc

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {secret.KEY_ENV: KEY}), \
                mock.patch.object(gc, "COOKIES_PATH", os.path.join(tmp, "cookies.txt")):
            Path(gc.COOKIES_PATH).write_text("UID=1;_d=abc", encoding="utf-8")     # user-provided, plain
            self.assertEqual(cookies.use_cookies(), {"UID": "1", "_d": "abc"})
            stored = Path(gc.COOKIES_PATH).read_text(encoding="utf-8")
            self.assertTrue(stored.startswith(secret.PREFIX))                       # now encrypted
            self.assertEqual(cookies.use_cookies(), {"UID": "1", "_d": "abc"})

            session = mock.Mock()
            session.cookies.items.return_value = [("UID", "2"), ("vc3", "x")]
            cookies.save_cookies(session)
            self.assertNotIn("vc3", Path(gc.COOKIES_PATH).read_text(encoding="utf-8"))
            self.assertEqual(cookies.use_cookies(), {"UID": "2", "vc3": "x"})


@unittest.skipUnless(sys.platform == "win32", "DPAPI is Windows only")
class DpapiTest(unittest.TestCase):
    def test_round_trip(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(secret.KEY_ENV, None)
            self.assertEqual(secret.backend(), "dpapi")
            value = secret.protect("密码 123")
            self.assertTrue(value.startswith(secret.PREFIX))
            self.assertEqual(secret.unprotect(value), "密码 123")


if __name__ == "__main__":
    unittest.main()
