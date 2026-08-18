# -*- coding: utf-8 -*-
"""Tests for release hub, artifact promotion, and two-tier approval."""

from __future__ import annotations

import unittest


class ReleaseHubBffTests(unittest.TestCase):
    def test_build_release_hub_structure(self):
        from models.data import projects_db
        from services.release.release_hub_bff import build_release_hub

        pid = "__test_release_hub__"
        projects_db[pid] = {"name": "Hub Test", "channels": ["wechat"]}
        data = build_release_hub(pid)
        self.assertEqual(data["project_id"], pid)
        self.assertTrue(any(c["id"] == "release-console" for c in data["module_cards"]))
        self.assertIn("promotion_candidates", data)
        self.assertIn("server_promotion_candidates", data)
        self.assertIn("coordinated_deploy_feed", data)
        self.assertIn("release_health", data)
        self.assertGreaterEqual(len(data["prod_wizard_steps"]), 4)
        projects_db.pop(pid, None)


class ArtifactPromotionTests(unittest.TestCase):
    def setUp(self):
        from models.db import init_db

        init_db()

    def test_env_rank_blocks_downgrade(self):
        from models.data import projects_db
        from services.release.bundle_promotion_service import promote_bundle_to_env

        pid = "__test_promotion__"
        projects_db[pid] = {"name": "Promo Test"}
        with self.assertRaises(ValueError):
            promote_bundle_to_env(pid, "missing-bundle", "production", "tester")
        projects_db.pop(pid, None)

    def test_list_promotion_candidates_empty_project(self):
        from models.data import projects_db
        from services.release.bundle_promotion_service import list_promotion_candidates

        pid = "__test_promotion_list__"
        projects_db[pid] = {"name": "Empty Promo"}
        rows = list_promotion_candidates(pid)
        self.assertIsInstance(rows, list)
        projects_db.pop(pid, None)


class TwoTierApprovalPolicyTests(unittest.TestCase):
    def test_production_has_two_tiers(self):
        from services.release.release_policy_service import get_env_release_policy

        policy = get_env_release_policy("__any__", "production")
        self.assertTrue(policy.get("require_approval"))
        self.assertTrue(policy.get("two_tier_approval"))
        self.assertEqual(policy.get("approval_tiers"), ["qa", "release_manager"])


if __name__ == "__main__":
    unittest.main()
