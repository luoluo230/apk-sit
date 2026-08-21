# -*- coding: utf-8 -*-
"""AFK pack: gacha, hero, idle, tower, iap integration tests."""

from __future__ import annotations

import hashlib
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

from models.db import get_cursor
from services.baas import auth_service, gacha_service, hero_service, idle_service, iap_service, pve_service, tower_service
from services.baas.battle_antifraud import compute_replay_hash
from services.baas.registry import default_feature_configs
from services.baas.wallet_helpers import credit_wallet

_TEST_PROJECT = "test_baas_afk_pack_proj"
_GAME_ID = "baas-afk-pack-game"
_GAME_KEY = "baas-afk-pack-key-secret"


class BaasAfkPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from models.data import projects_db
        from repositories.admin import projects_repo
        from services.baas.service_crud import ensure_service, update_service

        projects_db[_TEST_PROJECT] = {
            "name": "BaaS AFK Pack Test",
            "game_id": _GAME_ID,
            "game_key": _GAME_KEY,
            "server_mode": "casual_baas",
            "status": "active",
            "created_by": "admin",
        }
        projects_repo.upsert_project(_TEST_PROJECT, projects_db[_TEST_PROJECT])
        svc, cls.api_secret = ensure_service(_TEST_PROJECT, "development", actor="admin")
        cls.service_id = svc["service_id"]
        flags = {k: True for k in ("login", "hero", "gacha", "idle", "tower", "iap", "pve", "economy")}
        update_service(
            _TEST_PROJECT,
            cls.service_id,
            {"feature_flags": flags, "feature_configs": default_feature_configs()},
            actor="admin",
        )
        login = auth_service.guest_login(cls.service_id, display_name="afk_tester")
        cls.player_id = login["player_id"]
        with get_cursor() as cur:
            credit_wallet(cur, cls.service_id, cls.player_id, "diamond", 10000)
            credit_wallet(cur, cls.service_id, cls.player_id, "gold", 100000)

    def test_gacha_pull_grants_hero(self):
        pull = gacha_service.pull(self.service_id, self.player_id, "standard", count=1)
        self.assertIn("results", pull)
        roster = hero_service.get_roster(self.service_id, self.player_id)
        self.assertGreaterEqual(roster["count"], 1)

    def test_hero_level_up(self):
        gacha_service.pull(self.service_id, self.player_id, "standard", count=1)
        roster = hero_service.get_roster(self.service_id, self.player_id)
        if not roster["heroes"]:
            self.skipTest("no hero from gacha")
        hid = roster["heroes"][0]["hero_id"]
        up = hero_service.level_up(self.service_id, self.player_id, hid)
        self.assertGreaterEqual(up["level"], 2)

    def test_idle_claim_after_pve_clear(self):
        team = {"heroes": [1, 2, 3]}
        start = pve_service.start_battle(self.service_id, self.player_id, "1-1", team=team)
        seed = int(start["seed"])
        win = True
        stars = 1
        ticks = 20
        checksum = hashlib.sha256(f"{seed}:1-1:{int(win)}:{stars}".encode()).hexdigest()[:16]
        replay_hash = compute_replay_hash(seed=seed, battle_type="pve", team=team, win=win, ticks=ticks)
        pve_service.settle_battle(
            self.service_id,
            self.player_id,
            start["battle_id"],
            win=win,
            stars=stars,
            duration_ms=5000,
            checksum=checksum,
            replay_hash=replay_hash,
            replay_ticks=ticks,
        )
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO baas_idle_state (service_id, player_id, last_claim_at, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(service_id, player_id) DO UPDATE SET last_claim_at=excluded.last_claim_at
                """,
                (self.service_id, self.player_id, "2020-01-01T00:00:00Z", "2020-01-01T00:00:00Z"),
            )
        status = idle_service.get_status(self.service_id, self.player_id)
        self.assertTrue(status.get("eligible"))
        claim = idle_service.claim(self.service_id, self.player_id)
        self.assertGreater(claim.get("claimed_gold", 0), 0)

    def test_tower_floor_progression(self):
        team = {"heroes": [1, 2, 3]}
        start = tower_service.start_battle(self.service_id, self.player_id, "main", 1, team=team)
        stage_key = "main:1"
        seed = int(start["seed"])
        win = True
        stars = 1
        ticks = 20
        checksum = hashlib.sha256(f"{seed}:{stage_key}:{int(win)}:{stars}".encode()).hexdigest()[:16]
        replay_hash = compute_replay_hash(seed=seed, battle_type="tower", team=team, win=win, ticks=ticks)
        result = tower_service.settle_battle(
            self.service_id,
            self.player_id,
            start["battle_id"],
            win=win,
            stars=stars,
            duration_ms=5000,
            checksum=checksum,
            replay_hash=replay_hash,
            replay_ticks=ticks,
        )
        self.assertTrue(result.get("win"))
        prog = tower_service.get_progress(self.service_id, self.player_id, "main")
        self.assertEqual(prog["current_floor"], 1)

    def test_iap_dev_verify(self):
        order = iap_service.create_order(self.service_id, self.player_id, "com.game.diamond60", platform="dev")
        receipt = f"dev-receipt-{order['order_id']}"
        delivered = iap_service.verify_and_deliver(
            self.service_id, self.player_id, order["order_id"], receipt=receipt
        )
        self.assertEqual(delivered.get("status"), "delivered")
        self.assertGreater(delivered.get("rewards", {}).get("diamond", 0), 0)


if __name__ == "__main__":
    unittest.main()
