# -*- coding: utf-8 -*-
"""AFK 留存事件钩子：任务 / 成就 / 战令经验 在玩法结算后自动推进。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.db import get_cursor, init_db
from services.baas.helpers import _now_iso
from services.baas.service_crud import feature_enabled, get_feature_config


def _task_defs(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for bucket, rows in (("daily", cfg.get("daily_tasks") or []), ("weekly", cfg.get("weekly_tasks") or [])):
        for row in rows:
            tid = str(row.get("id") or "")
            if tid:
                out[tid] = {"target": int(row.get("target") or 1), "task_type": bucket}
    return out


def _bump_task(cur, service_id: str, player_id: str, task_id: str, delta: int = 1) -> None:
    if not feature_enabled(service_id, "periodic_task"):
        return
    tid = str(task_id or "").strip()
    if not tid or delta <= 0:
        return
    cfg = get_feature_config(service_id, "periodic_task")
    defs = _task_defs(cfg)
    if tid not in defs:
        return
    target = int(defs[tid]["target"])
    task_type = defs[tid]["task_type"]
    row = cur.execute(
        "SELECT progress, status FROM baas_periodic_tasks WHERE service_id=? AND player_id=? AND task_id=?",
        (service_id, player_id, tid),
    ).fetchone()
    if row and str(row["status"] or "") in ("claimed", "completed"):
        if str(row["status"] or "") == "claimed":
            return
    prev = int(row["progress"] or 0) if row else 0
    progress = min(target, prev + int(delta))
    status = "completed" if progress >= target else "active"
    now = _now_iso()
    cur.execute(
        """
        INSERT INTO baas_periodic_tasks (service_id, player_id, task_id, task_type, progress, status, updated_at, claimed_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(service_id, player_id, task_id) DO UPDATE SET
            progress=excluded.progress, status=excluded.status, updated_at=excluded.updated_at
        """,
        (service_id, player_id, tid, task_type, progress, status, now, ""),
    )


def _set_achievement(cur, service_id: str, player_id: str, achievement_id: str, progress: int) -> None:
    if not feature_enabled(service_id, "achievement"):
        return
    aid = str(achievement_id or "").strip()
    if not aid:
        return
    cfg = get_feature_config(service_id, "achievement")
    target = next((int(d.get("target") or 1) for d in (cfg.get("definitions") or []) if str(d.get("id")) == aid), 1)
    row = cur.execute(
        "SELECT progress, status FROM baas_player_achievements WHERE service_id=? AND player_id=? AND achievement_id=?",
        (service_id, player_id, aid),
    ).fetchone()
    if row and str(row["status"] or "") in ("claimed", "completed"):
        return
    prev = int(row["progress"] or 0) if row else 0
    progress = max(prev, int(progress))
    status = "completed" if progress >= target else "in_progress"
    now = _now_iso()
    cur.execute(
        """
        INSERT INTO baas_player_achievements (service_id, player_id, achievement_id, status, progress, updated_at, claimed_at)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(service_id, player_id, achievement_id) DO UPDATE SET
            progress=excluded.progress, status=excluded.status, updated_at=excluded.updated_at
        """,
        (service_id, player_id, aid, status, progress, now, ""),
    )


def _max_cleared_stage(cur, service_id: str, player_id: str) -> int:
    row = cur.execute(
        """
        SELECT COUNT(*) AS cnt FROM baas_chapter_progress
        WHERE service_id=? AND player_id=? AND cleared=1
        """,
        (service_id, player_id),
    ).fetchone()
    return int(row["cnt"] or 0) if row else 0


def _count_settled_battles(cur, service_id: str, player_id: str, battle_type: str) -> int:
    row = cur.execute(
        """
        SELECT COUNT(*) AS cnt FROM baas_battles
        WHERE service_id=? AND player_id=? AND battle_type=? AND status='settled'
        """,
        (service_id, player_id, battle_type),
    ).fetchone()
    return int(row["cnt"] or 0) if row else 0


def _tower_best_floor(cur, service_id: str, player_id: str) -> int:
    row = cur.execute(
        """
        SELECT MAX(floor) AS mx FROM baas_tower_progress
        WHERE service_id=? AND player_id=?
        """,
        (service_id, player_id),
    ).fetchone()
    return int(row["mx"] or 0) if row else 0


def _add_battlepass_xp(cur, service_id: str, player_id: str, xp: int) -> None:
    if not feature_enabled(service_id, "battlepass") or xp <= 0:
        return
    cfg = get_feature_config(service_id, "battlepass")
    season_id = str(cfg.get("season_id") or "s1")
    max_level = int(cfg.get("levels") or 30)
    row = cur.execute(
        "SELECT level, xp, premium, claimed_levels_json FROM baas_battlepass_progress WHERE service_id=? AND player_id=? AND season_id=?",
        (service_id, player_id, season_id),
    ).fetchone()
    level = int(row["level"] or 1) if row else 1
    cur_xp = int(row["xp"] or 0) if row else 0
    premium = bool(row["premium"]) if row else False
    claimed_json = str(row["claimed_levels_json"] or "[]") if row else "[]"
    new_xp = cur_xp + int(xp)
    while new_xp >= 100 and level < max_level:
        new_xp -= 100
        level += 1
    now = _now_iso()
    cur.execute(
        """
        INSERT INTO baas_battlepass_progress (service_id, player_id, season_id, level, xp, premium, claimed_levels_json, updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(service_id, player_id, season_id) DO UPDATE SET
            level=excluded.level, xp=excluded.xp, updated_at=excluded.updated_at
        """,
        (service_id, player_id, season_id, level, new_xp, premium, claimed_json, now),
    )


def on_player_login(service_id: str, player_id: str) -> None:
    init_db()
    with get_cursor() as cur:
        _bump_task(cur, service_id, player_id, "daily_login", 1)


def on_pve_win(service_id: str, player_id: str, *, stage_id: str = "") -> None:
    init_db()
    with get_cursor() as cur:
        _bump_task(cur, service_id, player_id, "daily_stage_3", 1)
        _bump_task(cur, service_id, player_id, "weekly_stage_20", 1)
        cleared = _max_cleared_stage(cur, service_id, player_id)
        for aid, threshold in (("ach_stage_10", 10), ("ach_stage_50", 50), ("ach_stage_100", 100)):
            _set_achievement(cur, service_id, player_id, aid, cleared)
        _add_battlepass_xp(cur, service_id, player_id, 15)


def on_gacha_pull(service_id: str, player_id: str, *, count: int = 1) -> None:
    init_db()
    with get_cursor() as cur:
        _bump_task(cur, service_id, player_id, "daily_gacha_1", count)
        _bump_task(cur, service_id, player_id, "weekly_gacha_10", count)
        row = cur.execute(
            """
            SELECT COALESCE(SUM(total_pulls), 0) AS cnt FROM baas_gacha_state
            WHERE service_id=? AND player_id=?
            """,
            (service_id, player_id),
        ).fetchone()
        total = int(row["cnt"] or 0) if row else count
        _set_achievement(cur, service_id, player_id, "ach_gacha_10", total)
        _set_achievement(cur, service_id, player_id, "ach_gacha_50", total)
        _add_battlepass_xp(cur, service_id, player_id, 10 * count)


def on_arena_settled(service_id: str, player_id: str) -> None:
    init_db()
    with get_cursor() as cur:
        _bump_task(cur, service_id, player_id, "daily_arena_3", 1)
        _bump_task(cur, service_id, player_id, "weekly_arena_15", 1)
        cnt = _count_settled_battles(cur, service_id, player_id, "arena")
        _set_achievement(cur, service_id, player_id, "ach_arena_10", cnt)
        _add_battlepass_xp(cur, service_id, player_id, 20)


def on_idle_claim(service_id: str, player_id: str) -> None:
    init_db()
    with get_cursor() as cur:
        _bump_task(cur, service_id, player_id, "daily_idle_1", 1)
        _add_battlepass_xp(cur, service_id, player_id, 5)


def on_tower_win(service_id: str, player_id: str, *, floor: int = 0) -> None:
    init_db()
    with get_cursor() as cur:
        _bump_task(cur, service_id, player_id, "weekly_tower_5", 1)
        best = _tower_best_floor(cur, service_id, player_id)
        if floor > 0:
            best = max(best, int(floor))
        _set_achievement(cur, service_id, player_id, "ach_tower_10", best)
        _add_battlepass_xp(cur, service_id, player_id, 12)


def on_dungeon_run(service_id: str, player_id: str) -> None:
    init_db()
    with get_cursor() as cur:
        _bump_task(cur, service_id, player_id, "daily_dungeon_2", 1)
        _bump_task(cur, service_id, player_id, "weekly_dungeon_15", 1)
        _set_achievement(cur, service_id, player_id, "ach_dungeon_20", _count_settled_battles(cur, service_id, player_id, "dungeon"))


def on_enhance(service_id: str, player_id: str, *, count: int = 1) -> None:
    init_db()
    with get_cursor() as cur:
        _bump_task(cur, service_id, player_id, "daily_enhance_3", count)
