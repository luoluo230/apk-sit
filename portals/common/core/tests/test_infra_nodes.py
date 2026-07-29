# -*- coding: utf-8 -*-
"""Tests for P1-05 infra_nodes unified registry."""

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

from models.db import init_db
from repositories import infra_nodes_repo
from services.infra import infra_node_registry as inr
from services.build.build_node_service import register_or_heartbeat, build_grid_summary


class InfraNodesRepoTests(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_build_heartbeat_persists_to_db(self):
        node = register_or_heartbeat(
            {
                "role": "build-android",
                "hostname": "node-android-1",
                "unity_version": "2022.3.1f1",
            }
        )
        self.assertTrue(node.get("online"))
        saved = infra_nodes_repo.get_node(str(node.get("id") or ""))
        self.assertIsNotNone(saved)
        self.assertEqual(saved.get("role"), "build-android")
        self.assertEqual(saved.get("jenkins_label"), "build-android")

    def test_runtime_upsert_separate_role(self):
        inr.upsert_runtime_node(
            "GomeKu",
            {
                "ServerId": "gateway-cn-1",
                "Type": "gateway",
                "Role": "gateway",
                "Host": "127.0.0.1",
                "Port": 15050,
                "DisplayName": "Gateway",
            },
        )
        runtime_nodes = inr.list_nodes(plane="runtime")
        self.assertTrue(any(str(n.get("role") or "").startswith("runtime-") for n in runtime_nodes))
        build_nodes = inr.list_nodes(plane="build")
        self.assertFalse(any(str(n.get("id") or "") == "gateway-cn-1" for n in build_nodes))

    def test_recommended_build_node(self):
        register_or_heartbeat({"role": "build-android", "hostname": "rec-host"})
        rec = inr.recommended_build_node_for_platform("android")
        self.assertTrue(rec.get("available"))
        self.assertEqual(rec.get("jenkins_label"), "build-android")

    def test_build_grid_summary_includes_runtime(self):
        inr.upsert_runtime_node("GomeKu", {"ServerId": "ops-cn-1", "Type": "ops", "Port": 5504})
        summary = build_grid_summary()
        self.assertIn("runtime_nodes", summary)


class BuildGridAssignedNodeTests(unittest.TestCase):
    @mock.patch("services.infra.infra_node_registry.resolve_online_build_node")
    def test_resolve_assigned_node_prefers_online(self, online_mock):
        from services.build.build_grid import resolve_assigned_node

        online_mock.return_value = {"jenkins_label": "build-android", "expected_label": "build-android"}
        self.assertEqual(resolve_assigned_node("android"), "build-android")


if __name__ == "__main__":
    unittest.main()
