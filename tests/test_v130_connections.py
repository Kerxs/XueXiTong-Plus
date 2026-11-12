# -*- coding: utf-8 -*-
"""After an outage or a change of network the pooled connections are dropped (1.3.0): on the phone
they are dead after the power-saving sleep or a Wi-Fi <-> mobile data switch, and each one used to
cost a timeout and a retry before it was replaced."""
import unittest
from unittest import mock

from api import net
from api.base import SessionManager


class ResetConnectionsTest(unittest.TestCase):
    def test_pools_are_closed_and_the_session_stays(self):
        session = SessionManager.get_session()
        session.cookies.set("probe", "1")
        closed = []
        with mock.patch.object(type(session.adapters["https://"]), "close", lambda self: closed.append(self)):
            SessionManager.reset_connections()
        self.assertEqual(len(closed), len(session.adapters))
        self.assertIs(SessionManager.get_session(), session)          # same session: cookies, headers
        self.assertEqual(session.cookies.get("probe"), "1")


    def test_a_failing_close_is_ignored(self):
        session = SessionManager.get_session()

        def boom(self):
            raise OSError("closed twice")

        with mock.patch.object(type(session.adapters["https://"]), "close", boom):
            SessionManager.reset_connections()        # no exception

    def test_network_recovery_drops_the_old_connections(self):
        answers = iter([False, False, True])
        with mock.patch.object(net, "reset_connections") as reset, mock.patch.object(net, "logger"), \
                mock.patch.object(net.pause, "wait_if_paused"):
            waited = net.wait_for_network(sleep=lambda s: None, check=lambda: next(answers))
        self.assertGreaterEqual(waited, 0)
        reset.assert_called_once()

    def test_no_outage_no_reset(self):
        with mock.patch.object(net, "reset_connections") as reset:
            self.assertEqual(net.wait_for_network(check=lambda: True), 0.0)
        reset.assert_not_called()

    def test_the_phone_bridge_calls_it(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "android/app/src/main/python/xxtplus_android.py"
        spec = importlib.util.spec_from_file_location("xxtplus_android_conn", path)
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        with mock.patch.object(net, "reset_connections") as reset:
            bridge.network_changed()
        reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
