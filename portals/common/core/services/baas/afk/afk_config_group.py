# -*- coding: utf-8 -*-
"""玩家数值分组。分组表来自 Excel 导出的 config_groups，默认组不改任何数值。"""

from __future__ import annotations

from typing import Any, Dict

from models.db import get_cursor, init_db
from services.baas.afk.afk_config_loader import load_afk_bundle
from services.baas.helpers import _json_dump, _json_load, _now_iso

_DATA_KEY = "_config_group"
_FACTOR_KEYS = (
    "stage_power_mul",
    "stage_reward_mul",
    "dungeon_power_mul",
    "dungeon_reward_mul",
    "idle_gold_mul",
)


def _groups() -> Dict[str, Dict[str, Any]]:
    bundle = load_afk_bundle() or {}
    rows = bundle.get("config_groups") or []
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        gid = str(row.get("group_id") or "").strip()
        if gid:
            out[gid] = dict(row)
    if "default" not in out:
        out["default"] = {
            "group_id": "default",
            "name_zh": "默认",
            "stage_power_mul": 1,
            "stage_reward_mul": 1,
            "dungeon_power_mul": 1,
            "dungeon_reward_mul": 1,
            "idle_gold_mul": 1,
            "stamina_max_add": 0,
        }
    return out


def list_groups() -> Dict[str, Any]:
    groups = _groups()
    return {"groups": [groups[k] for k in groups]}


def player_group_id(service_id: str, player_id: str) -> str:
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT value_json FROM baas_player_data WHERE service_id=? AND player_id=? AND data_key=?",
            (service_id, player_id, _DATA_KEY),
        ).fetchone()
    if not row:
        return "default"
    gid = str(_json_load(row["value_json"], {}).get("group_id") or "default").strip()
    return gid or "default"


def set_player_group(service_id: str, player_id: str, group_id: str) -> Dict[str, Any]:
    gid = str(group_id or "").strip() or "default"
    groups = _groups()
    if gid not in groups:
        raise ValueError(f"分组不存在：{gid}")
    payload = _json_dump({"group_id": gid})
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_player_data (service_id, player_id, data_key, value_json, version, updated_at)
            VALUES (?,?,?,?,1,?)
            ON CONFLICT(service_id, player_id, data_key) DO UPDATE SET
                value_json=excluded.value_json, version=baas_player_data.version+1, updated_at=excluded.updated_at
            """,
            (service_id, player_id, _DATA_KEY, payload, now),
        )
    return group_factors(service_id, player_id)


def group_factors(service_id: str, player_id: str) -> Dict[str, Any]:
    gid = player_group_id(service_id, player_id)
    groups = _groups()
    row = groups.get(gid) or groups["default"]
    factors = {"group_id": str(row.get("group_id") or "default"), "name_zh": row.get("name_zh") or ""}
    for key in _FACTOR_KEYS:
        try:
            factors[key] = float(row.get(key) if row.get(key) not in (None, "") else 1)
        except (TypeError, ValueError):
            factors[key] = 1.0
        if factors[key] <= 0:
            factors[key] = 1.0
    try:
        factors["stamina_max_add"] = int(row.get("stamina_max_add") or 0)
    except (TypeError, ValueError):
        factors["stamina_max_add"] = 0
    return factors


def scale_int(service_id: str, player_id: str, key: str, value: int) -> int:
    mul = float(group_factors(service_id, player_id).get(key) or 1)
    return max(0, int(round(int(value) * mul)))


def scale_rewards(service_id: str, player_id: str, key: str, rewards: Dict[str, Any]) -> Dict[str, Any]:
    mul = float(group_factors(service_id, player_id).get(key) or 1)
    if abs(mul - 1.0) < 1e-9:
        return dict(rewards or {})
    out: Dict[str, Any] = {}
    for name, amount in (rewards or {}).items():
        try:
            number = int(amount)
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue
        out[str(name)] = max(1, int(round(number * mul)))
    return out
