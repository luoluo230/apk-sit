# -*- coding: utf-8 -*-
"""公会扩展：捐献、科技、商店、讨伐。"""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.afk.afk_reward_grants import grant_rewards
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.wallet_helpers import debit_wallet


def _guild_cfg(service_id: str) -> Dict[str, Any]:
    return get_feature_config(service_id, "guild")


def _member_guild(cur, service_id: str, player_id: str) -> str:
    row = cur.execute(
        "SELECT guild_id FROM baas_guild_members WHERE service_id=? AND player_id=?",
        (service_id, player_id),
    ).fetchone()
    return str(row["guild_id"]) if row else ""


def _ensure_guild_meta(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baas_guild_meta (
            guild_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            tech_json TEXT NOT NULL DEFAULT '{}',
            raid_hp_dealt INTEGER NOT NULL DEFAULT 0,
            raid_phase INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (service_id, guild_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baas_guild_donate_log (
            service_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            donate_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (service_id, player_id, guild_id, donate_date)
        )
        """
    )


def donate(service_id: str, player_id: str, *, currency: str = "gold", amount: int = 1000) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    cfg = _guild_cfg(service_id)
    init_db()
    with get_cursor() as cur:
        _ensure_guild_meta(cur)
        gid = _member_guild(cur, service_id, player_id)
        if not gid:
            raise ValueError("未加入公会")
        today = _now_iso()[:10]
        limit = int(cfg.get("daily_donate_limit") or 3)
        row = cur.execute(
            "SELECT count FROM baas_guild_donate_log WHERE service_id=? AND player_id=? AND guild_id=? AND donate_date=?",
            (service_id, player_id, gid, today),
        ).fetchone()
        used = int(row["count"] or 0) if row else 0
        if used >= limit:
            raise ValueError("今日捐献次数已满")
        debit_wallet(cur, service_id, player_id, currency, int(amount))
        rewards = dict(cfg.get("donate_rewards") or {"guild_coin": 50, "guild_badge": 10})
        granted = grant_rewards(cur, service_id, player_id, rewards)
        cur.execute(
            """
            INSERT INTO baas_guild_donate_log (service_id, player_id, guild_id, donate_date, count)
            VALUES (?,?,?,?,1)
            ON CONFLICT(service_id, player_id, guild_id, donate_date) DO UPDATE SET count=count+1
            """,
            (service_id, player_id, gid, today),
        )
    return {"guild_id": gid, "rewards": granted, "donate_used": used + 1, "donate_limit": limit}


def upgrade_tech(service_id: str, player_id: str, tech_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    cfg = _guild_cfg(service_id)
    tid = str(tech_id or "").strip()
    node = next((n for n in (cfg.get("tech_nodes") or []) if str(n.get("id")) == tid), None)
    if not node:
        raise ValueError("科技不存在")
    init_db()
    with get_cursor() as cur:
        _ensure_guild_meta(cur)
        gid = _member_guild(cur, service_id, player_id)
        if not gid:
            raise ValueError("未加入公会")
        meta = cur.execute("SELECT tech_json FROM baas_guild_meta WHERE service_id=? AND guild_id=?", (service_id, gid)).fetchone()
        tech = _json_load(meta["tech_json"], {}) if meta else {}
        lv = int(tech.get(tid) or 0)
        max_lv = int(node.get("max_level") or 10)
        if lv >= max_lv:
            raise ValueError("科技已满级")
        cost = int(cfg.get("tech_upgrade_cost_badge") or 20) * (lv + 1)
        debit_wallet(cur, service_id, player_id, "guild_badge", cost)
        tech[tid] = lv + 1
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_guild_meta (guild_id, service_id, tech_json, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(service_id, guild_id) DO UPDATE SET tech_json=excluded.tech_json, updated_at=excluded.updated_at
            """,
            (gid, service_id, _json_dump(tech), now),
        )
    return {"tech_id": tid, "level": lv + 1, "tech": tech}


def guild_shop_purchase(service_id: str, player_id: str, goods_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    cfg = _guild_cfg(service_id)
    gid_s = str(goods_id or "")
    goods = next((g for g in (cfg.get("guild_shop") or []) if str(g.get("id")) == gid_s), None)
    if not goods:
        raise ValueError("商品不存在")
    init_db()
    with get_cursor() as cur:
        gid = _member_guild(cur, service_id, player_id)
        if not gid:
            raise ValueError("未加入公会")
        debit_wallet(cur, service_id, player_id, str(goods.get("currency_id") or "guild_coin"), int(goods.get("price") or 0))
        item_key = str(goods.get("item_key") or "")
        qty = int(goods.get("quantity") or 1)
        rewards = {item_key: qty} if item_key else {}
        granted = grant_rewards(cur, service_id, player_id, rewards)
    return {"goods_id": gid_s, "grants": granted}


def raid_hit(service_id: str, player_id: str, damage: int) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    cfg = _guild_cfg(service_id)
    phases = list(cfg.get("raid_phases") or [])
    if not phases:
        raise ValueError("讨伐未配置")
    init_db()
    with get_cursor() as cur:
        _ensure_guild_meta(cur)
        gid = _member_guild(cur, service_id, player_id)
        if not gid:
            raise ValueError("未加入公会")
        meta = cur.execute("SELECT * FROM baas_guild_meta WHERE service_id=? AND guild_id=?", (service_id, gid)).fetchone()
        phase_idx = int(meta["raid_phase"] or 1) if meta else 1
        dealt = int(meta["raid_hp_dealt"] or 0) if meta else 0
        phase = next((p for p in phases if int(p.get("phase_id") or 0) == phase_idx), phases[0])
        pool = int(phase.get("hp_pool") or 100000)
        dealt += max(1, int(damage))
        phase_cleared = dealt >= pool
        rewards_granted = []
        if phase_cleared:
            rewards_granted = grant_rewards(cur, service_id, player_id, dict(phase.get("rewards") or {}))
            phase_idx = min(phase_idx + 1, int(phases[-1].get("phase_id") or phase_idx))
            dealt = 0
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_guild_meta (guild_id, service_id, tech_json, raid_hp_dealt, raid_phase, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, guild_id) DO UPDATE SET
                raid_hp_dealt=excluded.raid_hp_dealt, raid_phase=excluded.raid_phase, updated_at=excluded.updated_at
            """,
            (gid, service_id, meta["tech_json"] if meta else "{}", dealt, phase_idx, now),
        )
    return {"damage": damage, "raid_hp_dealt": dealt, "raid_phase": phase_idx, "phase_cleared": phase_cleared, "rewards": rewards_granted}


def guild_status(service_id: str, player_id: str) -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        _ensure_guild_meta(cur)
        gid = _member_guild(cur, service_id, player_id)
        if not gid:
            return {"in_guild": False}
        meta = cur.execute("SELECT * FROM baas_guild_meta WHERE service_id=? AND guild_id=?", (service_id, gid)).fetchone()
        guild = cur.execute("SELECT * FROM baas_guilds WHERE service_id=? AND guild_id=?", (service_id, gid)).fetchone()
    return {
        "in_guild": True,
        "guild_id": gid,
        "name": guild["name"] if guild else "",
        "tech": _json_load(meta["tech_json"], {}) if meta else {},
        "raid_hp_dealt": int(meta["raid_hp_dealt"] or 0) if meta else 0,
        "raid_phase": int(meta["raid_phase"] or 1) if meta else 1,
    }
