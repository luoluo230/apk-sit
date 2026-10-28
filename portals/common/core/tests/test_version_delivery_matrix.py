# -*- coding: utf-8 -*-
"""Delivery-line matrix: env x channel x platform inventory for the versions page."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from services.admin.version_delivery_matrix_service import (  # noqa: E402
    _cell_status,
    build_version_delivery_matrix,
)


class CellStatusTests(unittest.TestCase):
    def test_live_prefers_bundle_label(self):
        cell = _cell_status(
            bundle_id="b1",
            version_name="1.0.0",
            version_code="12",
            has_group=True,
            channel_vc_count=1,
            artifact_ready=True,
        )
        self.assertEqual(cell["status"], "live")
        self.assertEqual(cell["label"], "1.0.0 / 12")

    def test_no_vc_when_group_exists_without_channel_build(self):
        cell = _cell_status(
            bundle_id="",
            version_name="",
            version_code="",
            has_group=True,
            channel_vc_count=0,
            artifact_ready=False,
        )
        self.assertEqual(cell["status"], "no_vc")

    def test_empty_when_no_group(self):
        cell = _cell_status(
            bundle_id="",
            version_name="",
            version_code="",
            has_group=False,
            channel_vc_count=0,
            artifact_ready=False,
        )
        self.assertEqual(cell["status"], "empty")


class BuildMatrixTests(unittest.TestCase):
    @patch("services.release.channel_journey_bff._delivery_lines_for_env")
    @patch("services.admin.version_download_service.list_versions")
    @patch("services.admin.version_delivery_matrix_service.list_version_groups")
    @patch("services.admin.version_delivery_matrix_service.get_platform_defs_for_env")
    @patch("services.admin.version_delivery_matrix_service.get_channels_for_env")
    @patch(
        "services.admin.version_delivery_matrix_service.project_env_label",
        return_value="开发环境",
    )
    @patch(
        "services.admin.version_delivery_matrix_service.normalize_release_env_key",
        side_effect=lambda key, project_id=None: key or "development",
    )
    @patch(
        "services.admin.version_delivery_matrix_service._version_row_platform",
        side_effect=lambda row: str(row.get("platform") or "android"),
    )
    @patch(
        "services.admin.version_delivery_matrix_service._version_row_env_key",
        side_effect=lambda row, pid: str(row.get("env_key") or "development"),
    )
    def test_cells_cover_channel_platform_and_live_status(
        self,
        _env,
        _plat,
        _norm,
        _label,
        mock_channels,
        mock_platforms,
        mock_groups,
        mock_versions,
        mock_lines,
    ):
        mock_channels.return_value = [
            {"id": "wechat", "name": "微信"},
            {"id": "douyin", "name": "抖音"},
        ]
        mock_platforms.return_value = [
            {"value": "android", "label": "Android"},
            {"value": "ios", "label": "iOS"},
        ]
        mock_groups.return_value = (
            {"version_groups": [{"version_name": "1.0.0", "platform": "android", "pipeline_ready": True}]},
            200,
        )
        mock_versions.return_value = (
            {
                "versions": [
                    {
                        "channel_id": "wechat",
                        "platform": "android",
                        "env_key": "development",
                        "apk_status": "missing",
                    },
                    {
                        "channel_id": "douyin",
                        "platform": "android",
                        "env_key": "development",
                        "apk_status": "found",
                    },
                ]
            },
            200,
        )
        mock_lines.return_value = [
            {
                "channel_id": "wechat",
                "platform": "android",
                "bundle_id": "bundle-1",
                "version_name": "1.0.0",
                "version_code": "12",
            }
        ]

        payload = build_version_delivery_matrix("demo", "admin", "development")
        self.assertEqual(payload["env_key"], "development")
        self.assertEqual(len(payload["cells"]), 4)
        by_key = {(row["channel_id"], row["platform"]): row for row in payload["cells"]}
        self.assertEqual(by_key[("wechat", "android")]["status"], "live")
        self.assertEqual(by_key[("wechat", "android")]["label"], "1.0.0 / 12")
        self.assertIn("env_key=development", by_key[("wechat", "android")]["href"])
        self.assertIn("channel_id=wechat", by_key[("wechat", "android")]["href"])
        self.assertIn("platform=android", by_key[("wechat", "android")]["href"])
        self.assertEqual(by_key[("douyin", "android")]["status"], "built")
        self.assertEqual(by_key[("wechat", "ios")]["status"], "empty")
        self.assertEqual(by_key[("douyin", "ios")]["status"], "empty")


if __name__ == "__main__":
    unittest.main()
