# -*- coding: utf-8 -*-
"""Server framework module split tests."""

from __future__ import annotations

import json
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

from app_new import app  # noqa: F401


class ServerFrameworkModuleTests(unittest.TestCase):
    TOPO_PROJECT = "test_fw_topology"
    BAAS_PROJECT = "test_fw_baas"
    GAME_TOPO = "fw-topo-game"
    GAME_BAAS = "fw-baas-game"

    @classmethod
    def setUpClass(cls):
        from repositories.admin import projects_repo
        from services.baas.service_crud import ensure_service

        projects_repo.upsert_project(cls.TOPO_PROJECT, {
            "name": "FW Topology",
            "game_id": cls.GAME_TOPO,
            "game_key": "fw-topo-key",
            "server_mode": "topology",
            "status": "active",
        })
        projects_repo.upsert_project(cls.BAAS_PROJECT, {
            "name": "FW BaaS",
            "game_id": cls.GAME_BAAS,
            "game_key": "fw-baas-key",
            "server_mode": "casual_baas",
            "status": "active",
        })
        svc, secret = ensure_service(cls.BAAS_PROJECT, "development", actor="admin")
        cls.baas_service_id = svc["service_id"]
        cls.baas_api_secret = secret or ""

    def setUp(self):
        self.client = app.test_client()
        app.config["WTF_CSRF_ENABLED"] = False

    def test_client_network_module_topology(self):
        resp = self.client.get(
            "/api/public/client-network-module",
            query_string={"game_id": self.GAME_TOPO, "game_key": "fw-topo-key"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["client_module"]["key"], "topology_client")
        self.assertEqual(body["server_module"]["key"], "topology_server")

    def test_client_network_module_baas(self):
        resp = self.client.get(
            "/api/public/client-network-module",
            query_string={"game_id": self.GAME_BAAS, "game_key": "fw-baas-key"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["client_module"]["key"], "baas_client")
        self.assertEqual(body["package_path"], "packages/client_network/baas")

    def test_client_bootstrap_routes_baas(self):
        if not self.baas_api_secret:
            self.skipTest("no api secret")
        resp = self.client.get(
            "/api/public/client-bootstrap",
            query_string={
                "game_id": self.GAME_BAAS,
                "game_key": "fw-baas-key",
                "env": "development",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body.get("framework"), "casual_baas")
        self.assertEqual(body.get("client_module"), "baas_client")
        self.assertIn("public_api_base", body)


if __name__ == "__main__":
    unittest.main()
