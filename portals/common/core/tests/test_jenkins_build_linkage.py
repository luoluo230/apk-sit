# -*- coding: utf-8 -*-
"""Jenkins client↔server BUILD_NUMBER linkage tests."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")

from models.db import init_db
from services.release import server_artifact_service as sas
from services.release.jenkins_build_linkage_service import (
    find_server_artifact_for_client_build,
    link_server_artifact_to_client_build,
    resolve_server_artifact_for_order,
)


class JenkinsBuildLinkageTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.project_id = "GomeKu"
        self.art = sas.register_artifact(
            self.project_id,
            {"artifact_id": "sart-link-1", "version_label": "1.0.0-link", "checksum": "abc"},
        )

    def test_link_and_find_by_client_build(self):
        link_server_artifact_to_client_build(
            self.project_id,
            self.art["artifact_id"],
            client_instance_id="8082",
            client_build_number="117",
            release_order_id="ro-link-117",
        )
        found = find_server_artifact_for_client_build(self.project_id, "8082", "117")
        self.assertIsNotNone(found)
        self.assertEqual(found.get("artifact_id"), self.art["artifact_id"])

    def test_resolve_server_artifact_from_order_build_job(self):
        link_server_artifact_to_client_build(
            self.project_id,
            self.art["artifact_id"],
            client_instance_id="8082",
            client_build_number="118",
        )
        order = {
            "payload": {
                "jenkins_instance_id": "8082",
                "build_job_id": "118",
                "deploy_server_with_client": True,
            }
        }
        aid = resolve_server_artifact_for_order(self.project_id, order)
        self.assertEqual(aid, self.art["artifact_id"])


if __name__ == "__main__":
    unittest.main()
