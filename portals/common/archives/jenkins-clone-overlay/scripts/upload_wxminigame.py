#!/usr/bin/env python3
# -*- coding: utf-8
"""Upload wxgame bundle to WeChat backend via miniprogram-ci when configured."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def main() -> int:
    bundle = os.environ.get("WXGAME_BUNDLE", "").strip()
    app_id = os.environ.get("WX_APP_ID", "").strip()
    if not bundle or not os.path.isfile(bundle):
        print("SKIP: WXGAME_BUNDLE missing", file=sys.stderr)
        return 0
    if not app_id:
        print("SKIP: WX_APP_ID missing", file=sys.stderr)
        return 0
    if os.environ.get("AUTO_UPLOAD_WX", "").lower() not in ("1", "true", "yes", "on"):
        print("SKIP: AUTO_UPLOAD_WX disabled")
        return 0
    ci = os.environ.get("MINIPROGRAM_CI_BIN", "miniprogram-ci").strip()
    project_path = os.environ.get("WX_EXPORT_DIR", "").strip()
    if not project_path or not os.path.isdir(project_path):
        print("SKIP: WX_EXPORT_DIR missing (miniprogram-ci needs minigame dir)", file=sys.stderr)
        return 0
    cmd = [ci, "upload", "--ppd", project_path, "--appid", app_id, "--version", os.environ.get("VERSION_NAME", "1.0.0")]
    key_path = os.environ.get("WX_UPLOAD_KEY_PATH", "").strip()
    if key_path and os.path.isfile(key_path):
        cmd.extend(["--pkp", key_path])
    print(json.dumps({"cmd": cmd}, ensure_ascii=False))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        print("SKIP: miniprogram-ci not installed", file=sys.stderr)
        return 0
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    print("OK: WeChat upload submitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
