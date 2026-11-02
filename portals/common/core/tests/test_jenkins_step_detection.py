# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from services.release.jenkins_step_detection import parse_detection_steps


class JenkinsStepDetectionTests(unittest.TestCase):
    def test_selected_steps_follow_params(self):
        steps = parse_detection_steps(
            "",
            parameters={
                "CONFIG_EXPORT_ENABLED": "false",
                "RESOURCE_BUILD_ENABLED": "true",
                "HOT_RELEASE_ENABLED": "false",
                "APK_BUILD_ENABLED": "true",
            },
            building=True,
        )
        ids = [s["id"] for s in steps]
        self.assertEqual(ids, ["env_prep", "resource_build", "apk_build"])
        self.assertEqual(steps[0]["status"], "running")

    def test_progress_marks_completed_and_running(self):
        log = """
[阶段 0] 环境准备
======= 可插拔版本构建流水线 =======
[阶段 1] 配置导出发布
=== Step 1: 配置导出发布 (ConfigRemotePublish) ===
Step 1 完成
[阶段 2] 资源打包
=== Step 2: 资源打包 ===
"""
        steps = parse_detection_steps(
            log,
            parameters={
                "CONFIG_EXPORT_ENABLED": "true",
                "RESOURCE_BUILD_ENABLED": "true",
                "HOT_RELEASE_ENABLED": "true",
                "APK_BUILD_ENABLED": "false",
            },
            building=True,
        )
        by_id = {s["id"]: s for s in steps}
        self.assertEqual(by_id["env_prep"]["status"], "success")
        self.assertEqual(by_id["config_export"]["status"], "success")
        self.assertEqual(by_id["resource_build"]["status"], "running")
        self.assertEqual(by_id["hot_release"]["status"], "pending")
        self.assertNotIn("apk_build", by_id)

    def test_aborted_marks_stopped(self):
        log = """
[阶段 0] 环境准备
======= 可插拔版本构建流水线 =======
[阶段 1] 配置导出发布
=== Step 1: 配置导出发布 ===
"""
        steps = parse_detection_steps(
            log,
            parameters={"CONFIG_EXPORT_ENABLED": "true", "RESOURCE_BUILD_ENABLED": "true"},
            building=False,
            result="ABORTED",
            stopped=True,
        )
        by_id = {s["id"]: s for s in steps}
        self.assertEqual(by_id["env_prep"]["status"], "success")
        self.assertEqual(by_id["config_export"]["status"], "stopped")
        self.assertEqual(by_id["resource_build"]["status"], "pending")

    def test_failure_marks_red(self):
        log = """
[阶段 1] 配置导出发布
=== Step 1: 配置导出发布 ===
FAIL: Step1 ConfigRemotePublish 退出
"""
        steps = parse_detection_steps(
            log,
            parameters={"CONFIG_EXPORT_ENABLED": "true"},
            building=False,
            result="FAILURE",
        )
        by_id = {s["id"]: s for s in steps}
        self.assertEqual(by_id["config_export"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
