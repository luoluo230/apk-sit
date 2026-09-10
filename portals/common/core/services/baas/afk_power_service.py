# -*- coding: utf-8 -*-
"""统一 gate 战力：等级 + 升星 + 天赋 + 共享装备成长（与公式表对齐）。"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from models.db import get_cursor, init_db
from services.baas.afk_config_loader import afk_formulas, hero_def_map, load_afk_bundle
from services.baas.afk_formula_engine import eval_formula, hero_stats
from services.baas.afk_growth_service import EQUIP_SLOTS
from services.baas.service_crud import get_feature_config

QUALITY_STAT_MUL = {3: 1.28, 4: 1.48, 5: 1.72}


def _merged_formulas() -> Dict[str, str]:
    bundle = load_afk_bundle() or {}
    eco = bundle.get("economy_system") or {}
    merged = dict(afk_formulas())
    for k, v in (eco.get("formulas") or {}).items():
        merged[str(k)] = str(v)
    return merged


def stage_index(stage_id: str) -> int:
    sid = str(stage_id or "").strip()
    if sid.startswith("AFK_"):
        try:
            parts = sid.split("_")
            return (int(parts[1]) - 1) * 10 + int(parts[2])
        except (IndexError, ValueError):
            return 0
    if "-" in sid:
        try:
            ch, st = sid.split("-", 1)
            return (int(ch) - 1) * 10 + int(st)
        except ValueError:
            return 0
    try:
        return int(sid)
    except ValueError:
        return 0


def stage_power_required(stage_id: str, *, stage_row: Optional[Mapping[str, Any]] = None, formulas: Optional[Dict[str, str]] = None) -> int:
    """关卡战力门槛：优先用表内烘焙值，否则走分段公式。"""
    table = formulas or _merged_formulas()
    num = stage_index(stage_id)
    if num <= 0 and stage_row:
        num = int(stage_row.get("stage") or stage_row.get("stage_id_num") or 1)
    if num <= 0:
        num = 1
    base = int(stage_row.get("power_required") or 0) if stage_row else 0
    if base <= 0:
        base = eval_formula("stage_power_required", {"stage_id": num}, formulas=table)
    return max(1, int(base))


def growth_gate_for_stage(stage_id: str) -> Dict[str, Any]:
    """50 关以后养成门槛：拉长节奏，每 40 关升一档。"""
    num = stage_index(stage_id)
    if num < 50:
        return {"required": False}
    tier = (num - 50) // 60
    need_star = max(3, min(5, 2 + tier) - (0 if tier < 2 else 1))
    return {
        "required": True,
        "min_avg_star": need_star,
        "min_star_on_team": need_star,
        "min_equip_enhance_avg": max(1, min(18, 1 + tier)),
        "min_dungeon_runs_total": min(50, 3 + tier * 4),
        "stage_index": num,
    }


def _equip_team_bonus(equipment: List[Dict[str, Any]], formulas: Dict[str, str]) -> Dict[str, int]:
    atk = hp = defv = 0
    for eq in equipment:
        quality = int(eq.get("quality") or 3)
        enhance = int(eq.get("enhance_level") or 0)
        refine = int(eq.get("refine_level") or 0)
        awaken = int(eq.get("awaken") or 0)
        gems = int(eq.get("gem_count") or 0)
        stat_mul = float(QUALITY_STAT_MUL.get(quality, 1.28))
        enh_mul = eval_formula(
            "equip_enhance_mul",
            {"enhance_level": enhance, "quality": quality},
            formulas=formulas,
            expr=str(formulas.get("equip_enhance_mul") or "1 + enhance_level * (0.035 + quality * 0.004)"),
        )
        refine_pct = eval_formula(
            "equip_refine_pct",
            {"refine_level": refine, "quality": quality},
            formulas=formulas,
            expr="refine_level * (2 + quality * 0.5)",
        )
        base_atk = int(18 * quality * stat_mul * (enh_mul / 100.0 if enh_mul > 20 else enh_mul))
        base_hp = int(120 * quality * stat_mul * (enh_mul / 100.0 if enh_mul > 20 else enh_mul))
        base_def = int(6 * quality * stat_mul * (1 + refine_pct / 100.0))
        if awaken:
            base_atk = int(base_atk * 1.12)
            base_hp = int(base_hp * 1.12)
            base_def = int(base_def * 1.12)
        base_atk += gems * 5
        base_hp += gems * 25
        base_def += gems * 2
        atk += base_atk
        hp += base_hp
        defv += base_def
    return {"atk": atk, "hp": hp, "def": defv}


def _load_equipment(cur, service_id: str, player_id: str) -> List[Dict[str, Any]]:
    rows = cur.execute(
        """
        SELECT slot, quality, enhance_level, refine_level, awaken, gem_count
        FROM baas_player_equipment WHERE service_id=? AND player_id=?
        """,
        (service_id, player_id),
    ).fetchall()
    if rows:
        return [dict(r) for r in rows]
    return [{"slot": s, "quality": 3, "enhance_level": 0, "refine_level": 0, "awaken": 0, "gem_count": 0} for s in EQUIP_SLOTS]


def _load_heroes(cur, service_id: str, player_id: str) -> Dict[int, Dict[str, Any]]:
    rows = cur.execute(
        """
        SELECT hero_id, level, star, talent_points
        FROM baas_player_heroes WHERE service_id=? AND player_id=?
        """,
        (service_id, player_id),
    ).fetchall()
    return {int(r["hero_id"]): dict(r) for r in rows}


def hero_power_unified(
    hero_def: Mapping[str, Any],
    *,
    level: int,
    star: int = 1,
    talent_points: int = 0,
    equip_share: Optional[Mapping[str, int]] = None,
    formulas: Optional[Dict[str, str]] = None,
) -> Dict[str, int]:
    table = formulas or _merged_formulas()
    star = max(1, int(star or 1))
    star_mul = 1.0 + (star - 1) * 0.08
    eq = dict(equip_share or {})
    stats = hero_stats(hero_def, int(level or 1), equipment=eq, formulas=table)
    atk = int(stats["atk"] * star_mul)
    hp = int(stats["hp"] * star_mul)
    defv = int(stats["def"] * star_mul)
    talent_atk = int(talent_points) * 3
    talent_hp = int(talent_points) * 20
    atk += talent_atk
    hp += talent_hp
    pvars = {
        "hero_atk": atk,
        "hero_hp": hp,
        "hero_def": defv,
        "level": int(level or 1),
        "quality": int(hero_def.get("quality") or 3),
    }
    power = eval_formula("hero_power", pvars, formulas=table)
    return {"atk": atk, "hp": hp, "def": defv, "power": power, "star": star, "talent_points": talent_points}


def team_power_unified(
    service_id: str,
    player_id: str,
    team_ids: Optional[List[int]] = None,
    *,
    hero_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = hero_cfg or get_feature_config(service_id, "hero")
    defs = hero_def_map(cfg)
    formulas = _merged_formulas()
    init_db()
    with get_cursor() as cur:
        owned = _load_heroes(cur, service_id, player_id)
        equipment = _load_equipment(cur, service_id, player_id)
    if not owned:
        return {"team_power": 0, "heroes": [], "avg_star": 0, "equip_enhance_avg": 0}
    ids = [int(x) for x in (team_ids or []) if int(x) in owned]
    if not ids:
        ids = sorted(owned.keys())[:5]
    eq_bonus = _equip_team_bonus(equipment, formulas)
    share = {k: int(v // max(1, len(ids))) for k, v in eq_bonus.items()}
    total = 0
    stars: List[int] = []
    for hid in ids:
        row = owned[hid]
        meta = defs.get(hid) or {}
        p = hero_power_unified(
            meta,
            level=int(row.get("level") or 1),
            star=int(row.get("star") or 1),
            talent_points=int(row.get("talent_points") or 0),
            equip_share=share,
            formulas=formulas,
        )
        total += int(p["power"])
        stars.append(int(row.get("star") or 1))
    qualities = {int(defs.get(h, {}).get("quality") or 3) for h in ids if h in defs}
    bond = 120 if len(qualities) == 1 and len(ids) >= 3 else 60 if len(ids) >= 3 else 0
    enhance_avg = sum(int(e.get("enhance_level") or 0) for e in equipment) / max(1, len(equipment))
    return {
        "team_power": int(total + bond),
        "heroes": ids,
        "bond_bonus": bond,
        "equip_bonus": eq_bonus,
        "avg_star": round(sum(stars) / max(1, len(stars)), 2),
        "equip_enhance_avg": round(enhance_avg, 2),
    }


def validate_growth_gate(service_id: str, player_id: str, stage_id: str, team_ids: Optional[List[int]] = None) -> Tuple[bool, str]:
    gate = growth_gate_for_stage(stage_id)
    if not gate.get("required"):
        return True, ""
    info = team_power_unified(service_id, player_id, team_ids=team_ids)
    if float(info.get("avg_star") or 0) < float(gate.get("min_avg_star") or 0):
        return False, f"需队伍平均 {gate['min_avg_star']} 星以上（当前 {info.get('avg_star')}）"
    if float(info.get("equip_enhance_avg") or 0) < float(gate.get("min_equip_enhance_avg") or 0):
        return False, f"需装备平均强化 +{gate['min_equip_enhance_avg']}（当前 {info.get('equip_enhance_avg')}）"
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT COALESCE(SUM(run_count),0) AS cnt FROM baas_dungeon_daily WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
    runs = int(row["cnt"] or 0) if row else 0
    if runs < int(gate.get("min_dungeon_runs_total") or 0):
        return False, f"需累计完成副本 {gate['min_dungeon_runs_total']} 次（当前 {runs}）"
    return True, ""
