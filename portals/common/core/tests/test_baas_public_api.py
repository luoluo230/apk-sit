# -*- coding: utf-8 -*-
"""BaaS public API integration tests."""

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


_TEST_PROJECT = "test_baas_public_proj"
_GAME_ID = "baas-public-game"
_GAME_KEY = "baas-public-key-secret"


class BaasPublicApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from models.data import projects_db
        from repositories.admin import projects_repo
        from services.baas.service_crud import ensure_service

        projects_db[_TEST_PROJECT] = {
            "name": "BaaS Public Test",
            "game_id": _GAME_ID,
            "game_key": _GAME_KEY,
            "server_mode": "casual_baas",
            "status": "active",
            "created_by": "admin",
        }
        projects_repo.upsert_project(_TEST_PROJECT, projects_db[_TEST_PROJECT])
        svc, cls.api_secret = ensure_service(_TEST_PROJECT, "development", actor="admin")
        cls.service_id = svc["service_id"]
        if not cls.api_secret:
            from services.baas.service_crud import rotate_api_secret

            cls.api_secret, _ = rotate_api_secret(_TEST_PROJECT, cls.service_id)

    def setUp(self):
        self.client = app.test_client()
        app.config["WTF_CSRF_ENABLED"] = False

    def _headers(self):
        return {
            "X-Baas-Api-Key": self.api_secret,
            "Content-Type": "application/json",
        }

    def test_baas_bootstrap(self):
        resp = self.client.get(
            "/api/public/baas-bootstrap",
            query_string={
                "game_id": _GAME_ID,
                "game_key": _GAME_KEY,
                "env": "development",
                "service_id": self.service_id,
            },
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("service_id"), self.service_id)
        self.assertIn("endpoints", payload)

    def test_guest_login_announce_mail_cloudsave_flow(self):
        base = f"/api/baas/v1/{self.service_id}"
        login_resp = self.client.post(
            f"{base}/auth/guest",
            headers=self._headers(),
            data=json.dumps({"display_name": "P1"}),
        )
        self.assertEqual(login_resp.status_code, 200)
        login = login_resp.get_json()["data"]
        player_headers = dict(self._headers())
        player_headers["Authorization"] = f"Bearer {login['token']}"
        player_headers["X-Baas-Player-Id"] = login["player_id"]

        ann = self.client.get(f"{base}/announcements/active", headers=self._headers())
        self.assertEqual(ann.status_code, 200)
        self.assertTrue(ann.get_json().get("ok"))

        mail = self.client.get(f"{base}/mail/inbox", headers=player_headers)
        self.assertEqual(mail.status_code, 200)
        self.assertTrue(mail.get_json().get("ok"))

        save = self.client.put(
            f"{base}/cloudsave/profile",
            headers=player_headers,
            data=json.dumps({"value": {"level": 1}}),
        )
        self.assertEqual(save.status_code, 200)
        self.assertTrue(save.get_json().get("ok"))

        load = self.client.get(f"{base}/cloudsave/profile", headers=player_headers)
        self.assertEqual(load.status_code, 200)
        body = load.get_json()["data"]
        self.assertEqual((body.get("value") or {}).get("level"), 1)


if __name__ == "__main__":
    unittest.main()
