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

    def test_pvp_matchmake_and_frame_fanout(self):
        from models.db import get_cursor, init_db
        from services.baas import room_service

        init_db()
        with get_cursor() as cur:
            cur.execute(
                "UPDATE baas_services SET feature_flags=? WHERE service_id=?",
                ('{"login":true,"cloudsave":true,"mail":true,"announce":true,"pvp":true}', self.service_id),
            )

        room_service._rooms.clear()
        room_service._replays.clear()
        base = f"/api/baas/v1/{self.service_id}"

        def guest(name: str):
            resp = self.client.post(
                f"{base}/auth/guest",
                headers=self._headers(),
                data=json.dumps({"display_name": name}),
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()["data"]
            headers = dict(self._headers())
            headers["Authorization"] = f"Bearer {data['token']}"
            headers["X-Baas-Player-Id"] = data["player_id"]
            return data, headers

        p1, h1 = guest("FanA")
        p2, h2 = guest("FanB")

        m1 = self.client.post(f"{base}/pvp/matchmake", headers=h1, data=json.dumps({"battle_mode": "pvp_1v1"}))
        self.assertEqual(m1.status_code, 200)
        room1 = m1.get_json()["data"]
        room_id = room1["room_id"]

        m2 = self.client.post(f"{base}/pvp/matchmake", headers=h2, data=json.dumps({"battle_mode": "pvp_1v1"}))
        self.assertEqual(m2.status_code, 200)
        room2 = m2.get_json()["data"]
        self.assertEqual(room2["room_id"], room_id)
        self.assertEqual(room2["status"], "ready")

        start = self.client.post(f"{base}/rooms/{room_id}/start-battle", headers=h1, data=json.dumps({}))
        self.assertEqual(start.status_code, 200)
        self.assertEqual(start.get_json()["data"]["status"], "active")

        push = self.client.post(
            f"{base}/rooms/{room_id}/frames",
            headers=h1,
            data=json.dumps({"frame": {"action": "move", "x": 3}}),
        )
        self.assertEqual(push.status_code, 200)

        poll = self.client.get(
            f"{base}/rooms/{room_id}/frames?since_seq=0&wait_ms=2000",
            headers={**self._headers(), "X-Baas-Player-Id": p2["player_id"]},
        )
        self.assertEqual(poll.status_code, 200)
        polled = poll.get_json()["data"]
        frames = polled.get("frames") or []
        self.assertTrue(frames)
        self.assertEqual(frames[0].get("player_id"), p1["player_id"])

        finish = self.client.post(
            f"{base}/rooms/{room_id}/finish-battle",
            headers=h1,
            data=json.dumps({"result": {"winner": p1["player_id"]}}),
        )
        self.assertEqual(finish.status_code, 200)
        self.assertEqual(finish.get_json()["data"]["status"], "finished")


if __name__ == "__main__":
    unittest.main()
