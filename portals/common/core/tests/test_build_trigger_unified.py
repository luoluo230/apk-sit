# -*- coding: utf-8 -*-
"""Verify the 3 historical build entry points converge on release_order_service.request_build."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: F401 — bootstrap imports
from services.release import release_order_service as ros


class BuildTriggerUnifiedTests(unittest.TestCase):
    """Both /admin/build/trigger and /commercial-release/trigger route through request_build."""

    def test_request_build_pulls_pipeline_from_group(self):
        """request_build must read the pipeline from version_group, not version row."""
        fake_order = {
            "release_order_id": "ro-test-1",
            "project_id": "p1",
            "version_id": "v1",
            "version_code": "100",
            "version_name": "1.0.0",
            "channel_id": "wechat",
            "channel_name": "WeChat",
            "platform": "android",
            "env_key": "development",
            "status": "draft",
            "payload": {},
        }
        fake_version = {
            "id": "v1",
            "version_name": "1.0.0",
            "version_code": "100",
            "channel": "wechat",
            "platform": "android",
            "env_key": "development",
            "pipeline": {},
        }
        effective_pipeline = {
            "apk_build": {"enabled": True, "git_branch": "main"},
            "config_export": {"enabled": True},
        }
        jenkins_binding = {"jenkins_instance_id": "inst-1", "jenkins_job_id": "Android"}

        with mock.patch.object(ros, "get_release_order", return_value=fake_order), \
             mock.patch.object(ros, "_find_version", return_value=fake_version), \
             mock.patch("services.admin.version_service.resolve_effective_pipeline", return_value=effective_pipeline) as eff_p, \
             mock.patch("services.admin.version_service.resolve_effective_jenkins", return_value=jenkins_binding) as eff_j, \
             mock.patch("services.commercial_release_plan.plan_defaults_from_pipeline", return_value={"appName": "X"}) as defaults, \
             mock.patch("services.commercial_release_plan.plan_to_jenkins_params", return_value=({"VERSION_NAME": "1.0.0"}, "/tmp")) as params, \
             mock.patch("services.jenkins_manager.prepare_instance_for_project_build", return_value=(True, None)), \
             mock.patch("services.jenkins_manager.get_jenkins_url_for_instance", return_value="http://j"), \
             mock.patch("services.jenkins_manager.get_builds_dir_for_instance", return_value="/tmp/builds"), \
             mock.patch("services.jenkins.trigger_build", return_value=(True, 42, None)), \
             mock.patch("models.data.record_build_version"), \
             mock.patch.object(ros, "get_cursor") as cursor_cm:
            cursor_cm.return_value.__enter__.return_value = mock.MagicMock()
            cursor_cm.return_value.__exit__.return_value = False
            with mock.patch.object(ros, "_event"):
                ros.request_build("p1", "ro-test-1", "tester")

        eff_p.assert_called_once_with("p1", fake_version)
        eff_j.assert_called_once()
        defaults.assert_called_once()
        passed_version = defaults.call_args.args[0]
        self.assertEqual(passed_version.get("pipeline"), effective_pipeline)
        params.assert_called_once()

    def test_request_build_fails_when_group_pipeline_missing(self):
        fake_order = {
            "release_order_id": "ro-test-2",
            "project_id": "p1",
            "version_id": "v1",
            "version_code": "100",
            "version_name": "1.0.0",
            "channel_id": "wechat",
            "channel_name": "WeChat",
            "platform": "android",
            "env_key": "development",
            "status": "draft",
            "payload": {},
        }
        fake_version = {"id": "v1", "version_name": "1.0.0", "version_code": "100"}
        with mock.patch.object(ros, "get_release_order", return_value=fake_order), \
             mock.patch.object(ros, "_find_version", return_value=fake_version), \
             mock.patch("services.admin.version_service.resolve_effective_pipeline", return_value={}):
            with self.assertRaises(ValueError) as ctx:
                ros.request_build("p1", "ro-test-2", "tester")
            self.assertIn("版本组管线模板", str(ctx.exception))

    def test_ensure_draft_release_order_returns_existing(self):
        existing = {"release_order_id": "ro-existing", "status": "draft"}
        with mock.patch.object(ros, "find_draft_release_order", return_value=existing):
            out = ros.ensure_draft_release_order("p1", "v1", "tester")
        self.assertEqual(out, existing)


if __name__ == "__main__":
    unittest.main()
