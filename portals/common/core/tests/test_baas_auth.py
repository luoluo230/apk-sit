# -*- coding: utf-8 -*-
"""BaaS auth service tests."""

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

from services.baas import auth_service
from services.baas.service_crud import ensure_service, get_service


_TEST_PROJECT = "test_baas_auth_proj"


class BaasAuthServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from models.data import projects_db
        from repositories.admin import projects_repo

        projects_db[_TEST_PROJECT] = {
            "name": "BaaS Auth Test",
            "game_id": "baas-auth-game",
            "game_key": "baas-auth-key",
            "server_mode": "casual_baas",
            "status": "active",
            "created_by": "admin",
        }
        projects_repo.upsert_project(_TEST_PROJECT, projects_db[_TEST_PROJECT])

    def test_guest_login_and_resolve_player(self):
        svc, secret = ensure_service(_TEST_PROJECT, "development", actor="admin")
        self.assertTrue(secret or svc.get("service_id"))
        service_id = svc["service_id"]
        session = auth_service.guest_login(service_id, display_name="Tester")
        self.assertTrue(session.get("player_id"))
        self.assertTrue(session.get("token"))
        player = auth_service.resolve_player(service_id, session["player_id"], session["token"])
        self.assertEqual(player["player_id"], session["player_id"])

    def test_invalid_token_rejected(self):
        svc, _ = ensure_service(_TEST_PROJECT, "testing", actor="admin")
        with self.assertRaises(ValueError):
            auth_service.resolve_player(svc["service_id"], "missing", "bad-token")


if __name__ == "__main__":
    unittest.main()
