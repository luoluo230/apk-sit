# -*- coding: utf-8 -*-
"""Smoke: channel dual pipeline entry points."""

from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from services.release.release_order_service import resolve_channel_journey_entries


def main() -> int:
    from services.release.release_order_service import _delivery_lines_for_env

    lines = _delivery_lines_for_env("GomeKu", "development")
    channel_id = str((lines[0] or {}).get("channel_id") or "wechat")
    entries = resolve_channel_journey_entries("GomeKu", "development", channel_id)
    checks = [
        entries["build_entry"]["label"] == "进入构建流程",
        entries["release_entry"]["label"] == "进入发版流程",
        f"/channels/{channel_id}/build" in entries["build_entry"]["href"],
        f"/channels/{channel_id}/release" in entries["release_entry"]["href"],
    ]
    print("smoke_channel_journeys:")
    print(f"  build.href = {entries['build_entry']['href']}")
    print(f"  release.href = {entries['release_entry']['href']}")
    print(f"  RESULT = {'PASS' if all(checks) else 'FAIL'}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
