# -*- coding: utf-8 -*-
"""Release policy and pipeline readiness."""

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

from services.release import release_policy_service as rps


class ReleasePolicyServiceTests(unittest.TestCase):
    def test_minimal_required_fields_for_development(self):
        fields = rps.get_required_plan_fields("any_project", "development")
        self.assertEqual(fields, ["reason", "owner"])

    def test_development_runtime_required_defaults_auto(self):
        policy = rps.normalize_release_policy({}, "development")
        self.assertEqual(policy.get("runtime_required"), rps.RUNTIME_REQUIRED_AUTO)
        self.assertTrue(policy.get("auto_ensure_runtime"))

    def test_production_runtime_required_defaults_block(self):
        policy = rps.normalize_release_policy({}, "production")
        self.assertEqual(policy.get("runtime_required"), rps.RUNTIME_REQUIRED_BLOCK)

    def test_full_required_fields_for_production(self):
        fields = rps.get_required_plan_fields("any_project", "production")
        self.assertIn("validation_plan", fields)
        self.assertIn("rollback_plan", fields)

    def test_assess_pipeline_readiness_missing(self):
        state = rps.assess_pipeline_readiness({}, {})
        self.assertFalse(state["ready"])
        self.assertFalse(state["checks"]["jenkins_instance"])

    def test_assess_pipeline_readiness_ok(self):
        version = {
            "jenkins_instance_id": "inst1",
            "jenkins_job_id": "Android",
            "pipeline": {
                "config_export": {"enabled": True},
                "apk_build": {"enabled": False},
            },
        }
        state = rps.assess_pipeline_readiness(version, {})
        self.assertTrue(state["ready"])

    def test_resolve_jenkins_job_channel_override(self):
        version = {"jenkins_job_id": "Android", "channel": "1002"}
        meta = {
            "jenkins_job_id": "Android",
            "jenkins_job_overrides": {"1002": "Android_Douyin"},
        }
        self.assertEqual(rps.resolve_jenkins_job(version, meta, "1002"), "Android_Douyin")

    def test_apply_release_defaults(self):
        from repositories.admin import projects_repo

        pid = "test_release_defaults_proj"
        projects_repo.upsert_project(
            pid,
            {
                "id": pid,
                "name": pid,
                "release_defaults": {
                    "validation_plan": "自定义验证",
                    "rollback_plan": "自定义回滚",
                },
            },
        )
        out = rps.apply_release_defaults_to_payload(pid, "development", {"reason": "test"})
        self.assertEqual(out.get("validation_plan"), "自定义验证")
        self.assertEqual(out.get("rollback_plan"), "自定义回滚")


if __name__ == "__main__":
    unittest.main()
