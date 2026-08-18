# -*- coding: utf-8 -*-
"""Tests for coordinated client+server rollback."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")

from models.db import init_db
from services.release import server_artifact_service as sas
from services.release import server_release_service as srs
from services.release.server_coordinated_rollback import maybe_coordinated_server_rollback


class CoordinatedRollbackTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.project_id = "GomeKu"
        self.art_v1 = sas.register_artifact(
            self.project_id,
            {"artifact_id": "sart-rb-v1", "version_label": "1.0.0", "checksum": "v1"},
        )
        self.art_v2 = sas.register_artifact(
            self.project_id,
            {"artifact_id": "sart-rb-v2", "version_label": "1.0.1", "checksum": "v2"},
        )
        self.sro_v1 = srs.create_server_release(
            self.project_id,
            {
                "artifact_id": self.art_v1["artifact_id"],
                "topology_id": "topo-dev",
                "env_key": "development",
                "target_services": ["game-cn-1"],
            },
            "tester",
        )
        self.sro_v2 = srs.create_server_release(
            self.project_id,
            {
                "artifact_id": self.art_v2["artifact_id"],
                "topology_id": "topo-dev",
                "env_key": "development",
                "target_services": ["game-cn-1"],
            },
            "tester",
        )

    def test_skips_without_server_link(self):
        target = {
            "release_order_id": "ro-target",
            "status": "verified",
            "payload": {},
        }
        out = maybe_coordinated_server_rollback(self.project_id, target, None, "tester")
        self.assertTrue(out.get("skipped"))

    def test_coordinated_rollback_restores_target_artifact(self):
        target = {
            "release_order_id": "ro-target-rb",
            "status": "verified",
            "payload": {
                "server_release_id": self.sro_v1["server_release_id"],
                "rollback_with_server": True,
            },
        }
        superseded = {
            "release_order_id": "ro-super-rb",
            "status": "published",
            "payload": {
                "deploy_server_with_client": True,
                "server_release_id": self.sro_v2["server_release_id"],
            },
        }
        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-rb-1", "status": "PENDING"}]
            out = maybe_coordinated_server_rollback(self.project_id, target, superseded, "tester")
        self.assertFalse(out.get("skipped"))
        self.assertTrue(out.get("steps"))


if __name__ == "__main__":
    unittest.main()
