# -*- coding: utf-8 -*-
"""公会战：赛季报名、战斗提交、跨服积分榜。"""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.retention_services import submit_score, top_scores
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas import social_services


def _season_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    season = dict(cfg.get("active_season") or {})
    if not season.get("season_id"):
        season = {"season_id": "gw_s1", "name": "公会战 S1", "max_guilds": 64}
    return season


def get_active_season(service_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    cfg = get_feature_config(service_id, "guild")
    season = _season_cfg(cfg)
    sid = str(season.get("season_id") or "gw_s1")
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT guild_id, total_score, battles_won, battles_lost, updated_at
            FROM baas_guild_war_entries
            WHERE service_id=? AND season_id=?
            ORDER BY total_score DESC, battles_won DESC
            LIMIT 50
            """,
            (service_id, sid),
        ).fetchall()
    return {
        "season_id": sid,
        "name": season.get("name"),
        "standings": [dict(r) for r in rows],
        "board_id": f"guild_war:{sid}",
    }


def register_guild(service_id: str, player_id: str, guild_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    cfg = get_feature_config(service_id, "guild")
    season = _season_cfg(cfg)
    sid = str(season.get("season_id") or "gw_s1")
    gid = str(guild_id or "").strip()
    guild = social_services.get_guild(service_id, gid)
    if str(guild.get("leader_player_id") or "") != player_id:
        raise ValueError("仅会长可报名公会战")
    init_db()
    with get_cursor() as cur:
        exists = cur.execute(
            "SELECT 1 FROM baas_guild_war_entries WHERE service_id=? AND season_id=? AND guild_id=?",
            (service_id, sid, gid),
        ).fetchone()
        if exists:
            return {"season_id": sid, "guild_id": gid, "status": "registered"}
        count = cur.execute(
            "SELECT COUNT(1) AS c FROM baas_guild_war_entries WHERE service_id=? AND season_id=?",
            (service_id, sid),
        ).fetchone()
        if int(count["c"] or 0) >= int(season.get("max_guilds") or 64):
            raise ValueError("本赛季报名已满")
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_guild_war_entries (
                service_id, season_id, guild_id, total_score, battles_won, battles_lost, payload_json, updated_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (service_id, sid, gid, 0, 0, 0, "{}", now),
        )
    return {"season_id": sid, "guild_id": gid, "status": "registered"}


def submit_battle_result(
    service_id: str,
    player_id: str,
    guild_id: str,
    *,
    win: bool,
    score_delta: int = 0,
) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    cfg = get_feature_config(service_id, "guild")
    season = _season_cfg(cfg)
    sid = str(season.get("season_id") or "gw_s1")
    gid = str(guild_id or "").strip()
    init_db()
    with get_cursor() as cur:
        member = cur.execute(
            "SELECT 1 FROM baas_guild_members WHERE service_id=? AND guild_id=? AND player_id=?",
            (service_id, gid, player_id),
        ).fetchone()
        if not member:
            raise ValueError("非公会成员")
        row = cur.execute(
            "SELECT * FROM baas_guild_war_entries WHERE service_id=? AND season_id=? AND guild_id=?",
            (service_id, sid, gid),
        ).fetchone()
        if not row:
            raise ValueError("公会未报名本赛季")
        delta = int(score_delta or (50 if win else 10))
        total = int(row["total_score"] or 0) + delta
        won = int(row["battles_won"] or 0) + (1 if win else 0)
        lost = int(row["battles_lost"] or 0) + (0 if win else 1)
        now = _now_iso()
        cur.execute(
            """
            UPDATE baas_guild_war_entries
            SET total_score=?, battles_won=?, battles_lost=?, updated_at=?
            WHERE service_id=? AND season_id=? AND guild_id=?
            """,
            (total, won, lost, now, service_id, sid, gid),
        )
        match_id = new_id("gwm_")
        cur.execute(
            """
            INSERT INTO baas_guild_war_matches (
                match_id, service_id, season_id, guild_id, player_id, win, score_delta, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (match_id, service_id, sid, gid, player_id, 1 if win else 0, delta, now),
        )
    board_id = f"guild_war:{sid}"
    guild_info = social_services.get_guild(service_id, gid)
    submit_score(service_id, gid, board_id, float(total), display_name=str(guild_info.get("name") or gid))
    return {
        "season_id": sid,
        "guild_id": gid,
        "win": win,
        "score_delta": delta,
        "total_score": total,
        "board_id": board_id,
    }


def cross_server_top(service_id: str, board_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """跨服榜：基于 guild_war 专用 board_id 或配置 scope=cross_server 的榜。"""
    if not feature_enabled(service_id, "leaderboard"):
        return []
    cfg = get_feature_config(service_id, "leaderboard")
    boards = {str(b.get("id") or ""): b for b in (cfg.get("boards") or [])}
    bid = str(board_id or "").strip()
    board = boards.get(bid, {})
    if str(board.get("scope") or "") == "cross_server" or bid.startswith("guild_war:"):
        return top_scores(service_id, bid, limit=limit)
    return top_scores(service_id, bid, limit=limit)
