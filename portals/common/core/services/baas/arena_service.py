# -*- coding: utf-8 -*-
"""Async arena: fight other players' defense snapshots (AFK-style PVP)."""

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
    verify_power_delta,
    verify_replay_hash,
)
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.pve_service import _utc_today, _authoritative_outcome
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.afk_power_service import team_power_unified


def _arena_cfg(service_id: str) -> Dict[str, Any]:
    return get_feature_config(service_id, "arena")


def _pve_cfg(service_id: str) -> Dict[str, Any]:
    return get_feature_config(service_id, "pve")


def _heroes_for_service(service_id: str) -> Dict[int, Dict[str, Any]]:
    return heroes_catalog(_pve_cfg(service_id))


def _derived_power(defense: Optional[Dict[str, Any]], service_id: str) -> int:
    heroes = _heroes_for_service(service_id)
    power = team_power(defense, heroes)
    if power <= 0 and isinstance(defense, dict):
        try:
            power = int(defense.get("power") or 0)
        except (TypeError, ValueError):
            power = 0
    return max(0, power)


def _owned_team_power(service_id: str, player_id: str, team: Optional[Dict[str, Any]]) -> int:
    requested = [int(x) for x in (team or {}).get("heroes") or []]
    info = team_power_unified(service_id, player_id, team_ids=requested, hero_cfg=get_feature_config(service_id, "hero"))
    if len(info.get("heroes") or []) != len(requested):
        raise ValueError("阵容包含未拥有英雄")
    return max(0, int(info.get("team_power") or 0))


def _rating_row(cur, service_id: str, player_id: str) -> Dict[str, Any]:
    row = cur.execute(
        "SELECT * FROM baas_arena_ratings WHERE service_id=? AND player_id=?",
        (service_id, player_id),
    ).fetchone()
    if row:
        data = dict(row)
    else:
        data = {
            "service_id": service_id,
            "player_id": player_id,
            "rating": 1000,
            "wins": 0,
            "losses": 0,
            "daily_attempts_used": 0,
            "daily_reset_date": _utc_today(),
        }
    if str(data.get("daily_reset_date") or "") != _utc_today():
        data["daily_attempts_used"] = 0
        data["daily_reset_date"] = _utc_today()
    return data


def _save_rating(cur, service_id: str, player_id: str, data: Dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO baas_arena_ratings (
            service_id, player_id, rating, wins, losses, daily_attempts_used, daily_reset_date, updated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(service_id, player_id) DO UPDATE SET
            rating=excluded.rating, wins=excluded.wins, losses=excluded.losses,
            daily_attempts_used=excluded.daily_attempts_used,
            daily_reset_date=excluded.daily_reset_date, updated_at=excluded.updated_at
        """,
        (
            service_id,
            player_id,
            int(data.get("rating") or 1000),
            int(data.get("wins") or 0),
            int(data.get("losses") or 0),
            int(data.get("daily_attempts_used") or 0),
            str(data.get("daily_reset_date") or _utc_today()),
            _now_iso(),
        ),
    )


def get_state(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "arena"):
        raise ValueError("竞技场功能未启用")
    cfg = _arena_cfg(service_id)
    init_db()
    with get_cursor() as cur:
        rating = _rating_row(cur, service_id, player_id)
        _save_rating(cur, service_id, player_id, rating)
        snap = cur.execute(
            """
            SELECT payload_json, power, display_name, updated_at FROM baas_player_snapshots
            WHERE service_id=? AND player_id=? AND snapshot_type=?
            """,
            (service_id, player_id, "defense"),
        ).fetchone()
    return {
        "rating": int(rating.get("rating") or 1000),
        "wins": int(rating.get("wins") or 0),
        "losses": int(rating.get("losses") or 0),
        "daily_attempts_used": int(rating.get("daily_attempts_used") or 0),
        "daily_attempts_max": int(cfg.get("daily_attempts") or 5),
        "season_id": str(cfg.get("season_id") or "arena_s1"),
        "season_name": str(cfg.get("season_name") or ""),
        "has_defense": bool(snap),
        "defense_power": int(snap["power"] or 0) if snap else 0,
    }


def update_defense(
    service_id: str,
    player_id: str,
    *,
    defense: Dict[str, Any],
    power: int = 0,
    display_name: str = "",
) -> Dict[str, Any]:
    if not feature_enabled(service_id, "arena"):
        raise ValueError("竞技场功能未启用")
    heroes = _heroes_for_service(service_id)
    ok, msg = validate_team(defense, heroes)
    if not ok:
        raise ValueError(msg)
    derived = _owned_team_power(service_id, player_id, defense)
    if derived <= 0:
        raise ValueError("防守阵容战力无效")
    if int(power or 0) > 0 and derived > 0:
        gap = abs(int(power) - derived) / float(derived)
        ac = anti_cheat_cfg(_pve_cfg(service_id))
        if gap > float(ac.get("max_power_delta_ratio") or 0.35) + 1e-6:
            # A client-provided display value is never authoritative.  Keep the
            # snapshot usable at the server-derived value and record the anomaly
            # for review instead of allowing a forged value to control matchmaking.
            audit_battle_anomaly(
                service_id,
                player_id,
                "",
                "defense_power_mismatch",
                {"client_power": int(power), "server_power": derived},
            )
    final_power = derived
    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_player_snapshots (
                service_id, player_id, snapshot_type, payload_json, power, display_name, updated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, snapshot_type) DO UPDATE SET
                payload_json=excluded.payload_json, power=excluded.power,
                display_name=excluded.display_name, updated_at=excluded.updated_at
            """,
            (service_id, player_id, "defense", _json_dump(defense or {}), final_power, display_name or player_id, now),
        )
    return {"ok": True, "updated_at": now, "power": final_power}


def list_opponents(service_id: str, player_id: str, *, count: int = 3) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "arena"):
        raise ValueError("竞技场功能未启用")
    cfg = _arena_cfg(service_id)
    limit = min(max(1, int(count or cfg.get("opponent_count") or 3)), 10)
    init_db()
    with get_cursor() as cur:
        rating = _rating_row(cur, service_id, player_id)
        base = int(rating.get("rating") or 1000)
        rows = cur.execute(
            """
            SELECT r.player_id, r.rating, s.display_name, s.power, s.payload_json, s.updated_at
            FROM baas_arena_ratings r
            INNER JOIN baas_player_snapshots s
              ON s.service_id=r.service_id AND s.player_id=r.player_id AND s.snapshot_type='defense'
            WHERE r.service_id=? AND r.player_id<>?
              AND r.rating BETWEEN ? AND ?
            ORDER BY ABS(r.rating - ?) ASC, RANDOM() LIMIT ?
            """,
            (service_id, player_id, base - 250, base + 250, base, limit),
        ).fetchall()
        if len(rows) < limit:
            extra = cur.execute(
                """
                SELECT r.player_id, r.rating, s.display_name, s.power, s.payload_json, s.updated_at
                FROM baas_arena_ratings r
                INNER JOIN baas_player_snapshots s
                  ON s.service_id=r.service_id AND s.player_id=r.player_id AND s.snapshot_type='defense'
                WHERE r.service_id=? AND r.player_id<>?
                ORDER BY RANDOM() LIMIT ?
                """,
                (service_id, player_id, limit),
            ).fetchall()
            seen = {r["player_id"] for r in rows}
            for row in extra:
                if row["player_id"] not in seen:
                    rows.append(row)
                    seen.add(row["player_id"])
                if len(rows) >= limit:
                    break
    out = []
    for row in rows:
        out.append({
            "player_id": row["player_id"],
            "display_name": row["display_name"] or row["player_id"],
            "rating": int(row["rating"] or 1000),
            "power": int(row["power"] or 0),
            "defense_preview": _json_load(row["payload_json"], {}),
        })
    if not out:
        for i in range(1, limit + 1):
            bot_id = f"arena_bot_{i}"
            bot = get_defense(service_id, bot_id)
            out.append({
                "player_id": bot_id,
                "display_name": bot.get("display_name") or bot_id,
                "rating": int(bot.get("rating") or 1000),
                "power": int(bot.get("power") or 800),
                "defense_preview": bot.get("defense") or {},
            })
    return out


def get_defense(service_id: str, target_player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "arena"):
        raise ValueError("竞技场功能未启用")
    tid = str(target_player_id or "").strip()
    if not tid:
        raise ValueError("player_id 必填")
    if tid.startswith("arena_bot_"):
        suffix = tid.rsplit("_", 1)[-1]
        idx = int(suffix) if suffix.isdigit() else 1
        heroes = [11, 12, 21, 22, 3][: min(5, idx + 1)]
        power = 750 + idx * 130
        return {
            "player_id": tid,
            "display_name": f"训练假人 #{idx}",
            "power": power,
            "defense": {"heroes": heroes},
            "rating": 980 + idx * 40,
            "updated_at": _now_iso(),
        }
    init_db()
    with get_cursor() as cur:
        snap = cur.execute(
            """
            SELECT payload_json, power, display_name, updated_at FROM baas_player_snapshots
            WHERE service_id=? AND player_id=? AND snapshot_type=?
            """,
            (service_id, tid, "defense"),
        ).fetchone()
        if not snap:
            raise ValueError("对手防守阵容不存在")
        rating = cur.execute(
            "SELECT rating FROM baas_arena_ratings WHERE service_id=? AND player_id=?",
            (service_id, tid),
        ).fetchone()
    return {
        "player_id": tid,
        "display_name": snap["display_name"] or tid,
        "power": int(snap["power"] or 0),
        "defense": _json_load(snap["payload_json"], {}),
        "rating": int(rating["rating"] or 1000) if rating else 1000,
        "updated_at": snap["updated_at"],
    }


def start_battle(service_id: str, player_id: str, defender_id: str, *, team: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not feature_enabled(service_id, "arena"):
        raise ValueError("竞技场功能未启用")
    cfg = _arena_cfg(service_id)
    did = str(defender_id or "").strip()
    if not did:
        raise ValueError("player_id 必填")
    if did == player_id:
        raise ValueError("不能挑战自己")
    heroes = _heroes_for_service(service_id)
    ok, msg = validate_team(team, heroes)
    if not ok:
        raise ValueError(msg)
    attacker_power = _owned_team_power(service_id, player_id, team)
    defense = get_defense(service_id, did)
    defender_power = int(defense.get("power") or 0)
    ac = anti_cheat_cfg(_pve_cfg(service_id))
    verify_power_delta(attacker_power, defender_power, ac)
    init_db()
    with get_cursor() as cur:
        rating = _rating_row(cur, service_id, player_id)
        max_attempts = int(cfg.get("daily_attempts") or 5)
        if int(rating.get("daily_attempts_used") or 0) >= max_attempts:
            raise ValueError("今日竞技场次数已用完")
        battle_id = new_id("arena_")
        seed = random.randint(1, 2_000_000_000)
        now = _now_iso()
        rating["daily_attempts_used"] = int(rating.get("daily_attempts_used") or 0) + 1
        _save_rating(cur, service_id, player_id, rating)
        cur.execute(
            """
            INSERT INTO baas_battles (
                battle_id, service_id, player_id, battle_type, stage_id, defender_id,
                status, seed, team_json, result_json, started_at, settled_at, replay_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                battle_id, service_id, player_id, "arena", "", did,
                "pending", seed, _json_dump(team or {}), "{}", now, "", "",
            ),
        )
    return {
        "battle_id": battle_id,
        "battle_type": "arena",
        "defender_id": did,
        "defender": defense,
        "seed": seed,
        "team_power": attacker_power,
        "server_time": now,
        "daily_attempts_used": rating["daily_attempts_used"],
        "daily_attempts_max": max_attempts,
        "season_id": str(cfg.get("season_id") or "arena_s1"),
    }


def settle_battle(
    service_id: str,
    player_id: str,
    battle_id: str,
    *,
    win: bool = False,
    duration_ms: int = 0,
    checksum: str = "",
    replay_hash: str = "",
    replay_ticks: int = 0,
) -> Dict[str, Any]:
    """Apply the server-frozen async-arena outcome; client reports are audit-only."""
    if not feature_enabled(service_id, "arena"):
        raise ValueError("竞技场功能未启用")
    cfg = _arena_cfg(service_id)
    bid = str(battle_id or "").strip()
    if not bid:
        raise ValueError("battle_id 必填")
    init_db()
    with get_cursor() as cur:
        row = cur.execute("SELECT * FROM baas_battles WHERE battle_id=? AND service_id=? AND player_id=?", (bid, service_id, player_id)).fetchone()
        if not row:
            raise ValueError("战斗不存在")
        if str(row["battle_type"] or "") != "arena":
            raise ValueError("战斗类型不匹配")
        if str(row["status"] or "") == "settled":
            return _json_load(row["result_json"], {})
        if str(row["status"] or "") != "pending":
            raise ValueError("战斗已结束或已过期")
        defender_id = str(row["defender_id"] or "")
        plan = dict((_json_load(row["result_json"], {}) or {}).get("authority") or {})
        if not plan:
            team = _json_load(row["team_json"], {})
            defense = get_defense(service_id, defender_id)
            plan = _authoritative_outcome(int(row["seed"] or 0), _owned_team_power(service_id, player_id, team), int(defense.get("power") or 0))
        server_win = bool(plan.get("win"))
        att = _rating_row(cur, service_id, player_id)
        delta = int(cfg.get("win_rating_delta") or 15) if server_win else int(cfg.get("lose_rating_delta") or -10)
        att["rating"] = max(0, int(att.get("rating") or 1000) + delta)
        if server_win:
            att["wins"] = int(att.get("wins") or 0) + 1
        else:
            att["losses"] = int(att.get("losses") or 0) + 1
        _save_rating(cur, service_id, player_id, att)
        now = _now_iso()
        rewards = dict(cfg.get("win_rewards") or {"gold": 50}) if server_win else dict(cfg.get("lose_rewards") or {"gold": 10})
        result = {"battle_id": bid, "win": server_win, "defender_id": defender_id, "rating_delta": delta, "rating": att["rating"], "rewards": rewards, "duration_ms": int(plan.get("duration_ms") or 0), "authority": {"team_power": int(plan.get("team_power") or 0), "power_required": int(plan.get("power_required") or 0)}, "client_report": {"win": bool(win), "duration_ms": int(duration_ms or 0), "ticks": int(replay_ticks or 0)}, "season_id": str(cfg.get("season_id") or "arena_s1"), "settled_at": now}
        cur.execute("UPDATE baas_battles SET status=?, result_json=?, settled_at=?, replay_hash=? WHERE battle_id=?", ("settled", _json_dump(result), now, str(replay_hash or ""), bid))
        from services.baas.pve_service import _credit_wallet
        for currency, amount in rewards.items():
            _credit_wallet(cur, service_id, player_id, str(currency), int(amount or 0))
        final_rating = float(att["rating"])
    board_id = str(cfg.get("rating_board_id") or "arena")
    if feature_enabled(service_id, "leaderboard"):
        from services.baas import retention_services
        retention_services.submit_score(service_id, player_id, board_id, final_rating)
    result["arena_state"] = get_state(service_id, player_id)
    try:
        from services.baas.afk_retention_hooks import on_arena_settled
        on_arena_settled(service_id, player_id)
    except Exception:
        pass
    return result

