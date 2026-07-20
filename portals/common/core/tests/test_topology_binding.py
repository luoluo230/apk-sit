# -*- coding: utf-8 -*-
"""Topology binding resolution and picker aggregation."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: F401 — bootstrap imports

from models.db import _get_conn, init_db
from services.release.topology_binding_service import (
    build_topology_binding_picker,
    delete_topology_binding_for_scope,
    resolve_topology_binding,
    upsert_topology_binding,
)


_TEST_PROJECT = "test_topology_binding_proj"


def _clear_bindings(project_id: str) -> None:
    init_db()
    with _get_conn() as conn:
        conn.execute("DELETE FROM topology_bindings WHERE project_id=?", (project_id,))
        conn.commit()


class TopologyBindingTests(unittest.TestCase):
    def setUp(self):
        _clear_bindings(_TEST_PROJECT)

    def tearDown(self):
        _clear_bindings(_TEST_PROJECT)

    def test_platform_priority_over_env_channel_legacy(self):
        upsert_topology_binding(
            {
                "project_id": _TEST_PROJECT,
                "env_key": "development",
                "channel_id": "wechat",
                "platform": "",
                "topology_id": "topo-legacy-channel",
            },
            actor="test",
        )
        upsert_topology_binding(
            {
                "project_id": _TEST_PROJECT,
                "env_key": "development",
                "channel_id": "wechat",
                "platform": "android",
                "topology_id": "topo-android-specific",
            },
            actor="test",
        )
        android = resolve_topology_binding(
            _TEST_PROJECT,
            "development",
            "wechat",
            platform="android",
        )
        ios = resolve_topology_binding(
            _TEST_PROJECT,
            "development",
            "wechat",
            platform="ios",
        )
        self.assertEqual(android["topology_id"], "topo-android-specific")
        self.assertEqual(android["binding_source"], "env_channel_platform")
        self.assertEqual(ios["topology_id"], "topo-legacy-channel")
        self.assertEqual(ios["binding_source"], "env_channel")

    def test_version_override_wins_over_platform(self):
        upsert_topology_binding(
            {
                "project_id": _TEST_PROJECT,
                "env_key": "development",
                "channel_id": "wechat",
                "platform": "android",
                "topology_id": "topo-platform-default",
            },
            actor="test",
        )
        upsert_topology_binding(
            {
                "project_id": _TEST_PROJECT,
                "env_key": "development",
                "channel_id": "wechat",
                "platform": "android",
                "version_name": "1.0.1",
                "topology_id": "topo-version-101",
            },
            actor="test",
        )
        resolved = resolve_topology_binding(
            _TEST_PROJECT,
            "development",
            "wechat",
            platform="android",
            version_name="1.0.1",
        )
        self.assertEqual(resolved["topology_id"], "topo-version-101")
        self.assertEqual(resolved["binding_source"], "version")

    def test_delete_scope_restores_inheritance(self):
        upsert_topology_binding(
            {
                "project_id": _TEST_PROJECT,
                "env_key": "development",
                "channel_id": "wechat",
                "platform": "android",
                "topology_id": "topo-scope-bound",
            },
            actor="test",
        )
        upsert_topology_binding(
            {
                "project_id": _TEST_PROJECT,
                "topology_id": "topo-project-default",
            },
            actor="test",
        )
        deleted = delete_topology_binding_for_scope(
            _TEST_PROJECT,
            env_key="development",
            channel_id="wechat",
            platform="android",
        )
        self.assertTrue(deleted)
        resolved = resolve_topology_binding(
            _TEST_PROJECT,
            "development",
            "wechat",
            platform="android",
        )
        self.assertEqual(resolved["topology_id"], "topo-project-default")
        self.assertEqual(resolved["binding_source"], "project_default")

    def test_picker_marks_current_hit(self):
        upsert_topology_binding(
            {
                "project_id": _TEST_PROJECT,
                "env_key": "development",
                "channel_id": "wechat",
                "platform": "android",
                "topology_id": "topo-hit-me",
            },
            actor="test",
        )
        data = build_topology_binding_picker(
            _TEST_PROJECT,
            "development",
            "wechat",
            platform="android",
        )
        self.assertEqual(data["resolved"]["topology_id"], "topo-hit-me")
        matching = [row for row in data["topologies"] if row.get("topology_id") == "topo-hit-me"]
        if matching:
            self.assertTrue(matching[0].get("flags", {}).get("is_current_hit"))


if __name__ == "__main__":
    unittest.main()
