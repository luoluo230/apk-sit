# -*- coding: utf-8 -*-
"""Topology registry IO mocks. Plan P1-01 Step 3."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TopologyRegistryTests(unittest.TestCase):
    @patch("services.ops.topology_registry._migrate_topology_storage_if_needed")
    @patch("services.ops.topology_registry._load_topology_registry", return_value=[])
    @patch("services.ops.topology_registry._load_topology_contents", return_value={})
    def test_list_topologies_empty(self, _mock_contents, _mock_registry, _mock_migrate):
        from services.ops.topology_registry import _list_topologies

        rows = _list_topologies("DemoProj", "production")
        self.assertEqual(rows, [])

    @patch("services.ops.topology_registry._purge_design_demo_topology_registry")
    @patch("services.ops.topology_registry._migrate_topology_storage_if_needed")
    @patch("services.ops.topology_registry._load_topology_registry")
    @patch("services.ops.topology_registry._load_topology_contents", return_value={})
    def test_list_topologies_filters_env(self, _mock_contents, mock_registry, *_patches):
        mock_registry.return_value = [
            {"topology_id": "t1", "project_id": "DemoProj", "env_key": "production", "name": "Prod"},
            {"topology_id": "t2", "project_id": "DemoProj", "env_key": "development", "name": "Dev"},
        ]
        from services.ops.topology_registry import _list_topologies

        rows = _list_topologies("DemoProj", "production")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["topology_id"], "t1")


if __name__ == "__main__":
    unittest.main()
