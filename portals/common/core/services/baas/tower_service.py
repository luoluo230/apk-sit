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


def _tower_cfg(cfg: Dict[str, Any], tower_id: str) -> Dict[str, Any]:
    tid = str(tower_id or "main").strip()
    for row in cfg.get("towers") or []:
        if str(row.get("id") or "") == tid:
            return dict(row)
    raise ValueError("塔不存在")


def _floor_def(tower: Dict[str, Any], floor: int) -> Dict[str, Any]:
    for row in tower.get("floors") or []:
        if int(row.get("floor") or 0) == int(floor):
            return dict(row)
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
    }


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
        result["progress"] = get_progress(service_id, player_id, tower_id)
        return result
