# -*- coding: utf-8 -*-
"""留存赛季调度与 VIP 特权单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch


class TestAfkRetentionScheduler(unittest.TestCase):
    def test_bump_season_id(self):
        from services.baas.afk.afk_retention_scheduler import _bump_season_id

        self.assertEqual(_bump_season_id("arena_afk_s1"), "arena_afk_s2")
        self.assertEqual(_bump_season_id("afk_bp_s9"), "afk_bp_s10")

    def test_season_not_expired_without_date(self):
        from services.baas.afk.afk_retention_scheduler import _season_expired

        self.assertFalse(_season_expired(None))
        self.assertFalse(_season_expired(""))

    def test_dungeon_limit_includes_vip_extra(self):
        from services.baas.afk.afk_growth_service import _dungeon_daily_limit

        dg = {"daily_limit": 3}
        with patch("services.baas.afk.afk_vip_service.extra_dungeon_attempts", return_value=2):
            self.assertEqual(_dungeon_daily_limit("svc", "p1", dg), 5)


if __name__ == "__main__":
    unittest.main()
