# -*- coding: utf-8 -*-
"""PVE stage battles: start / settle / chapter progress (AFK-style)."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.battle_antifraud import (
    anti_cheat_cfg,
    audit_battle_anomaly,
    compute_replay_hash,
    heroes_catalog,
    prior_stage_id,
    team_hero_ids,
    team_power,
    validate_team,
    verify_checksum,
    verify_duration,
    verify_replay_hash,
)
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.afk_config_loader import afk_formulas, hero_def_map
from services.baas.service_crud import feature_enabled, get_feature_config


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _stage_def(cfg: Dict[str, Any], stage_id: str) -> Dict[str, Any]:
    """Resolve a stage through its stable ID or the universal ``chapter-stage`` alias.

    AFK content uses IDs such as ``AFK_01_01`` while a lightweight BaaS client
    commonly uses ``1-1``.  Both identify the same configured row; battles are
    always persisted with the configured stable ID returned to the client.
    """
    sid = str(stage_id or "").strip()
    for row in cfg.get("stages") or []:
        if str(row.get("id") or "") == sid:
            return dict(row)
    if "-" in sid:
        try:
            chapter, stage = (int(part) for part in sid.split("-", 1))
        except ValueError:
            chapter = stage = 0
        if chapter > 0 and stage > 0:
            for row in cfg.get("stages") or []:
                if int(row.get("chapter") or 0) == chapter and int(row.get("stage") or 0) == stage:
                    return dict(row)
    raise ValueError("关卡不存在")


def _stamina_state(cur, service_id: str, player_id: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    row = cur.execute(
        "SELECT value_json FROM baas_player_data WHERE service_id=? AND player_id=? AND data_key=?",
        (service_id, player_id, "_pve_stamina"),
    ).fetchone()
    max_stamina = int(cfg.get("stamina_max") or 120)
    recover_sec = int(cfg.get("stamina_recover_seconds") or 360)
    payload = _json_load(row["value_json"] if row else "{}", {"current": max_stamina, "updated_at": _now_iso()})
    current = int(payload.get("current") or max_stamina)
    updated_at = str(payload.get("updated_at") or _now_iso())
    try:
        elapsed = (datetime.fromisoformat(_now_iso().replace("Z", "+00:00")) - datetime.fromisoformat(updated_at.replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        elapsed = 0
    if elapsed > 0 and recover_sec > 0:
        regen = int(elapsed // recover_sec)
        if regen > 0:
            current = min(max_stamina, current + regen)
            payload["updated_at"] = _now_iso()
    payload["current"] = current
    payload["max"] = max_stamina
    payload["recover_seconds"] = recover_sec
    return payload


def _save_stamina(cur, service_id: str, player_id: str, payload: Dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO baas_player_data (service_id, player_id, data_key, value_json, version, updated_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(service_id, player_id, data_key) DO UPDATE SET
            value_json=excluded.value_json, version=baas_player_data.version+1, updated_at=excluded.updated_at
        """,
        (service_id, player_id, "_pve_stamina", _json_dump(payload), 1, _now_iso()),
    )


def _stage_cleared(cur, service_id: str, player_id: str, stage_id: str) -> bool:
    if not stage_id:
        return True
    row = cur.execute(
        """
        SELECT cleared FROM baas_chapter_progress
        WHERE service_id=? AND player_id=? AND stage_id=?
        """,
        (service_id, player_id, stage_id),
    ).fetchone()
    return bool(row and int(row["cleared"] or 0))


def _player_hero_levels(cur, service_id: str, player_id: str) -> Dict[int, int]:
    rows = cur.execute(
        "SELECT hero_id, level FROM baas_player_heroes WHERE service_id=? AND player_id=?",
        (service_id, player_id),
    ).fetchall()
    out: Dict[int, int] = {}
    for row in rows:
        try:
            out[int(row["hero_id"])] = int(row["level"] or 1)
        except (TypeError, ValueError):
            continue
    return out


def get_stamina(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "pve"):
        raise ValueError("PVE 功能未启用")
    cfg = get_feature_config(service_id, "pve")
    init_db()
    with get_cursor() as cur:
        state = _stamina_state(cur, service_id, player_id, cfg)
        _save_stamina(cur, service_id, player_id, state)
    return {"stamina": state}


def get_progress(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "pve"):
        raise ValueError("PVE 功能未启用")
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT stage_id, stars, best_time_ms, cleared, updated_at
            FROM baas_chapter_progress WHERE service_id=? AND player_id=?
            ORDER BY stage_id
            """,
            (service_id, player_id),
        ).fetchall()
    stages = [dict(r) for r in rows]
    return {"stages": stages, "total_cleared": sum(1 for s in stages if int(s.get("cleared") or 0))}


def start_battle(
    service_id: str,
    player_id: str,
    stage_id: str,
    *,
    team: Optional[Dict[str, Any]] = None,
    display_name: str = "",
) -> Dict[str, Any]:
    if not feature_enabled(service_id, "pve"):
        raise ValueError("PVE 功能未启用")
    cfg = get_feature_config(service_id, "pve")
    stage = _stage_def(cfg, stage_id)
    # Persist and sign the configured canonical ID, never an arbitrary client alias.
    stage_id = str(stage.get("id") or stage_id)
    heroes = heroes_catalog(cfg)
    ok, msg = validate_team(team, heroes)
    if not ok:
        raise ValueError(msg)
    init_db()
    with get_cursor() as cur:
        hero_cfg = get_feature_config(service_id, "hero")
        team_ids = team_hero_ids(team)
        from services.baas.afk_power_service import stage_power_required, validate_growth_gate, team_power_unified

        power_info = team_power_unified(service_id, player_id, team_ids=team_ids, hero_cfg=hero_cfg)
        power = int(power_info.get("team_power") or 0)
        required = stage_power_required(stage_id, stage_row=stage, formulas=afk_formulas())
        if required > 0 and power < required:
            raise ValueError("战力不足，无法挑战该关卡")
        ok_gate, gate_msg = validate_growth_gate(service_id, player_id, stage_id, team_ids=team_ids)
        if not ok_gate:
            raise ValueError(gate_msg or "养成进度未达该关卡要求")
        prev = prior_stage_id(cfg, stage_id)
        if prev and not _stage_cleared(cur, service_id, player_id, prev):
            raise ValueError("请先通关前置关卡")
        cost = int(stage.get("stamina_cost") or 6)
        stamina = _stamina_state(cur, service_id, player_id, cfg)
        if int(stamina.get("current") or 0) < cost:
            raise ValueError("体力不足")
        stamina["current"] = int(stamina["current"]) - cost
        _save_stamina(cur, service_id, player_id, stamina)
        battle_id = new_id("pve_")
        seed = random.randint(1, 2_000_000_000)
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_battles (
                battle_id, service_id, player_id, battle_type, stage_id, defender_id,
                status, seed, team_json, result_json, started_at, settled_at, replay_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                battle_id,
                service_id,
                player_id,
                "pve",
                stage_id,
                "",
                "pending",
                seed,
                _json_dump(team or {}),
                "{}",
                now,
                "",
                "",
            ),
        )
    return {
        "battle_id": battle_id,
        "battle_type": "pve",
        "stage_id": stage_id,
        "seed": seed,
        "stage": stage,
        "team_power": power,
        "power_required": required,
        "stamina": stamina,
        "server_time": now,
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
    if not feature_enabled(service_id, "pve"):
        raise ValueError("PVE 功能未启用")
    cfg = get_feature_config(service_id, "pve")
    ac = anti_cheat_cfg(cfg)
    bid = str(battle_id or "").strip()
    if not bid:
        raise ValueError("battle_id 必填")
    stars = max(0, min(3, int(stars or 0)))
    if win and stars <= 0:
        stars = 1
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_battles WHERE battle_id=? AND service_id=? AND player_id=?",
            (bid, service_id, player_id),
        ).fetchone()
        if not row:
            raise ValueError("战斗不存在")
        if str(row["battle_type"] or "") != "pve":
            raise ValueError("战斗类型不匹配")
        if str(row["status"] or "") == "settled":
            return _json_load(row["result_json"], {})
        if str(row["status"] or "") != "pending":
            raise ValueError("战斗已结束或已过期")
        stage_id = str(row["stage_id"] or "")
        stage = _stage_def(cfg, stage_id)
        team = _json_load(row["team_json"], {})
        seed = int(row["seed"] or 0)
        expected_checksum = hashlib.sha256(f"{seed}:{stage_id}:{int(win)}:{stars}".encode()).hexdigest()[:16]
        expected_replay = compute_replay_hash(
            seed=seed,
            battle_type="pve",
            team=team,
            win=win,
            ticks=int(replay_ticks or 0),
        )
        try:
            verify_checksum(expected_checksum, checksum, required=ac["require_checksum"])
            verify_replay_hash(expected_replay, replay_hash, required=ac["require_replay_hash"])
            verify_duration(int(duration_ms or 0), ac)
        except ValueError as exc:
            audit_battle_anomaly(service_id, player_id, bid, str(exc), {"battle_type": "pve", "stage_id": stage_id})
            raise
        rewards = dict(stage.get("rewards") or {})
        if not win:
            rewards = {}
        now = _now_iso()
        result = {
            "battle_id": bid,
            "win": bool(win),
            "stars": stars if win else 0,
            "duration_ms": int(duration_ms or 0),
            "rewards": rewards,
            "stage_id": stage_id,
            "replay_hash": str(replay_hash or ""),
            "settled_at": now,
        }
        cur.execute(
            "UPDATE baas_battles SET status=?, result_json=?, settled_at=?, replay_hash=? WHERE battle_id=?",
            ("settled", _json_dump(result), now, str(replay_hash or ""), bid),
        )
        if win:
            prev = cur.execute(
                """
                SELECT stars, best_time_ms FROM baas_chapter_progress
                WHERE service_id=? AND player_id=? AND stage_id=?
                """,
                (service_id, player_id, stage_id),
            ).fetchone()
            best_stars = max(stars, int(prev["stars"] or 0) if prev else 0)
            best_time = int(duration_ms or 0)
            if prev and int(prev["best_time_ms"] or 0) > 0 and best_time > 0:
                best_time = min(int(prev["best_time_ms"]), best_time)
            cur.execute(
                """
                INSERT INTO baas_chapter_progress (service_id, player_id, stage_id, stars, best_time_ms, cleared, updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(service_id, player_id, stage_id) DO UPDATE SET
                    stars=excluded.stars, best_time_ms=excluded.best_time_ms,
                    cleared=1, updated_at=excluded.updated_at
                """,
                (service_id, player_id, stage_id, best_stars, best_time, 1, now),
            )
        if rewards:
            for currency, amount in rewards.items():
                _credit_wallet(cur, service_id, player_id, str(currency), int(amount or 0))
    if win:
        try:
            from services.baas.afk_retention_hooks import on_pve_win
            on_pve_win(service_id, player_id, stage_id=stage_id)
        except Exception:
            pass
    result["progress"] = get_progress(service_id, player_id)
    return result


def _credit_wallet(cur, service_id: str, player_id: str, currency_id: str, amount: int) -> None:
    from services.baas.retention_services import _wallet_row

    row = _wallet_row(cur, service_id, player_id, currency_id)
    balance = int(row["balance"] or 0) + int(amount) if row else int(amount)
    cur.execute(
        """
        INSERT INTO baas_wallets (service_id, player_id, currency_id, balance, updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(service_id, player_id, currency_id) DO UPDATE SET
            balance=excluded.balance, updated_at=excluded.updated_at
        """,
        (service_id, player_id, currency_id, balance, _now_iso()),
    )
