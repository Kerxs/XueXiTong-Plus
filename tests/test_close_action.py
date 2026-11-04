# -*- coding: utf-8 -*-
"""关闭窗口时: ask (default) / tray / quit, and migration from the old yes/no setting."""
import unittest
from unittest import mock

from PySide6.QtCore import QCoreApplication, QSettings


class CloseActionTest(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        QCoreApplication.setOrganizationName("ChaoxingDesktopCloseActionTest")
        QSettings().clear()

    def tearDown(self):
        QSettings().clear()

    def _tray(self, available=True):
        from ui import tray

        t = tray.Tray.__new__(tray.Tray)
        t._settings = QSettings()
        t._available = available
        # Property signals need the QObject initialised.
        tray.QObject.__init__(t)
        return t

    def test_default_is_ask(self):
        self.assertEqual(self._tray().closeAction, "ask")

    def test_old_setting_off_means_quit(self):
        QSettings().setValue("ui/closeToTray", "false")
        self.assertEqual(self._tray().closeAction, "quit")
        QSettings().setValue("ui/closeToTray", "true")      # default-on users are asked once
        self.assertEqual(self._tray().closeAction, "ask")

    def test_remembered_choice_and_no_tray(self):
        t = self._tray()
        t.closeAction = "tray"
        self.assertEqual(t.closeAction, "tray")
        self.assertTrue(t.closeToTray)
        t.closeAction = "bogus"                              # ignored
        self.assertEqual(t.closeAction, "tray")
        self.assertEqual(self._tray(available=False).closeAction, "quit")   # nothing to hide to


if __name__ == "__main__":
    unittest.main()
