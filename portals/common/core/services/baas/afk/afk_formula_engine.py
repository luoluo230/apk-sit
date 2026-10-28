# -*- coding: utf-8 -*-
"""AFK 正式数值公式 — 与 maclient/tools/afk_formula_engine.py 保持同步。"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Mapping, Optional

QUALITY_ATK_MUL = {1: 0.88, 2: 0.95, 3: 1.0, 4: 1.12, 5: 1.28}
QUALITY_HP_MUL = {1: 0.90, 2: 0.96, 3: 1.0, 4: 1.10, 5: 1.22}
QUALITY_COST_MUL = {1: 0.92, 2: 0.97, 3: 1.0, 4: 1.08, 5: 1.18}


def _quality_cell(quality: int, field: str, fallback: Mapping[int, float]) -> float:
    try:
        from services.baas.afk.afk_config_loader import load_afk_bundle

        rows = (load_afk_bundle() or {}).get("quality_mul") or []
    except Exception:
        rows = []
    for row in rows:
        try:
            if int(row.get("quality") or 0) != int(quality):
                continue
        except (TypeError, ValueError):
            continue
        raw = row.get(field)
        if raw in (None, ""):
            break
        try:
            return float(raw)
        except (TypeError, ValueError):
            break
    return float(fallback.get(int(quality), 1.0))


def merge_formulas(custom: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    base = dict(DEFAULT_FORMULAS)
    if custom:
        base.update({str(k): str(v) for k, v in custom.items()})
    return base


DEFAULT_FORMULAS: Dict[str, str] = {
    "hero_atk": "floor(base_atk * pow(1 + atk_growth, level - 1) * quality_atk_mul)",
    "hero_hp": "floor(base_hp * pow(1 + hp_growth, level - 1) * quality_hp_mul)",
    "hero_def": "floor(base_def + (level - 1) * def_per_level + quality * 2)",
    "hero_power": "floor((hero_atk * 1.0 + hero_hp * 0.10 + hero_def * 2.0 + level * 6 + quality * 35) * (1 + max(0, level - 80) * 0.0364))",
    "team_power": "sum(hero_power)",
    "battle_damage": "max(1, floor(raw * 100 / (100 + target_def) * (1 + dmg_amp) * (1 - dr) * crit_mul))",
    "battle_heal": "floor(caster_atk * heal_ratio + flat_heal)",
    "battle_shield": "floor(caster_atk * shield_ratio + flat_shield)",
    "level_up_gold": "floor(70 * pow(level, 1.52) * quality_cost_mul)",
    "stage_gold": "floor(8000 + 48000 * pow(stage_id, 0.3))",
    "stage_exp": "floor(max(60, (8000 + 48000 * pow(stage_id, 0.3)) / 3500))",
    "stamina_cost": "6 + chapter // 6",
    "gacha_cost_diamond": "280",
    "stage_power_required": "floor(480 * pow(1.026, stage_id - 1))",
    "stage_late_multiplier": "1 + max(0, stage_id - 40) * 0.015",
    "enemy_hp": "floor(monster_base_hp * stage_hp_scale * tier_hp_mul)",
    "enemy_atk": "floor(monster_base_atk * stage_atk_scale * tier_atk_mul)",
    "idle_gold_per_hour": "idle_gold_per_hour_value(max_cleared_stage, team_power)",
    "idle_max_hours": "12",
    "iap_value_gold_equiv": "floor(diamond_amount * 12)",
}


def idle_gold_per_hour_value(stage: float, team_power: float = 0) -> float:
    del team_power
    s = max(1, int(stage))
    stage_gold = 8000 + 48000 * (s ** 0.3)
    if s < 40:
        day_equiv = 8
    elif s < 200:
        day_equiv = 6
    elif s < 800:
        day_equiv = 5
    else:
        day_equiv = 4
    per_hour = stage_gold * day_equiv / 32.0
    return float(max(80, int(per_hour)))


def idle_item_rewards(stage: int, minutes: int) -> Dict[str, int]:
    s = max(0, int(stage))
    hours = max(0, int(minutes)) / 60.0
    try:
        from services.baas.afk.afk_config_loader import load_afk_bundle

        rules = (load_afk_bundle() or {}).get("idle_material_rules") or []
    except Exception:
        rules = []
    if isinstance(rules, list) and rules:
        out: Dict[str, int] = {}
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if s < int(rule.get("min_stage") or 0) or hours < float(rule.get("min_hours") or 0):
                continue
            item = str(rule.get("item_key") or "")
            if not item:
                continue
            every = float(rule.get("every_hours") or 0)
            flat = int(rule.get("flat_count") or 0)
            count = max(1, int(hours // every)) if every > 0 else flat
            if count > 0:
                out[item] = count
        return out
    out = {}
    if s >= 12 and hours >= 3:
        out["enhance_stone"] = max(1, int(hours // 3))
    if s >= 40 and hours >= 4:
        out["hero_exp_orb_s"] = max(1, int(hours // 4))
    if s >= 150 and hours >= 6:
        out["hero_exp_orb_m"] = max(1, int(hours // 8))
    if s >= 400 and hours >= 8:
        out["refine_core"] = 1
    return out


def _safe_eval(expr: str, vars_map: Mapping[str, Any]) -> float:
    allowed = {
        "floor": math.floor, "ceil": math.ceil, "pow": pow, "max": max, "min": min, "abs": abs, "sum": sum,
        "idle_gold_per_hour_value": idle_gold_per_hour_value,
    }
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
    from services.baas.afk.afk_class_balance import balanced_combat_bases
    from services.baas.afk.afk_config_loader import balance_number

    bases = balanced_combat_bases(hero)
    vars_map = {
        "base_atk": bases["base_atk"],
        "base_hp": bases["base_hp"],
        "base_def": bases["base_def"],
        "atk_growth": float(hero.get("growth_atk") or balance_number("default_growth_atk", 0.065)),
        "hp_growth": float(hero.get("growth_hp") or balance_number("default_growth_hp", 0.07)),
        "def_per_level": float(hero.get("def_per_level") or balance_number("default_def_per_level", 1.2)),
        "quality": q,
        "quality_atk_mul": _quality_cell(q, "atk_mul", QUALITY_ATK_MUL),
        "quality_hp_mul": _quality_cell(q, "hp_mul", QUALITY_HP_MUL),
        "quality_cost_mul": _quality_cell(q, "cost_mul", QUALITY_COST_MUL),
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
    power = int(eval_formula("hero_power", pvars, formulas=table) * bases["role_power_mul"])
    return {
        "atk": atk, "hp": hp, "def": defv, "power": power, "level": lv,
        "class_id": bases["class_id"], "role_power_mul": bases["role_power_mul"],
    }


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
