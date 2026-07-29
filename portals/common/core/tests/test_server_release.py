# -*- coding: utf-8
"""Tests for P2-01 server release plane."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from models.db import init_db
from services.release import server_artifact_service as sas
from services.release import server_release_service as srs


class ServerArtifactTests(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_register_artifact_from_path(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as fh:
            fh.write(b"fake-server-bundle")
            path = fh.name
        try:
            row = sas.register_artifact(
                "GomeKu",
                {"version_label": "1.0.0", "protocol_version": "v1"},
                source_path=path,
            )
            self.assertTrue(row.get("artifact_id"))
            self.assertTrue(row.get("checksum"))
            saved = sas.get_artifact(row["artifact_id"])
            self.assertEqual(saved.get("version_label"), "1.0.0")
        finally:
            os.remove(path)


class ServerReleaseTransitionTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.artifact = sas.register_artifact(
            "GomeKu",
            {"artifact_id": "sart-test-1", "version_label": "1.0.1", "bundle_path": "/tmp/fake.zip", "checksum": "abc"},
        )
        self.release = srs.create_server_release(
            "GomeKu",
            {
                "topology_id": "topo-dev",
                "artifact_id": self.artifact["artifact_id"],
                "target_services": ["game-cn-1"],
                "env_key": "development",
            },
            "tester",
        )

    def test_create_ready_with_artifact(self):
        self.assertEqual(self.release.get("status"), "ready")

    def test_transition_to_deploying_requires_deploy(self):
        rid = self.release["server_release_id"]
        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-1", "status": "PENDING"}]
            out = srs.deploy_server_release("GomeKu", rid, "tester")
        self.assertEqual(out.get("status"), "deploying")
        enqueue.assert_called_once()

    def test_complete_deploy_marks_deployed(self):
        rid = self.release["server_release_id"]
        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-1"}]
            srs.deploy_server_release("GomeKu", rid, "tester")
        out = srs.complete_deploy_server_release("GomeKu", rid, ok=True, actor="agent")
        self.assertEqual(out.get("status"), "deployed")

    def test_precheck_gate_passes_when_deployed(self):
        rid = self.release["server_release_id"]
        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-1"}]
            srs.deploy_server_release("GomeKu", rid, "tester")
        srs.complete_deploy_server_release("GomeKu", rid, ok=True, actor="agent")
        gate = srs.assess_server_release_for_precheck("GomeKu", rid, min_server_version="1.0.0")
        self.assertTrue(gate.get("ok"))

    def test_precheck_gate_fails_when_draft(self):
        draft = srs.create_server_release(
            "GomeKu",
            {"topology_id": "topo-dev", "target_services": ["game-cn-1"], "env_key": "development"},
            "tester",
        )
        gate = srs.assess_server_release_for_precheck("GomeKu", draft["server_release_id"])
        self.assertFalse(gate.get("ok"))


class PrecheckIntegrationTests(unittest.TestCase):
    @mock.patch("services.release.release_policy_service.get_env_release_policy", return_value={"runtime_required": "block", "auto_ensure_runtime": False})
    @mock.patch("services.release.validation_plan_runner.run_validation_plan", return_value={"ok": True, "items": []})
    @mock.patch("services.ops.runtime_service._runtime_active_for_scope", return_value={"active": True, "run_id": "run-1"})
    @mock.patch("services.release.order_publish_flow.run_scope_precheck")
    @mock.patch("services.release.order_publish_flow.resolve_topology_binding_for_scope", return_value={"topology_id": "topo-1"})
    @mock.patch("services.release.order_publish_flow.resolve_scope", return_value={"scope_id": "scope-1"})
    @mock.patch("services.admin.version_service.enrich_version_client_urls", side_effect=lambda _p, v: v)
    @mock.patch("services.release.order_publish_flow._find_version", return_value={"id": "v1", "version_name": "1.0.0"})
    @mock.patch("services.release.order_crud._transition")
    @mock.patch("services.release.order_crud.get_release_order")
    @mock.patch("services.release.order_publish_flow.get_cursor")
    @mock.patch("services.release.order_publish_flow._event")
    def test_precheck_blocks_prod_when_server_not_deployed(
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
        _runtime,
        _validation,
        _policy,
    ):
        from services.release import order_publish_flow as opf

        init_db()
        artifact = sas.register_artifact(
            "p1",
            {"artifact_id": "sart-precheck", "version_label": "1.0.0", "bundle_path": "/tmp/x.zip", "checksum": "x"},
        )
        sro = srs.create_server_release(
            "p1",
            {"topology_id": "topo-1", "artifact_id": artifact["artifact_id"], "target_services": ["game-cn-1"], "env_key": "production"},
            "tester",
        )
        order = {
            "release_order_id": "ro-srv-1",
            "project_id": "p1",
            "env_key": "production",
            "channel_id": "1001",
            "platform": "android",
            "version_id": "v1",
            "version_code": "12",
            "status": "artifacts_ready",
            "payload": {"server_release_id": sro["server_release_id"], "min_server_version": "1.0.0"},
        }
        scope_precheck_mock.return_value = {"ok": True, "scope_id": "scope-1", "topology_id": "topo-1"}
        get_order_mock.side_effect = [order, {**order, "status": "precheck_failed"}]
        cursor_cm.return_value.__enter__.return_value = mock.MagicMock()
        cursor_cm.return_value.__exit__.return_value = False
        out = opf.precheck_release_order("p1", "ro-srv-1", "tester")
        self.assertEqual(out["status"], "precheck_failed")


if __name__ == "__main__":
    unittest.main()
