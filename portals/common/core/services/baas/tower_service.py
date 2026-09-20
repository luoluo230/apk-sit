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

    for row in tower.get("floors") or []:
        if int(row.get("floor") or 0) == int(floor):
            return dict(row)
    if tower.get("scaling") or tower.get("max_floor"):
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
        heroes = list((team.get("heroes") or []))
        if assist_hero_id > 0 and len(heroes) < 6:
            heroes.append(int(assist_hero_id))
            team["heroes"] = heroes
            team["assist_friend_id"] = aid
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
    power = team_power(team, heroes)
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
            (battle_id, service_id, player_id, "tower", stage_key, "", "pending", seed, _json_dump(team or {}), "{}", now, "", ""),
        )
    return {
        "battle_id": battle_id,
        "battle_type": "tower",
        "tower_id": tower_id,
        "floor": floor,
        "seed": seed,
        "team_power": power,
    }


def settle_battle(
    service_id: str,
    player_id: str,
    battle_id: str,
    *,
    win: bool,
    stars: int = 0,
    duration_ms: int = 0,
    checksum: str = "",
    replay_hash: str = "",
    replay_ticks: int = 0,
) -> Dict[str, Any]:
    if not feature_enabled(service_id, "tower"):
        raise ValueError("爬塔功能未启用")
    cfg = get_feature_config(service_id, "tower")
    pve = get_feature_config(service_id, "pve") if feature_enabled(service_id, "pve") else {}
    ac = anti_cheat_cfg(pve) if pve else {"require_checksum": False, "require_replay_hash": False, "min_duration_ms": 0, "max_duration_ms": 600000}
    bid = str(battle_id or "").strip()
    stars = max(0, min(3, int(stars or 0)))
    if win and stars <= 0:
        stars = 1
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_battles WHERE battle_id=? AND service_id=? AND player_id=?",
            (bid, service_id, player_id),
        ).fetchone()
        if not row or str(row["battle_type"] or "") != "tower":
            raise ValueError("战斗不存在")
        if str(row["status"] or "") == "settled":
            return _json_load(row["result_json"], {})
        stage_key = str(row["stage_id"] or "")
        parts = stage_key.split(":", 1)
        tower_id = parts[0] if parts else "main"
        floor = int(parts[1]) if len(parts) > 1 else 1
        tower = _tower_cfg(cfg, tower_id)
        floor_def = _floor_def(tower, floor)
        team = _json_load(row["team_json"], {})
        seed = int(row["seed"] or 0)
        expected_checksum = hashlib.sha256(f"{seed}:{stage_key}:{int(win)}:{stars}".encode()).hexdigest()[:16]
        expected_replay = compute_replay_hash(seed=seed, battle_type="tower", team=team, win=win, ticks=int(replay_ticks or 0))
        try:
            verify_checksum(expected_checksum, checksum, required=ac["require_checksum"])
            verify_replay_hash(expected_replay, replay_hash, required=ac["require_replay_hash"])
            verify_duration(int(duration_ms or 0), ac)
        except ValueError as exc:
            audit_battle_anomaly(service_id, player_id, bid, str(exc), {"battle_type": "tower", "floor": floor})
            raise
        rewards = dict(floor_def.get("rewards") or {}) if win else {}
        now = _now_iso()
        result = {"battle_id": bid, "win": bool(win), "stars": stars, "rewards": rewards, "tower_id": tower_id, "floor": floor, "settled_at": now}
        cur.execute(
            "UPDATE baas_battles SET status=?, result_json=?, settled_at=?, replay_hash=? WHERE battle_id=?",
            ("settled", _json_dump(result), now, str(replay_hash or ""), bid),
        )
        if win:
            cur.execute(
                """
                INSERT INTO baas_tower_progress (service_id, player_id, tower_id, floor, best_stars, updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(service_id, player_id, tower_id) DO UPDATE SET
                    floor=excluded.floor, best_stars=excluded.best_stars, updated_at=excluded.updated_at
                """,
                (service_id, player_id, tower_id, floor, stars, now),
            )
            for currency, amount in rewards.items():
                credit_wallet(cur, service_id, player_id, str(currency), int(amount or 0))
            from services.baas import retention_services

            # Ranking is an optional retention capability. Tower progression and rewards
        # must remain usable when a lightweight deployment deliberately omits it.
        if feature_enabled(service_id, "leaderboard"):
            retention_services.submit_score(service_id, player_id, f"tower_{tower_id}", float(floor))
        result["progress"] = get_progress(service_id, player_id, tower_id)
        result["boss_type"] = floor_def.get("boss_type") or "normal"
        settled_floor = floor
    if win:
        try:
            from services.baas.afk_retention_hooks import on_tower_win
            on_tower_win(service_id, player_id, floor=settled_floor)
        except Exception:
            pass
    return result
