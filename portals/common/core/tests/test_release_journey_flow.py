# -*- coding: utf-8 -*-
"""Release journey: build/release split, phases, quick-build, workflow redirect."""

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
from services.release import order_diagnostics as diag
from services.release import release_order_service as ros


class ReleaseJourneyNextActionTests(unittest.TestCase):
    def test_artifacts_ready_primary_is_continue_release(self):
        fake_order = {
            "release_order_id": "ro-1",
            "project_id": "p1",
            "version_id": "v1",
            "version_code": "100",
            "version_name": "1.0.0",
            "channel_id": "wechat",
            "channel_name": "WeChat",
            "platform": "android",
            "env_key": "development",
            "status": "artifacts_ready",
            "payload": {},
            "artifacts": [],
        }
        with mock.patch.object(ros, "get_release_order", return_value=fake_order), \
             mock.patch.object(diag, "_build_pipeline_snapshot", return_value={"ready": True}), \
             mock.patch.object(diag, "_pipeline_build_ready", return_value=True):
            action = ros.resolve_release_order_next_action("p1", "ro-1")
        self.assertEqual(action["phases"], ["准备", "构建", "发版"])
        self.assertEqual(action["phase_index"], 1)
        self.assertEqual(action["primary"]["api_action"], "precheck")
        self.assertIn("继续发版", action["primary"]["label"])

    def test_draft_primary_is_trigger_build(self):
        fake_order = {
            "release_order_id": "ro-2",
            "project_id": "p1",
            "version_id": "v1",
            "version_code": "100",
            "version_name": "1.0.0",
            "channel_id": "wechat",
            "channel_name": "WeChat",
            "platform": "android",
            "env_key": "development",
            "status": "draft",
            "payload": {},
            "artifacts": [],
        }
        with mock.patch.object(ros, "get_release_order", return_value=fake_order):
            action = ros.resolve_release_order_next_action("p1", "ro-2")
        self.assertEqual(action["primary"]["api_action"], "build")
        self.assertIn("触发构建", action["primary"]["label"])

    def test_ready_phase_index_is_release(self):
        fake_order = {
            "release_order_id": "ro-3",
            "project_id": "p1",
            "version_id": "v1",
            "version_code": "100",
            "version_name": "1.0.0",
            "channel_id": "wechat",
            "channel_name": "WeChat",
            "platform": "android",
            "env_key": "development",
            "status": "ready",
            "payload": {},
            "artifacts": [],
        }
        with mock.patch.object(ros, "get_release_order", return_value=fake_order):
            action = ros.resolve_release_order_next_action("p1", "ro-3")
        self.assertEqual(action["phase_index"], 2)


class QuickBuildVersionTests(unittest.TestCase):
    def test_quick_build_returns_existing_artifacts_ready(self):
        draft = {"release_order_id": "ro-q1", "status": "artifacts_ready", "env_key": "development"}
        with mock.patch.object(ros, "ensure_draft_release_order", return_value=draft):
            out = ros.quick_build_version("p1", "v1", "tester")
        self.assertEqual(out["status"], "artifacts_ready")

    def test_quick_build_triggers_request_build_for_draft(self):
        draft = {"release_order_id": "ro-q2", "status": "draft", "env_key": "development", "payload": {}, "reason": "x", "created_by": "tester"}
        built = {**draft, "status": "building"}
        with mock.patch.object(ros, "ensure_draft_release_order", return_value=draft), \
             mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"form_depth": "minimal"}), \
             mock.patch.object(ros, "request_build", return_value=built) as rb:
            out = ros.quick_build_version("p1", "v1", "tester")
        rb.assert_called_once_with("p1", "ro-q2", "tester")
        self.assertEqual(out["status"], "building")


class WorkflowRedirectTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    @patch("models.data.can_view_project", return_value=True)
    @patch.dict("models.data.project_versions_db", {
        "GomeKu": [{
            "id": "vc-test-1",
            "channel": "wechat",
            "platform": "android",
            "env_key": "development",
            "stage": "development",
        }],
    }, clear=False)
    @patch.dict("models.data.projects_db", {"GomeKu": {"name": "GomeKu"}}, clear=False)
    def test_workflow_redirects_to_release_start_build(self, _mock_view):
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = self.client.get("/admin/projects/GomeKu/versions/vc-test-1/workflow", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers.get("Location") or ""
        self.assertIn("/environments/development/channels/", loc)
        self.assertIn("/build", loc)
        self.assertIn("version_id=vc-test-1", loc)


if __name__ == "__main__":
    unittest.main()
