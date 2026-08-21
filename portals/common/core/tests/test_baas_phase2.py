# -*- coding: utf-8 -*-
"""Phase 2 reinforcement: IAP verify, inventory, guild war."""

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

from app_new import app  # noqa: F401

from models.db import get_cursor
from services.baas import auth_service, guild_war_service, iap_service, inventory_service, social_services
from services.baas.registry import default_feature_configs
from services.baas.service_crud import ensure_service, update_service

_TEST_PROJECT = "test_baas_phase2_proj"
_GAME_ID = "baas-phase2-game"
_GAME_KEY = "baas-phase2-key-secret"


class BaasPhase2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from models.data import projects_db
        from repositories.admin import projects_repo

        projects_db[_TEST_PROJECT] = {
            "name": "BaaS Phase2 Test",
            "game_id": _GAME_ID,
            "game_key": _GAME_KEY,
            "server_mode": "casual_baas",
            "status": "active",
            "created_by": "admin",
        }
        projects_repo.upsert_project(_TEST_PROJECT, projects_db[_TEST_PROJECT])
        svc, _ = ensure_service(_TEST_PROJECT, "development", actor="admin")
        cls.service_id = svc["service_id"]
        flags = {k: True for k in ("login", "iap", "inventory", "guild", "leaderboard", "hero")}
        update_service(
            _TEST_PROJECT,
            cls.service_id,
            {"feature_flags": flags, "feature_configs": default_feature_configs()},
            actor="admin",
        )
        login = auth_service.guest_login(cls.service_id, display_name="phase2_tester")
        cls.player_id = login["player_id"]

    def test_inventory_grant_and_list(self):
        with get_cursor() as cur:
            granted = inventory_service.grant_item(cur, self.service_id, self.player_id, "sword_001", quantity=1)
        self.assertEqual(granted["item_def_id"], "sword_001")
        bag = inventory_service.list_inventory(self.service_id, self.player_id, item_type="equipment")
        self.assertGreaterEqual(bag["count"], 1)

    def test_iap_dev_verify_still_works(self):
        order = iap_service.create_order(self.service_id, self.player_id, "com.game.diamond60", platform="dev")
        receipt = f"dev-{order['order_id']}"
        out = iap_service.verify_and_deliver(self.service_id, self.player_id, order["order_id"], receipt=receipt)
        self.assertEqual(out.get("status"), "delivered")

    def test_guild_war_register_and_submit(self):
        guild = social_services.create_guild(self.service_id, self.player_id, "Phase2Guild")
        reg = guild_war_service.register_guild(self.service_id, self.player_id, guild["guild_id"])
        self.assertEqual(reg["status"], "registered")
        result = guild_war_service.submit_battle_result(
            self.service_id, self.player_id, guild["guild_id"], win=True, score_delta=30,
        )
        self.assertGreater(result.get("total_score", 0), 0)
        season = guild_war_service.get_active_season(self.service_id)
        self.assertTrue(season.get("standings"))


if __name__ == "__main__":
    unittest.main()
