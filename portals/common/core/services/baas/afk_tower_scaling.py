# -*- coding: utf-8 -*-
"""无限之塔层数生成：999+ 层程序化数值 + Boss 标记。"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _scaling(tower: Dict[str, Any]) -> Dict[str, Any]:
    return dict(tower.get("scaling") or {})


def max_floor(tower: Dict[str, Any]) -> int:
    sc = _scaling(tower)
    return int(sc.get("max_floor") or tower.get("max_floor") or 999)


def floor_def(tower: Dict[str, Any], floor: int) -> Dict[str, Any]:
    """生成单层配置（优先 milestones 表，否则公式）。"""
    f = int(floor)
    if f < 1:
        raise ValueError("层数无效")
    cap = max_floor(tower)
    if f > cap:
        raise ValueError(f"已超过最高层 {cap}")

    for row in tower.get("milestones") or []:
        if int(row.get("floor") or 0) == f:
            return dict(row)

    sc = _scaling(tower)
    base_pwr = int(sc.get("power_base") or 400)
    pwr_step = int(sc.get("power_per_floor") or 85)
    hp_base = float(sc.get("hp_scale_base") or 1.0)
    hp_step = float(sc.get("hp_scale_per_floor") or 0.012)
    atk_base = float(sc.get("atk_scale_base") or 1.0)
    atk_step = float(sc.get("atk_scale_per_floor") or 0.008)
    gold_base = int(sc.get("gold_base") or 80)
    gold_step = int(sc.get("gold_per_floor") or 12)

    boss_type = ""
    if f % 50 == 0:
        boss_type = "major"
    elif f % 10 == 0:
        boss_type = "minor"

    hp_mul = 1.0
    atk_mul = 1.0
    pwr_mul = 1.0
    if boss_type == "minor":
        hp_mul = float(sc.get("minor_boss_hp_mul") or 1.35)
        atk_mul = float(sc.get("minor_boss_atk_mul") or 1.25)
        pwr_mul = float(sc.get("minor_boss_power_mul") or 1.15)
    elif boss_type == "major":
        hp_mul = float(sc.get("major_boss_hp_mul") or 1.85)
        atk_mul = float(sc.get("major_boss_atk_mul") or 1.55)
        pwr_mul = float(sc.get("major_boss_power_mul") or 1.35)

    rewards: Dict[str, Any] = {"gold": gold_base + f * gold_step}
    if f % 5 == 0:
        rewards["tower_key"] = 1 + f // 100
    if f % 10 == 0:
        rewards["diamond"] = 10 + f // 50
    if boss_type == "minor":
        rewards["enhance_stone"] = 5 + f // 20
    if boss_type == "major":
        rewards["star_up_crystal"] = 2 + f // 100
        rewards["diamond"] = rewards.get("diamond", 0) + 30 + f // 25

    return {
        "floor": f,
        "power_required": int((base_pwr + f * pwr_step) * pwr_mul),
        "enemy_hp_scale": (hp_base + f * hp_step) * hp_mul,
        "enemy_atk_scale": (atk_base + f * atk_step) * atk_mul,
        "boss_type": boss_type or "normal",
        "rewards": rewards,
    }


def daily_passive_rewards(best_floor: int, tower: Dict[str, Any]) -> Dict[str, Any]:
    """根据最高通关层数计算每日可领挂机奖励。"""
    f = max(0, int(best_floor))
    if f <= 0:
        return {}
    sc = _scaling(tower)
    gold = int(sc.get("daily_gold_base") or 200) + f * int(sc.get("daily_gold_per_floor") or 8)
    out: Dict[str, Any] = {"gold": gold}
    if f >= 10:
        out["tower_key"] = 1 + f // 50
    if f >= 50:
        out["diamond"] = max(5, f // 100)
    if f >= 100:
        out["hero_summon_scroll"] = 1
    return out
