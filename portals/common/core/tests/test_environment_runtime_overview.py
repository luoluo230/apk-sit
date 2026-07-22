# -*- coding: utf-8 -*-
"""P16 environment runtime overview BFF tests."""

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

from app_new import app  # noqa: F401

from services.ops.environment_runtime_service import build_environment_runtime_overview, _query_runtime_services

_TEST_PROJECT = "test_p16_runtime_proj"

_MOCK_PROJECT = {
    "name": "P16 Test",
    "channels": ["1001"],
    "platforms": ["android"],
    "release_environments": [
        {
            "env_key": "production",
            "label": "生产环境",
            "builtin": True,
            "enabled": True,
            "order": 40,
            "channels": ["1001"],
            "platforms": ["android"],
            "disabled_channels": [],
            "disabled_platforms": [],
        }
    ],
}


def _mock_projects_db():
    return {_TEST_PROJECT: dict(_MOCK_PROJECT)}


def _mock_overview_card():
    return {
        "project_id": _TEST_PROJECT,
        "environments": [
            {
                "env_key": "production",
                "env_label": "生产环境",
                "health": "healthy",
                "delivery_line_count": 2,
                "configured_line_count": 2,
                "blocker_hint": "",
                "failed_count": 0,
                "latest_orders": [{"version_code": "1.0.0"}],
            }
        ],
        "environment_options": [{"env_key": "production", "env_label": "生产环境"}],
        "channel_options": [{"channel_id": "1001", "channel_name": "微信"}],
        "platform_options": [{"value": "android", "label": "Android"}],
    }


class EnvironmentRuntimeOverviewTests(unittest.TestCase):
    def test_service_pagination_and_filter(self):
        rows = []
        for idx in range(15):
            rows.append(
                {
                    "service_id": f"s{idx}",
                    "name": f"svc-{idx}",
                    "cluster": "gateway" if idx < 8 else "user",
                    "category": "api" if idx < 8 else "core",
                    "health_pct": 100 if idx % 2 == 0 else 40,
                    "health_bucket": "healthy" if idx % 2 == 0 else "bad",
                    "run_bucket": "running" if idx % 3 else "offline",
                    "is_live": True,
                    "is_running": idx % 3 != 0,
                }
            )
        page = _query_runtime_services(rows, cluster="gateway", page=1, page_size=5)
        self.assertEqual(page["total"], 8)
        self.assertEqual(len(page["items"]), 5)
        self.assertEqual(page["items"][0]["cluster"], "gateway")

        filtered = _query_runtime_services(rows, health="bad", page=1, page_size=10)
        self.assertEqual(filtered["total"], 7)

    def test_build_without_ops_permission(self):
        with patch("services.ops.environment_runtime_service.projects_db", _mock_projects_db()), patch(
            "services.ops.environment_runtime_service.has_scope", return_value=False
        ), patch(
            "services.ops.environment_runtime_service.project_overview", return_value=_mock_overview_card()
        ):
            data = build_environment_runtime_overview(_TEST_PROJECT, "production", {})
        self.assertEqual(data["context"]["env_key"], "production")
        self.assertFalse(data["data_quality"]["can_ops"])
        self.assertEqual(data["data_quality"]["probe_source"], "no-permission")
        self.assertIn("dashboard", data)
        self.assertIn("on_call", data["sidebar"])
        self.assertGreaterEqual(len(data["sidebar"]["quick_links"]), 3)

    def test_build_with_ops_mocks(self):
        fake_agents = [{"agent_id": "ag1", "status": "ONLINE", "effective_status": "ONLINE", "metrics": {"business": {"error_rate": 0.5}}}]
        fake_services = [
            {
                "service_id": "svc-login",
                "display_name": "LoginService",
                "node_id": "n1",
                "agent_id": "ag1",
                "status": "ONLINE",
                "probe_status": "PASS",
                "probe_rtt_ms": 80,
                "run_state": "RUNNING",
                "metrics": {"cpu_percent": 35, "mem_percent": 62, "qps": 120},
                "updated_at": "2026-07-06T02:00:00Z",
            }
        ]

        with patch("services.ops.environment_runtime_service.projects_db", _mock_projects_db()), patch(
            "services.ops.environment_runtime_service.has_scope", return_value=True
        ), patch(
            "services.ops.environment_runtime_service.project_overview", return_value=_mock_overview_card()
        ), patch(
            "services.ops.helpers._logical_agents_for_project", return_value=fake_agents
        ), patch(
            "services.ops.helpers._services_for_project", return_value=fake_services
        ), patch(
            "services.ops.helpers._resolve_topology_context",
            return_value={"topology": {"id": "topo-1", "name": "Main Topology", "nodes": [{"id": "n1", "name": "gate-1"}]}},
        ), patch(
            "services.ops.helpers._runtime_active_for_scope",
            return_value={"active": True, "run_id": "run-1", "reason": "start_alive"},
        ):
            data = build_environment_runtime_overview(_TEST_PROJECT, "production", {})

        self.assertTrue(data["data_quality"]["can_ops"])
        self.assertEqual(data["data_quality"]["probe_source"], "agent-registry")
        self.assertEqual(data["kpis"]["service_health"]["value"], 100.0)
        self.assertEqual(data["kpis"]["service_health"]["link_text"], "健康概览")
        self.assertEqual(len(data["services"]), 1)
        self.assertEqual(data["services"][0]["name"], "gate-1")
        self.assertTrue(data["services"][0].get("is_live"))
        self.assertIn("services_page", data)
        self.assertEqual(data["services_page"]["live_total"], 1)
        self.assertTrue(data["runtime"]["active"])

    def test_api_route_returns_json(self):
        with patch("routes.delivery.scope_api.projects_db", _mock_projects_db()), patch(
            "routes.delivery.scope_api.build_environment_runtime_overview",
            return_value={"context": {"env_key": "production"}},
        ):
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = "admin"
            resp = client.get(f"/api/projects/{_TEST_PROJECT}/environments/production/runtime-overview")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body["data"]["context"]["env_key"], "production")

    def test_runtime_page_redirect(self):
        with patch("routes.delivery.pages.projects_db", _mock_projects_db()):
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = "admin"
            resp = client.get(
                f"/admin/projects/{_TEST_PROJECT}/overview/runtime?env_key=production&channel_id=1001",
                follow_redirects=False,
            )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/environments/production/runtime", resp.headers.get("Location", ""))
        self.assertIn("channel_id=1001", resp.headers.get("Location", ""))


if __name__ == "__main__":
    unittest.main()
