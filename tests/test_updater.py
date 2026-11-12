import hashlib
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from ui import updater as upd

app = QCoreApplication.instance() or QCoreApplication([])


class VersionTestCase(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(upd.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(upd.parse_version("1.2"), (1, 2, 0))
        self.assertEqual(upd.parse_version("nonsense"), (0,))
        self.assertTrue(upd.is_newer("v1.0.1", "1.0.0"))
        self.assertTrue(upd.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(upd.is_newer("1.0.0", "1.0.0"))
        self.assertFalse(upd.is_newer("0.9", "1.0.0"))

    def test_pick_asset(self):
        release = {"assets": [
            {"name": "XueXiTong-Plus-Windows-1.1.0.zip"},
            {"name": "XueXiTong-Plus-Setup-1.1.0.exe", "browser_download_url": "x"},
        ]}
        self.assertEqual(upd.pick_asset(release)["name"], "XueXiTong-Plus-Setup-1.1.0.exe")
        # What GitHub turns a Chinese-named asset into.
        self.assertEqual(upd.pick_asset({"assets": [{"name": "PLUS-Setup-1.0.0.exe"}]})["name"], "PLUS-Setup-1.0.0.exe")
        self.assertIsNone(upd.pick_asset({"assets": [{"name": "other.exe"}]}))


class ReleaseHandlingTestCase(unittest.TestCase):
    def setUp(self):
        self.u = upd.Updater("1.0.0")

    def test_newer_release_is_available(self):
        seen = []
        self.u.updateAvailable.connect(lambda: seen.append(True))
        self.u._on_release({"tag_name": "v1.1.0", "body": "notes",
                            "assets": [{"name": "XueXiTong-Plus-Setup-1.1.0.exe", "size": 10, "browser_download_url": "x"}]})
        self.assertEqual(self.u.state, "available")
        self.assertEqual(self.u.latestVersion, "1.1.0")
        self.assertEqual(seen, [True])

    def test_same_version_is_latest(self):
        self.u._silent = False
        self.u._on_release({"tag_name": "v1.0.0", "assets": []})
        self.assertEqual(self.u.state, "latest")

    def test_silent_check_stays_quiet(self):
        self.u._silent = True
        self.u._on_release({"tag_name": "v1.0.0", "assets": []})
        self.assertEqual(self.u.state, "idle")

    def test_newer_without_installer_is_error(self):
        self.u._silent = False
        self.u._on_release({"tag_name": "v2.0.0", "assets": [{"name": "readme.txt"}]})
        self.assertEqual(self.u.state, "error")


class ShutdownAfterWorkerFinishedTestCase(unittest.TestCase):
    """Regression: exiting after an update check crashed with
    'Internal C++ object (_CheckWorker) already deleted'."""

    def test_shutdown_after_finished_worker_is_deleted(self):
        from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QThread, QTimer

        class Quick(QThread):
            def run(self):
                pass

        u = upd.Updater("1.0.0")
        u._start(Quick())
        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)  # run deleteLater
        u.shutdown()   # must not raise
        u.cancel()     # must not raise
        self.assertIsNone(u._worker)


class DownloadTestCase(unittest.TestCase):
    def _run(self, payload: bytes, digest: str):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            src.write_bytes(payload)
            w = upd._DownloadWorker(src.as_uri(), "XueXiTong-Plus-Setup-test.exe", len(payload), digest)
            out = {}
            w.done.connect(lambda p: out.setdefault("done", p))
            w.failed.connect(lambda m: out.setdefault("failed", m))
            # a local file stands in for the download; the address rule has its own tests
            # (tests/test_v130_security.py)
            with mock.patch.object(upd, "trusted_download", return_value=True):
                w.run()  # synchronous
            if "done" in out:
                data = Path(out["done"]).read_bytes()
                Path(out["done"]).unlink()
                out["data"] = data
            return out

    def test_download_with_matching_digest(self):
        payload = b"setup" * 1000
        out = self._run(payload, "sha256:" + hashlib.sha256(payload).hexdigest())
        self.assertNotIn("failed", out)
        self.assertEqual(out["data"], payload)

    def test_download_rejects_wrong_digest(self):
        out = self._run(b"tampered", "sha256:" + "0" * 64)
        self.assertIn("SHA-256", out["failed"])


if __name__ == "__main__":
    unittest.main()
