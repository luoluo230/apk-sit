# -*- coding: utf-8 -*-
"""Tests for P1-04 dev delivery simplification."""

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

from services.release import order_publish_flow as opf
from services.release import order_crud as oc
from services.release import release_policy_service as rps
from services.ops import runtime_ensure_service as res


class RuntimeEnsureServiceTests(unittest.TestCase):
    @mock.patch("services.ops.runtime_service._runtime_active_for_scope")
    def test_ensure_runtime_idempotent_when_active(self, active_mock):
        active_mock.return_value = {"active": True, "run_id": "run-live"}
        out = res.ensure_runtime_for_scope("p1", "development", "topo-1", "tester")
        self.assertTrue(out["active"])
        self.assertEqual(out["run_id"], "run-live")
        self.assertFalse(out["started"])

    @mock.patch("services.ops.runtime_orchestrator._spawn_runtime_start_orchestration")
    @mock.patch("services.ops.topology_registry._load_topology_scoped")
    @mock.patch("services.ops.topology_registry._project_uses_runtime_topology", return_value=True)
    @mock.patch("services.ops.storage._upsert_runtime_run")
    @mock.patch("services.ops.runtime_service._runtime_active_for_scope")
    def test_ensure_runtime_starts_when_inactive(
        self,
        active_mock,
        upsert_mock,
        uses_topo_mock,
        load_topo_mock,
        spawn_mock,
    ):
        active_mock.side_effect = [
            {"active": False, "run_id": ""},
            {"active": True, "run_id": "run-new"},
        ]
        load_topo_mock.return_value = {"nodes": [{"id": "gs-1"}], "edges": []}
        out = res.ensure_runtime_for_scope("p1", "development", "topo-1", "tester", poll_sec=5)
        self.assertTrue(out["active"])
        self.assertTrue(out["started"])
        spawn_mock.assert_called_once()
        upsert_mock.assert_called_once()


class ReleasePolicyAutoEnsureTests(unittest.TestCase):
    def test_development_defaults_auto_ensure(self):
        policy = rps.normalize_release_policy({}, "development")
        self.assertEqual(policy.get("runtime_required"), rps.RUNTIME_REQUIRED_AUTO)
        self.assertTrue(policy.get("auto_ensure_runtime"))

    def test_production_never_auto_ensure(self):
        policy = rps.normalize_release_policy({}, "production")
        self.assertEqual(policy.get("runtime_required"), rps.RUNTIME_REQUIRED_BLOCK)
        self.assertFalse(policy.get("auto_ensure_runtime"))
        self.assertFalse(rps.should_auto_ensure_runtime("p1", "production", policy))

    def test_should_auto_ensure_for_development(self):
        policy = rps.get_env_release_policy("any_project", "development")
        self.assertTrue(rps.should_auto_ensure_runtime("any_project", "development", policy))


def _order(**extra):
    base = {
        "release_order_id": "ro-dev-1",
        "project_id": "p1",
        "env_key": "development",
        "channel_id": "1001",
        "platform": "android",
        "version_id": "v1",
        "version_code": "12",
        "status": "artifacts_ready",
        "payload": {},
    }
    base.update(extra)
    return base


class PrecheckAutoEnsureTests(unittest.TestCase):
    @mock.patch("services.ops.runtime_ensure_service.ensure_runtime_for_scope")
    @mock.patch("services.ops.runtime_service._runtime_active_for_scope")
    @mock.patch("services.release.validation_plan_runner.run_validation_plan", return_value={"ok": True, "items": []})
    @mock.patch("services.release.bundle_service.run_scope_precheck")
    @mock.patch.object(opf, "resolve_topology_binding_for_scope", return_value={"topology_id": "topo-1"})
    @mock.patch.object(opf, "resolve_scope", return_value={"scope_id": "scope-1"})
    @mock.patch("services.admin.version_service.enrich_version_client_urls", side_effect=lambda _p, v: v)
    @mock.patch.object(opf, "_find_version", return_value={"id": "v1", "version_name": "1.0.0"})
    @mock.patch.object(oc, "_transition", return_value=_order())
    @mock.patch.object(oc, "get_release_order")
    @mock.patch.object(opf, "get_cursor")
    @mock.patch.object(opf, "_event")
    def test_dev_precheck_auto_ensures_runtime(
        self,
        _event,
        cursor_cm,
        get_order_mock,
        _transition,
        _find_version,
        _enrich,
        _scope,
        _binding,
        scope_precheck_mock,
        _validation,
        active_mock,
        ensure_mock,
    ):
        scope_precheck_mock.return_value = {"ok": True, "scope_id": "scope-1", "topology_id": "topo-1"}
        ensure_mock.return_value = {"active": True, "run_id": "run-auto", "started": True, "error": ""}
        active_mock.return_value = {"active": True, "run_id": "run-auto"}
        order = _order()
        get_order_mock.side_effect = [order, {**order, "status": "ready"}]
        cursor_cm.return_value.__enter__.return_value = mock.MagicMock()
        cursor_cm.return_value.__exit__.return_value = False

        out = opf.precheck_release_order("p1", "ro-dev-1", "tester")
        ensure_mock.assert_called_once()
        self.assertEqual(out["status"], "ready")

    @mock.patch("services.ops.runtime_ensure_service.ensure_runtime_for_scope")
    @mock.patch("services.ops.runtime_service._runtime_active_for_scope", return_value={"active": False, "run_id": ""})
    @mock.patch("services.release.validation_plan_runner.run_validation_plan", return_value={"ok": True, "items": []})
    @mock.patch("services.release.bundle_service.run_scope_precheck")
    @mock.patch.object(opf, "resolve_topology_binding_for_scope", return_value={"topology_id": "topo-1"})
    @mock.patch.object(opf, "resolve_scope", return_value={"scope_id": "scope-1"})
    @mock.patch("services.admin.version_service.enrich_version_client_urls", side_effect=lambda _p, v: v)
    @mock.patch.object(opf, "_find_version", return_value={"id": "v1", "version_name": "1.0.0"})
    @mock.patch.object(oc, "_transition", return_value=_order(env_key="production"))
    @mock.patch.object(oc, "get_release_order")
    @mock.patch.object(opf, "get_cursor")
    @mock.patch.object(opf, "_event")
    def test_prod_precheck_does_not_auto_ensure(
        self,
        _event,
        cursor_cm,
        get_order_mock,
        _transition,
        _find_version,
        _enrich,
        _scope,
        _binding,
        scope_precheck_mock,
        _validation,
        _active,
        ensure_mock,
    ):
        scope_precheck_mock.return_value = {"ok": True, "scope_id": "scope-1", "topology_id": "topo-1"}
        order = _order(env_key="production", status="artifacts_ready")
        get_order_mock.side_effect = [order, {**order, "status": "precheck_failed"}]
        cursor_cm.return_value.__enter__.return_value = mock.MagicMock()
        cursor_cm.return_value.__exit__.return_value = False

        opf.precheck_release_order("p1", "ro-dev-1", "tester")
        ensure_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
