# -*- coding: utf-8 -*-
"""Version pipeline config merge and roundtrip."""

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

from services.admin import version_service as vs


class VersionPipelineConfigTests(unittest.TestCase):
    def test_deep_merge_preserves_sibling_keys(self):
        base = {
            "config_export": {"enabled": True, "remote_prefix": "MyGame1"},
            "hot_release": {"enabled": True, "release_targets": "code,resource"},
        }
        patch = {
            "apk_build": {"enabled": False, "git_branch": "main"},
            "hot_release": {"release_targets": "code"},
        }
        merged = vs._merge_version_pipeline(base, patch)
        self.assertTrue(merged["config_export"]["enabled"])
        self.assertEqual(merged["config_export"]["remote_prefix"], "MyGame1")
        self.assertEqual(merged["hot_release"]["release_targets"], "code")
        self.assertFalse(merged["apk_build"]["enabled"])
        self.assertEqual(merged["apk_build"]["git_branch"], "main")

    def test_sync_pipeline_release_fields_writes_git_branch(self):
        merged = vs._merge_version_pipeline(
            {},
            {"apk_build": {"git_branch": "develop", "unity_version": "6000.3.8f1"}},
        )
        self.assertEqual(merged["git_branch"], "develop")
        self.assertEqual(merged["apk_build"]["git_branch"], "develop")

    def test_plan_defaults_keys_from_pipeline(self):
        """Mirror commercial_release_routes plan_defaults mapping."""
        pipeline = {
            "config_export": {
                "enabled": True,
                "remote_prefix": "GameRoot",
                "include_code": False,
            },
            "resource_build": {"enabled": True, "provider": "addressables-v2", "scenario": "default"},
            "hot_release": {
                "enabled": True,
                "release_targets": "code",
                "release_mode": "build-upload",
                "code_enabled": True,
                "resource_enabled": False,
            },
            "apk_build": {"enabled": False, "git_branch": "main"},
        }
        version = {"version_name": "1.0.0", "version_code": "12"}
        ce = pipeline["config_export"]
        rb = pipeline["resource_build"]
        hr = pipeline["hot_release"]
        ab = pipeline["apk_build"]
        defaults = {
            "configEnabled": ce.get("enabled"),
            "configRemotePrefix": ce.get("remote_prefix"),
            "configIncludeCode": ce.get("include_code"),
            "resourceEnabled": rb.get("enabled"),
            "resourceProvider": rb.get("provider"),
            "hotReleaseEnabled": hr.get("enabled"),
            "apkBuildEnabled": ab.get("enabled"),
            "releaseTargets": hr.get("release_targets"),
            "gitBranch": ab.get("git_branch"),
        }
        self.assertTrue(defaults["configEnabled"])
        self.assertEqual(defaults["configRemotePrefix"], "GameRoot")
        self.assertFalse(defaults["configIncludeCode"])
        self.assertTrue(defaults["resourceEnabled"])
        self.assertTrue(defaults["hotReleaseEnabled"])
        self.assertFalse(defaults["apkBuildEnabled"])
        self.assertEqual(defaults["releaseTargets"], "code")
        self.assertEqual(defaults["gitBranch"], "main")

    def test_resolve_runtime_compat_fields_bootstrap_roundtrip(self):
        data = {
            "version_name": "2.0.0",
            "force_update": True,
            "resource_server_url": "https://oss.example.com/MyGame1",
            "catalog_file_name": "catalog_2.0.0.bin",
            "min_client_version": "1.5.0",
            "rollout_percentage": 30,
            "is_revoked": False,
        }
        resolved = vs._resolve_runtime_compat_fields(data)
        self.assertTrue(resolved["force_update"])
        self.assertEqual(resolved["resource_server_url"], "https://oss.example.com/MyGame1")
        self.assertEqual(resolved["catalog_file_name"], "catalog_2.0.0.bin")
        self.assertEqual(resolved["min_client_version"], "1.5.0")
        self.assertEqual(resolved["rollout_percentage"], 30)
        self.assertFalse(resolved["is_revoked"])

    def test_apply_project_build_defaults_to_pipeline(self):
        from repositories.admin import projects_repo

        project_id = "test_pipeline_tpl"
        projects_repo.upsert_project(
            project_id,
            {
                "id": project_id,
                "name": project_id,
                "build_config": {
                    "app_name": "MyApp",
                    "unity_project_path": "/data/unity/proj",
                    "output_base_dir": "/data/out",
                    "default_git_branch": "develop",
                },
            },
        )
        merged = vs._apply_project_build_defaults_to_pipeline(project_id, {})
        apk = merged.get("apk_build") or {}
        self.assertEqual(apk.get("app_name"), "MyApp")
        self.assertEqual(apk.get("unity_project_path"), "/data/unity/proj")
        self.assertEqual(apk.get("output_base_dir"), "/data/out")
        self.assertEqual(apk.get("git_branch"), "develop")
        self.assertEqual(merged.get("git_branch"), "develop")

    def test_version_matches_group_scope(self):
        row = {
            "version_name": "2.0.0",
            "stage": "dev",
            "platform": "android",
        }
        self.assertTrue(vs._version_matches_group_scope(row, "2.0.0", "development", "android", "p1"))
        self.assertFalse(vs._version_matches_group_scope(row, "2.0.0", "production", "android", "p1"))
        self.assertFalse(vs._version_matches_group_scope(row, "2.0.0", "development", "ios", "p1"))

    def test_build_client_bootstrap_snapshot_gate_fields(self):
        from services.release.bundle_service import build_client_bootstrap_snapshot

        version_row = {
            "id": "v1",
            "version_name": "1.0.0",
            "version_code": "12",
            "platform": "android",
            "resource_server_url": "https://oss.example.com/MyGame1",
            "catalog_file_name": "catalog_1.0.0.bin",
            "min_client_version": "1.0.0",
            "rollout_percentage": 50,
            "force_update": True,
            "is_revoked": False,
            "channel": "wechat",
        }
        scope = {"env_key": "development", "channel_id": "1001", "scope_id": "g:development:1001"}
        client = build_client_bootstrap_snapshot(version_row, scope)
        required = (
            "resource_relative_path",
            "catalog_file_name",
            "min_client_version",
            "rollout_percentage",
            "force_update",
            "is_revoked",
            "catalog_url",
            "config_manifest_url",
            "code_manifest_url",
        )
        for key in required:
            self.assertIn(key, client)
        self.assertTrue(client["force_update"])
        self.assertEqual(client["rollout_percentage"], 50)
        self.assertIn("catalog_1.0.0.bin", client["catalog_url"])


    def test_resolve_effective_pipeline_falls_back_to_lazy_init(self):
        from repositories.admin import projects_repo, versions_repo

        project_id = "test_effective_pipeline_lazy"
        projects_repo.upsert_project(
            project_id,
            {
                "id": project_id,
                "name": project_id,
                "channels": ["wechat"],
                "platforms": ["android"],
                "viewers": ["tester"],
                "editors": ["tester"],
                "release_environments": [
                    {"env_key": "development", "label": "开发", "enabled": True},
                ],
                "version_groups": [],
            },
        )
        versions_repo.save_versions(
            project_id,
            [
                {
                    "id": "vc-1",
                    "version_name": "1.5.0",
                    "version_code": "150",
                    "channel": "wechat",
                    "stage": "dev",
                    "env_key": "development",
                    "platform": "android",
                    "pipeline": {"apk_build": {"enabled": True, "git_branch": "feature/x"}},
                    "updated_at": "2026-06-20T00:00:00",
                }
            ],
        )
        eff = vs.resolve_effective_pipeline(
            project_id,
            {"version_name": "1.5.0", "env_key": "development", "platform": "android"},
        )
        self.assertEqual(eff.get("apk_build", {}).get("git_branch"), "feature/x")
        self.assertTrue(eff.get("apk_build", {}).get("enabled"))


if __name__ == "__main__":
    unittest.main()
