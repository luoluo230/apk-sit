# -*- coding: utf-8 -*-
"""Tests for distributed build grid routing."""

import unittest

from services.build.build_grid import (
    artifact_type_for_platform,
    normalize_build_platform,
    resolve_assigned_node,
    resolve_jenkins_job_for_platform,
)
from services.build.build_node_service import build_grid_summary, register_or_heartbeat


class BuildGridTests(unittest.TestCase):
    def test_normalize_platform(self):
        self.assertEqual(normalize_build_platform("iOS"), "ios")
        self.assertEqual(normalize_build_platform("wxminigame"), "wechat_minigame")
        self.assertEqual(normalize_build_platform("Android"), "android")

    def test_job_routing(self):
        self.assertEqual(resolve_jenkins_job_for_platform("android"), "Android")
        self.assertEqual(resolve_jenkins_job_for_platform("ios"), "iOS")
        self.assertEqual(resolve_jenkins_job_for_platform("wechat_minigame"), "WxMinigame")

    def test_agent_labels(self):
        self.assertEqual(resolve_assigned_node("android"), "build-android")
        self.assertEqual(resolve_assigned_node("ios"), "build-ios")
        self.assertEqual(resolve_assigned_node("wechat_minigame"), "build-wxminigame")

    def test_artifact_types(self):
        self.assertEqual(artifact_type_for_platform("ios"), "ipa")
        self.assertEqual(artifact_type_for_platform("wechat_minigame"), "wxgame_bundle")

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
