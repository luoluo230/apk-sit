# -*- coding: utf-8 -*-
"""无限之塔 1–9999 层。刚解锁时前 20 层好打，之后按对数锚点平滑抬高，顶层对齐主线 2000 关。"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

TOWER_CAP = 9999

# (层数, 需求战力)。层间按对数插值，避免某一层突然翻倍。
_ANCHORS: List[Tuple[int, int]] = [
    (1, 900),
    (20, 2200),
    (80, 5600),
    (200, 18000),
    (500, 90000),
    (1000, 450000),
    (2000, 2800000),
    (4000, 42000000),
    (7000, 320000000),
    (9999, 1600000000),
]


def _scaling(tower: Dict[str, Any]) -> Dict[str, Any]:
    return dict(tower.get("scaling") or {})


def max_floor(tower: Dict[str, Any]) -> int:
    sc = _scaling(tower)
    raw = int(sc.get("max_floor") or tower.get("max_floor") or TOWER_CAP)
    return max(1, min(TOWER_CAP, raw))


def _anchors() -> List[Tuple[int, int]]:
    from services.baas.afk.afk_config_loader import load_afk_bundle

    raw = (load_afk_bundle() or {}).get("tower_anchors")
    parsed: List[Tuple[int, int]] = []
    if isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                continue
            try:
                parsed.append((int(row.get("floor")), int(row.get("power"))))
            except (TypeError, ValueError):
                continue
    parsed.sort()
    return parsed or list(_ANCHORS)


def _interp_power(floor: int) -> int:
    anchors = _anchors()
    f = max(1, int(floor))
    if f <= anchors[0][0]:
        return anchors[0][1]
    if f >= anchors[-1][0]:
        return anchors[-1][1]
    for idx in range(1, len(anchors)):
        left_f, left_p = anchors[idx - 1]
        right_f, right_p = anchors[idx]
        if f <= right_f:
            span = max(1, right_f - left_f)
            t = (f - left_f) / span
            log_p = math.log(left_p) + (math.log(right_p) - math.log(left_p)) * t
            return max(1, int(round(math.exp(log_p))))
    return anchors[-1][1]


def floor_def(tower: Dict[str, Any], floor: int) -> Dict[str, Any]:
    f = int(floor)
    if f < 1:
        raise ValueError("层数无效")
    cap = max_floor(tower)
    if f > cap:
        raise ValueError(f"已超过最高层 {cap}")

    for row in tower.get("milestones") or []:
        if int(row.get("floor") or 0) == f and row.get("power_required"):
            return dict(row)

    boss_type = "normal"
    if f % 100 == 0:
        boss_type = "major"
    elif f % 10 == 0:
        boss_type = "minor"

    pwr_mul = 1.0
    if boss_type == "minor":
        pwr_mul = 1.12
    elif boss_type == "major":
        pwr_mul = 1.28

    power = int(_interp_power(f) * pwr_mul)
    hp_scale = round((power / 900.0) ** 0.45, 3)
    atk_scale = round(hp_scale * (0.92 if boss_type == "normal" else 1.05), 3)

    rewards: Dict[str, Any] = {"gold": int(40 + 18 * (f ** 0.72))}
    if f % 10 == 0:
        rewards["enhance_stone"] = 2 + f // 200
    if f % 50 == 0:
        rewards["hero_exp_orb_s"] = 2 + f // 400
    if f % 100 == 0:
        rewards["diamond"] = 8 + f // 500
        rewards["star_up_crystal"] = 1 + f // 1000
    if f % 1000 == 0:
        rewards["hero_summon_scroll"] = 1

    return {
        "floor": f,
        "power_required": power,
        "enemy_hp_scale": hp_scale,
        "enemy_atk_scale": atk_scale,
        "boss_type": boss_type,
        "rewards": rewards,
    }


def daily_passive_rewards(best_floor: int, tower: Dict[str, Any]) -> Dict[str, Any]:
    f = max(0, min(int(best_floor), max_floor(tower)))
    if f <= 0:
        return {}
    out: Dict[str, Any] = {"gold": int(120 + 15 * (f ** 0.65))}
    if f >= 10:
        out["enhance_stone"] = 1 + f // 80
    if f >= 100:
        out["diamond"] = max(5, f // 200)
    if f >= 500:
        out["hero_exp_orb_s"] = 1 + f // 500
    return out
