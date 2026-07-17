# -*- coding: utf-8 -*-
"""Release order diagnostic issue summarization."""

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

from services.release import release_order_service as ros


class ReleaseOrderDiagnosticsTests(unittest.TestCase):
    def test_summarize_collapses_duplicate_url_fields(self):
        payload = {
            "missing_client_fields": [
                "apk_url",
                "resource_url",
                "config_url",
                "apk_version",
                "resource_version",
                "config_version",
            ],
            "missing_artifact_fields": [
                "apk_url",
                "resource_url",
                "config_url",
                "catalog_url",
                "config_manifest_url",
                "code_manifest_url",
            ],
        }
        order = {
            "artifacts": [
                {"artifact_type": "apk", "status": "registered", "artifact_path": "/path/apk"},
                {"artifact_type": "resource", "status": "registered", "artifact_path": "/path/res"},
                {"artifact_type": "config", "status": "registered", "artifact_path": "/path/cfg"},
                {"artifact_type": "code", "status": "missing"},
            ],
        }
        issues = ros.summarize_order_diagnostic_issues(order, payload)
        labels = [item["label"] for item in issues]
        self.assertLessEqual(len(issues), 5, labels)
        self.assertIn("代码热更包", labels)
        self.assertIn("APK 安装包", labels)
        self.assertIn("资源包", labels)
        self.assertIn("配置包", labels)

    def test_summarize_assigns_contextual_fix_links(self):
        payload = {
            "missing_artifact_fields": ["apk_url", "catalog_url", "resource_url", "config_url"],
        }
        order = {
            "artifacts": [
                {"artifact_type": "apk", "status": "registered", "artifact_path": "/path/apk"},
                {"artifact_type": "resource", "status": "registered", "artifact_path": "/path/res"},
                {"artifact_type": "config", "status": "registered", "artifact_path": "/path/cfg"},
                {"artifact_type": "code", "status": "missing"},
            ],
        }
        pipeline_snapshot = {
            "readiness": {"ready": True},
            "effective_pipeline": {
                "hot_release": {"enabled": True},
                "apk_build": {"enabled": True},
            },
        }
        issues = ros.summarize_order_diagnostic_issues(order, payload, pipeline_snapshot=pipeline_snapshot)
        by_id = {item["id"]: item for item in issues}
        self.assertEqual(by_id["apk"]["fix"], "buildConfig")
        self.assertEqual(by_id["apk"]["fix_section"], "client_policy")
        self.assertEqual(by_id["apk"]["fix_label"], "补充下载地址")
        self.assertEqual(by_id["apk"]["highlight_fields"], ["resource_server_url"])
        self.assertEqual(by_id["code"]["fix"], "trigger_build")
        self.assertEqual(by_id["code"]["fix_label"], "触发 Jenkins 构建")

    def test_summarize_unreachable_when_bootstrap_configured(self):
        payload = {
            "missing_artifact_fields": ["apk_url", "catalog_url", "resource_url", "config_url"],
            "artifact_targets": {
                "apk_url": "https://cdn.example.com/a.apk",
                "catalog_url": "https://cdn.example.com/catalog.bin",
                "resource_url": "https://cdn.example.com/res",
                "config_url": "https://cdn.example.com/cfg",
                "config_manifest_url": "https://cdn.example.com/cfg/manifest.json",
            },
            "artifact_checks": {
                "apk_url": {"ok": False, "status": 404},
                "catalog_url": {"ok": False, "status": 404},
                "resource_url": {"ok": False, "status": 404},
                "config_url": {"ok": False, "status": 404},
                "config_manifest_url": {"ok": False, "status": 404},
            },
        }
        order = {
            "project_id": "GomeKu",
            "version_id": "069d97a9",
            "version_code": "1",
            "artifacts": [
                {"artifact_type": "apk", "status": "registered", "artifact_path": "/path/apk"},
                {"artifact_type": "resource", "status": "registered", "artifact_path": "/path/res"},
                {"artifact_type": "config", "status": "registered", "artifact_path": "/path/cfg"},
                {"artifact_type": "code", "status": "missing"},
            ],
        }
        pipeline_snapshot = {"readiness": {"ready": True}, "effective_pipeline": {"hot_release": {"enabled": True}}}
        issues = ros.summarize_order_diagnostic_issues(order, payload, pipeline_snapshot=pipeline_snapshot)
        by_id = {item["id"]: item for item in issues}
        self.assertEqual(by_id["apk"]["fix"], "buildHistory")
        self.assertEqual(by_id["apk"]["fix_label"], "查看构建历史")
        self.assertIn("OSS", by_id["apk"]["hint"])
        self.assertEqual(by_id["code"]["fix"], "trigger_build")

    def test_summarize_includes_runtime_error(self):
        payload = {"runtime_error": "目标拓扑没有运行中的 runtime", "missing_client_fields": []}
        issues = ros.summarize_order_diagnostic_issues({}, payload)
        self.assertTrue(any(item["id"] == "runtime" for item in issues))


if __name__ == "__main__":
    unittest.main()
