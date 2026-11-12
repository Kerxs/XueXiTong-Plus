# -*- coding: utf-8 -*-
"""The setup program's payload: the release folder, appended to the end of the setup exe.

Layout (all at the end of the file, so the exe in front of it does not matter):

    [header: UTF-8 JSON] [the files: one solid .tar.xz stream] [footer: MAGIC, header length, stream length]

Two things make it much smaller than the LZMA zip used up to 1.2.9 (74 -> about 30 MB):

* One solid stream. A zip compresses each of the ~1300 files on its own; here similar files
  (sorted by type) share one dictionary, and executables go through the x86 filter first.
* Files the setup program already carries are not stored twice. The setup exe is a one-file
  PyInstaller program that unpacks its own Qt and Python into a temporary folder (``_MEIPASS``)
  — the very same DLLs the app needs. Those are listed in the header as ``shared`` (path, where
  it is in the setup's folder, SHA-256) and copied from there at install time. Only files whose
  hash matched at build time are shared, and every copy is verified again when installing.

Release zips (``--payload XueXiTong-Plus-Windows-<ver>.zip``, used for development) still work.
No Qt in this module: it is tested on its own (tests/test_payload.py).
"""

from __future__ import annotations

import hashlib
import io
import json
import lzma
import os
import shutil
import struct
import tarfile
import zipfile
from pathlib import Path

MAGIC = b"XXTPLUS\x01"
FOOTER = struct.Struct("<8sQQ")          # magic, header length, stream length
CHUNK = 1024 * 1024
# 64 MB dictionary: the whole release fits a few times over, so identical and similar files far
# apart still find each other. Decompression needs about that much memory.
XZ_FILTERS = [{"id": lzma.FILTER_X86},
              {"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME, "dict_size": 64 * 1024 * 1024}]


def sha256(path: os.PathLike | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for block in iter(lambda: fp.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _skip(rel: str) -> bool:
    """Qt build leftovers: very deep paths, never loaded."""
    return "/objects-" in "/" + rel or rel.endswith(".obj")


def _safe(rel: str) -> bool:
    parts = rel.split("/")
    return bool(rel) and not rel.startswith("/") and ":" not in parts[0] and ".." not in parts and "" not in parts


def build(release_dir: str, out: str, manifest: dict[str, str] | None = None) -> dict:
    """Write the payload for ``release_dir``. ``manifest``: {path inside the setup program's own
    folder: sha256} (written by packaging/setup.spec); a release file ``_internal/<that path>`` with
    the same hash is shared instead of stored. Returns the header."""
    release = Path(release_dir)
    files = []
    for folder, _dirs, names in os.walk(release):
        for name in names:
            full = Path(folder) / name
            rel = full.relative_to(release).as_posix()
            if not _skip(rel):
                files.append((rel, full))
    shared, stored, total = [], [], 0
    for rel, full in files:
        size = full.stat().st_size
        total += size
        inside = rel[len("_internal/"):] if rel.startswith("_internal/") else None
        if manifest and inside and inside in manifest:
            digest = sha256(full)
            if manifest[inside] == digest:
                shared.append({"path": rel, "from": inside, "sha256": digest, "size": size})
                continue
        stored.append((rel, full))
    # Similar files next to each other compress better: by extension, then by name.
    stored.sort(key=lambda item: (Path(item[0]).suffix.lower(), Path(item[0]).name.lower(), item[0]))
    header = {"format": 1, "files": len(files), "size": total, "shared": shared}
    head = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(out, "wb") as fp:
        fp.write(head)
        start = fp.tell()
        with lzma.open(fp, "wb", format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, filters=XZ_FILTERS) as xz:
            with tarfile.open(fileobj=xz, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for rel, full in stored:
                    info = tarfile.TarInfo(rel)
                    info.size = full.stat().st_size
                    with open(full, "rb") as src:
                        tar.addfile(info, src)
        length = fp.tell() - start
        fp.write(FOOTER.pack(MAGIC, len(head), length))
    return header


class _Window(io.RawIOBase):
    """Read-only view of ``length`` bytes of a file starting at ``start``."""

    def __init__(self, fp, start: int, length: int):
        self.fp, self.left = fp, length
        fp.seek(start)

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        size = min(len(buffer), self.left)
        if size <= 0:
            return 0
        data = self.fp.read(size)
        buffer[:len(data)] = data
        self.left -= len(data)
        return len(data)


class Payload:
    """What is appended to the setup exe (or a release zip given with --payload)."""

    def __init__(self, path: os.PathLike | str, zip_root: str = ""):
        self.path = Path(path)
        self.zip_root = zip_root          # "学习通PLUS/": the folder inside a release zip
        self.ok = False
        self.size = 0                     # bytes once installed
        self.kind = ""
        self.header: dict = {}
        self._start = self._length = 0
        try:
            self._read()
        except (OSError, ValueError, zipfile.BadZipFile, struct.error):
            self.ok = False

    def _read(self) -> None:
        with open(self.path, "rb") as fp:
            fp.seek(0, os.SEEK_END)
            end = fp.tell()
            if end >= FOOTER.size:
                fp.seek(end - FOOTER.size)
                magic, head_len, length = FOOTER.unpack(fp.read(FOOTER.size))
                if magic == MAGIC and 0 < head_len < 64 * 1024 * 1024 and head_len + length + FOOTER.size <= end:
                    fp.seek(end - FOOTER.size - length - head_len)
                    self.header = json.loads(fp.read(head_len).decode("utf-8"))
                    self._start, self._length = end - FOOTER.size - length, length
                    self.size = int(self.header.get("size", 0))
                    self.kind = "solid"
                    self.ok = self.header.get("format") == 1 and self.header.get("files", 0) > 0
                    return
        with zipfile.ZipFile(self.path) as archive:
            members = self._zip_members(archive)
            self.size = sum(m.file_size for m in members)
            self.kind = "zip"
            self.ok = bool(members)

    def _zip_members(self, archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        out = []
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if not name.startswith(self.zip_root) or name.endswith("/"):
                continue
            rel = name[len(self.zip_root):]
            if _safe(rel) and not _skip(rel):
                out.append(info)
        return out

    def extract(self, target: os.PathLike | str, progress=lambda fraction, name: None,
                shared_root: os.PathLike | str | None = None) -> None:
        """Write every file below ``target``. ``shared_root``: the setup program's own folder
        (sys._MEIPASS), where the shared files are copied from. Raises on anything that is off."""
        if not self.ok:
            raise RuntimeError("安装包内容为空或已损坏。")
        target = Path(target)
        total = self.size or 1
        done = 0

        def write(rel: str, source, size: int) -> None:
            nonlocal done
            if not _safe(rel):
                raise RuntimeError(f"安装包里有不正常的文件名：{rel}")
            dest = target / Path(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as dst:
                shutil.copyfileobj(source, dst, CHUNK)
            done += size
            progress(min(1.0, done / total), rel)

        if self.kind == "zip":
            with zipfile.ZipFile(self.path) as archive:
                for info in self._zip_members(archive):
                    with archive.open(info) as src:
                        write(info.filename.replace("\\", "/")[len(self.zip_root):], src, info.file_size)
            return

        shared = self.header.get("shared") or []
        if shared and shared_root is None:
            raise RuntimeError("这个安装包需要由安装程序本身来安装（缺少共用文件）。")
        with open(self.path, "rb") as fp:
            window = io.BufferedReader(_Window(fp, self._start, self._length), CHUNK)
            with lzma.open(window, "rb") as xz, tarfile.open(fileobj=xz, mode="r|") as tar:
                for member in tar:
                    if not member.isreg():
                        raise RuntimeError(f"安装包里有不正常的内容：{member.name}")
                    write(member.name, tar.extractfile(member), member.size)
        for item in shared:
            source = Path(shared_root) / item["from"]
            if not _safe(item["from"]) or not source.is_file() or sha256(source) != item["sha256"]:
                raise RuntimeError(f"安装程序自带的文件不完整：{item['from']}。请重新下载安装包。")
            with open(source, "rb") as src:
                write(item["path"], src, item["size"])
