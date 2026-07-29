# -*- coding: utf-8 -*-
"""Bootstrap startup E2E: readable errors + single-request contract (P2-02 Step 2)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from models.db import init_db


class BootstrapStartupE2ETests(unittest.TestCase):
    def setUp(self):
        init_db()
        from app_new import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def test_invalid_credentials_returns_readable_error(self):
        resp = self.client.get(
            "/api/public/runtime-bootstrap?"
            "game_id=bad&game_key=bad&env_key=development&channel=wechat&platform=android"
        )
        self.assertEqual(resp.status_code, 401)
        body = resp.get_json() or {}
        self.assertFalse(body.get("ok"))
        self.assertTrue(str(body.get("error") or "").strip())

    def test_missing_bundle_returns_readable_error(self):
        with mock.patch("routes.delivery.public_api.projects_db", {"GomeKu": {"game_id": "g1", "game_key": "k1"}}):
            with mock.patch("routes.delivery.public_api.resolve_channel_id", return_value="1001"):
                with mock.patch("routes.delivery.public_api.get_channel_by_id", return_value={"apk_subdir": "wechat"}):
                    with mock.patch("routes.delivery.public_api.find_scope", return_value={"scope_id": "s1", "env_key": "development"}):
                        with mock.patch("services.release.bundle_service.find_active_bundle", return_value=None):
                            resp = self.client.get(
                                "/api/public/runtime-bootstrap?"
                                "game_id=g1&game_key=k1&env_key=development&channel=wechat&platform=android"
                            )
        self.assertEqual(resp.status_code, 404)
        body = resp.get_json() or {}
        self.assertFalse(body.get("ok"))
        err = str(body.get("error") or "")
        self.assertTrue(err)
        self.assertIn("Bundle", err)

    def test_successful_bootstrap_returns_ok(self):
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures",
            "runtime_bootstrap_contract_v2.sample.json",
        )
        with open(fixture_path, encoding="utf-8") as fh:
            fixture = json.load(fh)
        bootstrap = dict(fixture.get("bootstrap") or {})
        bundle = {
            "bundle_id": fixture.get("active_bundle_id"),
            "scope_id": fixture.get("scope_id"),
            "client": bootstrap,
            "server": {"network_profile_snapshot": fixture.get("network_profile") or {}},
        }
        rollout = {"rollout_percentage": 100, "rollout_bucket": 0, "bundle": bundle}

        with mock.patch("routes.delivery.public_api.projects_db", {"GomeKu": {"game_id": "g1", "game_key": "k1"}}):
            with mock.patch("routes.delivery.public_api.resolve_channel_id", return_value="1001"):
                with mock.patch("routes.delivery.public_api.get_channel_by_id", return_value={"apk_subdir": "wechat"}):
                    with mock.patch("routes.delivery.public_api.find_scope", return_value={"scope_id": fixture["scope_id"]}):
                        with mock.patch("services.release.bundle_service.find_active_bundle", return_value=bundle):
                            with mock.patch("services.release.bundle_service.resolve_gray_rollout_bundle", return_value=rollout):
                                resp = self.client.get(
                                    "/api/public/runtime-bootstrap?"
                                    "game_id=g1&game_key=k1&env_key=development&channel=wechat&platform=android&version_name=1.0.0"
                                )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("active_bundle_id"), fixture.get("active_bundle_id"))


if __name__ == "__main__":
    unittest.main()
