# -*- coding: utf-8 -*-
"""Tests for release console and env registry fixes."""

from __future__ import annotations

import unittest


class EnvRegistryReleasePolicyTests(unittest.TestCase):
    def test_merge_release_policy_from_project(self):
        from models.data import projects_db
        from services.release.env_registry import get_project_env_defs

        pid = "__test_release_console__"
        projects_db[pid] = {
            "name": "Test",
            "release_environments": [
                {
                    "env_key": "development",
                    "release_policy": {"form_depth": "full", "require_approval": True},
                }
            ],
        }
        defs = get_project_env_defs(pid)
        dev = next(r for r in defs if r["env_key"] == "development")
        self.assertIn("release_policy", dev)
        self.assertEqual(dev["release_policy"]["form_depth"], "full")
        self.assertTrue(dev["release_policy"]["require_approval"])
        projects_db.pop(pid, None)


class ReleaseBatchServiceTests(unittest.TestCase):
    def setUp(self):
        from models.db import init_db

        init_db()

    def test_batch_status_aggregation_partial_failed(self):
        from services.release.release_batch_service import _aggregate_batch_status

        orders = [{"status": "ready"}, {"status": "precheck_failed"}]
        self.assertEqual(_aggregate_batch_status(orders), "partial_failed")

    def test_batch_id_format(self):
        from services.release.release_batch_service import _batch_id

        bid = _batch_id()
        self.assertTrue(bid.startswith("rbatch-"))


if __name__ == "__main__":
    unittest.main()
