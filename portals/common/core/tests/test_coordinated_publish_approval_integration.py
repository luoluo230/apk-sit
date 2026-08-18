# -*- coding: utf-8 -*-
"""Staging/production approval + coordinated server publish integration."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")

from services.release import order_crud as oc
from services.release import order_publish_flow as opf


def _order(**overrides):
    base = {
        "release_order_id": "ro-coord-1",
        "project_id": "p1",
        "version_id": "v1",
        "version_code": "100",
        "version_name": "1.0.0",
        "channel_id": "wechat",
        "platform": "android",
        "env_key": "staging",
        "status": "artifacts_ready",
        "scope_id": "scope-1",
        "payload": {"deploy_server_with_client": True, "target_topology_id": "topo-1"},
        "artifacts": [],
    }
    base.update(overrides)
    return base


class CoordinatedPublishApprovalTests(unittest.TestCase):
    def test_staging_two_tier_approval_flow(self):
        pending = _order(env_key="staging", status="awaiting_approval")
        approved = {**pending, "status": "approved"}
        with mock.patch.object(oc, "get_release_order", side_effect=[pending, pending, pending, approved]), \
             mock.patch.object(oc, "_transition", return_value=pending), \
             mock.patch.object(opf, "get_cursor") as cursor_cm, \
             mock.patch.object(opf, "_event"):
            cursor = mock.MagicMock()
            cursor.execute.return_value.fetchall.side_effect = [
                [{"approval_id": "ra-1", "note": "tier:qa"}],
                [{"approval_id": "ra-2", "note": "tier:release_manager"}],
            ]
            cursor.execute.return_value.fetchone.side_effect = [
                {"cnt": 1},
                {"cnt": 0},
            ]
            cursor_cm.return_value.__enter__.return_value = cursor
            cursor_cm.return_value.__exit__.return_value = False
            opf.approve_release_order("p1", "ro-coord-1", "qa", note="tier:qa")
            out = opf.approve_release_order("p1", "ro-coord-1", "release_manager", note="tier:release_manager")
        self.assertEqual(out["status"], "approved")

    def test_coordinated_deploy_resolves_linked_server_artifact(self):
        from services.release.server_coordinated_deploy import maybe_deploy_server_with_client

        order = _order(
            status="approved",
            payload={
                "deploy_server_with_client": True,
                "target_topology_id": "topo-1",
                "target_services": ["game-cn-1"],
                "jenkins_instance_id": "8082",
                "build_job_id": "200",
            },
        )
        with mock.patch(
            "services.release.jenkins_build_linkage_service.resolve_server_artifact_for_order",
            return_value="sart-linked-200",
        ), mock.patch("services.release.server_release_service.create_server_release") as create_fn, \
             mock.patch("services.release.server_release_service.get_server_release") as get_fn, \
             mock.patch("services.release.server_release_service.deploy_server_release") as deploy_fn, \
             mock.patch("services.release.server_coordinated_deploy.get_cursor") as cursor_cm, \
             mock.patch("services.release.server_coordinated_deploy._event"):
            create_fn.return_value = {"server_release_id": "sro-200", "artifact_id": "sart-linked-200", "target_services": ["game-cn-1"]}
            get_fn.return_value = {
                "server_release_id": "sro-200",
                "artifact_id": "sart-linked-200",
                "target_services": ["game-cn-1"],
                "topology_id": "topo-1",
            }
            deploy_fn.return_value = {"status": "deploying", "artifact_id": "sart-linked-200", "payload": {}}
            cursor = mock.MagicMock()
            cursor.execute.return_value.fetchone.return_value = None
            cursor_cm.return_value.__enter__.return_value = cursor
            cursor_cm.return_value.__exit__.return_value = False
            out = maybe_deploy_server_with_client(
                "p1", "ro-coord-1", order, order["payload"], topology_id="topo-1", actor="tester"
            )
        create_fn.assert_called_once()
        self.assertFalse(out.get("skipped"))

    def test_production_publish_blocked_without_approval(self):
        order = _order(env_key="production", status="ready")
        with mock.patch.object(oc, "get_release_order", return_value=order):
            with self.assertRaises(ValueError) as ctx:
                opf.publish_release_order("p1", "ro-coord-1", "tester")
            self.assertIn("审批", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
