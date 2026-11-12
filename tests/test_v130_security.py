# -*- coding: utf-8 -*-
"""1.3.0 security fixes: Windows' own programs are started by full path, updates only come from
this project's release downloads and only with a checksum."""
import hashlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ui import updater, winsetup


class SystemProgramsTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_full_paths_under_the_windows_folder(self):
        root = Path(os.environ["SystemRoot"]).resolve()
        for name in ("powershell", "cmd", "tasklist", "netstat", "ping"):
            path = Path(winsetup.system_exe(name))
            self.assertTrue(path.is_absolute(), name)
            self.assertTrue(path.exists(), name)
            self.assertIn(root, path.resolve().parents, name)

    def test_no_bare_program_names_are_started(self):
        # A bare name is looked up in the folder of the running exe first (the Downloads folder for
        # the setup program): every call goes through winsetup.system_exe.
        for file in ("ui/winsetup.py", "ui/runtime_deps.py", "installer/setup.py", "gui.py"):
            source = Path(file).read_text(encoding="utf-8")
            for bare in ('["powershell"', '["tasklist"', '["cmd"', "f'cmd ", '"cmd /'):
                self.assertNotIn(bare, source, f"{file}: {bare}")
        # ui/localmodels.py passes names to _run(), which resolves them
        self.assertIn("winsetup.system_exe(args[0])", Path("ui/localmodels.py").read_text(encoding="utf-8"))

    def test_folder_removal_refuses_names_cmd_would_expand(self):
        with mock.patch.object(winsetup.subprocess, "Popen") as popen:
            winsetup.schedule_folder_removal(Path(r"C:\Users\x\%TEMP%\app"))
            popen.assert_not_called()
            winsetup.schedule_folder_removal(Path(r"C:\Users\x\Programs\app"))
            command = popen.call_args.args[0]
        self.assertIn("rmdir /s /q", command)
        if sys.platform == "win32":
            self.assertIn("System32", command)


class FakeResponse(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class UpdateDownloadTest(unittest.TestCase):
    DATA = b"MZ" + b"setup" * 1000
    URL = f"https://github.com/{updater.REPO}/releases/download/v9.9.9/XueXiTong-Plus-Setup-9.9.9.exe"
    NAME = "XueXiTong-Plus-Setup-9.9.9.exe"

    def run_download(self, url=None, name=None, digest=None):
        digest = ("sha256:" + hashlib.sha256(self.DATA).hexdigest()) if digest is None else digest
        worker = updater._DownloadWorker(url or self.URL, name or self.NAME, len(self.DATA), digest)
        done, failed = [], []
        worker.done.connect(done.append)
        worker.failed.connect(failed.append)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(updater.tempfile, "gettempdir", return_value=tmp),                 mock.patch.object(updater, "_request", return_value=FakeResponse(self.DATA)) as request:
            worker.run()
            return done, failed, request.call_count

    def test_a_verified_download_is_accepted(self):
        done, failed, _ = self.run_download()
        self.assertEqual((len(done), failed), (1, []))

    def test_without_a_checksum_nothing_is_installed(self):
        done, failed, _ = self.run_download(digest="")
        self.assertEqual(done, [])
        self.assertIn("校验值", failed[0])

    def test_a_wrong_checksum_is_refused(self):
        done, failed, _ = self.run_download(digest="sha256:" + "0" * 64)
        self.assertEqual(done, [])
        self.assertIn("SHA-256", failed[0])

    def test_other_addresses_are_not_even_requested(self):
        for url in ("https://evil.example/XueXiTong-Plus-Setup-9.9.9.exe",
                    "http://github.com/Kerxs/XueXiTong-Plus/releases/download/v9/XueXiTong-Plus-Setup-9.9.9.exe",
                    "https://github.com/someone-else/XueXiTong-Plus/releases/download/v9/XueXiTong-Plus-Setup-9.9.9.exe"):
            done, failed, requests = self.run_download(url=url)
            self.assertEqual((done, requests), ([], 0), url)
            self.assertTrue(failed)

    def test_a_file_name_with_a_folder_in_it_is_refused(self):
        done, failed, requests = self.run_download(name="..\..\XueXiTong-Plus-Setup-9.9.9.exe")
        self.assertEqual((done, requests), ([], 0))


if __name__ == "__main__":
    unittest.main()
