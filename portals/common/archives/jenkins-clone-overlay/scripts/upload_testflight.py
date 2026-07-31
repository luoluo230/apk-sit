#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload IPA to TestFlight via App Store Connect API (optional)."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def main() -> int:
    ipa = os.environ.get("IPA_FILE", "").strip()
    if not ipa or not os.path.isfile(ipa):
        print("SKIP: IPA_FILE missing", file=sys.stderr)
        return 0
    key_id = os.environ.get("ASC_API_KEY_ID", "").strip()
    issuer = os.environ.get("ASC_API_ISSUER", "").strip()
    key_path = os.environ.get("ASC_API_KEY_PATH", "").strip()
    if not (key_id and issuer and key_path and os.path.isfile(key_path)):
        print("SKIP: ASC API credentials not configured", file=sys.stderr)
        return 0
    if not shutil_which("xcrun"):
        print("SKIP: xcrun not available (requires macOS)", file=sys.stderr)
        return 0
    cmd = [
        "xcrun", "altool", "--upload-app", "-f", ipa,
        "--apiKey", key_id, "--apiIssuer", issuer,
    ]
    print(json.dumps({"cmd": cmd}, ensure_ascii=False))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    print("OK: TestFlight upload submitted")
    return 0


def shutil_which(name: str) -> bool:
    from shutil import which
    return bool(which(name))


if __name__ == "__main__":
    raise SystemExit(main())
