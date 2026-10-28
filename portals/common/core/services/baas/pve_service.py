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
from services.baas.afk.afk_config_loader import afk_formulas, hero_def_map
from services.baas.service_crud import feature_enabled, get_feature_config


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _bundle_stage_row(stage_id: str) -> Dict[str, Any]:
    """关卡金币、体力和推荐战力以共享 bundle 为准，避免库里的旧快照把产出留在改表之前。"""
    from services.baas.afk.afk_config_loader import bundle_generation, load_afk_bundle

    generation = bundle_generation()
    table = getattr(_bundle_stage_row, "_table", None)
    if table is None or getattr(_bundle_stage_row, "_generation", None) != generation:
        bundle = load_afk_bundle() or {}
        rows = ((bundle.get("pve") or {}).get("stages")) or []
        table = {str(row.get("id") or ""): row for row in rows if row.get("id")}
        _bundle_stage_row._table = table
        _bundle_stage_row._generation = generation
    return dict(table.get(str(stage_id or "")) or {})


def _overlay_bundle_stage(row: Dict[str, Any]) -> Dict[str, Any]:
    fresh = _bundle_stage_row(str(row.get("id") or ""))
    if not fresh:
        return row
    merged = dict(row)
    rewards = fresh.get("rewards")
    if isinstance(rewards, dict):
        merged["rewards"] = dict(rewards)
    for key in ("reward_gold", "reward_exp", "power_required", "recommended_power", "stamina_cost"):
        if key in fresh:
            merged[key] = fresh[key]
    return merged


def _stage_def(cfg: Dict[str, Any], stage_id: str) -> Dict[str, Any]:
    """Resolve a stage through its stable ID or the universal ``chapter-stage`` alias.

    AFK content uses IDs such as ``AFK_01_01`` while a lightweight BaaS client
    commonly uses ``1-1``.  Both identify the same configured row; battles are
    always persisted with the configured stable ID returned to the client.
    """
    sid = str(stage_id or "").strip()
    for row in cfg.get("stages") or []:
        if str(row.get("id") or "") == sid:
            return _overlay_bundle_stage(dict(row))
    if "-" in sid:
        try:
            chapter, stage = (int(part) for part in sid.split("-", 1))
        except ValueError:
            chapter = stage = 0
        if chapter > 0 and stage > 0:
            for row in cfg.get("stages") or []:
                if int(row.get("chapter") or 0) == chapter and int(row.get("stage") or 0) == stage:
                    return _overlay_bundle_stage(dict(row))
    raise ValueError("关卡不存在")


def _vip_stamina_bonus(cur, service_id: str, player_id: str) -> int:
    try:
        row = cur.execute(
            "SELECT vip_level FROM baas_vip_progress WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
    except Exception:
        return 0
    level = int(row["vip_level"] or 0) if row else 0
    if level < 1:
        return 0
    from services.baas.afk.afk_vip_service import _privileges, _vip_cfg

    try:
        return max(0, int(_privileges(_vip_cfg(), level).get("stamina_bonus") or 0))
    except (TypeError, ValueError):
        return 0


def _group_stamina_add(service_id: str, player_id: str) -> int:
    try:
        from services.baas.afk.afk_config_group import group_factors

        return max(0, int(group_factors(service_id, player_id).get("stamina_max_add") or 0))
    except Exception:
        return 0


def _stamina_state(cur, service_id: str, player_id: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    row = cur.execute(
        "SELECT value_json FROM baas_player_data WHERE service_id=? AND player_id=? AND data_key=?",
        (service_id, player_id, "_pve_stamina"),
    ).fetchone()
    max_stamina = int(cfg.get("stamina_max") or 120)
    max_stamina += _vip_stamina_bonus(cur, service_id, player_id)
    max_stamina += _group_stamina_add(service_id, player_id)
    recover_sec = int(cfg.get("stamina_recover_seconds") or 360)
    payload = _json_load(row["value_json"] if row else "{}", {"current": max_stamina, "updated_at": _now_iso()})
    current = max(0, min(max_stamina, int(payload.get("current", max_stamina))))
    updated_at = str(payload.get("updated_at") or _now_iso())
    try:
        elapsed = (datetime.fromisoformat(_now_iso().replace("Z", "+00:00")) - datetime.fromisoformat(updated_at.replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        elapsed = 0
    if elapsed < 0 or current >= max_stamina:
        payload["updated_at"] = _now_iso()
    if elapsed > 0 and recover_sec > 0 and current < max_stamina:
        regen = int(elapsed // recover_sec)
        if regen > 0:
            current = min(max_stamina, current + regen)
            from datetime import timedelta
            anchor = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            payload["updated_at"] = _now_iso() if current >= max_stamina else (anchor + timedelta(seconds=regen * recover_sec)).isoformat()
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
        from services.baas.afk.afk_power_service import stage_power_required, team_power_unified

        power_info = team_power_unified(service_id, player_id, team_ids=team_ids, hero_cfg=hero_cfg)
        power = int(power_info.get("team_power") or 0)
        required = stage_power_required(stage_id, stage_row=stage, formulas=afk_formulas())
        from services.baas.afk.afk_config_group import scale_int

        required = scale_int(service_id, player_id, "stage_power_mul", required)
        if required > 0 and power < required:
            raise ValueError(f"战力不足，无法挑战该关卡（推荐战力 {required}）")
        prev = prior_stage_id(cfg, stage_id)
        if prev and not _stage_cleared(cur, service_id, player_id, prev):
            raise ValueError("请先通关前置关卡")
        cost = int(stage.get("stamina_cost") or 6)
        from services.baas.afk.afk_power_service import stage_index
        if stage_index(str(stage.get("id") or stage_id)) <= 30:
            cost = min(cost, 3)
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
                _json_dump({"authority": _authoritative_outcome(seed, power, required)}),
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


def _authoritative_outcome(seed: int, team_power_value: int, power_required: int) -> Dict[str, int | bool]:
    """胜负只看开战时冻结的战力，和关卡推荐战力比。

    队伍战力大于等于推荐战力就赢，低于就输。种子不再改胜负，避免低战力打赢、高战力打不过。
    """
    required = max(1, int(power_required or 1))
    power = max(0, int(team_power_value or 0))
    win = power >= required
    ratio = power / float(required)
    stars = 0 if not win else 3 if ratio >= 1.35 else 2 if ratio >= 1.15 else 1
    duration_ms = 8500 + (int(seed or 0) % 3500)
    return {"win": bool(win), "stars": int(stars), "duration_ms": int(duration_ms), "team_power": power, "power_required": required}


def _grant_team_exp(cur, service_id: str, player_id: str, team: Dict[str, Any], amount: int, hero_cfg: Dict[str, Any]) -> List[Dict[str, int]]:
    """Applies configured PVE experience to the frozen, server-owned formation."""
    award = max(0, int(amount or 0))
    if award <= 0:
        return []
    cap = max(1, int(hero_cfg.get("max_level") or 100))
    updates: List[Dict[str, int]] = []
    for hero_id in team_hero_ids(team):
        row = cur.execute(
            "SELECT level, exp FROM baas_player_heroes WHERE service_id=? AND player_id=? AND hero_id=?",
            (service_id, player_id, hero_id),
        ).fetchone()
        if not row:
            continue
        level = max(1, int(row["level"] or 1))
        exp = max(0, int(row["exp"] or 0)) + award
        while level < cap and exp >= level * 100:
            exp -= level * 100
            level += 1
        if level >= cap:
            exp = min(exp, max(0, cap * 100 - 1))
        cur.execute(
            "UPDATE baas_player_heroes SET level=?, exp=?, updated_at=? WHERE service_id=? AND player_id=? AND hero_id=?",
            (level, exp, _now_iso(), service_id, player_id, hero_id),
        )
        updates.append({"hero_id": int(hero_id), "level": level, "exp": exp})
    return updates


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
    """Settle a PVE battle from the authority plan stored at start.

    Legacy client result fields remain accepted for wire compatibility and audit,
    but none participates in reward/progression decisions.
    """
    if not feature_enabled(service_id, "pve"):
        raise ValueError("PVE 功能未启用")
    cfg = get_feature_config(service_id, "pve")
    bid = str(battle_id or "").strip()
    if not bid:
        raise ValueError("battle_id 必填")
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
        plan_doc = _json_load(row["result_json"], {})
        authority = dict(plan_doc.get("authority") or {})
        if not authority:
            # A pre-authority pending row has no immutable result inputs.
            # Recomputing from the player's current roster would make an old
            # client report control a new economic decision. Expire it safely
            # and make the client create a fully frozen replacement battle.
            cur.execute("UPDATE baas_battles SET status=? WHERE battle_id=?", ("expired", bid))
            # get_cursor rolls back on an escaping exception. Persist the
            # one-way invalidation before returning the retry error.
            cur.connection.commit()
            raise ValueError("战斗版本已更新，请重新发起挑战")
        consumed = cur.execute("""UPDATE baas_battles SET status='settling'
            WHERE battle_id=? AND service_id=? AND player_id=? AND status='pending' RETURNING battle_id""",
            (bid, service_id, player_id)).fetchone()
        if consumed is None:
            latest = cur.execute("SELECT status,result_json FROM baas_battles WHERE battle_id=? AND service_id=? AND player_id=?", (bid, service_id, player_id)).fetchone()
            if latest and latest["status"] == "settled": return _json_load(latest["result_json"], {})
            raise ValueError("战斗结算处理中，请稍后重试")
        server_win = bool(authority.get("win"))
        server_stars = max(0, min(3, int(authority.get("stars") or 0))) if server_win else 0
        rewards = dict(stage.get("rewards") or {}) if server_win else {}
        if server_win:
            from services.baas.afk.afk_config_group import scale_rewards

            rewards = scale_rewards(service_id, player_id, "stage_reward_mul", rewards)
        exp_gain = int(rewards.pop("exp", 0) or 0) if server_win else 0
        hero_cfg = get_feature_config(service_id, "hero")
        hero_updates = _grant_team_exp(cur, service_id, player_id, team, exp_gain, hero_cfg) if server_win else []
        from services.baas.afk.afk_home_service import grant_account_exp, ensure_idle_started
        account = grant_account_exp(cur, service_id, player_id, exp_gain) if server_win else None
        if server_win: ensure_idle_started(cur, service_id, player_id)
        now = _now_iso()
        result = {
            "battle_id": bid,
            "win": server_win,
            "stars": server_stars,
            "duration_ms": int(authority.get("duration_ms") or 0),
            "rewards": rewards,
            "experience": exp_gain,
            "account": account,
            "hero_updates": hero_updates,
            "stage_id": stage_id,
            "authority": {"team_power": int(authority.get("team_power") or 0), "power_required": int(authority.get("power_required") or 0)},
            "client_report": {"win": bool(win), "stars": int(stars or 0), "duration_ms": int(duration_ms or 0), "ticks": int(replay_ticks or 0)},
            "settled_at": now,
        }
        cur.execute(
            "UPDATE baas_battles SET status=?, result_json=?, settled_at=?, replay_hash=? WHERE battle_id=?",
            ("settled", _json_dump(result), now, str(replay_hash or ""), bid),
        )
        if server_win:
            prev = cur.execute(
                "SELECT stars, best_time_ms FROM baas_chapter_progress WHERE service_id=? AND player_id=? AND stage_id=?",
                (service_id, player_id, stage_id),
            ).fetchone()
            best_stars = max(server_stars, int(prev["stars"] or 0) if prev else 0)
            best_time = int(authority.get("duration_ms") or 0)
            if prev and int(prev["best_time_ms"] or 0) > 0:
                best_time = min(int(prev["best_time_ms"]), best_time)
            cur.execute(
                """INSERT INTO baas_chapter_progress (service_id, player_id, stage_id, stars, best_time_ms, cleared, updated_at)
                   VALUES (?,?,?,?,?,?,?) ON CONFLICT(service_id, player_id, stage_id) DO UPDATE SET
                   stars=excluded.stars, best_time_ms=excluded.best_time_ms, cleared=1, updated_at=excluded.updated_at""",
                (service_id, player_id, stage_id, best_stars, best_time, 1, now),
            )
        for currency, amount in rewards.items():
            _credit_wallet(cur, service_id, player_id, str(currency), int(amount or 0))
    if server_win:
        try:
            from services.baas.afk.afk_retention_hooks import on_pve_win
            on_pve_win(service_id, player_id, stage_id=stage_id)
        except Exception:
            pass
    result["progress"] = get_progress(service_id, player_id)
    return result

def _credit_wallet(cur, service_id: str, player_id: str, currency_id: str, amount: int) -> None:
    from services.baas.wallet_helpers import credit_wallet
    credit_wallet(cur, service_id, player_id, currency_id, amount)
