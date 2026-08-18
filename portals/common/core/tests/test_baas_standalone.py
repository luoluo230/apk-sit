# -*- coding: utf-8 -*-
"""Standalone BaaS app + GM API tests."""

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
os.environ["BAAS_STANDALONE"] = "1"
os.environ["PORTAL_SERVER_FRAMEWORKS"] = "baas"

from config import load_dotenv

load_dotenv()

from server_frameworks.casual_baas.standalone_app import create_baas_app


class BaasStandaloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from repositories.admin import projects_repo
        from services.baas import auth_service
        from services.baas.service_crud import ensure_service

        cls.project_id = "test_baas_standalone"
        projects_repo.upsert_project(cls.project_id, {
            "name": "Standalone Test",
            "game_id": "baas-standalone-game",
            "game_key": "baas-standalone-key",
            "server_mode": "casual_baas",
            "status": "active",
            "created_by": "admin",
        })
        svc, cls.api_secret = ensure_service(cls.project_id, "development", actor="admin")
        cls.service_id = svc["service_id"]
        if not cls.api_secret:
            from services.baas.service_crud import rotate_api_secret
            cls.api_secret, _ = rotate_api_secret(cls.project_id, cls.service_id)
        session = auth_service.guest_login(cls.service_id, display_name="GMTest")
        cls.player_id = session["player_id"]
        cls.player_token = session["token"]

    def setUp(self):
        self.app = create_baas_app()
        self.client = self.app.test_client()
        self.app.config["WTF_CSRF_ENABLED"] = False

    def test_health_standalone(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body.get("service"), "casual_baas_standalone")

    def test_gm_wallet_and_gift_code(self):
        from flask import session as flask_session

        with self.client.session_transaction() as sess:
            sess["user"] = "admin"
        base = f"/api/projects/{self.project_id}/baas/services/{self.service_id}/gm"
        w = self.client.post(
            base + "/wallet",
            data=json.dumps({"player_id": self.player_id, "currency_id": "gold", "delta": 500, "reason": "test"}),
            content_type="application/json",
        )
        self.assertEqual(w.status_code, 200)
        g = self.client.post(
            base + "/gift-codes",
            data=json.dumps({"code": "TESTGIFT", "max_uses": 10, "rewards": [{"type": "gold", "amount": 1}]}),
            content_type="application/json",
        )
        self.assertEqual(g.status_code, 200)
        dash = self.client.get(base + "/dashboard")
        self.assertEqual(dash.status_code, 200)
        self.assertGreaterEqual(dash.get_json()["data"]["gift_code_count"], 1)


if __name__ == "__main__":
    unittest.main()
