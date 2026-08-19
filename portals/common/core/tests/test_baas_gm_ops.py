# -*- coding: utf-8 -*-
"""GM ops: bans, announcements, gift code types, activities."""

from __future__ import annotations

import unittest
import uuid

from models.db import get_cursor, init_db
from services.baas import activity_service, announce_service, gm_service, retention_services


class BaasGmOpsTests(unittest.TestCase):
    SERVICE = "svc_gm_ops_test"

    def setUp(self):
        init_db()
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO baas_services (service_id, project_id, env_key, name, status, feature_flags, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(service_id) DO UPDATE SET feature_flags=excluded.feature_flags
                """,
                (
                    self.SERVICE,
                    "p_test",
                    "development",
                    "GM Test",
                    "active",
                    '{"gift":true,"announce":true,"activity":true}',
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )
            cur.execute(
                """
                INSERT INTO baas_feature_configs (service_id, feature_key, config_json, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(service_id, feature_key) DO UPDATE SET config_json=excluded.config_json
                """,
                (self.SERVICE, "gift", '{"enabled":true,"codes":[]}', "2026-01-01T00:00:00"),
            )
            cur.execute(
                """
                INSERT INTO baas_feature_configs (service_id, feature_key, config_json, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(service_id, feature_key) DO UPDATE SET config_json=excluded.config_json
                """,
                (self.SERVICE, "activity", '{"enabled":true}', "2026-01-01T00:00:00"),
            )
            cur.execute(
                """
                INSERT INTO baas_feature_configs (service_id, feature_key, config_json, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(service_id, feature_key) DO UPDATE SET config_json=excluded.config_json
                """,
                (self.SERVICE, "announce", '{"enabled":true}', "2026-01-01T00:00:00"),
            )

    def test_ban_and_announce_and_activity(self):
        gm_service.ban_player(self.SERVICE, "p1", reason="cheat", actor="admin")
        self.assertTrue(gm_service.is_player_banned(self.SERVICE, "p1"))
        ann = gm_service.save_announcement(
            self.SERVICE,
            {"title": "Maint", "body": "Tonight maintenance", "display_type": "marquee", "status": "published"},
            actor="admin",
        )
        self.assertEqual(ann["display_type"], "marquee")
        rows = announce_service.list_active(self.SERVICE, display_type="marquee")
        self.assertTrue(any(r["title"] == "Maint" for r in rows))
        act = gm_service.save_activity(
            self.SERVICE,
            {
                "title": "七日登录",
                "activity_type": "login_event",
                "starts_at": "2020-01-01T00:00:00",
                "ends_at": "2099-01-01T00:00:00",
                "gates": {"level_min": 1},
                "payload": {"days": 7},
                "status": "published",
            },
            actor="admin",
        )
        active = activity_service.list_active_for_player(self.SERVICE, {"level": 5})
        self.assertTrue(any(r["activity_id"] == act["activity_id"] for r in active))

    def test_gift_code_types(self):
        code = "COMP" + uuid.uuid4().hex[:6].upper()
        gm_service.upsert_gift_code(
            self.SERVICE,
            {
                "code": code,
                "code_type": "compensation",
                "max_uses": 100,
                "per_player_limit": 2,
                "rewards": [{"type": "gold", "amount": 50}],
            },
            actor="admin",
        )
        retention_services.redeem_gift(self.SERVICE, "p2", code)
        retention_services.redeem_gift(self.SERVICE, "p2", code)
        with self.assertRaises(ValueError):
            retention_services.redeem_gift(self.SERVICE, "p2", code)

    def test_room_gm_admin_ops(self):
        import os
        import sys
        from unittest import mock

        _CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _CORE not in sys.path:
            sys.path.insert(0, _CORE)

        with get_cursor() as cur:
            cur.execute(
                """
                UPDATE baas_services SET feature_flags=?
                WHERE service_id=?
                """,
                ('{"gift":true,"announce":true,"activity":true,"pvp":true}', self.SERVICE),
            )

        from services.baas import room_service

        room_service._rooms.clear()
        room_service._replays.clear()

        with mock.patch("services.baas.room_service.feature_enabled", return_value=True), mock.patch(
            "services.baas.room_service.get_feature_config",
            return_value={"max_players": 2, "max_spectators": 4},
        ):
            host = room_service.create_room(self.SERVICE, "host", visibility="public")
            room_service.join_room(self.SERVICE, "guest", room_id=host["room_id"])
            room_service.start_battle(self.SERVICE, host["room_id"], "host")

        rows = gm_service.list_rooms_admin(self.SERVICE, status="active")
        self.assertTrue(any(r["room_id"] == host["room_id"] for r in rows))
        detail = gm_service.get_room_admin(self.SERVICE, host["room_id"])
        self.assertEqual(detail["status"], "active")
        gm_service.kick_room_player_admin(self.SERVICE, host["room_id"], "guest", actor="admin")
        finished = gm_service.finish_room_battle_admin(
            self.SERVICE,
            host["room_id"],
            result={"winner": "host"},
            actor="admin",
        )
        self.assertEqual(finished["status"], "finished")
        replays = gm_service.list_room_replays_admin(self.SERVICE, limit=5)
        self.assertTrue(any(r.get("replay_id") == finished.get("replay_id") for r in replays))
        gm_service.close_room_admin(self.SERVICE, host["room_id"], reason="gm_test", actor="admin")
        audit = gm_service.list_gm_audit(self.SERVICE, limit=30)
        actions = {row["action"] for row in audit}
        self.assertIn("baas_gm_room_kick", actions)
        self.assertIn("baas_gm_room_finish", actions)
        self.assertIn("baas_gm_room_close", actions)

    def test_mail_template_and_grant_items(self):
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO baas_players (player_id, service_id, auth_provider, external_id, display_name, profile_json, token, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(player_id) DO UPDATE SET token=excluded.token
                """,
                (
                    "p_grant",
                    self.SERVICE,
                    "guest",
                    "ext_grant",
                    "GrantUser",
                    "{}",
                    "tok_grant_123",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )
        tpl = gm_service.save_mail_template(
            self.SERVICE,
            {"title": "补偿", "body": "请领取", "attachments": [{"type": "gold", "amount": 1}]},
            actor="admin",
        )
        self.assertTrue(tpl.get("template_id"))
        templates = gm_service.list_mail_templates(self.SERVICE)
        self.assertTrue(any(t["template_id"] == tpl["template_id"] for t in templates))
        grant = gm_service.grant_items(
            self.SERVICE,
            "p_grant",
            [{"item_id": "101", "quantity": 3}],
            actor="admin",
        )
        self.assertEqual(len(grant["attachments"]), 1)
        audit = gm_service.list_gm_audit(self.SERVICE, limit=20)
        self.assertTrue(any(r["action"] == "baas_gm_grant_items" for r in audit))


if __name__ == "__main__":
    unittest.main()
