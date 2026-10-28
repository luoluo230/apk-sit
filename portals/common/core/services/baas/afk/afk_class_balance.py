# -*- coding: utf-8 -*-
"""与 maclient/tools/afk_class_balance.py 同一套职业预算。服务端结算以这里为准。"""

from __future__ import annotations

from typing import Any, Dict, Mapping

ROLE_TO_CLASS = {"战士": 1, "法师": 2, "游侠": 3, "辅助": 4, "坦克": 5}

CLASS_BUDGET: Dict[int, Dict[str, Any]] = {
    1: {"key": "warrior", "name": "战士", "role": "front", "atk": 168, "hp": 1280, "def": 34, "role_power_mul": 1.00,
        "signature_zh": "暴击与吸血"},
    2: {"key": "mage", "name": "法师", "role": "back", "atk": 255, "hp": 760, "def": 12, "role_power_mul": 1.00,
        "signature_zh": "法术爆发"},
    3: {"key": "ranger", "name": "游侠", "role": "back", "atk": 214, "hp": 980, "def": 18, "role_power_mul": 1.00,
        "signature_zh": "攻速与暴击"},
    4: {"key": "support", "name": "辅助", "role": "mid", "atk": 108, "hp": 1180, "def": 26, "role_power_mul": 1.22,
        "signature_zh": "治疗与护盾"},
    5: {"key": "tank", "name": "坦克", "role": "front", "atk": 92, "hp": 1960, "def": 62, "role_power_mul": 0.86,
        "signature_zh": "减伤与格挡"},
}

CLASS_COUNTER: Dict[int, Dict[int, float]] = {
    1: {1: 1.0, 2: 0.90, 3: 1.12, 4: 1.0, 5: 0.90},
    2: {1: 1.12, 2: 1.0, 3: 0.90, 4: 1.0, 5: 1.08},
    3: {1: 0.90, 2: 1.12, 3: 1.0, 4: 1.0, 5: 1.06},
    4: {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0},
    5: {1: 1.10, 2: 0.92, 3: 0.96, 4: 1.0, 5: 1.0},
}


def _bundle_rows(key: str):
    from services.baas.afk.afk_config_loader import load_afk_bundle

    raw = (load_afk_bundle() or {}).get(key)
    return raw if isinstance(raw, list) else []


def class_budgets() -> Dict[int, Dict[str, Any]]:
    rows = _bundle_rows("class_budget")
    if not rows:
        return CLASS_BUDGET
    out: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        try:
            out[int(row.get("class_id"))] = row
        except (TypeError, ValueError):
            continue
    return out or CLASS_BUDGET


def class_id_of(hero: Mapping[str, Any]) -> int:
    raw = hero.get("class_id")
    try:
        cid = int(raw or 0)
    except (TypeError, ValueError):
        cid = 0
    if cid in class_budgets():
        return cid
    role = str(hero.get("role") or hero.get("class_name") or "")
    return ROLE_TO_CLASS.get(role, 1)


def identity_mul(hero_id: int) -> float:
    from services.baas.afk.afk_config_loader import balance_number

    hid = int(hero_id or 1)
    prime = int(balance_number("identity_mul_prime", 17))
    span = int(balance_number("identity_mul_span", 7)) or 7
    center = int(balance_number("identity_mul_center", 3))
    step = balance_number("identity_mul_step", 0.008)
    return 1.0 + ((hid * prime) % span - center) * step


def balanced_combat_bases(hero: Mapping[str, Any]) -> Dict[str, Any]:
    cid = class_id_of(hero)
    budget = class_budgets()[cid]
    try:
        hid = int(hero.get("hero_id") or hero.get("id") or 1)
    except (TypeError, ValueError):
        hid = 1
    mul = identity_mul(hid)
    return {
        "class_id": cid,
        "base_atk": max(1, int(round(budget["atk"] * mul))),
        "base_hp": max(1, int(round(budget["hp"] * mul))),
        "base_def": max(1, int(round(budget["def"] * mul))),
        "role_power_mul": float(budget["role_power_mul"]),
    }


def campaign_power_required(stage_num: int) -> int:
    """前期推荐战力抬得很慢，养成花掉的金币会把队伍远远甩在关卡前面。第 2000 关收到 4 亿。"""
    import math

    anchors = (
        (1, 1200),
        (100, 6000),
        (300, 80000),
        (600, 1500000),
        (1100, 25000000),
        (1600, 120000000),
        (2000, 400000000),
    )
    exported = []
    for row in _bundle_rows("campaign_power_anchors"):
        try:
            exported.append((int(row.get("stage")), int(row.get("power"))))
        except (TypeError, ValueError):
            continue
    if len(exported) >= 2:
        anchors = tuple(sorted(exported))
    stage = max(1, min(int(stage_num), 2000))
    if stage <= anchors[0][0]:
        return anchors[0][1]
    for index in range(1, len(anchors)):
        left_stage, left_power = anchors[index - 1]
        right_stage, right_power = anchors[index]
        if stage > right_stage:
            continue
        span = max(1, right_stage - left_stage)
        blend = (stage - left_stage) / span
        power = math.exp(math.log(left_power) + (math.log(right_power) - math.log(left_power)) * blend)
        return max(1, int(round(power)))
    return anchors[-1][1]


def apply_opening_ease(stage_num: int, power: int) -> int:
    return campaign_power_required(stage_num)
