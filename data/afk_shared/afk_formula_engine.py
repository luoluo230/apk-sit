#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AFK 正式数值公式引擎 — 客户端 / BaaS / 验收脚本共用。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Mapping, Optional

STAGE_COUNT_MAX = 2000
HERO_LEVEL_CAP = 525

QUALITY_ATK_MUL = {3: 1.0, 4: 1.12, 5: 1.28, 6: 1.42, 7: 1.58}
QUALITY_HP_MUL = {3: 1.0, 4: 1.10, 5: 1.22, 6: 1.35, 7: 1.50}
QUALITY_COST_MUL = {3: 1.0, 4: 1.08, 5: 1.18, 6: 1.28, 7: 1.38}


def stage_power_required_for_id(stage_id: int) -> int:
    """分段战力：2000 关；30 天拉满 ~800 关。"""
    s = max(1, min(int(stage_id), STAGE_COUNT_MAX))
    if s <= 100:
        return int(450 * pow(1.031, s - 1))
    if s <= 350:
        base = int(450 * pow(1.031, 99))
        return int(base * pow(1.012, s - 100))
    if s <= 900:
        base = int(450 * pow(1.031, 99) * pow(1.012, 250))
        return int(base * pow(1.0053, s - 350))
    base = int(450 * pow(1.031, 99) * pow(1.012, 250) * pow(1.0058, 550))
    return int(base * pow(1.0052, min(s, STAGE_COUNT_MAX) - 900))

FORMULA_DEFS: Dict[str, str] = {
    # 成长（525 级用有效等级压缩，避免战力溢出）
    "hero_level_effective": "min(level - 1, 79) + max(0, min(level - 1, 199) - 79) * 0.32 + max(0, min(level - 1, 399) - 199) * 0.14 + max(0, level - 1 - 399) * 0.05",
    "hero_atk": "floor(base_atk * pow(1 + atk_growth, hero_level_effective) * quality_atk_mul)",
    "hero_hp": "floor(base_hp * pow(1 + hp_growth, hero_level_effective) * quality_hp_mul)",
    "hero_def": "floor(base_def + (level - 1) * def_per_level + quality * 2)",
    # 战力（与剑与远征类卡牌一致：攻血防加权 + 等级/品质修正）
    "hero_power": "floor(hero_atk * 1.0 + hero_hp * 0.10 + hero_def * 2.0 + level * 6 + quality * 35)",
    "team_power": "sum(hero_power)",
    # 战斗
    "battle_damage": "max(1, floor(raw * 100 / (100 + target_def) * (1 + dmg_amp) * (1 - dr) * crit_mul))",
    "battle_heal": "floor(caster_atk * heal_ratio + flat_heal)",
    "battle_shield": "floor(caster_atk * shield_ratio + flat_shield)",
    # 经济
    "level_up_gold": "floor(70 * pow(level, 1.52) * quality_cost_mul)",
    "stage_gold": "floor(85 + stage_id * 3.8 + chapter * 18 * star_mul)",
    "stage_exp": "floor(35 + stage_id * 1.8 + chapter * 8)",
    "stamina_cost": "5 + chapter // 8",
    "gacha_cost_diamond": "280",
    # 关卡难度
    "stage_power_required": "stage_power_required_for_id(stage_id)",
    "stage_late_multiplier": "1",
    "enemy_hp": "floor(monster_base_hp * stage_hp_scale * tier_hp_mul)",
    "enemy_atk": "floor(monster_base_atk * stage_atk_scale * tier_atk_mul)",
    # 挂机 ROI
    "idle_gold_per_hour": "floor(220 + max_cleared_stage * 3.2 + team_power * 0.042)",
    "idle_exp_per_hour": "floor(80 + max_cleared_stage * 1.6 + team_power * 0.018)",
    "idle_max_hours": "16",
    # 付费参考点（验收用）
    "iap_value_gold_equiv": "floor(diamond_amount * 12)",
}


def _safe_eval(expr: str, vars_map: Mapping[str, Any]) -> float:
    allowed = {
        "floor": math.floor,
        "ceil": math.ceil,
        "pow": pow,
        "max": max,
        "min": min,
        "abs": abs,
        "sum": sum,
        "stage_power_required_for_id": stage_power_required_for_id,
    }
    loc = dict(allowed)
    loc.update({k: float(v) if isinstance(v, (int, float)) else v for k, v in vars_map.items()})
    expr = str(expr or "0").strip()
    if not re.fullmatch(r"[0-9a-zA-Z_+\-*/()., \t]+", expr):
        raise ValueError("invalid formula expr: " + expr)
    return float(eval(expr, {"__builtins__": {}}, loc))


def eval_formula(
    formula_id: str,
    vars_map: Optional[Mapping[str, Any]] = None,
    *,
    formulas: Optional[Mapping[str, str]] = None,
    expr: Optional[str] = None,
) -> int:
    table = merge_formulas_from_dict(formulas) if formulas else FORMULA_DEFS
    e = expr if expr is not None else table.get(formula_id, "0")
    if e is None:
        raise KeyError(formula_id)
    return int(_safe_eval(e, vars_map or {}))


def hero_stats(
    hero: Mapping[str, Any],
    level: int = 1,
    equipment: Optional[Mapping[str, int]] = None,
    *,
    formulas: Optional[Mapping[str, str]] = None,
) -> Dict[str, int]:
    table = merge_formulas_from_dict(formulas) if formulas else FORMULA_DEFS
    lv = max(1, int(level))
    q = int(hero.get("quality") or 3)
    eq = equipment or {}
    vars_map = {
        "base_atk": int(hero.get("base_atk") or 100),
        "base_hp": int(hero.get("base_hp") or 1000),
        "base_def": int(hero.get("base_def") or 20),
        "atk_growth": float(hero.get("growth_atk") or 0.065),
        "hp_growth": float(hero.get("growth_hp") or 0.07),
        "def_per_level": float(hero.get("def_per_level") or 1.2),
        "quality": q,
        "quality_atk_mul": QUALITY_ATK_MUL.get(q, 1.0),
        "quality_hp_mul": QUALITY_HP_MUL.get(q, 1.0),
        "quality_cost_mul": QUALITY_COST_MUL.get(q, 1.0),
        "level": lv,
    }
    vars_map["hero_level_effective"] = eval_formula("hero_level_effective", vars_map, formulas=table)
    atk = eval_formula("hero_atk", vars_map, formulas=table)
    hp = eval_formula("hero_hp", vars_map, formulas=table)
    defv = eval_formula("hero_def", vars_map, formulas=table)
    atk += int(eq.get("atk") or 0)
    hp += int(eq.get("hp") or 0)
    defv += int(eq.get("def") or 0)
    pvars = {**vars_map, "hero_atk": atk, "hero_hp": hp, "hero_def": defv}
    power = eval_formula("hero_power", pvars, formulas=table)
    return {"atk": atk, "hp": hp, "def": defv, "power": power, "level": lv}


def team_power(
    heroes: list,
    levels: Optional[Mapping[int, int]] = None,
    *,
    formulas: Optional[Mapping[str, str]] = None,
) -> int:
    total = 0
    levels = levels or {}
    for h in heroes:
        hid = int(h.get("hero_id") or h.get("id") or 0)
        lv = int(levels.get(hid, h.get("level") or 1))
        total += hero_stats(h, lv, formulas=formulas)["power"]
    return total


def level_up_cost(hero: Mapping[str, Any], level: int, *, formulas: Optional[Mapping[str, str]] = None) -> int:
    table = merge_formulas_from_dict(formulas) if formulas else FORMULA_DEFS
    q = int(hero.get("quality") or 3)
    return eval_formula("level_up_gold", {
        "level": max(1, int(level)),
        "quality_cost_mul": QUALITY_COST_MUL.get(q, 1.0),
    }, formulas=table)


def merge_formulas_from_dict(extra: Mapping[str, str]) -> Dict[str, str]:
    out = dict(FORMULA_DEFS)
    out.update({str(k): str(v) for k, v in extra.items()})
    return out
