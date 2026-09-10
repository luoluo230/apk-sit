# -*- coding: utf-8 -*-
"""AFK 好友 / 助战 — 轻量社交。"""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.afk_config_loader import load_afk_bundle
from services.baas.helpers import _now_iso, new_id
from services.baas.service_crud import feature_enabled


def _ensure_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baas_friend_links (
            service_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            friend_player_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'accepted',
            assist_count_today INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (service_id, player_id, friend_player_id)
        )
        """
    )


def _friend_cfg() -> Dict[str, Any]:
    bundle = load_afk_bundle() or {}
    return dict(bundle.get("friend") or {})


def list_friends(service_id: str, player_id: str) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "login"):
        return []
    init_db()
    with get_cursor() as cur:
        _ensure_table(cur)
        rows = cur.execute(
            """
            SELECT friend_player_id, status, assist_count_today, created_at
            FROM baas_friend_links
            WHERE service_id=? AND player_id=? AND status='accepted'
            ORDER BY created_at DESC
            """,
            (service_id, player_id),
        ).fetchall()
    return [dict(r) for r in rows]


def add_friend(service_id: str, player_id: str, friend_player_id: str) -> Dict[str, Any]:
    fid = str(friend_player_id or "").strip()
    if not fid:
        raise ValueError("好友 ID 必填")
    if fid == player_id:
        raise ValueError("不能添加自己")
    cfg = _friend_cfg()
    max_friends = int(cfg.get("max_friends") or 30)
    init_db()
    with get_cursor() as cur:
        _ensure_table(cur)
        exists = cur.execute(
            "SELECT 1 FROM baas_players WHERE service_id=? AND player_id=?",
            (service_id, fid),
        ).fetchone()
        if not exists:
            raise ValueError("玩家不存在")
        cnt = cur.execute(
            "SELECT COUNT(*) AS c FROM baas_friend_links WHERE service_id=? AND player_id=? AND status='accepted'",
            (service_id, player_id),
        ).fetchone()
        if int(cnt["c"] or 0) >= max_friends:
            raise ValueError("好友数量已满")
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_friend_links (service_id, player_id, friend_player_id, status, assist_count_today, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, friend_player_id) DO UPDATE SET
                status='accepted', updated_at=excluded.updated_at
            """,
            (service_id, player_id, fid, "accepted", 0, now, now),
        )
        cur.execute(
            """
            INSERT INTO baas_friend_links (service_id, player_id, friend_player_id, status, assist_count_today, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, friend_player_id) DO NOTHING
            """,
            (service_id, fid, player_id, "accepted", 0, now, now),
        )
    return {"friend_player_id": fid, "status": "accepted"}


def assist_friend(service_id: str, player_id: str, friend_player_id: str) -> Dict[str, Any]:
    fid = str(friend_player_id or "").strip()
    cfg = _friend_cfg()
    daily_limit = int(cfg.get("assist_daily_limit") or 10)
    init_db()
    with get_cursor() as cur:
        _ensure_table(cur)
        row = cur.execute(
            """
            SELECT assist_count_today FROM baas_friend_links
            WHERE service_id=? AND player_id=? AND friend_player_id=? AND status='accepted'
            """,
            (service_id, player_id, fid),
        ).fetchone()
        if not row:
            raise ValueError("不是好友")
        used = int(row["assist_count_today"] or 0)
        if used >= daily_limit:
            raise ValueError("今日助战次数已用完")
        now = _now_iso()
        cur.execute(
            """
            UPDATE baas_friend_links SET assist_count_today=assist_count_today+1, updated_at=?
            WHERE service_id=? AND player_id=? AND friend_player_id=?
            """,
            (now, service_id, player_id, fid),
        )
        rewards = dict(cfg.get("assist_rewards") or {"gold": 200})
        if rewards:
            from services.baas.afk_reward_grants import grant_rewards
            grant_rewards(cur, service_id, player_id, rewards)
    return {"friend_player_id": fid, "rewards": rewards, "assist_used": used + 1, "assist_limit": daily_limit}
