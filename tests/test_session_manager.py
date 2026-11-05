# -*- coding: utf-8 -*-
"""SessionManager keeps one requests.Session (it used to rebuild it on every get_session())."""
import unittest
from unittest import mock

from api import base


class SessionManagerTest(unittest.TestCase):
    def setUp(self):
        self._saved = base.SessionManager._instance
        base.SessionManager._instance = None

    def tearDown(self):
        base.SessionManager._instance = self._saved

    def test_one_session_and_cookies_read_once(self):
        with mock.patch.object(base, "use_cookies", return_value={"_uid": "1"}) as read:
            first = base.SessionManager.get_session()
            for _ in range(5):
                self.assertIs(base.SessionManager.get_session(), first)
            self.assertEqual(read.call_count, 1)
            self.assertEqual(first.cookies.get("_uid"), "1")

    def test_update_cookies_still_refreshes_the_shared_session(self):
        with mock.patch.object(base, "use_cookies", return_value={}):
            session = base.SessionManager.get_session()
        with mock.patch.object(base, "use_cookies", return_value={"_uid": "2"}):
            base.SessionManager.update_cookies()
        self.assertIs(base.SessionManager.get_session(), session)
        self.assertEqual(session.cookies.get("_uid"), "2")


if __name__ == "__main__":
    unittest.main()
