# -*- coding: utf-8 -*-
"""PORTAL_SERVER_FRAMEWORKS 503 gating matrix for bootstrap endpoints."""

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

from app_new import app  # noqa: E402
from models.db import init_db  # noqa: E402


class ServerFrameworkGatingTests(unittest.TestCase):
    TOPO_PROJECT = "gate_topo_proj"
    BAAS_PROJECT = "gate_baas_proj"
    GAME_TOPO = "gate-topo-gid"
    GAME_BAAS = "gate-baas-gid"

    @classmethod
    def setUpClass(cls):
        from repositories.admin import projects_repo
        from services.baas.service_crud import ensure_service

        init_db()
        projects_repo.upsert_project(cls.TOPO_PROJECT, {
            "name": "Gate Topo",
            "game_id": cls.GAME_TOPO,
            "game_key": "gate-topo-key",
            "server_mode": "topology",
            "status": "active",
        })
        projects_repo.upsert_project(cls.BAAS_PROJECT, {
            "name": "Gate BaaS",
            "game_id": cls.GAME_BAAS,
            "game_key": "gate-baas-key",
            "server_mode": "casual_baas",
            "status": "active",
        })
        ensure_service(cls.BAAS_PROJECT, "development", actor="admin")

    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_topology_disabled_returns_503_on_runtime_bootstrap(self):
        with mock.patch("server_frameworks.registry.is_module_enabled") as enabled:
            enabled.side_effect = lambda key: key != "topology_server"
            resp = self.client.get(
                "/api/public/runtime-bootstrap",
                query_string={
                    "game_id": self.GAME_TOPO,
                    "game_key": "gate-topo-key",
                    "env_key": "development",
                    "channel": "wechat",
                    "platform": "android",
                },
            )
        self.assertEqual(resp.status_code, 503)
        body = resp.get_json() or {}
        self.assertFalse(body.get("ok", True))

    def test_topology_disabled_unified_client_bootstrap_503(self):
        with mock.patch("server_frameworks.bootstrap.is_module_enabled") as enabled:
            enabled.side_effect = lambda key: key != "topology_server"
            resp = self.client.get(
                "/api/public/client-bootstrap",
                query_string={
                    "game_id": self.GAME_TOPO,
                    "game_key": "gate-topo-key",
                    "env": "development",
                    "channel": "wechat",
                    "platform": "android",
                },
            )
        self.assertEqual(resp.status_code, 503)

    def test_baas_disabled_returns_503_on_baas_bootstrap(self):
        with mock.patch("server_frameworks.bootstrap.is_module_enabled") as enabled:
            enabled.side_effect = lambda key: key != "casual_baas_server"
            resp = self.client.get(
                "/api/public/baas-bootstrap",
                query_string={
                    "game_id": self.GAME_BAAS,
                    "game_key": "gate-baas-key",
                    "env": "development",
                },
            )
        self.assertEqual(resp.status_code, 503)
        body = resp.get_json() or {}
        self.assertIn("BaaS", str(body.get("error") or ""))

    def test_baas_disabled_unified_client_bootstrap_503(self):
        with mock.patch("server_frameworks.bootstrap.is_module_enabled") as enabled:
            enabled.side_effect = lambda key: key != "casual_baas_server"
            resp = self.client.get(
                "/api/public/client-bootstrap",
                query_string={
                    "game_id": self.GAME_BAAS,
                    "game_key": "gate-baas-key",
                    "env": "development",
                },
            )
        self.assertEqual(resp.status_code, 503)

    def test_baas_enabled_unified_bootstrap_ok(self):
        with mock.patch("server_frameworks.bootstrap.is_module_enabled", return_value=True):
            resp = self.client.get(
                "/api/public/client-bootstrap",
                query_string={
                    "game_id": self.GAME_BAAS,
                    "game_key": "gate-baas-key",
                    "env": "development",
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json() or {}
        self.assertTrue(body.get("ok"))

    def test_client_network_module_not_gated_by_503(self):
        with mock.patch("server_frameworks.registry.is_module_enabled") as enabled:
            enabled.side_effect = lambda key: key != "topology_server"
            resp = self.client.get(
                "/api/public/client-network-module",
                query_string={"game_id": self.GAME_TOPO, "game_key": "gate-topo-key"},
            )
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
