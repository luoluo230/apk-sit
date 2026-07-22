# -*- coding: utf-8 -*-
"""Channel build/release journey BFF and scope bundle ops."""

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

from app_new import app  # noqa: F401
from services.release import channel_journey_bff as cjb
from services.release import order_crud as oc
from services.release import release_order_service as ros


class ChannelBuildJourneyTests(unittest.TestCase):
    def test_resolve_build_journey_has_steps(self):
        with mock.patch.object(cjb, "_lines_for_channel", return_value=[{
            "channel_id": "wechat",
            "channel_name": "微信",
            "platform": "android",
            "platform_label": "Android",
            "scope_id": "scope-1",
            "configured": True,
            "version_id": "vc-1",
            "version_name": "1.0.1",
            "version_code": "1",
        }]), mock.patch.object(cjb, "_platform_state_for_journey", return_value={
            "platform": "android",
            "pipeline_ready": True,
            "version_id": "vc-1",
            "order_status": "draft",
            "artifact_ready": False,
            "versions": [],
        }):
            data = ros.resolve_channel_build_journey("p1", "development", "wechat", platform="android")
        self.assertEqual(len(data["steps"]), 6)
        self.assertIn("/channels/wechat/build", data["links"]["build_journey"])


class ChannelReleaseJourneyTests(unittest.TestCase):
    def test_resolve_release_journey_has_steps(self):
        with mock.patch.object(cjb, "_lines_for_channel", return_value=[{
            "channel_id": "wechat",
            "channel_name": "微信",
            "platform": "android",
            "platform_label": "Android",
            "scope_id": "scope-1",
            "configured": True,
        }]), mock.patch.object(cjb, "_platform_state_for_journey", return_value={
            "platform": "android",
            "scope_id": "scope-1",
            "artifact_ready": True,
            "publishable_bundles": [{"bundle_id": "b1", "is_active": True}],
            "order_status": "artifacts_ready",
            "release_order_id": "ro-1",
            "versions": [],
        }), mock.patch.object(oc, "list_release_orders", return_value=[]), \
             mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"form_depth": "minimal"}):
            data = ros.resolve_channel_release_journey("p1", "development", "wechat", platform="android")
        self.assertEqual(len(data["steps"]), 7)
        self.assertIn("/channels/wechat/release", data["links"]["release_journey"])


class ChannelJourneyApiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    @mock.patch("routes.project_delivery.resolve_channel_build_journey")
    @mock.patch("routes.project_delivery.get_project_env_defs", return_value=[{"env_key": "development"}])
    @mock.patch.dict("routes.project_delivery.projects_db", {"demo": {"name": "Demo"}}, clear=False)
    def test_build_journey_api(self, _env_defs, mock_resolve):
        mock_resolve.return_value = {"steps": [], "current_step": 0}
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = self.client.get("/api/projects/demo/environments/development/channels/wechat/build-journey")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue((resp.get_json() or {}).get("ok"))


class ReleaseOrderStartRedirectTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    @mock.patch.dict("routes.project_delivery.projects_db", {"demo": {"name": "Demo"}}, clear=False)
    @mock.patch.dict("models.data.project_versions_db", {
        "demo": [{
            "id": "vc-1",
            "channel": "wechat",
            "channel_id": "wechat",
            "platform": "android",
            "env_key": "development",
        }],
    }, clear=False)
    def test_start_build_redirects_to_channel_build(self):
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = self.client.get("/admin/projects/demo/release-orders/start?intent=build&version_id=vc-1", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers.get("Location") or ""
        self.assertIn("/environments/development/channels/wechat/build", loc)

    @mock.patch.dict("routes.project_delivery.projects_db", {"demo": {"name": "Demo"}}, clear=False)
    @mock.patch.dict("models.data.project_versions_db", {
        "demo": [{
            "id": "vc-1",
            "channel": "wechat",
            "platform": "android",
            "env_key": "development",
        }],
    }, clear=False)
    def test_start_release_redirects_to_channel_release(self):
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = self.client.get("/admin/projects/demo/release-orders/start?intent=release&version_id=vc-1", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers.get("Location") or ""
        self.assertIn("/environments/development/channels/wechat/release", loc)


if __name__ == "__main__":
    unittest.main()
