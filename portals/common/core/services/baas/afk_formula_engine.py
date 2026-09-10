# -*- coding: utf-8 -*-
"""AFK 正式数值公式 — 与 maclient/tools/afk_formula_engine.py 保持同步。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Mapping, Optional

QUALITY_ATK_MUL = {1: 0.88, 2: 0.95, 3: 1.0, 4: 1.12, 5: 1.28}
QUALITY_HP_MUL = {1: 0.90, 2: 0.96, 3: 1.0, 4: 1.10, 5: 1.22}
QUALITY_COST_MUL = {1: 0.92, 2: 0.97, 3: 1.0, 4: 1.08, 5: 1.18}


def merge_formulas(custom: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    base = dict(DEFAULT_FORMULAS)
    if custom:
        base.update({str(k): str(v) for k, v in custom.items()})
    return base


DEFAULT_FORMULAS: Dict[str, str] = {
    "hero_atk": "floor(base_atk * pow(1 + atk_growth, level - 1) * quality_atk_mul)",
    "hero_hp": "floor(base_hp * pow(1 + hp_growth, level - 1) * quality_hp_mul)",
    "hero_def": "floor(base_def + (level - 1) * def_per_level + quality * 2)",
    "hero_power": "floor(hero_atk * 1.0 + hero_hp * 0.10 + hero_def * 2.0 + level * 6 + quality * 35)",
    "team_power": "sum(hero_power)",
    "battle_damage": "max(1, floor(raw * 100 / (100 + target_def) * (1 + dmg_amp) * (1 - dr) * crit_mul))",
    "battle_heal": "floor(caster_atk * heal_ratio + flat_heal)",
    "battle_shield": "floor(caster_atk * shield_ratio + flat_shield)",
    "level_up_gold": "floor(70 * pow(level, 1.52) * quality_cost_mul)",
    "stage_gold": "floor(85 + stage_id * 3.8 + chapter * 18 * star_mul)",
    "stage_exp": "floor(35 + stage_id * 1.8 + chapter * 8)",
    "stamina_cost": "6 + chapter // 6",
    "gacha_cost_diamond": "280",
    "stage_power_required": "floor(480 * pow(1.026, stage_id - 1))",
    "stage_late_multiplier": "1 + max(0, stage_id - 40) * 0.015",
    "enemy_hp": "floor(monster_base_hp * stage_hp_scale * tier_hp_mul)",
    "enemy_atk": "floor(monster_base_atk * stage_atk_scale * tier_atk_mul)",
    "idle_gold_per_hour": "floor(180 + max_cleared_stage * 2.8 + team_power * 0.035)",
    "idle_max_hours": "12",
    "iap_value_gold_equiv": "floor(diamond_amount * 12)",
}


def _safe_eval(expr: str, vars_map: Mapping[str, Any]) -> float:
    allowed = {"floor": math.floor, "ceil": math.ceil, "pow": pow, "max": max, "min": min, "abs": abs, "sum": sum}
    loc = dict(allowed)
    loc.update({k: float(v) if isinstance(v, (int, float)) else v for k, v in vars_map.items()})
    expr = str(expr or "0").strip()
    if not re.fullmatch(r"[0-9a-zA-Z_+\-*/()., \t]+", expr):
        raise ValueError("invalid formula expr: " + expr)
    return float(eval(expr, {"__builtins__": {}}, loc))


def eval_formula(formula_id: str, vars_map: Optional[Mapping[str, Any]] = None, *, formulas: Optional[Mapping[str, str]] = None, expr: Optional[str] = None) -> int:
    table = merge_formulas(formulas)
    e = expr if expr is not None else table.get(formula_id, "0")
    return int(_safe_eval(e, vars_map or {}))


def hero_stats(hero: Mapping[str, Any], level: int = 1, equipment: Optional[Mapping[str, int]] = None, *, formulas: Optional[Mapping[str, str]] = None) -> Dict[str, int]:
    lv = max(1, int(level))
    q = int(hero.get("quality") or 1)
    eq = equipment or {}
    vars_map = {
        "base_atk": int(hero.get("base_atk") or hero.get("base_atk") or 100),
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
    # Formula bundles may introduce derived inputs (the AFK v3 bundle defines
    # hero_level_effective and uses it from hero_atk/hero_hp).  Resolve that
    # prerequisite before evaluating dependent formulas so server and client
    # consume the same bundle without a NameError.
    table = merge_formulas(formulas)
    if "hero_level_effective" in table:
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


def level_up_cost(hero: Mapping[str, Any], level: int, *, formulas: Optional[Mapping[str, str]] = None) -> int:
    q = int(hero.get("quality") or 1)
    return eval_formula("level_up_gold", {"level": max(1, int(level)), "quality_cost_mul": QUALITY_COST_MUL.get(q, 1.0)}, formulas=formulas)


def team_power_from_defs(hero_defs: Dict[int, Dict[str, Any]], hero_ids: list, levels: Optional[Mapping[int, int]] = None, *, formulas: Optional[Mapping[str, str]] = None) -> int:
    total = 0
    levels = levels or {}
    for hid in hero_ids:
        try:
            i = int(hid)
        except (TypeError, ValueError):
            continue
        meta = hero_defs.get(i) or {}
        if not meta:
            total += 100
            continue
        lv = int(levels.get(i, 1))
        total += hero_stats(meta, lv, formulas=formulas)["power"]
    return total
