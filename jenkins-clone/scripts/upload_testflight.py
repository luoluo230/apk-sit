#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload IPA to TestFlight via App Store Connect API."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def shutil_which(name: str) -> bool:
    from shutil import which

    return bool(which(name))


def main() -> int:
    ipa = os.environ.get("IPA_FILE", "").strip()
    if not ipa or not os.path.isfile(ipa):
        print("ERROR: IPA_FILE missing", file=sys.stderr)
        return 1

    upload_enabled = str(os.environ.get("EXTERNAL_UPLOAD_TESTFLIGHT", "true")).strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not upload_enabled:
        print("SKIP: EXTERNAL_UPLOAD_TESTFLIGHT=false")
        return 0

    key_id = os.environ.get("ASC_API_KEY_ID", "").strip()
    issuer = os.environ.get("ASC_API_ISSUER", "").strip()
    key_path = os.environ.get("ASC_API_KEY_PATH", "").strip()
    release_env = str(os.environ.get("RELEASE_ENVIRONMENT", "")).strip().lower()
    is_production = release_env in ("production", "prod")
    strict = is_production or str(os.environ.get("IOS_TESTFLIGHT_STRICT", "")).strip().lower() in (
        "1",
        "true",
        "yes",
    )

    if not (key_id and issuer and key_path and os.path.isfile(key_path)):
        msg = "ASC API credentials not configured (bind Jenkins Credential or set ASC_API_KEY_*)"
        if strict:
            print(f"ERROR: {msg}", file=sys.stderr)
            return 1
        print(f"SKIP: {msg}", file=sys.stderr)
        return 0

    if not shutil_which("xcrun"):
        msg = "xcrun not available (requires macOS)"
        if strict:
            print(f"ERROR: {msg}", file=sys.stderr)
            return 1
        print(f"SKIP: {msg}", file=sys.stderr)
        return 0

    cmd = [
        "xcrun",
        "altool",
        "--upload-app",
        "-f",
        ipa,
        "--apiKey",
        key_id,
        "--apiIssuer",
        issuer,
    ]
    print(json.dumps({"cmd": cmd}, ensure_ascii=False))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    print("OK: TestFlight upload submitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
