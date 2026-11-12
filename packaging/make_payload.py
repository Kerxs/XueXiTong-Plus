# -*- coding: utf-8 -*-
"""Build the installer payload from the release folder (see installer/payload.py for the format).

Usage: python make_payload.py <dist>\\学习通PLUS <out.bin> [setup-manifest.json]

The manifest ({path in the setup program's own folder: sha256}) is written by packaging/setup.spec
when the setup program is built; files it lists with the same content are not stored again.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from installer.payload import build  # noqa: E402

if __name__ == "__main__":
    manifest = None
    if len(sys.argv) > 3 and os.path.isfile(sys.argv[3]):
        with open(sys.argv[3], encoding="utf-8") as fp:
            manifest = json.load(fp)
    header = build(sys.argv[1], sys.argv[2], manifest)
    shared = sum(item["size"] for item in header["shared"])
    print(f"payload: {os.path.getsize(sys.argv[2]) / 1048576:.1f} MB for {header['size'] / 1048576:.0f} MB "
          f"({header['files']} files; {len(header['shared'])} files / {shared / 1048576:.0f} MB shared with the setup program)")
