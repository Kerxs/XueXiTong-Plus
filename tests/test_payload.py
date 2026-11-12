# -*- coding: utf-8 -*-
"""The setup program's payload (installer/payload.py): one solid stream appended to the setup exe,
with the files the setup program carries itself copied from its own folder instead of stored twice."""
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from installer.payload import FOOTER, MAGIC, Payload, build

QT = b"MZ-qt-core" * 4000
PY = b"MZ-python" * 3000


def make_release(root: Path) -> Path:
    release = root / "学习通PLUS"
    (release / "_internal" / "PySide6" / "qml" / "objects-Release").mkdir(parents=True)
    (release / "_internal" / "onnx").mkdir()
    (release / "学习通PLUS.exe").write_bytes(b"MZ" + b"x" * 5000)
    (release / "卸载学习通PLUS.exe").write_bytes(b"MZ" + b"x" * 5000)
    (release / "_internal" / "PySide6" / "Qt6Core.dll").write_bytes(QT)
    (release / "_internal" / "python313.dll").write_bytes(PY)
    (release / "_internal" / "onnx" / "model.onnx").write_bytes(bytes(range(256)) * 400)
    (release / "_internal" / "PySide6" / "qml" / "objects-Release" / "left.obj").write_bytes(b"junk")
    return release


def tree(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


class PayloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.release = make_release(self.root)
        self.expected = {k: v for k, v in tree(self.release).items() if "objects-" not in k}

    def tearDown(self):
        self.tmp.cleanup()

    def setup_folder(self, **changed) -> tuple[Path, dict]:
        """The setup program's own folder (_MEIPASS) and its manifest."""
        folder = self.root / "mei"
        (folder / "PySide6").mkdir(parents=True)
        (folder / "PySide6" / "Qt6Core.dll").write_bytes(changed.get("qt", QT))
        (folder / "python313.dll").write_bytes(changed.get("py", PY))
        manifest = {"PySide6/Qt6Core.dll": hashlib.sha256(QT).hexdigest(),
                    "python313.dll": hashlib.sha256(changed.get("manifest_py", PY)).hexdigest()}
        return folder, manifest

    def test_round_trip_behind_an_exe(self):
        out = self.root / "payload.bin"
        header = build(str(self.release), str(out))
        self.assertEqual(header["shared"], [])
        setup = self.root / "setup.exe"                     # the payload sits behind the program
        setup.write_bytes(b"MZ" + b"\x00" * 70000 + out.read_bytes())
        payload = Payload(setup)
        self.assertTrue(payload.ok)
        self.assertEqual(payload.size, sum(len(v) for v in self.expected.values()))
        seen = []
        payload.extract(self.root / "installed", lambda fraction, name: seen.append(fraction))
        self.assertEqual(tree(self.root / "installed"), self.expected)
        self.assertEqual(seen[-1], 1.0)
        self.assertEqual(seen, sorted(seen))

    def test_files_the_setup_program_carries_are_not_stored_again(self):
        folder, manifest = self.setup_folder()
        plain, shared = self.root / "plain.bin", self.root / "shared.bin"
        build(str(self.release), str(plain))
        header = build(str(self.release), str(shared), manifest)
        self.assertEqual(sorted(i["path"] for i in header["shared"]),
                         ["_internal/PySide6/Qt6Core.dll", "_internal/python313.dll"])
        payload = Payload(shared)
        payload.extract(self.root / "installed", shared_root=folder)
        self.assertEqual(tree(self.root / "installed"), self.expected)       # the same files as before
        with self.assertRaises(RuntimeError):                                # not without the setup's folder
            Payload(shared).extract(self.root / "nowhere")

    def test_a_file_that_differs_is_stored_not_shared(self):
        _, manifest = self.setup_folder(manifest_py=b"another build of python")
        header = build(str(self.release), str(self.root / "p.bin"), manifest)
        self.assertEqual([i["path"] for i in header["shared"]], ["_internal/PySide6/Qt6Core.dll"])

    def test_a_damaged_shared_file_fails_the_install(self):
        folder, manifest = self.setup_folder()
        out = self.root / "p.bin"
        build(str(self.release), str(out), manifest)
        (folder / "PySide6" / "Qt6Core.dll").write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "不完整"):
            Payload(out).extract(self.root / "installed", shared_root=folder)

    def test_release_zip_still_installs(self):
        archive = self.root / "release.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for rel, data in tree(self.release).items():
                z.writestr("学习通PLUS/" + rel, data)
            z.writestr("学习通PLUS/../evil.txt", b"x")                         # never written
            z.writestr("other/file.txt", b"x")
        payload = Payload(archive, "学习通PLUS/")
        self.assertTrue(payload.ok)
        payload.extract(self.root / "installed")
        self.assertEqual(tree(self.root / "installed"), self.expected)
        self.assertFalse((self.root / "evil.txt").exists())

    def test_not_a_payload(self):
        junk = self.root / "junk.exe"
        junk.write_bytes(b"MZ" + b"\x01" * 5000)
        self.assertFalse(Payload(junk).ok)
        with self.assertRaises(RuntimeError):
            Payload(junk).extract(self.root / "x")
        broken = self.root / "broken.bin"
        broken.write_bytes(b"{}" + FOOTER.pack(MAGIC, 2, 999999))            # a length that cannot be
        self.assertFalse(Payload(broken).ok)

    def test_unsafe_names_in_the_stream_are_refused(self):
        import io
        import json
        import lzma
        import tarfile

        out = self.root / "evil.bin"
        head = json.dumps({"format": 1, "files": 1, "size": 1, "shared": []}).encode()
        stream = io.BytesIO()
        with lzma.open(stream, "wb") as xz, tarfile.open(fileobj=xz, mode="w|") as tar:
            info = tarfile.TarInfo("../outside.txt")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        out.write_bytes(head + stream.getvalue() + FOOTER.pack(MAGIC, len(head), len(stream.getvalue())))
        with self.assertRaisesRegex(RuntimeError, "不正常"):
            Payload(out).extract(self.root / "installed")
        self.assertFalse((self.root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
