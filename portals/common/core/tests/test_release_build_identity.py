# -*- coding: utf-8 -*-
"""Build identity: job, channel id/key, platform reject, WeChat AppId, mode narrowing."""

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

from services.commercial_release_plan import apply_release_mode, narrowed_step_notes, plan_to_jenkins_params
from services.release import order_build_sync as obs
from services.release import order_crud as oc
from services.release import release_order_service as ros


def _order(platform="android"):
    return {
        "release_order_id": "ro-1",
        "project_id": "p1",
        "version_id": "v1",
        "version_code": "100",
        "version_name": "1.2.0",
        "channel_id": "1001",
        "channel_name": "微信",
        "platform": platform,
        "env_key": "development",
        "status": "draft",
        "payload": {},
    }


class ReleaseModeNarrowTests(unittest.TestCase):
    def test_default_mode_keeps_pipeline_switches(self):
        params = {
            "CONFIG_EXPORT_ENABLED": "true",
            "RESOURCE_BUILD_ENABLED": "false",
            "HOT_RELEASE_ENABLED": "true",
            "APK_BUILD_ENABLED": "true",
        }
        apply_release_mode(params, {"releaseUpload": True}, "build-upload", "code,resource")
        self.assertEqual(params["APK_BUILD_ENABLED"], "true")
        self.assertEqual(params["RESOURCE_BUILD_ENABLED"], "false")
        self.assertEqual(params["CONFIG_EXPORT_ENABLED"], "true")
        self.assertEqual(narrowed_step_notes(params, "build-upload"), [])

    def test_upload_mode_only_turns_steps_off(self):
        params = {
            "CONFIG_EXPORT_ENABLED": "false",
            "RESOURCE_BUILD_ENABLED": "true",
            "HOT_RELEASE_ENABLED": "true",
            "APK_BUILD_ENABLED": "true",
        }
        apply_release_mode(params, {"configEnabled": True}, "upload", "code,resource")
        self.assertEqual(params["CONFIG_EXPORT_ENABLED"], "false")
        self.assertEqual(params["RESOURCE_BUILD_ENABLED"], "false")
        self.assertEqual(params["APK_BUILD_ENABLED"], "false")
        self.assertIn("本次不打安装包", narrowed_step_notes(params, "upload"))


class RequestBuildIdentityTests(unittest.TestCase):
    def test_unknown_platform_is_rejected(self):
        order = _order(platform="switch")
        with mock.patch.object(oc, "get_release_order", return_value=order), \
             mock.patch.object(obs, "_find_version", return_value={"id": "v1", "platform": "switch"}):
            with self.assertRaises(ValueError) as ctx:
                ros.request_build("p1", "ro-1", "tester")
        self.assertIn("不支持的构建平台", str(ctx.exception))

    def test_wechat_without_app_id_is_rejected(self):
        order = _order(platform="wechat_minigame")
        with mock.patch.object(oc, "get_release_order", return_value=order), \
             mock.patch.object(obs, "_find_version", return_value={"id": "v1", "platform": "wechat_minigame", "version_name": "1.2.0"}), \
             mock.patch("services.build.build_node_service.assert_build_ready"), \
             mock.patch("services.admin.version_service.resolve_effective_wx_minigame", return_value={"wx_app_id": ""}):
            with self.assertRaises(ValueError) as ctx:
                ros.request_build("p1", "ro-1", "tester")
        self.assertIn("AppId", str(ctx.exception))

    def test_plan_writes_wx_app_id(self):
        version = {"id": "v1", "version_name": "1.2.0", "platform": "wechat_minigame"}
        with mock.patch(
            "services.admin.version_service.resolve_effective_wx_minigame",
            return_value={"wx_app_id": "wx123", "wx_project_name": "GomeKu"},
        ), mock.patch(
            "models.data.projects_db",
            {"p1": {"game_id": "g-p1", "game_key": "k-p1"}},
        ):
            params, _ = plan_to_jenkins_params(
                {"releasePlatform": "wechat_minigame", "apkBuildEnabled": False},
                "inline.json",
                version,
                project_id="p1",
            )
        self.assertEqual(params["WX_APP_ID"], "wx123")
        self.assertEqual(params["RELEASE_PLATFORM"], "wechat_minigame")
        self.assertEqual(params["GAME_ID"], "g-p1")
        self.assertEqual(params["GAME_KEY"], "k-p1")

    def test_plan_requires_game_credentials(self):
        with mock.patch("models.data.projects_db", {"p1": {"name": "NoCreds"}}):
            with self.assertRaises(ValueError) as ctx:
                plan_to_jenkins_params(
                    {"apkBuildEnabled": False},
                    "inline.json",
                    {"id": "v1", "version_name": "1.0.0"},
                    project_id="p1",
                )
        self.assertIn("game_id", str(ctx.exception))

    def test_plan_writes_game_credentials_from_project(self):
        with mock.patch(
            "models.data.projects_db",
            {"GomeKu": {"game_id": "gomeku-abc", "game_key": "secret-key"}},
        ):
            params, _ = plan_to_jenkins_params(
                {"apkBuildEnabled": False},
                "inline.json",
                {"id": "v1", "version_name": "1.0.0"},
                project_id="GomeKu",
            )
        self.assertEqual(params["GAME_ID"], "gomeku-abc")
        self.assertEqual(params["GAME_KEY"], "secret-key")
        self.assertEqual(params["PROJECT_ID"], "GomeKu")


if __name__ == "__main__":
    unittest.main()
