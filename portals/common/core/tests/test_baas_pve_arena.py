# -*- coding: utf-8 -*-
"""PVE + async arena integration tests."""

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

_TEST_PROJECT = "test_baas_pve_arena_proj"
_GAME_ID = "baas-pve-arena-game"
_GAME_KEY = "baas-pve-arena-key-secret"


class BaasPveArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from models.data import projects_db
        from repositories.admin import projects_repo
        from services.baas.service_crud import ensure_service, update_service

        projects_db[_TEST_PROJECT] = {
            "name": "BaaS PVE Arena Test",
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
        update_service(
            _TEST_PROJECT,
            cls.service_id,
            {
                "feature_flags": {
                    "login": True,
                    "pve": True,
                    "arena": True,
                    "leaderboard": True,
                    "economy": True,
                }
            },
            actor="admin",
        )

    def setUp(self):
        self.client = app.test_client()
        app.config["WTF_CSRF_ENABLED"] = False

    def _login(self):
        base = f"/api/baas/v1/{self.service_id}"
        headers = {"X-Baas-Api-Key": self.api_secret, "Content-Type": "application/json"}
        resp = self.client.post(f"{base}/auth/guest", headers=headers, data=json.dumps({"display_name": "Hero"}))
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        player_headers = dict(headers)
        player_headers["Authorization"] = f"Bearer {data['token']}"
        player_headers["X-Baas-Player-Id"] = data["player_id"]
        return base, player_headers, data["player_id"]

    def test_pve_start_settle_flow(self):
        base, headers, _pid = self._login()
        prog = self.client.get(f"{base}/pve/progress", headers=headers)
        self.assertEqual(prog.status_code, 200)
        self.assertTrue(prog.get_json().get("ok"))
        start = self.client.post(
            f"{base}/pve/battle/start",
            headers=headers,
            data=json.dumps({"stage_id": "1-1", "team": {"heroes": [1, 2, 3]}}),
        )
        self.assertEqual(start.status_code, 200)
        start_body = start.get_json()
        self.assertTrue(start_body.get("ok"))
        battle_id = start_body["data"]["battle_id"]
        seed = start_body["data"]["seed"]
        import hashlib

        checksum = hashlib.sha256(f"{seed}:1-1:1:3".encode()).hexdigest()[:16]
        settle = self.client.post(
            f"{base}/pve/battle/settle",
            headers=headers,
            data=json.dumps({"battle_id": battle_id, "win": True, "stars": 3, "duration_ms": 12000, "checksum": checksum}),
        )
        self.assertEqual(settle.status_code, 200)
        settle_body = settle.get_json()
        self.assertTrue(settle_body.get("ok"))
        self.assertTrue(settle_body["data"].get("win"))
        progress = settle_body["data"].get("progress") or {}
        self.assertGreaterEqual(progress.get("total_cleared", 0), 1)

    def test_arena_offline_battle_flow(self):
        base, headers, pid = self._login()
        base2, headers2, pid2 = self._login()
        self.assertNotEqual(pid, pid2)
        for h, p, defense in ((headers, pid, {"heroes": [11, 12]}), (headers2, pid2, {"heroes": [21, 22]})):
            resp = self.client.post(
                f"{base}/arena/defense",
                headers=h,
                data=json.dumps({"defense": defense, "power": 500}),
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json().get("ok"))
        opponents = self.client.get(f"{base}/arena/opponents?count=3", headers=headers)
        self.assertEqual(opponents.status_code, 200)
        opp_list = opponents.get_json().get("data") or []
        defender_id = pid2
        if opp_list:
            defender_id = opp_list[0]["player_id"]
        start = self.client.post(
            f"{base}/arena/battle/start",
            headers=headers,
            data=json.dumps({"defender_id": defender_id, "team": {"heroes": [1, 2]}}),
        )
        self.assertEqual(start.status_code, 200)
        start_data = start.get_json()["data"]
        battle_id = start_data["battle_id"]
        seed = start_data["seed"]
        import hashlib

        checksum = hashlib.sha256(f"{seed}:{defender_id}:1".encode()).hexdigest()[:16]
        settle = self.client.post(
            f"{base}/arena/battle/settle",
            headers=headers,
            data=json.dumps({"battle_id": battle_id, "win": True, "duration_ms": 8000, "checksum": checksum}),
        )
        self.assertEqual(settle.status_code, 200)
        result = settle.get_json()["data"]
        self.assertTrue(result.get("win"))
        self.assertIn("rating", result)
        self.assertIn("arena_state", result)


if __name__ == "__main__":
    unittest.main()
