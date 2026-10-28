# -*- coding: utf-8 -*-
"""VIP 等级、特权、每日领取。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.afk.afk_config_loader import load_afk_bundle
from services.baas.afk.afk_reward_grants import grant_rewards
from services.baas.helpers import _json_dump, _json_load, _now_iso
from services.baas.service_crud import feature_enabled, get_feature_config


def _vip_cfg() -> Dict[str, Any]:
    bundle = load_afk_bundle() or {}
    return dict(bundle.get("vip_iap") or {})


def _levels(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(cfg.get("vip_levels") or [])


def _level_for_exp(cfg: Dict[str, Any], exp: int) -> int:
    lv = 0
    for row in _levels(cfg):
        if int(exp) >= int(row.get("exp_required") or 0):
            lv = int(row.get("level") or lv)
    return lv


def _privileges(cfg: Dict[str, Any], level: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for row in _levels(cfg):
        if int(row.get("level") or 0) <= int(level):
            out.update(dict(row.get("privileges") or {}))
    return out


def _ensure_row(cur, service_id: str, player_id: str) -> Dict[str, Any]:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baas_vip_progress (
            service_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            vip_exp INTEGER NOT NULL DEFAULT 0,
            vip_level INTEGER NOT NULL DEFAULT 0,
            last_daily_claim_at TEXT NOT NULL DEFAULT '',
            premium_battlepass INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (service_id, player_id)
        )
        """
    )
    row = cur.execute(
        "SELECT * FROM baas_vip_progress WHERE service_id=? AND player_id=?",
        (service_id, player_id),
    ).fetchone()
    if row:
        return dict(row)
    now = _now_iso()
    cur.execute(
        """
        INSERT INTO baas_vip_progress (service_id, player_id, vip_exp, vip_level, last_daily_claim_at, premium_battlepass, updated_at)
        VALUES (?,?,0,0,'',0,?)
        """,
        (service_id, player_id, now),
    )
    return {"service_id": service_id, "player_id": player_id, "vip_exp": 0, "vip_level": 0, "last_daily_claim_at": "", "premium_battlepass": 0}


def get_state(service_id: str, player_id: str) -> Dict[str, Any]:
    cfg = _vip_cfg()
    init_db()
    with get_cursor() as cur:
        row = _ensure_row(cur, service_id, player_id)
    level = int(row.get("vip_level") or 0)
    exp = int(row.get("vip_exp") or 0)
    priv = _privileges(cfg, level)
    next_lv = next((r for r in _levels(cfg) if int(r.get("level") or 0) > level), None)
    return {
        "vip_level": level,
        "vip_exp": exp,
        "privileges": priv,
        "next_level_exp": int(next_lv.get("exp_required") or 0) if next_lv else None,
        "premium_battlepass": bool(row.get("premium_battlepass")),
        "last_daily_claim_at": row.get("last_daily_claim_at") or "",
    }


def add_vip_exp(service_id: str, player_id: str, amount: int, *, unlock_bp_premium: bool = False) -> Dict[str, Any]:
    amt = int(amount or 0)
    cfg = _vip_cfg()
    init_db()
    with get_cursor() as cur:
        row = _ensure_row(cur, service_id, player_id)
        exp = int(row.get("vip_exp") or 0) + amt
        level = _level_for_exp(cfg, exp)
        bp_premium = int(row.get("premium_battlepass") or 0) or (1 if unlock_bp_premium else 0)
        now = _now_iso()
        cur.execute(
            """
            UPDATE baas_vip_progress SET vip_exp=?, vip_level=?, premium_battlepass=?, updated_at=? WHERE service_id=? AND player_id=?
            """,
            (exp, level, bp_premium, now, service_id, player_id),
        )
        prof = cur.execute("SELECT profile_json FROM baas_players WHERE service_id=? AND player_id=?", (service_id, player_id)).fetchone()
        if prof:
            p = _json_load(prof["profile_json"], {})
            p["vip_level"] = level
            p["vip_exp"] = exp
            cur.execute("UPDATE baas_players SET profile_json=?, updated_at=? WHERE service_id=? AND player_id=?", (_json_dump(p), now, service_id, player_id))
        if unlock_bp_premium and feature_enabled(service_id, "battlepass"):
            bp_cfg = get_feature_config(service_id, "battlepass")
            season = str(bp_cfg.get("season_id") or "s1")
            cur.execute(
                """
                INSERT INTO baas_battlepass_progress (service_id, player_id, season_id, level, xp, premium, claimed_levels_json, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(service_id, player_id, season_id) DO UPDATE SET premium=1, updated_at=excluded.updated_at
                """,
                (service_id, player_id, season, 1, 0, 1, "[]", now),
            )
    return get_state(service_id, player_id)


def claim_daily(service_id: str, player_id: str) -> Dict[str, Any]:
    cfg = _vip_cfg()
    init_db()
    with get_cursor() as cur:
        row = _ensure_row(cur, service_id, player_id)
        level = int(row.get("vip_level") or 0)
        if level < 1:
            raise ValueError("VIP 等级不足")
        priv = _privileges(cfg, level)
        today = _now_iso()[:10]
        last = str(row.get("last_daily_claim_at") or "")[:10]
        if last == today:
            raise ValueError("今日已领取")
        rewards: Dict[str, Any] = {}
        if priv.get("daily_diamond"):
            rewards["diamond"] = int(priv["daily_diamond"])
        scrolls = priv.get("daily_scrolls") or {}
        if isinstance(scrolls, dict):
            rewards.update({k: int(v) for k, v in scrolls.items() if int(v or 0) > 0})
        elif priv.get("daily_hero_scroll"):
            rewards["hero_summon_scroll"] = int(priv["daily_hero_scroll"])
        granted = grant_rewards(cur, service_id, player_id, rewards) if rewards else []
        now = _now_iso()
        cur.execute(
            "UPDATE baas_vip_progress SET last_daily_claim_at=?, updated_at=? WHERE service_id=? AND player_id=?",
            (now, now, service_id, player_id),
        )
    return {"rewards": rewards, "granted": granted, "vip_level": level}


def privilege(service_id: str, player_id: str, key: str, default: Any = None) -> Any:
    st = get_state(service_id, player_id)
    return (st.get("privileges") or {}).get(key, default)


def shop_discount_mul(service_id: str, player_id: str) -> float:
    disc = float(privilege(service_id, player_id, "shop_discount", 0) or 0)
    return max(0.5, 1.0 - disc)


def idle_bonus_mul(service_id: str, player_id: str) -> float:
    return 1.0 + float(privilege(service_id, player_id, "idle_bonus_pct", 0) or 0) / 100.0


def extra_dungeon_attempts(service_id: str, player_id: str) -> int:
    return int(privilege(service_id, player_id, "dungeon_extra_daily", 0) or 0)
