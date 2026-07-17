# -*- coding: utf-8 -*-
"""Smoke: delivery action BFF labels and artifacts_ready wording."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from services.release import release_order_service as ros


def main() -> int:
    version = {
        "id": "vc-smoke",
        "version_name": "1.0.1",
        "version_code": "1",
        "channel": "wechat",
        "channel_id": "wechat",
        "platform": "android",
        "env_key": "development",
        "apk_status": "found",
    }
    order = {
        "release_order_id": "ro-smoke",
        "status": "artifacts_ready",
        "version_id": "vc-smoke",
        "env_key": "development",
        "channel_id": "wechat",
        "platform": "android",
        "version_name": "1.0.1",
        "version_code": "1",
    }
    with mock.patch.object(ros, "_find_version", return_value=version), \
         mock.patch.object(ros, "find_release_order_for_version", return_value=order), \
         mock.patch.object(ros, "find_draft_release_order", return_value=order), \
         mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"form_depth": "minimal"}), \
         mock.patch("services.release.release_policy_service.assess_delivery_readiness", return_value={"pipeline_ready": True}), \
         mock.patch("services.release.release_policy_service.build_config_href", return_value="/build-config"):
        actions = ros.resolve_delivery_actions("demo", "vc-smoke")
    checks = [
        actions["primary"]["label"] == "继续发版",
        actions["primary"].get("api_action") != "quick_build",
        "产物就绪" in (actions.get("status_hint") or ""),
    ]
    print("smoke_delivery_actions:")
    print(f"  primary.label = {actions['primary']['label']}")
    print(f"  status_hint = {actions.get('status_hint')}")
    print(f"  RESULT = {'PASS' if all(checks) else 'FAIL'}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
