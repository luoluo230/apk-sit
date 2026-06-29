# -*- coding: utf-8 -*-
"""Delivery scope helpers and overview channel aggregation."""

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

from app_new import app  # noqa: F401 — bootstrap imports

from data.delivery_scope import (
    get_channels_for_env,
    get_env_delivery_scope,
    get_platforms_for_env,
)
from services.release.release_order_service import project_overview


_TEST_PROJECT = "test_delivery_scope_proj"

_MOCK_CHANNELS = [
    {"id": "wechat", "name": "微信", "order": 10},
    {"id": "douyin", "name": "抖音", "order": 20},
]

_MOCK_PLATFORMS = [
    {"id": "android", "name": "Android", "order": 10},
    {"id": "ios", "name": "iOS", "order": 20},
    {"id": "windows", "name": "Windows", "order": 30},
]

_MOCK_PROJECT = {
    "channels": ["wechat", "douyin"],
    "disabled_channels": [],
    "platforms": ["android", "ios", "windows"],
    "disabled_platforms": [],
    "release_environments": [
        {
            "env_key": "development",
            "label": "开发环境",
            "builtin": True,
            "enabled": True,
            "order": 10,
            "channels": ["wechat"],
            "platforms": ["android"],
            "disabled_channels": [],
            "disabled_platforms": [],
        },
        {
            "env_key": "production",
            "label": "生产环境",
            "builtin": True,
            "enabled": True,
            "order": 40,
            "channels": ["wechat", "douyin"],
            "platforms": ["android", "ios"],
            "disabled_channels": [],
            "disabled_platforms": [],
        },
    ],
}


def _mock_projects_db():
    return {_TEST_PROJECT: dict(_MOCK_PROJECT)}


class DeliveryScopeTests(unittest.TestCase):
    @patch("models.data.projects_db", _mock_projects_db())
    @patch("data.projects.projects_db", _mock_projects_db())
    @patch("data.channels.channels_db", _MOCK_CHANNELS)
    def test_get_env_delivery_scope_no_name_error(self):
        scope = get_env_delivery_scope(_TEST_PROJECT, "development")
        self.assertEqual(scope["env_key"], "development")
        self.assertFalse(scope["inherits_project_channels"])
        self.assertFalse(scope["inherits_project_platforms"])
        assigned_platforms = scope["assigned_platforms"]
        self.assertEqual(len(assigned_platforms), 1)
        self.assertEqual(assigned_platforms[0]["platform_id"], "android")
        self.assertTrue(assigned_platforms[0]["enabled"])

    @patch("models.data.projects_db", _mock_projects_db())
    @patch("data.projects.projects_db", _mock_projects_db())
    @patch("data.channels.channels_db", _MOCK_CHANNELS)
    def test_env_channel_platform_subset(self):
        channels = get_channels_for_env(_TEST_PROJECT, "development")
        platforms = get_platforms_for_env(_TEST_PROJECT, "development")
        self.assertEqual([c["id"] for c in channels], ["wechat"])
        self.assertEqual([p["id"] for p in platforms], ["android"])

        prod_channels = get_channels_for_env(_TEST_PROJECT, "production")
        prod_platforms = get_platforms_for_env(_TEST_PROJECT, "production")
        self.assertEqual([c["id"] for c in prod_channels], ["wechat", "douyin"])
        self.assertEqual([p["id"] for p in prod_platforms], ["android", "ios"])

    @patch("services.release.release_order_service.list_project_env_keys", return_value=["development", "production"])
    @patch("services.release.release_order_service.list_release_orders", return_value=[])
    @patch("services.release.release_order_service._delivery_lines_for_env")
    @patch("models.data.projects_db", _mock_projects_db())
    @patch("data.projects.projects_db", _mock_projects_db())
    @patch("data.channels.channels_db", _MOCK_CHANNELS)
    def test_project_overview_channel_filter_counts(self, mock_lines, *_patches):
        def _lines(project_id, env_key):
            if env_key == "development":
                return [
                    {"channel_id": "wechat", "platform": "android", "platform_label": "Android", "configured": False},
                ]
            return [
                {"channel_id": "wechat", "platform": "android", "platform_label": "Android", "configured": True},
                {"channel_id": "douyin", "platform": "ios", "platform_label": "iOS", "configured": False},
            ]

        mock_lines.side_effect = _lines
        overview = project_overview(_TEST_PROJECT, {"channel_id": "wechat"})
        cards = {row["env_key"]: row for row in overview["environments"]}
        self.assertEqual(cards["development"]["delivery_line_count"], 1)
        self.assertEqual(cards["production"]["delivery_line_count"], 1)
        self.assertEqual(cards["production"]["channel_platform_labels"], ["Android"])

        douyin_overview = project_overview(_TEST_PROJECT, {"channel_id": "douyin"})
        douyin_cards = {row["env_key"]: row for row in douyin_overview["environments"]}
        self.assertNotIn("development", douyin_cards)
        self.assertEqual(douyin_cards["production"]["delivery_line_count"], 1)


class ApiAuthJsonTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_api_unauthenticated_returns_json_401(self):
        resp = self.client.get("/api/projects/demo/environments/development/delivery-scope")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json() or {}
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error"), "未登录")
        self.assertIn("application/json", resp.content_type)


if __name__ == "__main__":
    unittest.main()
