# -*- coding: utf-8 -*-
"""Release state machine integration: precheck → publish → verify (mock OSS/runtime)."""

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
from services.release import order_build_sync as obs
from services.release import order_crud as oc
from services.release import order_publish_flow as opf
from services.release import release_order_service as ros


def _order(**overrides):
    base = {
        "release_order_id": "ro-int-1",
        "project_id": "p1",
        "version_id": "v1",
        "version_code": "100",
        "version_name": "1.0.0",
        "channel_id": "wechat",
        "platform": "android",
        "env_key": "development",
        "status": "artifacts_ready",
        "scope_id": "scope-1",
        "payload": {},
        "artifacts": [],
    }
    base.update(overrides)
    return base


class PrecheckTransitionTests(unittest.TestCase):
    def test_dev_precheck_ok_becomes_ready(self):
        order = _order(env_key="development", status="artifacts_ready")
        precheck = {"ok": True, "scope_id": "scope-1", "topology_id": "topo-1", "binding_source": "matrix"}
        with mock.patch.object(oc, "get_release_order", side_effect=[order, {**order, "status": "ready"}]), \
             mock.patch.object(opf, "_find_version", return_value={"id": "v1", "version_name": "1.0.0"}), \
             mock.patch("services.admin.version_service.enrich_version_client_urls", side_effect=lambda _p, v: v), \
             mock.patch.object(opf, "resolve_scope", return_value={"scope_id": "scope-1"}), \
             mock.patch("services.release.bundle_service.run_scope_precheck", return_value=precheck), \
             mock.patch.object(opf, "resolve_topology_binding_for_scope", return_value={"topology_id": "topo-1"}), \
             mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"runtime_required": "block"}), \
             mock.patch("services.ops.helpers._runtime_active_for_scope", return_value={"active": True, "run_id": "run-1"}), \
             mock.patch.object(oc, "_transition", return_value=order), \
             mock.patch.object(opf, "get_cursor") as cursor_cm, \
             mock.patch.object(opf, "_event"):
            cursor_cm.return_value.__enter__.return_value = mock.MagicMock()
            cursor_cm.return_value.__exit__.return_value = False
            out = ros.precheck_release_order("p1", "ro-int-1", "tester")
        self.assertEqual(out["status"], "ready")

    def test_prod_precheck_ok_becomes_awaiting_approval(self):
        order = _order(env_key="production", status="artifacts_ready")
        precheck = {"ok": True, "scope_id": "scope-1", "topology_id": "topo-1", "binding_source": "matrix"}
        with mock.patch.object(oc, "get_release_order", side_effect=[order, {**order, "status": "awaiting_approval"}]), \
             mock.patch.object(opf, "_find_version", return_value={"id": "v1", "version_name": "1.0.0"}), \
             mock.patch("services.admin.version_service.enrich_version_client_urls", side_effect=lambda _p, v: v), \
             mock.patch.object(opf, "resolve_scope", return_value={"scope_id": "scope-1"}), \
             mock.patch("services.release.bundle_service.run_scope_precheck", return_value=precheck), \
             mock.patch.object(opf, "resolve_topology_binding_for_scope", return_value={"topology_id": "topo-1"}), \
             mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"runtime_required": "block"}), \
             mock.patch("services.ops.helpers._runtime_active_for_scope", return_value={"active": True, "run_id": "run-1"}), \
             mock.patch.object(oc, "_transition", return_value=order), \
             mock.patch.object(opf, "get_cursor") as cursor_cm, \
             mock.patch.object(opf, "_event"):
            cursor_cm.return_value.__enter__.return_value = mock.MagicMock()
            cursor_cm.return_value.__exit__.return_value = False
            out = ros.precheck_release_order("p1", "ro-int-1", "tester")
        self.assertEqual(out["status"], "awaiting_approval")


class PublishGovernanceTests(unittest.TestCase):
    def test_prod_publish_without_approval_rejected(self):
        order = _order(env_key="production", status="ready")
        with mock.patch.object(oc, "get_release_order", return_value=order):
            with self.assertRaises(ValueError) as ctx:
                ros.publish_release_order("p1", "ro-int-1", "tester")
            self.assertIn("审批", str(ctx.exception))

    def test_scope_publish_production_blocked_by_default(self):
        with mock.patch("services.release.storage.find_scope", return_value={"env_key": "production"}):
            with self.assertRaises(ValueError) as ctx:
                ros.activate_bundle_on_scope("p1", "scope-prod", "bundle-1", "tester")
            self.assertIn("禁止", str(ctx.exception))

    def test_scope_publish_requires_release_order_id(self):
        with mock.patch("services.release.storage.find_scope", return_value={"env_key": "development"}):
            with self.assertRaises(ValueError) as ctx:
                ros.activate_bundle_on_scope("p1", "scope-dev", "bundle-1", "tester")
            self.assertIn("release_order_id", str(ctx.exception))


class VerifySmokeTests(unittest.TestCase):
    def test_verify_ok_runs_smoke_before_verified(self):
        order = _order(status="published", bundle_id="bundle-1", scope_id="scope-1")
        verified = {**order, "status": "verified"}
        smoke = {"ok": True, "checks": [{"key": "catalog_url", "ok": True}]}
        with mock.patch.object(oc, "get_release_order", side_effect=[order, verified]), \
             mock.patch.object(oc, "_transition", side_effect=[order, verified]) as transition, \
             mock.patch.object(opf, "run_bootstrap_smoke_for_order", return_value=smoke) as smoke_fn:
            out = ros.verify_release_order("p1", "ro-int-1", "tester", ok=True)
        smoke_fn.assert_called_once_with("p1", "ro-int-1")
        self.assertGreaterEqual(transition.call_count, 2)
        self.assertEqual(transition.call_args.args[3], "verified")
        self.assertEqual(out["status"], "verified")

    def test_verify_smoke_fail_marks_verify_failed(self):
        order = _order(status="published", bundle_id="bundle-1", scope_id="scope-1")
        failed = {**order, "status": "verify_failed"}
        smoke = {"ok": False, "checks": [{"key": "catalog_url", "ok": False}]}
        with mock.patch.object(oc, "get_release_order", side_effect=[order, failed]), \
             mock.patch.object(oc, "_transition", side_effect=[order, failed]) as transition, \
             mock.patch.object(opf, "run_bootstrap_smoke_for_order", return_value=smoke):
            out = ros.verify_release_order("p1", "ro-int-1", "tester", ok=True)
        self.assertEqual(transition.call_args.args[3], "verify_failed")
        self.assertEqual(out["status"], "verify_failed")


class QuickPublishApiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    @mock.patch("routes.delivery.journey_api.quick_publish_delivery")
    @mock.patch.dict("models.data.projects_db", {"GomeKu": {"name": "GomeKu"}}, clear=False)
    def test_quick_publish_route(self, qp_mock):
        qp_mock.return_value = {"phase": "verified", "release_order_id": "ro-q1", "order": {"status": "verified"}}
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        resp = self.client.post(
            "/api/projects/GomeKu/delivery-attempts/quick-publish",
            json={
                "env_key": "development",
                "channel_id": "wechat",
                "platform": "android",
                "version_id": "vc-1",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        qp_mock.assert_called_once()


class ReleaseJourneyEnsureOrderTests(unittest.TestCase):
    def test_missing_order_exposes_ensure_api(self):
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
            "versions": [{"version_id": "vc-1", "artifacts_ready": True, "version_name": "1.0.1", "version_code": "1"}],
        }), mock.patch.object(cjb, "_enrich_state_from_version_id", side_effect=lambda _p, s, vid: {**s, "version_id": vid}), \
             mock.patch.object(oc, "find_release_order_for_version", return_value=None), \
             mock.patch.object(obs, "sync_building_release_orders", return_value=[]), \
             mock.patch.object(oc, "list_release_orders", return_value=[]), \
             mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"form_depth": "minimal"}):
            data = ros.resolve_channel_release_journey(
                "GomeKu",
                "development",
                "wechat",
                platform="android",
                version_id="vc-1",
            )
        state = data["per_platform"]["android"]
        self.assertIn("ensure_order_api", state)
        self.assertIn("ensure-release-order", state["ensure_order_api"])


if __name__ == "__main__":
    unittest.main()