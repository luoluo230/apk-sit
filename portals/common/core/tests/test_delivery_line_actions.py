# -*- coding: utf-8 -*-
"""Delivery line action BFF and environment matrix enrichment."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock
from unittest.mock import patch

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: F401
from services.release import order_build_sync as obs
from services.release import order_crud as oc
from services.release import release_order_service as ros


class ResolveDeliveryActionsTests(unittest.TestCase):
    def _version(self, **extra):
        base = {
            "id": "vc-1",
            "version_name": "1.0.1",
            "version_code": "1",
            "channel": "wechat",
            "channel_id": "wechat",
            "platform": "android",
            "env_key": "development",
            "apk_status": "found",
        }
        base.update(extra)
        return base

    def test_artifacts_ready_shows_continue_release_only(self):
        version = self._version()
        order = {
            "release_order_id": "ro-1",
            "status": "artifacts_ready",
            "version_id": "vc-1",
            "env_key": "development",
            "channel_id": "wechat",
            "platform": "android",
            "version_name": "1.0.1",
            "version_code": "1",
        }
        with mock.patch.object(obs, "_find_version", return_value=version), \
             mock.patch.object(obs, "find_release_order_for_version", return_value=order), \
             mock.patch.object(oc, "find_draft_release_order", return_value=order), \
             mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"form_depth": "minimal"}), \
             mock.patch("services.release.release_policy_service.assess_delivery_readiness", return_value={"pipeline_ready": True}), \
             mock.patch("services.release.release_policy_service.build_config_href", return_value="/build-config"):
            actions = ros.resolve_delivery_actions("p1", "vc-1")
        self.assertEqual(actions["primary"]["label"], "继续发版")
        self.assertIn("/release-orders/ro-1", actions["primary"]["href"])
        self.assertNotEqual(actions["primary"].get("api_action"), "quick_build")

    def test_delivery_actions_include_dual_entries(self):
        version = self._version()
        with mock.patch.object(obs, "_find_version", return_value=version), \
             mock.patch.object(obs, "find_release_order_for_version", return_value=None), \
             mock.patch.object(oc, "find_draft_release_order", return_value=None), \
             mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"form_depth": "minimal"}), \
             mock.patch("services.release.release_policy_service.assess_delivery_readiness", return_value={"pipeline_ready": True}), \
             mock.patch("services.release.release_policy_service.build_config_href", return_value="/build-config"):
            actions = ros.resolve_delivery_actions("p1", "vc-1")
        self.assertEqual(actions["build_entry"]["label"], "进入构建流程")
        self.assertEqual(actions["release_entry"]["label"], "进入发版流程")
        self.assertIn("/channels/wechat/build", actions["build_entry"]["href"])

    def test_enrich_unconfigured_line_without_version_id(self):
        line = {
            "channel_id": "wechat",
            "platform": "android",
            "version_id": "",
            "configured": False,
        }
        out = ros.enrich_delivery_line_actions("p1", line)
        self.assertEqual(out["status_hint"], "未配置 VersionCode · 请先新建 VC")
        self.assertEqual(out["delivery_actions"]["primary"]["label"], "新建 VC")

    def test_enrich_delivery_line_attaches_actions(self):
        line = {
            "channel_id": "wechat",
            "platform": "android",
            "version_id": "vc-1",
            "configured": True,
        }
        fake_actions = {
            "release_order_id": "ro-1",
            "release_order_status": "artifacts_ready",
            "pipeline_ready": True,
            "artifact_ready": True,
            "status_hint": "产物就绪 · 可继续发版",
            "primary": {"action": "continue_release", "label": "继续发版", "href": "/detail"},
            "secondary": [],
            "scope": {},
            "links": {},
        }
        with mock.patch.object(obs, "resolve_delivery_actions", return_value=fake_actions):
            out = ros.enrich_delivery_line_actions("p1", line)
        self.assertEqual(out["release_order_status"], "artifacts_ready")
        self.assertEqual(out["delivery_actions"]["primary"]["label"], "继续发版")


class DeliveryActionsApiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    @mock.patch("routes.delivery.journey_api.resolve_delivery_actions")
    @patch.dict("models.data.projects_db", {"demo": {"name": "Demo"}}, clear=False)
    def test_delivery_actions_api(self, mock_resolve):
        mock_resolve.return_value = {
            "primary": {"label": "继续发版", "href": "/detail"},
            "secondary": [],
            "status_hint": "产物就绪 · 可继续发版",
        }
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = self.client.get("/api/projects/demo/versions/vc-1/delivery-actions")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["data"]["primary"]["label"], "继续发版")


class ReleaseOrderStartRouteTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    @patch.dict("routes.project_delivery.projects_db", {"demo": {"name": "Demo"}}, clear=False)
    @patch.dict("models.data.project_versions_db", {
        "demo": [{
            "id": "vc-start",
            "channel": "wechat",
            "channel_id": "wechat",
            "platform": "android",
            "env_key": "development",
            "version_name": "1.0.1",
            "version_code": "1",
        }],
    }, clear=False)
    def test_build_intent_redirects_to_channel_build_journey(self):
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = self.client.get(
            "/admin/projects/demo/release-orders/start?intent=build&version_id=vc-start",
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/environments/development/channels/wechat/build", resp.headers.get("Location") or "")

    @patch.dict("routes.project_delivery.projects_db", {"demo": {"name": "Demo"}}, clear=False)
    @patch.dict("models.data.project_versions_db", {
        "demo": [{
            "id": "vc-start",
            "channel": "wechat",
            "channel_id": "wechat",
            "platform": "android",
            "env_key": "development",
        }],
    }, clear=False)
    def test_release_intent_redirects_to_channel_release_journey(self):
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = self.client.get(
            "/admin/projects/demo/release-orders/start?intent=release&version_id=vc-start",
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/environments/development/channels/wechat/release", resp.headers.get("Location") or "")


if __name__ == "__main__":
    unittest.main()
