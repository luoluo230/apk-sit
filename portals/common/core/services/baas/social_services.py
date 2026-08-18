# -*- coding: utf-8 -*-
"""Phase 3: guild, battlepass, periodic tasks."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config


def create_guild(service_id: str, player_id: str, name: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    gname = str(name or "").strip()
    if not gname:
        raise ValueError("公会名必填")
    guild_id = new_id("guild_")
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_guilds (guild_id, service_id, name, leader_player_id, member_count, payload_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (guild_id, service_id, gname, player_id, 1, "{}", now, now),
        )
        cur.execute(
            "INSERT INTO baas_guild_members (guild_id, service_id, player_id, role, joined_at) VALUES (?,?,?,?,?)",
            (guild_id, service_id, player_id, "leader", now),
        )
    return {"guild_id": guild_id, "name": gname, "leader_player_id": player_id}


def join_guild(service_id: str, player_id: str, guild_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "guild"):
        raise ValueError("公会功能未启用")
    cfg = get_feature_config(service_id, "guild")
    gid = str(guild_id or "").strip()
    init_db()
    with get_cursor() as cur:
        guild = cur.execute("SELECT * FROM baas_guilds WHERE service_id=? AND guild_id=?", (service_id, gid)).fetchone()
        if not guild:
            raise ValueError("公会不存在")
        if int(guild["member_count"] or 0) >= int(cfg.get("max_members") or 50):
            raise ValueError("公会已满")
        exists = cur.execute(
            "SELECT 1 FROM baas_guild_members WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
        if exists:
            raise ValueError("已在公会中")
        now = _now_iso()
        cur.execute(
            "INSERT INTO baas_guild_members (guild_id, service_id, player_id, role, joined_at) VALUES (?,?,?,?,?)",
            (gid, service_id, player_id, "member", now),
        )
        cur.execute(
            "UPDATE baas_guilds SET member_count=member_count+1, updated_at=? WHERE guild_id=?",
            (now, gid),
        )
    return {"guild_id": gid, "player_id": player_id, "role": "member"}


def get_guild(service_id: str, guild_id: str) -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        guild = cur.execute("SELECT * FROM baas_guilds WHERE service_id=? AND guild_id=?", (service_id, guild_id)).fetchone()
        if not guild:
            raise ValueError("公会不存在")
        members = cur.execute(
            "SELECT player_id, role, joined_at FROM baas_guild_members WHERE guild_id=? ORDER BY joined_at",
            (guild_id,),
        ).fetchall()
    return {
        "guild_id": guild["guild_id"],
        "name": guild["name"],
        "leader_player_id": guild["leader_player_id"],
        "member_count": guild["member_count"],
        "members": [dict(m) for m in members],
    }


def battlepass_state(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "battlepass"):
        raise ValueError("战令功能未启用")
    cfg = get_feature_config(service_id, "battlepass")
    season_id = str(cfg.get("season_id") or "s1")
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_battlepass_progress WHERE service_id=? AND player_id=? AND season_id=?",
            (service_id, player_id, season_id),
        ).fetchone()
    if not row:
        return {"season_id": season_id, "level": 1, "xp": 0, "premium": False, "claimed_levels": []}
    return {
        "season_id": season_id,
        "level": int(row["level"] or 1),
        "xp": int(row["xp"] or 0),
        "premium": bool(row["premium"]),
        "claimed_levels": _json_load(row["claimed_levels_json"], []),
    }


def battlepass_add_xp(service_id: str, player_id: str, xp: int) -> Dict[str, Any]:
    state = battlepass_state(service_id, player_id)
    cfg = get_feature_config(service_id, "battlepass")
    max_level = int(cfg.get("levels") or 30)
    new_xp = int(state["xp"]) + int(xp)
    level = min(max_level, int(state["level"]) + new_xp // 100)
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_battlepass_progress (service_id, player_id, season_id, level, xp, premium, claimed_levels_json, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, season_id) DO UPDATE SET
                level=excluded.level, xp=excluded.xp, updated_at=excluded.updated_at
            """,
            (
                service_id,
                player_id,
                state["season_id"],
                level,
                new_xp % 100,
                bool(state.get("premium")),
                _json_dump(state.get("claimed_levels") or []),
                now,
            ),
        )
    return battlepass_state(service_id, player_id)


def battlepass_claim(service_id: str, player_id: str, level: int) -> Dict[str, Any]:
    state = battlepass_state(service_id, player_id)
    if int(level) > int(state["level"]):
        raise ValueError("等级不足")
    claimed = list(state.get("claimed_levels") or [])
    if int(level) in claimed:
        raise ValueError("已领取")
    claimed.append(int(level))
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE baas_battlepass_progress SET claimed_levels_json=?, updated_at=?
            WHERE service_id=? AND player_id=? AND season_id=?
            """,
            (_json_dump(claimed), now, service_id, player_id, state["season_id"]),
        )
    return {"level": int(level), "claimed_levels": claimed}


def list_periodic_tasks(service_id: str, player_id: str) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "periodic_task"):
        return []
    cfg = get_feature_config(service_id, "periodic_task")
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT task_id, task_type, progress, status, claimed_at FROM baas_periodic_tasks WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchall()
    progress = {str(r["task_id"]): dict(r) for r in rows}
    out = []
    for task_type, tasks in (("daily", cfg.get("daily_tasks") or []), ("weekly", cfg.get("weekly_tasks") or [])):
        for t in tasks:
            tid = str(t.get("id") or "")
            row = progress.get(tid, {})
            out.append({
                "task_id": tid,
                "task_type": task_type,
                "name": t.get("name"),
                "target": t.get("target"),
                "progress": int(row.get("progress") or 0),
                "status": row.get("status") or "active",
            })
    return out


def claim_periodic_task(service_id: str, player_id: str, task_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "periodic_task"):
        raise ValueError("周期任务未启用")
    tid = str(task_id or "").strip()
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_periodic_tasks WHERE service_id=? AND player_id=? AND task_id=?",
            (service_id, player_id, tid),
        ).fetchone()
        if not row or row["status"] != "completed":
            raise ValueError("任务未完成")
        cur.execute(
            "UPDATE baas_periodic_tasks SET status='claimed', claimed_at=?, updated_at=? WHERE service_id=? AND player_id=? AND task_id=?",
            (now, now, service_id, player_id, tid),
        )
    return {"task_id": tid, "status": "claimed"}


def update_periodic_task(service_id: str, player_id: str, task_id: str, progress: int) -> Dict[str, Any]:
    if not feature_enabled(service_id, "periodic_task"):
        raise ValueError("周期任务未启用")
    tid = str(task_id or "").strip()
    cfg = get_feature_config(service_id, "periodic_task")
    target = 1
    for bucket in (cfg.get("daily_tasks") or []) + (cfg.get("weekly_tasks") or []):
        if str(bucket.get("id")) == tid:
            target = int(bucket.get("target") or 1)
            break
    status = "completed" if int(progress) >= target else "active"
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_periodic_tasks (service_id, player_id, task_id, task_type, progress, status, updated_at, claimed_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, task_id) DO UPDATE SET
                progress=excluded.progress, status=excluded.status, updated_at=excluded.updated_at
            """,
            (service_id, player_id, tid, "daily", int(progress), status, now, ""),
        )
    return {"task_id": tid, "progress": int(progress), "status": status}
