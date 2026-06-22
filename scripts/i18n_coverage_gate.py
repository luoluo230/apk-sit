#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify minimum UILocalizedText key coverage in maclient HotUpdate sources."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Storefront baseline keys (sheet:key). Extend as UI productization grows.
REQUIRED_KEYS = (
  "UI:login.title",
  "UI:sample.mail",
  "UI:common.confirm",
  "UI:common.cancel",
  "UI:error.network",
)

SET_KEY_RE = re.compile(r'SetKey\(\s*"([^"]+)"')
REGISTER_TEXT_RE = re.compile(
    r'RegisterText\(\s*"[^"]+"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"'
)


def _maclient_root() -> Path:
    env = os.environ.get("MACLIENT_ROOT", r"E:\maclient")
    return Path(env)


def _scan_keys(hotupdate_dir: Path) -> set[str]:
    found: set[str] = set()
    if not hotupdate_dir.is_dir():
        return found

    for path in hotupdate_dir.rglob("*.cs"):
        if "jenkins" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in SET_KEY_RE.finditer(text):
            key = match.group(1)
            sheet = "UI"
            sheet_match = re.search(
                rf'SetKey\(\s*"{re.escape(key)}"\s*,\s*"[^"]*"\s*,\s*"([^"]+)"',
                text,
            )
            if sheet_match:
                sheet = sheet_match.group(1)
            found.add(f"{sheet}:{key}")
        for match in REGISTER_TEXT_RE.finditer(text):
            sheet, key = match.group(1), match.group(2)
            found.add(f"{sheet}:{key}")
    return found


def main() -> int:
    root = _maclient_root()
    component = root / "Assets" / "Src" / "HotUpdate" / "Framework" / "UI" / "UILocalizedText.cs"
    hotupdate = root / "Assets" / "Src" / "HotUpdate"

    errors: list[str] = []
    if not component.is_file():
        errors.append(f"UILocalizedText component missing: {component}")
    else:
        print(f"OK component: {component}")

    found = _scan_keys(hotupdate)
    print(f"Scanned keys ({len(found)}): {', '.join(sorted(found)) or '(none)'}")

    missing = [key for key in REQUIRED_KEYS if key not in found]
    if missing:
        errors.append("missing UILocalizedText keys: " + ", ".join(missing))

    if errors:
        for item in errors:
            print(f"FAIL {item}", file=sys.stderr)
        return 1

    print(f"PASS all {len(REQUIRED_KEYS)} required UILocalizedText keys present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
