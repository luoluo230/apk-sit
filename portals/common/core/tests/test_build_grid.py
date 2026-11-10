# -*- coding: utf-8 -*-
"""Tests for distributed build grid routing."""

import unittest

from services.build.build_grid import (
    artifact_type_for_platform,
    normalize_build_platform,
    resolve_assigned_node,
    resolve_gameserver_job,
    resolve_jenkins_job_for_platform,
)
from services.build.build_node_service import build_grid_summary, register_or_heartbeat
from services.build.platform_capability import can_build, resolve_platform_capability


class BuildGridTests(unittest.TestCase):
    def test_normalize_platform(self):
        self.assertEqual(normalize_build_platform("iOS"), "ios")
        self.assertEqual(normalize_build_platform("wxminigame"), "wechat_minigame")
        self.assertEqual(normalize_build_platform("Android"), "android")
        with self.assertRaises(ValueError):
            normalize_build_platform("not-a-real-platform")
        with self.assertRaises(ValueError):
            normalize_build_platform("")

    def test_job_routing(self):
        self.assertEqual(resolve_jenkins_job_for_platform("android"), "Android")
        self.assertEqual(resolve_jenkins_job_for_platform("ios"), "iOS")
        self.assertEqual(resolve_jenkins_job_for_platform("wechat_minigame"), "WxMinigame")
        with self.assertRaises(ValueError):
            resolve_jenkins_job_for_platform("switch")
        server_job = resolve_gameserver_job()
        self.assertEqual(server_job["job_name"], "GameServer-Build")
        self.assertEqual(server_job["pipeline_script"], "gameserver_build_pipeline.sh")
        self.assertNotIn(server_job["job_name"], ("Android", "iOS", "WxMinigame"))

    def test_agent_labels(self):
        self.assertEqual(resolve_assigned_node("android"), "build-android")
        self.assertEqual(resolve_assigned_node("ios"), "build-ios")
        self.assertEqual(resolve_assigned_node("wechat_minigame"), "build-wxminigame")

    def test_artifact_types(self):
        self.assertEqual(artifact_type_for_platform("ios"), "ipa")
        self.assertEqual(artifact_type_for_platform("wechat_minigame"), "wxgame_bundle")

    def test_capability_blocks_excluded_platforms_despite_grid_jobs(self):
        """Jenkins job mapping may exist, but capability must not offer commercial build."""
        self.assertEqual(resolve_jenkins_job_for_platform("ios"), "iOS")
        ios_cap = resolve_platform_capability("ios")
        self.assertFalse(ios_cap["can_build"])
        self.assertFalse(can_build("ios"))
        self.assertIn("用户排除", str(ios_cap.get("build_block_reason") or ""))

    def test_node_heartbeat(self):
        node = register_or_heartbeat({
            "role": "build-android",
            "hostname": "test-host",
            "unity_version": "2022.3.1f1",
        })
        self.assertTrue(node.get("online"))
        summary = build_grid_summary()
        self.assertTrue(any(r.get("role_id") == "build-android" for r in summary.get("roles") or []))


if __name__ == "__main__":
    unittest.main()
