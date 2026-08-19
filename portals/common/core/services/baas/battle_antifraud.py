# -*- coding: utf-8 -*-
"""Shared battle validation, replay hash, and anomaly audit for PVE/arena."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from models.db import log_audit_db


def heroes_catalog(cfg: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in cfg.get("heroes") or []:
        try:
            hid = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        out[hid] = dict(row)
    return out


def team_hero_ids(team: Optional[Dict[str, Any]]) -> List[int]:
    raw = (team or {}).get("heroes") or []
    ids: List[int] = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


def team_power(team: Optional[Dict[str, Any]], heroes: Dict[int, Dict[str, Any]]) -> int:
    total = 0
    for hid in team_hero_ids(team):
        row = heroes.get(hid) or {}
        total += int(row.get("base_power") or 100)
    return total


def validate_team(
    team: Optional[Dict[str, Any]],
    heroes: Dict[int, Dict[str, Any]],
    *,
    min_count: int = 1,
    max_count: int = 5,
) -> Tuple[bool, str]:
    ids = team_hero_ids(team)
    if len(ids) < min_count:
        return False, "阵容英雄数量不足"
    if len(ids) > max_count:
        return False, "阵容英雄数量超限"
    seen = set()
    for hid in ids:
        if hid in seen:
            return False, "阵容存在重复英雄"
        seen.add(hid)
        if hid not in heroes:
            return False, f"未知英雄: {hid}"
    return True, ""


def anti_cheat_cfg(pve_cfg: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(pve_cfg.get("anti_cheat") or {})
    return {
        "require_checksum": bool(base.get("require_checksum", True)),
        "require_replay_hash": bool(base.get("require_replay_hash", True)),
        "min_duration_ms": int(base.get("min_duration_ms") or 3000),
        "max_duration_ms": int(base.get("max_duration_ms") or 600000),
        "max_power_delta_ratio": float(base.get("max_power_delta_ratio") or 0.35),
    }


def compute_replay_hash(
    *,
    seed: int,
    battle_type: str,
    team: Optional[Dict[str, Any]],
    defender_id: str = "",
    win: bool = False,
    ticks: int = 0,
) -> str:
    team_json = json.dumps(team or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    raw = f"{seed}:{battle_type}:{team_json}:{defender_id}:{int(win)}:{ticks}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def verify_checksum(expected: str, checksum: str, *, required: bool) -> None:
    provided = str(checksum or "").strip()
    if not provided:
        if required:
            raise ValueError("战斗校验码缺失")
        return
    if provided != expected:
        raise ValueError("战斗校验失败")


def verify_replay_hash(expected: str, replay_hash: str, *, required: bool) -> None:
    provided = str(replay_hash or "").strip()
    if not provided:
        if required:
            raise ValueError("战斗回放摘要缺失")
        return
    if provided != expected:
        raise ValueError("战斗回放摘要不匹配")


def verify_duration(duration_ms: int, ac: Dict[str, Any]) -> None:
    dur = int(duration_ms or 0)
    min_d = int(ac.get("min_duration_ms") or 0)
    max_d = int(ac.get("max_duration_ms") or 0)
    if min_d > 0 and dur > 0 and dur < min_d:
        raise ValueError("战斗时长异常(过快)")
    if max_d > 0 and dur > max_d:
        raise ValueError("战斗时长异常(过慢)")


def verify_power_delta(attacker_power: int, defender_power: int, ac: Dict[str, Any]) -> None:
    if defender_power <= 0:
        return
    ratio = float(ac.get("max_power_delta_ratio") or 0.35)
    gap = abs(attacker_power - defender_power) / float(defender_power)
    if gap > ratio + 1e-6:
        raise ValueError("战力差距超出允许范围")


def audit_battle_anomaly(
    service_id: str,
    player_id: str,
    battle_id: str,
    reason: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {"service_id": service_id, "player_id": player_id, "battle_id": battle_id, "reason": reason}
    if detail:
        payload.update(detail)
    log_audit_db("default", "baas_battle", f"anomaly:{reason}", json.dumps(payload, ensure_ascii=False), "")


def prior_stage_id(cfg: Dict[str, Any], stage_id: str) -> Optional[str]:
    stages = list(cfg.get("stages") or [])
    ordered = sorted(stages, key=lambda s: (int(s.get("chapter") or 0), int(s.get("stage") or 0)))
    prev = None
    for row in ordered:
        sid = str(row.get("id") or "")
        if sid == stage_id:
            return prev
        prev = sid
    return None
