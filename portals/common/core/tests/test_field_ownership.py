# -*- coding: utf-8 -*-
"""Field ownership: VC must not write pipeline / bootstrap; version_group is the single source."""

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
from repositories.admin import projects_repo, versions_repo
from services.admin import version_service
from services.release import release_policy_service as rps


PROJECT_ID = "test_field_ownership_proj"
ACTOR = "field_ownership_tester"


def _seed_project():
    projects_repo.upsert_project(
        PROJECT_ID,
        {
            "id": PROJECT_ID,
            "name": PROJECT_ID,
            "channels": ["wechat", "douyin"],
            "platforms": ["android"],
            "viewers": [ACTOR],
            "editors": [ACTOR],
            "release_environments": [
                {"env_key": "development", "label": "开发", "enabled": True},
            ],
            "version_groups": [
                {
                    "version_name": "1.0.0",
                    "env_key": "development",
                    "platform": "android",
                    "version_mode": "general",
                    "status": "active",
                    "jenkins_instance_id": "inst-grp",
                    "jenkins_job_id": "Android",
                    "pipeline_template": {
                        "apk_build": {"enabled": True, "git_branch": "main"},
                        "config_export": {"enabled": True, "remote_prefix": "MyGame"},
                    },
                    "resource_server_url": "https://cdn.example.com",
                    "catalog_file_name": "catalog_1.0.0.bin",
                    "rollout_percentage": 100,
                }
            ],
        },
    )
    versions_repo.save_versions(
        PROJECT_ID,
        [
            {
                "id": "vc-aa",
                "version_name": "1.0.0",
                "version_code": "100",
                "channel": "wechat",
                "stage": "dev",
                "env_key": "development",
                "platform": "android",
                "version_mode": "general",
                "version_status": "active",
                "pipeline": {"apk_build": {"enabled": False}},
            }
        ],
    )


class FieldOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _seed_project()

    def test_update_vc_with_pipeline_blocked(self):
        payload = {
            "id": "vc-aa",
            "edit_scope": "version_code",
            "pipeline": {"apk_build": {"enabled": True}},
            "version_name": "1.0.0",
            "version_code": "100",
            "platform": "android",
            "stage": "dev",
        }
        with app.test_request_context():
            body, status = version_service.update_version(PROJECT_ID, ACTOR, payload)
        self.assertEqual(status, 400)
        self.assertIn("blocked_fields", body)
        self.assertIn("pipeline", body["blocked_fields"])

    def test_update_vc_with_bootstrap_blocked(self):
        payload = {
            "id": "vc-aa",
            "edit_scope": "version_code",
            "resource_server_url": "https://other.example.com",
            "version_name": "1.0.0",
            "version_code": "100",
            "platform": "android",
            "stage": "dev",
        }
        with app.test_request_context():
            body, status = version_service.update_version(PROJECT_ID, ACTOR, payload)
        self.assertEqual(status, 400)
        self.assertIn("resource_server_url", body["blocked_fields"])

    def test_resolve_effective_pipeline_uses_group_template(self):
        versions = versions_repo.list_versions(PROJECT_ID)
        vc = next(v for v in versions if v["id"] == "vc-aa")
        eff = version_service.resolve_effective_pipeline(PROJECT_ID, vc)
        self.assertTrue(eff.get("apk_build", {}).get("enabled"))
        self.assertEqual(eff.get("config_export", {}).get("remote_prefix"), "MyGame")

    def test_resolve_effective_bootstrap_prefers_group(self):
        versions = versions_repo.list_versions(PROJECT_ID)
        vc = next(v for v in versions if v["id"] == "vc-aa")
        boot = version_service.resolve_effective_bootstrap_fields(PROJECT_ID, vc)
        self.assertEqual(boot.get("resource_server_url"), "https://cdn.example.com")
        self.assertEqual(boot.get("catalog_file_name"), "catalog_1.0.0.bin")
        self.assertEqual(int(boot.get("rollout_percentage") or 0), 100)

    def test_resolve_jenkins_uses_group_meta_first(self):
        versions = versions_repo.list_versions(PROJECT_ID)
        vc = next(v for v in versions if v["id"] == "vc-aa")
        jenkins = version_service.resolve_effective_jenkins(PROJECT_ID, vc)
        self.assertEqual(jenkins.get("jenkins_instance_id"), "inst-grp")

    def test_channel_binding_overrides_default_job(self):
        meta = version_service._get_group_meta(PROJECT_ID, "1.0.0", "development", "android") or {}
        projects_repo.upsert_project(
            PROJECT_ID,
            {
                **(projects_repo.get_project(PROJECT_ID) or {}),
                "channel_bindings": [
                    {"channel_id": "wechat", "jenkins_job": "Android_Wechat"},
                ],
            },
        )
        job = rps.resolve_jenkins_job(
            {"channel": "wechat"},
            meta,
            channel_id="wechat",
            project_id=PROJECT_ID,
        )
        self.assertEqual(job, "Android_Wechat")
        meta_with_override = dict(meta)
        meta_with_override["jenkins_job_overrides"] = {"wechat": "Android_Wechat_Group"}
        job2 = rps.resolve_jenkins_job(
            {"channel": "wechat"},
            meta_with_override,
            channel_id="wechat",
            project_id=PROJECT_ID,
        )
        self.assertEqual(job2, "Android_Wechat_Group")

    def test_update_vc_status_alone_does_not_trip_block(self):
        payload = {
            "id": "vc-aa",
            "edit_scope": "version_code",
            "version_name": "1.0.0",
            "version_code": "100",
            "platform": "android",
            "stage": "dev",
            "version_status": "testing",
        }
        with app.test_request_context():
            body, status = version_service.update_version(PROJECT_ID, ACTOR, payload)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("version", {}).get("version_status"), "testing")


if __name__ == "__main__":
    unittest.main()
