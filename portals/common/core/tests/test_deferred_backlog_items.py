# -*- coding: utf-8 -*-
"""Tests for deferred backlog items: favorites, design demo purge, gray rollout."""

from __future__ import annotations

import unittest


class TestUserFavoritesService(unittest.TestCase):
    def test_save_and_toggle_favorites(self):
        from services.admin import user_favorites_service

        username = "admin"
        user_favorites_service.save_user_favorites(username, {"page_favorites": {}, "project_favorites": []})
        data = user_favorites_service.toggle_page_favorite(username, "GomeKu::overview")
        self.assertTrue(data["page_favorites"]["GomeKu::overview"])
        data = user_favorites_service.toggle_project_favorite(username, "GomeKu")
        self.assertIn("GomeKu", data["project_favorites"])


class TestDesignDemoTopologyPurge(unittest.TestCase):
    def test_design_demo_row_detection(self):
        from services.ops import helpers as ops_helpers

        row = {
            "topology_id": "topology-design-gomeku-production",
            "project_id": "GomeKu",
            "description": "设计稿 demo 拓扑",
        }
        self.assertTrue(ops_helpers._is_design_demo_topology_row(row))

    def test_list_topologies_filters_design_demo(self):
        from services.ops import helpers as ops_helpers

        rows = ops_helpers._list_topologies("GomeKu")
        self.assertFalse(any(ops_helpers._is_design_demo_topology_row(r) for r in rows))


class TestGrayRolloutPlan(unittest.TestCase):
    def test_resolve_rollout_from_gray_plan(self):
        from services.release.order_publish_flow import _resolve_rollout_from_plan

        meta = _resolve_rollout_from_plan(
            {"release_strategy": "gray", "gray_ratio": "25", "gray_strategy": "ratio", "gray_duration": "30"}
        )
        self.assertEqual(meta["rollout_percentage"], 25)
        self.assertTrue(meta["is_gray_active"])

    def test_standard_plan_is_full_rollout(self):
        from services.release.order_publish_flow import _resolve_rollout_from_plan

        meta = _resolve_rollout_from_plan({"release_strategy": "standard"})
        self.assertEqual(meta["rollout_percentage"], 100)
        self.assertFalse(meta["is_gray_active"])


class TestGrayJourneyBff(unittest.TestCase):
    def test_gray_rollout_view(self):
        from services.release.channel_journey_bff import _gray_rollout_view

        view = _gray_rollout_view(
            {
                "release_order_id": "ro-1",
                "status": "published",
                "payload": {"release_strategy": "gray", "gray_ratio": "10"},
            },
            {"client": {"rollout_percentage": 10}, "gray_status": "active"},
        )
        self.assertTrue(view["is_gray_active"])
        self.assertTrue(view["can_expand_gray"])

    def test_can_expand_gray_false_on_hold(self):
        from services.release.channel_journey_bff import _gray_rollout_view

        view = _gray_rollout_view(
            {
                "release_order_id": "ro-1",
                "status": "published",
                "payload": {"release_strategy": "gray", "gray_ratio": "10", "gray_success_action": "hold"},
            },
            {"client": {"rollout_percentage": 10}, "gray_status": "active"},
        )
        self.assertFalse(view["can_expand_gray"])

    def test_gray_auto_expand_scheduled_view(self):
        from services.release.channel_journey_bff import _gray_rollout_view

        view = _gray_rollout_view(
            {
                "release_order_id": "ro-1",
                "status": "published",
                "published_at": "2026-07-24T10:00:00",
                "payload": {
                    "release_strategy": "gray",
                    "gray_ratio": "10",
                    "gray_success_action": "automatic",
                    "gray_duration": "30",
                },
            },
            {"client": {"rollout_percentage": 10}, "gray_status": "active"},
        )
        self.assertTrue(view["gray_auto_expand_scheduled"])
        self.assertEqual(view["gray_success_action_label"], "自动放量")
        self.assertTrue(view["gray_auto_expand_due_at"].startswith("2026-07-24T10:30:00"))


class TestOpenApiSchemaCoverage(unittest.TestCase):
    def test_openapi_spec_is_current_and_typed(self):
        import json
        import os
        import subprocess
        import sys

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        script = os.path.join(root, "scripts", "generate_openapi.py")
        env = os.environ.copy()
        env.pop("BAAS_STANDALONE", None)
        env.pop("PORTAL_SERVER_FRAMEWORKS", None)
        env.setdefault("APP_PORTAL_MODE", "admin")
        proc = subprocess.run([sys.executable, script, "--check"], cwd=root, capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        payload = json.loads(proc.stdout.strip())
        self.assertGreaterEqual(payload.get("paths", 0), 140)
        self.assertEqual(payload.get("ops_with_schema"), payload.get("operations"))


if __name__ == "__main__":
    unittest.main()
