# -*- coding: utf-8 -*-
"""爬塔 / 副本变体：独立进度表，战斗流程复用 PVE 反作弊。"""

from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.battle_antifraud import (
    anti_cheat_cfg,
    audit_battle_anomaly,
    compute_replay_hash,
    heroes_catalog,
    team_power,
    validate_team,
    verify_checksum,
    verify_duration,
    verify_replay_hash,
)
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.afk_power_service import team_power_unified
from services.baas.pve_service import _authoritative_outcome
from services.baas.wallet_helpers import credit_wallet
from services.baas.afk_tower_scaling import max_floor as tower_max_floor, daily_passive_rewards


def _tower_cfg(cfg: Dict[str, Any], tower_id: str) -> Dict[str, Any]:
    tid = str(tower_id or "main").strip()
    for row in cfg.get("towers") or []:
        if str(row.get("id") or "") == tid:
            return dict(row)
    raise ValueError("塔不存在")


def _floor_def(tower: Dict[str, Any], floor: int) -> Dict[str, Any]:
    from services.baas.afk_tower_scaling import floor_def as scaled_floor

    if tower.get("scaling") or int(tower.get("max_floor") or 0) >= 999:
        return scaled_floor(tower, floor)
    for row in tower.get("floors") or []:
        if int(row.get("floor") or 0) == int(floor):
            return dict(row)
    if tower.get("max_floor"):
        return scaled_floor(tower, floor)
    raise ValueError("层数不存在")


def get_progress(service_id: str, player_id: str, tower_id: str = "main") -> Dict[str, Any]:
    if not feature_enabled(service_id, "tower"):
        raise ValueError("爬塔功能未启用")
    tid = str(tower_id or "main").strip()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT floor, best_stars, updated_at FROM baas_tower_progress WHERE service_id=? AND player_id=? AND tower_id=?",
            (service_id, player_id, tid),
        ).fetchone()
    return {
        "tower_id": tid,
        "current_floor": int(row["floor"] or 0) if row else 0,
        "best_stars": int(row["best_stars"] or 0) if row else 0,
        "next_floor": (int(row["floor"] or 0) + 1) if row else 1,
        "max_floor": tower_max_floor(_tower_cfg(get_feature_config(service_id, "tower"), tid)),
    }


def claim_daily_rewards(service_id: str, player_id: str, tower_id: str = "main") -> Dict[str, Any]:
    if not feature_enabled(service_id, "tower"):
        raise ValueError("爬塔功能未启用")
    cfg = get_feature_config(service_id, "tower")
    tower = _tower_cfg(cfg, tower_id)
    progress = get_progress(service_id, player_id, tower_id)
    best = int(progress.get("current_floor") or 0)
    if best < 1:
        raise ValueError("尚未通关任何层")
    from services.baas.afk_tower_scaling import daily_passive_rewards as _daily_passive

    rewards = _daily_passive(best, tower)
    if not rewards:
        raise ValueError("无可领奖励")
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS baas_tower_daily_claim (
                service_id TEXT NOT NULL, player_id TEXT NOT NULL, tower_id TEXT NOT NULL,
                claim_date TEXT NOT NULL, claimed_at TEXT NOT NULL,
                PRIMARY KEY (service_id, player_id, tower_id, claim_date)
            )
            """
        )
        today = _now_iso()[:10]
        if cur.execute(
            "SELECT 1 FROM baas_tower_daily_claim WHERE service_id=? AND player_id=? AND tower_id=? AND claim_date=?",
            (service_id, player_id, tower_id, today),
        ).fetchone():
            raise ValueError("今日已领取")
        for currency, amount in rewards.items():
            credit_wallet(cur, service_id, player_id, str(currency), int(amount or 0))
        now = _now_iso()
        cur.execute(
            "INSERT INTO baas_tower_daily_claim (service_id, player_id, tower_id, claim_date, claimed_at) VALUES (?,?,?,?,?)",
            (service_id, player_id, tower_id, today, now),
        )
    return {"rewards": rewards, "best_floor": best}


def _owned_team_power(service_id: str, player_id: str, team: Optional[Dict[str, Any]]) -> int:
    requested = [int(x) for x in (team or {}).get("heroes") or []]
    info = team_power_unified(service_id, player_id, team_ids=requested, hero_cfg=get_feature_config(service_id, "hero"))
    if len(info.get("heroes") or []) != len(requested):
        raise ValueError("阵容包含未拥有英雄")
    return max(0, int(info.get("team_power") or 0))


def _validated_assist_power(service_id: str, player_id: str, team: Optional[Dict[str, Any]]) -> int:
    assist = dict((team or {}).get("assist") or {})
    friend_id = str(assist.get("friend_player_id") or "").strip()
    try:
        hero_id = int(assist.get("hero_id") or 0)
    except (TypeError, ValueError):
        hero_id = 0
    if not friend_id or hero_id <= 0:
        return 0
    from services.baas import afk_friend_service
    friends = {f["friend_player_id"] for f in afk_friend_service.list_friends(service_id, player_id)}
    if friend_id not in friends:
        raise ValueError("不是好友")
    info = team_power_unified(service_id, friend_id, team_ids=[hero_id], hero_cfg=get_feature_config(service_id, "hero"))
    if info.get("heroes") != [hero_id]:
        raise ValueError("助战英雄不可用")
    return max(0, int(info.get("team_power") or 0))


def start_battle_with_assist(
    service_id: str,
    player_id: str,
    tower_id: str,
    floor: int,
    *,
    team: Optional[Dict[str, Any]] = None,
    assist_friend_id: str = "",
    assist_hero_id: int = 0,
) -> Dict[str, Any]:
    """每日可邀请一位好友的一名英雄助战，仅助战一层。"""
    aid = str(assist_friend_id or "").strip()
    if aid:
        init_db()
        with get_cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS baas_tower_assist_log (
                    service_id TEXT NOT NULL, player_id TEXT NOT NULL, assist_date TEXT NOT NULL,
                    friend_id TEXT NOT NULL, floor INTEGER NOT NULL, used_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id, assist_date)
                )
                """
            )
            today = _now_iso()[:10]
            if cur.execute(
                "SELECT 1 FROM baas_tower_assist_log WHERE service_id=? AND player_id=? AND assist_date=?",
                (service_id, player_id, today),
            ).fetchone():
                raise ValueError("今日已使用好友助战")
            from services.baas import afk_friend_service

            friends = {f["friend_player_id"] for f in afk_friend_service.list_friends(service_id, player_id)}
            if aid not in friends:
                raise ValueError("不是好友")
        team = dict(team or {})
        if assist_hero_id <= 0:
            raise ValueError("助战英雄无效")
        # Keep friend identity separate from the player formation. start_battle
        # validates both ownership domains and freezes the resulting bonus.
        team["assist"] = {"friend_player_id": aid, "hero_id": int(assist_hero_id)}
    result = start_battle(service_id, player_id, tower_id, floor, team=team)
    if aid:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO baas_tower_assist_log (service_id, player_id, assist_date, friend_id, floor, used_at) VALUES (?,?,?,?,?,?)",
                (service_id, player_id, _now_iso()[:10], aid, int(floor), _now_iso()),
            )
    result["assist_used"] = bool(aid)
    return result


def start_battle(
    service_id: str,
    player_id: str,
    tower_id: str,
    floor: int,
    *,
    team: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not feature_enabled(service_id, "tower"):
        raise ValueError("爬塔功能未启用")
    cfg = get_feature_config(service_id, "tower")
    pve = get_feature_config(service_id, "pve") if feature_enabled(service_id, "pve") else {}
    heroes = heroes_catalog(pve) if pve else {}
    tower = _tower_cfg(cfg, tower_id)
    floor_def = _floor_def(tower, floor)
    progress = get_progress(service_id, player_id, tower_id)
    if int(floor) != int(progress.get("next_floor") or 1):
        raise ValueError("只能挑战下一层")
    ok, msg = validate_team(team, heroes)
    if not ok:
        raise ValueError(msg)
    player_power = _owned_team_power(service_id, player_id, team)
    assist_power = _validated_assist_power(service_id, player_id, team)
    power = player_power + assist_power
    required = int(floor_def.get("power_required") or 0)
    if required > 0 and power < required:
        raise ValueError("战力不足")
    init_db()
    with get_cursor() as cur:
        battle_id = new_id("tower_")
        seed = random.randint(1, 2_000_000_000)
        now = _now_iso()
        stage_key = f"{tower_id}:{floor}"
        cur.execute(
            """
            INSERT INTO baas_battles (
                battle_id, service_id, player_id, battle_type, stage_id, defender_id,
                status, seed, team_json, result_json, started_at, settled_at, replay_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (battle_id, service_id, player_id, "tower", stage_key, "", "pending", seed, _json_dump(team or {}), _json_dump({"authority": _authoritative_outcome(seed, power, required)}), now, "", ""),
        )
    return {
        "battle_id": battle_id,
        "battle_type": "tower",
        "tower_id": tower_id,
        "floor": floor,
        "seed": seed,
        "team_power": power,
        "assist_power": assist_power,
    }


def settle_battle(
    service_id: str,
    player_id: str,
    battle_id: str,
    *,
    win: bool = False,
    stars: int = 0,
    duration_ms: int = 0,
    checksum: str = "",
    replay_hash: str = "",
    replay_ticks: int = 0,
) -> Dict[str, Any]:
    """Settle a tower floor from its server-frozen authority plan."""
    if not feature_enabled(service_id, "tower"):
        raise ValueError("爬塔功能未启用")
    cfg = get_feature_config(service_id, "tower")
    bid = str(battle_id or "").strip()
    init_db()
    with get_cursor() as cur:
        row = cur.execute("SELECT * FROM baas_battles WHERE battle_id=? AND service_id=? AND player_id=?", (bid, service_id, player_id)).fetchone()
        if not row or str(row["battle_type"] or "") != "tower":
            raise ValueError("战斗不存在")
        if str(row["status"] or "") == "settled":
            return _json_load(row["result_json"], {})
        if str(row["status"] or "") != "pending":
            raise ValueError("战斗已结束或已过期")
        stage_key = str(row["stage_id"] or "")
        parts = stage_key.split(":", 1)
        tower_id = parts[0] if parts else "main"
        floor = int(parts[1]) if len(parts) > 1 else 1
        tower = _tower_cfg(cfg, tower_id)
        floor_def = _floor_def(tower, floor)
        plan = dict((_json_load(row["result_json"], {}) or {}).get("authority") or {})
        if not plan:
            # Do not retrofit old pending rows from mutable hero data. A tower
            # outcome without a start-time plan is expired and retried.
            cur.execute("UPDATE baas_battles SET status=? WHERE battle_id=?", ("expired", bid))
            cur.connection.commit()
            raise ValueError("战斗版本已更新，请重新发起挑战")
        server_win = bool(plan.get("win"))
        server_stars = int(plan.get("stars") or 0) if server_win else 0
        rewards = dict(floor_def.get("rewards") or {}) if server_win else {}
        now = _now_iso()
        result = {"battle_id": bid, "win": server_win, "stars": server_stars, "rewards": rewards, "tower_id": tower_id, "floor": floor, "authority": {"team_power": int(plan.get("team_power") or 0), "power_required": int(plan.get("power_required") or 0)}, "client_report": {"win": bool(win), "stars": int(stars or 0), "duration_ms": int(duration_ms or 0), "ticks": int(replay_ticks or 0)}, "settled_at": now}
        cur.execute("UPDATE baas_battles SET status=?, result_json=?, settled_at=?, replay_hash=? WHERE battle_id=?", ("settled", _json_dump(result), now, str(replay_hash or ""), bid))
        if server_win:
            cur.execute("""INSERT INTO baas_tower_progress (service_id, player_id, tower_id, floor, best_stars, updated_at)
                           VALUES (?,?,?,?,?,?) ON CONFLICT(service_id, player_id, tower_id) DO UPDATE SET
                           floor=excluded.floor, best_stars=excluded.best_stars, updated_at=excluded.updated_at""", (service_id, player_id, tower_id, floor, server_stars, now))
            for currency, amount in rewards.items():
                credit_wallet(cur, service_id, player_id, str(currency), int(amount or 0))
            if feature_enabled(service_id, "leaderboard"):
                from services.baas import retention_services
                retention_services.submit_score(service_id, player_id, f"tower_{tower_id}", float(floor))
        result["progress"] = get_progress(service_id, player_id, tower_id)
        result["boss_type"] = floor_def.get("boss_type") or "normal"
        settled_floor = floor
    if server_win:
        try:
            from services.baas.afk_retention_hooks import on_tower_win
            on_tower_win(service_id, player_id, floor=settled_floor)
        except Exception:
            pass
    return result

