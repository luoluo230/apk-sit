#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggressive mojibake cleanup pass for mixed ASCII/CJK comment lines."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOTS = [
    Path(r"E:\maclient\Assets"),
    Path(r"E:\maclient\game-server"),
    Path(r"e:\web\apk-site\portals\common\core"),
]
SKIP_DIRS = {"node_modules", "venv", ".git", "__pycache__", "bin", "obj", "Library", "release_bundles", "artifacts", "Generated", "ThirdParty"}
EXTS = {".cs", ".py", ".js", ".md", ".json", ".ps1", ".sh"}

MOJI_HINT = re.compile(
    r"[瀵瀛榛鍙渚璁鐏鏍浠鍦姣缂杩鐗闇鑷鍟娴鎴浼鍓鍏閫鍩缁鐢鏂鍝閬纭璧璺娓鍒鎵绯]"
)


def fix_chunk(chunk: str) -> str:
    if not MOJI_HINT.search(chunk):
        return chunk
    cleaned = re.sub(r"[\uE000-\uF8FF\ufffd]", "", chunk)
    cleaned = cleaned.replace("\u20ac", "").replace("€", "")
    try:
        return cleaned.encode("gbk").decode("utf-8")
    except UnicodeError:
        return chunk


def fix_line(line: str) -> str:
    if not MOJI_HINT.search(line):
        return line
    return re.sub(r"[^\x00-\x7f]+", lambda m: fix_chunk(m.group(0)), line)


MANUAL = {
    "子目录，空则无子盽": "子目录，空则无子目录",
    "默认 Catalog 文件名，运行时按版本号覆盖": "默认 Catalog 文件名，运行时按版本号覆盖目录",
    "绯荤粺鍏憡": "系统公告",
}


def iter_files():
    for root in ROOTS:
        if not root.is_dir():
            continue
        for dp, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            if any(s in Path(dp).parts for s in SKIP_DIRS):
                continue
            for fn in filenames:
                if Path(fn).suffix.lower() not in EXTS:
                    continue
                yield Path(dp) / fn


def main() -> None:
    changed = 0
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not MOJI_HINT.search(text):
            continue
        lines = [fix_line(l) for l in text.splitlines()]
        out = "\n".join(lines)
        if text.endswith("\n"):
            out += "\n"
        for src, dst in MANUAL.items():
            out = out.replace(src, dst)
        if out != text:
            path.write_text(out, encoding="utf-8", newline="\n")
            changed += 1
            print("fixed", path)
    print("pass3 changed", changed)


if __name__ == "__main__":
    main()
