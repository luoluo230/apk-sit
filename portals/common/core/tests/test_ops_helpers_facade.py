# -*- coding: utf-8 -*-
"""Facade export lock for split ops.helpers. Plan P1-01 Step 1."""

from __future__ import annotations

import unittest


class OpsHelpersFacadeTests(unittest.TestCase):
    def setUp(self):
        import services.ops.helpers as helpers

        self.helpers = helpers

    def test_cluster_importer_exports(self):
        for name in (
            "_load_cluster_json",
            "_sync_cluster_to_agents",
            "_sync_cluster_to_topology",
        ):
            self.assertTrue(callable(getattr(self.helpers, name, None)), name)

    def test_topology_registry_exports(self):
        for name in (
            "_list_topologies",
            "_load_topology_scoped",
            "_save_topology_scoped",
            "_resolve_topology_context",
        ):
            self.assertTrue(callable(getattr(self.helpers, name, None)), name)

    def test_runtime_exports(self):
        for name in (
            "_runtime_active_for_scope",
            "_spawn_runtime_start_orchestration",
        ):
            self.assertTrue(callable(getattr(self.helpers, name, None)), name)

    def test_diagnostics_exports(self):
        self.assertTrue(callable(self.helpers._build_diagnostics_summary))
        self.assertTrue(callable(self.helpers._diagnostics_fix_actions))
        row = {"target_key": "topology:n1", "status": "OFFLINE", "probe_status": "FAIL", "issues": []}
        actions = self.helpers._diagnostics_fix_actions(row)
        self.assertIsInstance(actions, list)
        self.assertTrue(any(a.get("action_type") == "health_check" for a in actions))

    def test_facade_render_helpers(self):
        for name in ("_render_ops_page", "_allow_ops_view", "_ops_csrf_token"):
            self.assertTrue(callable(getattr(self.helpers, name, None)), name)

    def test_helpers_line_budget(self):
        import inspect
        import services.ops.helpers as mod

        path = inspect.getfile(mod)
        with open(path, encoding="utf-8") as fp:
            lines = sum(1 for _ in fp)
        self.assertLessEqual(lines, 450)


if __name__ == "__main__":
    unittest.main()
