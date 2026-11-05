# -*- coding: utf-8 -*-
"""卸载学习通PLUS.exe in the install folder, and repairing a lost 应用和功能 entry.

The registry is mocked: these tests never touch the real HKCU uninstall key.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ui import winsetup


class UninstallerNameTest(unittest.TestCase):
    def test_launched_as_uninstaller(self):
        self.assertTrue(winsetup.launched_as_uninstaller(r"C:\x\学习通PLUS\卸载学习通PLUS.exe"))
        self.assertFalse(winsetup.launched_as_uninstaller(r"C:\x\学习通PLUS\学习通PLUS.exe"))
        self.assertFalse(winsetup.launched_as_uninstaller(r"C:\x\python.exe"))


class UninstallCommandsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_uses_the_uninstaller_when_present(self):
        (self.dir / winsetup.UNINSTALL_EXE).write_bytes(b"MZ")
        loud, quiet = winsetup.uninstall_commands(self.dir)
        self.assertEqual(loud, f"\"{self.dir / winsetup.UNINSTALL_EXE}\"")
        self.assertEqual(quiet, f"\"{self.dir / winsetup.UNINSTALL_EXE}\" --quiet")

    def test_falls_back_to_the_app(self):
        loud, quiet = winsetup.uninstall_commands(self.dir)
        self.assertEqual(loud, f"\"{self.dir / winsetup.APP_EXE}\" --uninstall")
        self.assertTrue(quiet.endswith("--uninstall --quiet"))


@unittest.skipUnless(sys.platform == "win32", "Windows only")
class EnsureRegisteredTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / winsetup.UNINSTALL_EXE).write_bytes(b"MZ")
        (self.dir / "data.bin").write_bytes(b"x" * 4096)
        self.register = mock.patch.object(winsetup, "register").start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(self.tmp.cleanup)

    def _state(self, info, uninstall=""):
        mock.patch.object(winsetup, "read_installed", return_value=info).start()
        mock.patch.object(winsetup, "_uninstall_string", return_value=uninstall).start()

    def test_not_an_installed_folder(self):
        self._state(None)
        self.assertFalse(winsetup.ensure_registered(self.dir, "1.2.4"))
        self.register.assert_not_called()

    def test_missing_entry_is_written(self):
        (self.dir / winsetup.MARKER).write_text("1.2.4")
        self._state(None)
        self.assertTrue(winsetup.ensure_registered(self.dir, "1.2.4"))
        args = self.register.call_args.args
        self.assertEqual((args[0], args[1]), (self.dir, "1.2.4"))
        self.assertGreaterEqual(args[2], 4096)

    def test_old_entry_is_updated(self):
        (self.dir / winsetup.MARKER).write_text("1.2.4")
        self._state({"version": "1.2.3", "location": str(self.dir)},
                    f"\"{self.dir / winsetup.APP_EXE}\" --uninstall")
        self.assertTrue(winsetup.ensure_registered(self.dir, "1.2.4"))

    def test_current_entry_is_left_alone(self):
        (self.dir / winsetup.MARKER).write_text("1.2.4")
        self._state({"version": "1.2.4", "location": str(self.dir).upper()},
                    winsetup.uninstall_commands(self.dir)[0])
        self.assertFalse(winsetup.ensure_registered(self.dir, "1.2.4"))
        self.register.assert_not_called()


if __name__ == "__main__":
    unittest.main()
