# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from services.release.bundle_service import create_bundle_from_publish, rollback_bundle, run_scope_precheck


class BundleServiceTests(unittest.TestCase):
    def test_create_bundle_supersedes_previous_published(self):
        rows = [
            {
                "bundle_id": "rb-old",
                "scope_id": "gomeku:production:1001",
                "publish_status": "published",
                "published_at": "2026-06-10T10:00:00",
                "updated_at": "2026-06-10T10:00:00",
            }
        ]
        scope = {
            "scope_id": "gomeku:production:1001",
            "project_id": "GomeKu",
            "env_key": "production",
            "channel_id": "1001",
        }
        version_row = {
            "id": "ver-1",
            "version_name": "1.0.1",
            "version_code": "13",
            "platform": "android",
            "apk_path": "apk",
            "resource_version": "1.0.1.13",
            "config_version": "1.0.1.13",
        }

        def _mutate(mutator):
            return mutator(rows)

        with patch("services.release.bundle_service.mutate_bundles", side_effect=_mutate), \
             patch("services.release.bundle_service.resolve_network_profile", return_value=({"gateway_ws": "ws://127.0.0.1:15050/ws/"}, "auto")), \
             patch("services.release.bundle_service.resolve_topology_id", return_value="topo-prod"):
            bundle = create_bundle_from_publish(scope, version_row, published_by="tester")

        published = [row for row in rows if row.get("publish_status") == "published"]
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["bundle_id"], bundle["bundle_id"])
        self.assertEqual(bundle["supersedes_bundle_id"], "rb-old")
        old = next(row for row in rows if row["bundle_id"] == "rb-old")
        self.assertEqual(old["publish_status"], "superseded")

    def test_rollback_restores_target_and_links_previous_active_bundle(self):
        rows = [
            {
                "bundle_id": "rb-old",
                "scope_id": "gomeku:production:1001",
                "publish_status": "superseded",
                "published_at": "2026-06-09T10:00:00",
                "updated_at": "2026-06-09T10:00:00",
            },
            {
                "bundle_id": "rb-new",
                "scope_id": "gomeku:production:1001",
                "publish_status": "published",
                "published_at": "2026-06-10T10:00:00",
                "updated_at": "2026-06-10T10:00:00",
            },
        ]

        def _mutate(mutator):
            return mutator(rows)

        with patch("services.release.bundle_service.mutate_bundles", side_effect=_mutate):
            rolled = rollback_bundle("gomeku:production:1001", "rb-old", rolled_by="tester")

        self.assertEqual(rolled["bundle_id"], "rb-old")
        self.assertEqual(rolled["publish_status"], "published")
        self.assertEqual(rolled["rollback_of_bundle_id"], "rb-new")
        published = [row for row in rows if row.get("publish_status") == "published"]
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["bundle_id"], "rb-old")
        superseded = next(row for row in rows if row["bundle_id"] == "rb-new")
        self.assertEqual(superseded["publish_status"], "superseded")

    def test_precheck_can_validate_remote_artifacts(self):
        scope = {
            "scope_id": "gomeku:production:1001",
            "project_id": "GomeKu",
            "env_key": "production",
            "channel_id": "1001",
        }
        version_row = {
            "scope_id": "gomeku:production:1001",
            "env_key": "production",
            "channel": "1001",
            "version_name": "1.0.1",
            "version_code": "13",
            "platform": "android",
            "apk_url": "https://cdn.example.com/app.apk",
            "resource_url": "https://cdn.example.com/res.zip",
            "config_url": "https://cdn.example.com/cfg.zip",
            "apk_version": "1.0.1",
            "resource_version": "1.0.1",
            "config_version": "1.0.1",
        }
        with patch("services.release.bundle_service.resolve_network_profile", return_value=({
            "gateway_ws": "ws://127.0.0.1:15050/ws/",
            "login_http": "http://127.0.0.1:15501",
            "game_ws": "ws://127.0.0.1:15502/ws/",
            "ops_http": "http://127.0.0.1:5504",
        }, "auto")), \
             patch("services.release.bundle_service.resolve_topology_id", return_value="topo-prod"), \
             patch("services.release.bundle_service._check_remote_artifact", side_effect=[
                 {"ok": True, "status": 200},
                 {"ok": False, "status": 404},
                 {"ok": True, "status": 200},
             ]):
            result = run_scope_precheck(scope, version_row, validate_artifacts=True)

        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_artifact_fields"], ["resource_url"])
        self.assertIn("artifact_checks", result)


if __name__ == "__main__":
    unittest.main()
