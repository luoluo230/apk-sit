# -*- coding: utf-8 -*-
"""Tests for ops runtime_service._runtime_active_for_scope."""

from __future__ import annotations

import unittest
from unittest import mock


class RuntimeActiveForScopeTests(unittest.TestCase):
    def test_no_start_run(self):
        with mock.patch("services.ops.runtime_service._load_runtime_runs", return_value=[]):
            from services.ops.runtime_service import _runtime_active_for_scope

            out = _runtime_active_for_scope("p1", "development", "topo-1")
        self.assertFalse(out["active"])
        self.assertEqual(out["reason"], "no_start_run")

    def test_start_alive(self):
        rows = [
            {
                "project_id": "p1",
                "env_key": "development",
                "topology_id": "topo-1",
                "op": "start",
                "status": "running",
                "run_id": "run-42",
                "updated_at": "2026-07-22T10:00:00Z",
            }
        ]
        with mock.patch("services.ops.runtime_service._load_runtime_runs", return_value=rows):
            from services.ops.runtime_service import _runtime_active_for_scope

            out = _runtime_active_for_scope("p1", "development", "topo-1")
        self.assertTrue(out["active"])
        self.assertEqual(out["run_id"], "run-42")
        self.assertEqual(out["reason"], "start_alive")

    def test_stopped_after_start(self):
        rows = [
            {
                "project_id": "p1",
                "env_key": "development",
                "topology_id": "topo-1",
                "op": "start",
                "status": "running",
                "run_id": "run-1",
                "updated_at": "2026-07-22T09:00:00Z",
            },
            {
                "project_id": "p1",
                "env_key": "development",
                "topology_id": "topo-1",
                "op": "stop",
                "status": "success",
                "run_id": "run-stop",
                "updated_at": "2026-07-22T10:00:00Z",
            },
        ]
        with mock.patch("services.ops.runtime_service._load_runtime_runs", return_value=rows):
            from services.ops.runtime_service import _runtime_active_for_scope

            out = _runtime_active_for_scope("p1", "development", "topo-1")
        self.assertFalse(out["active"])
        self.assertEqual(out["reason"], "stopped_after_start")


if __name__ == "__main__":
    unittest.main()
