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


if __name__ == "__main__":
    unittest.main()
