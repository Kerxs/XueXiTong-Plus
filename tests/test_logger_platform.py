"""api/logger.py on platforms without multiprocessing (Android) and secret redaction."""

import importlib
import io
import unittest
from unittest import mock


class LoggerWithoutMultiprocessingTest(unittest.TestCase):
    """Regression: the phone crashed on `import main` because loguru enqueue=True needs sem_open."""

    def test_import_works_when_multiprocessing_queues_fail(self):
        import multiprocessing

        def broken(*_a, **_k):
            raise OSError(38, "Function not implemented")

        with mock.patch.object(multiprocessing, "SimpleQueue", broken):
            import api.logger as log

            log = importlib.reload(log)
            self.assertFalse(log.can_enqueue())
            buf = io.StringIO()
            with mock.patch.object(log, "tqdm_stream", buf):
                log.logger.info("hello from android")
                log.logger.complete()
            self.assertIn("hello from android", buf.getvalue())
        importlib.reload(log)  # back to the normal (enqueue) setup for other tests

    def test_desktop_keeps_enqueue(self):
        import api.logger as log

        self.assertTrue(log.can_enqueue())


class RedactionTest(unittest.TestCase):
    def setUp(self):
        import api.logger as log

        self.log = log
        self.saved = set(log._secrets)
        log._secrets.clear()

    def tearDown(self):
        self.log._secrets.clear()
        self.log._secrets.update(self.saved)

    def test_registered_secrets_are_masked_in_logs(self):
        log = self.log
        log.register_secret("sk-abcdef123456")
        log.register_secret("xxx")         # template placeholder: ignored
        log.register_secret("12")          # too short to be a secret: ignored
        buf = io.StringIO()
        with mock.patch.object(log, "tqdm_stream", buf):
            log.logger.warning("request with key sk-abcdef123456 failed, xxx 12")
            log.logger.complete()
        out = buf.getvalue()
        self.assertNotIn("sk-abcdef123456", out)
        self.assertIn("***", out)
        self.assertIn("xxx 12", out)

    def test_config_secrets_registered(self):
        import main

        main.register_config_secrets(
            {"username": "13800001111", "password": "p@ssw0rd!"},
            {"tokens": "tokA1234,tokB5678", "key": "sk-zzzz9999", "go_authorization": "auth-1111"},
            {"url": "https://sctapi.ftqq.com/SCTkey123.send"},
        )
        text = self.log.redact("13800001111 p@ssw0rd! tokB5678 sk-zzzz9999 auth-1111 https://sctapi.ftqq.com/SCTkey123.send")
        for secret in ("13800001111", "p@ssw0rd!", "tokB5678", "sk-zzzz9999", "auth-1111", "SCTkey123"):
            self.assertNotIn(secret, text)

    def test_push_messages_are_redacted(self):
        from api.notification import NotificationService

        sent = []

        class Fake(NotificationService):
            def _init_service(self):
                pass

            def _send(self, message):
                sent.append(message)

        svc = Fake()
        svc.disabled = False
        self.log.register_secret("p@ssw0rd!")
        svc.send("出现错误 password=p@ssw0rd!")
        self.assertEqual(sent, ["出现错误 password=***"])


if __name__ == "__main__":
    unittest.main()
