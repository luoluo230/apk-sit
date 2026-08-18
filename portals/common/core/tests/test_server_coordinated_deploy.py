# -*- coding: utf-8 -*-
"""Tests for deploy_server_with_client orchestration."""

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
from services.release.server_coordinated_deploy import maybe_deploy_server_with_client


class CoordinatedDeployTests(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_skips_when_not_requested(self):
        out = maybe_deploy_server_with_client(
            "GomeKu",
            "ro-test",
            {"env_key": "development"},
            {},
            topology_id="topo-1",
            actor="tester",
        )
        self.assertTrue(out.get("skipped"))

    def test_deploys_linked_server_release(self):
        art = sas.register_artifact(
            "GomeKu",
            {"artifact_id": "sart-coord-1", "version_label": "1.0.0", "checksum": "abc"},
        )
        rel = srs.create_server_release(
            "GomeKu",
            {
                "artifact_id": art["artifact_id"],
                "topology_id": "topo-dev",
                "env_key": "development",
                "target_services": ["game-cn-1"],
            },
            "tester",
        )
        plan = {
            "deploy_server_with_client": True,
            "server_release_id": rel["server_release_id"],
        }
        with mock.patch("services.ops.server_deploy_dispatch.enqueue_deploy_server_artifact") as enqueue:
            enqueue.return_value = [{"job_id": "job-1", "status": "PENDING"}]
            out = maybe_deploy_server_with_client(
                "GomeKu",
                "ro-coord-1",
                {"env_key": "development"},
                plan,
                topology_id="topo-dev",
                actor="tester",
            )
        self.assertFalse(out.get("skipped"))
        self.assertEqual(out.get("server_release_id"), rel["server_release_id"])
        self.assertEqual(out.get("deploy_status"), "deploying")


if __name__ == "__main__":
    unittest.main()
