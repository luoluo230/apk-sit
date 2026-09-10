# -*- coding: utf-8 -*-
"""英雄背包：拥有、升级、装备（剑与远征式养成基础）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.afk_config_loader import afk_formulas
from services.baas.afk_formula_engine import hero_stats, level_up_cost
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.wallet_helpers import debit_wallet
from services.baas import inventory_service


def _hero_defs(cfg: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in cfg.get("hero_defs") or []:
        hid = int(row.get("id") or 0)
        if hid > 0:
            out[hid] = dict(row)
    return out


def get_roster(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "hero"):
        raise ValueError("英雄系统未启用")
    cfg = get_feature_config(service_id, "hero")
    defs = _hero_defs(cfg)
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT hero_id, level, exp, star, shards, talent_points, equipment_json, updated_at
            FROM baas_player_heroes WHERE service_id=? AND player_id=?
            ORDER BY hero_id
            """,
            (service_id, player_id),
        ).fetchall()
    heroes = []
    formulas = afk_formulas() or None
    for row in rows:
        hid = int(row["hero_id"])
        meta = defs.get(hid, {})
        level = int(row["level"] or 1)
        stats = hero_stats(meta, level, formulas=formulas) if meta else None
        power = int(stats["power"]) if stats else int(meta.get("base_power") or 100)
        heroes.append({
            "hero_id": hid,
            "name": meta.get("name", f"Hero{hid}"),
            "level": level,
            "exp": int(row["exp"] or 0),
            "star": int(row["star"] or 1) if "star" in row.keys() else 1,
            "shards": int(row["shards"] or 0) if "shards" in row.keys() else 0,
            "talent_points": int(row["talent_points"] or 0) if "talent_points" in row.keys() else 0,
            "quality": int(meta.get("quality") or 3),
            "equipment": _json_load(row["equipment_json"], {}),
            "role": meta.get("role", ""),
            "base_power": power,
            "atk": stats.get("atk") if stats else None,
            "hp": stats.get("hp") if stats else None,
            "def": stats.get("def") if stats else None,
        })
    return {"heroes": heroes, "count": len(heroes)}


def grant_hero(cur, service_id: str, player_id: str, hero_id: int, *, shards: int = 0) -> Dict[str, Any]:
    """内部：抽卡等模块发放英雄（已有则转为碎片）。"""
    cfg = get_feature_config(service_id, "hero")
    defs = _hero_defs(cfg)
    hid = int(hero_id or 0)
    if hid not in defs:
        raise ValueError("英雄 ID 无效")
    now = _now_iso()
    row = cur.execute(
        "SELECT * FROM baas_player_heroes WHERE service_id=? AND player_id=? AND hero_id=?",
        (service_id, player_id, hid),
    ).fetchone()
    duplicate = bool(row)
    if row:
        shards = int(shards or cfg.get("duplicate_shards") or 10)
        new_shards = int(row["shards"] or 0) + shards if "shards" in row.keys() else shards
        cur.execute(
            "UPDATE baas_player_heroes SET shards=?, updated_at=? WHERE service_id=? AND player_id=? AND hero_id=?",
            (new_shards, now, service_id, player_id, hid),
        )
        return {"hero_id": hid, "duplicate": True, "shards": shards, "total_shards": new_shards, "action": "converted_shards"}
    cur.execute(
        """
        INSERT INTO baas_player_heroes (service_id, player_id, hero_id, level, exp, equipment_json, updated_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (service_id, player_id, hid, 1, 0, "{}", now),
    )
    return {"hero_id": hid, "duplicate": False, "level": 1, "action": "granted"}


def bootstrap_new_player(cur, service_id: str, player_id: str) -> Dict[str, Any]:
    """新玩家初始英雄与基础资源（F2P 可玩，不依赖礼包）。"""
    if not feature_enabled(service_id, "hero"):
        return {"skipped": True}
    cfg = get_feature_config(service_id, "hero")
    starter_ids = [int(x) for x in (cfg.get("starter_hero_ids") or [1, 2, 3, 4, 5]) if int(x) > 0][:5]
    granted = []
    for hid in starter_ids:
        try:
            res = grant_hero(cur, service_id, player_id, hid)
            cur.execute(
                "UPDATE baas_player_heroes SET shards=? WHERE service_id=? AND player_id=? AND hero_id=?",
                (int(cfg.get("starter_shards") or 80), service_id, player_id, hid),
            )
            granted.append(res)
        except ValueError:
            pass
    from services.baas.wallet_helpers import credit_wallet

    gold = int(cfg.get("starter_gold") or 2500)
    diamond = int(cfg.get("starter_diamond") or 300)
    credit_wallet(cur, service_id, player_id, "gold", gold)
    credit_wallet(cur, service_id, player_id, "diamond", diamond)
    return {"heroes": granted, "gold": gold, "diamond": diamond}


def level_up(service_id: str, player_id: str, hero_id: int) -> Dict[str, Any]:
    if not feature_enabled(service_id, "hero"):
        raise ValueError("英雄系统未启用")
    cfg = get_feature_config(service_id, "hero")
    max_level = int(cfg.get("max_level") or 100)
    formulas = afk_formulas() or None
    hid = int(hero_id or 0)
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_heroes WHERE service_id=? AND player_id=? AND hero_id=?",
            (service_id, player_id, hid),
        ).fetchone()
        if not row:
            raise ValueError("未拥有该英雄")
        level = int(row["level"] or 1)
        if level >= max_level:
            raise ValueError("已达等级上限")
        meta = _hero_defs(cfg).get(hid, {})
        cost = level_up_cost(meta, level, formulas=formulas) if meta else int(cfg.get("level_cost_gold") or 100) * level
        debit_wallet(cur, service_id, player_id, "gold", cost)
        level += 1
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_heroes SET level=?, updated_at=? WHERE service_id=? AND player_id=? AND hero_id=?",
            (level, now, service_id, player_id, hid),
        )
    return {"hero_id": hid, "level": level, "spent_gold": cost}


def equip(
    service_id: str,
    player_id: str,
    hero_id: int,
    slot: str,
    equipment_id: str,
) -> Dict[str, Any]:
    if not feature_enabled(service_id, "hero"):
        raise ValueError("英雄系统未启用")
    cfg = get_feature_config(service_id, "hero")
    allowed = {str(s) for s in (cfg.get("equipment_slots") or ["weapon", "armor"])}
    slot_name = str(slot or "").strip()
    if slot_name not in allowed:
        raise ValueError("装备槽位无效")
    hid = int(hero_id or 0)
    equip_ref = str(equipment_id or "").strip()
    if inventory_service and feature_enabled(service_id, "inventory") and equip_ref:
        validated = inventory_service.validate_equip_slot(service_id, player_id, equip_ref, slot_name)
        equip_ref = str(validated.get("item_uid") or validated.get("item_def_id") or equip_ref)
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT equipment_json FROM baas_player_heroes WHERE service_id=? AND player_id=? AND hero_id=?",
            (service_id, player_id, hid),
        ).fetchone()
        if not row:
            raise ValueError("未拥有该英雄")
        equip_map = _json_load(row["equipment_json"], {})
        equip_map[slot_name] = equip_ref
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_heroes SET equipment_json=?, updated_at=? WHERE service_id=? AND player_id=? AND hero_id=?",
            (_json_dump(equip_map), now, service_id, player_id, hid),
        )
    return {"hero_id": hid, "slot": slot_name, "equipment_id": equip_ref, "equipment": equip_map}


def team_json_from_roster(service_id: str, player_id: str, hero_ids: List[int]) -> Dict[str, Any]:
    """供 PVE/竞技场校验：从已拥有英雄构建 team JSON。"""
    roster = get_roster(service_id, player_id)
    owned = {h["hero_id"] for h in roster.get("heroes") or []}
    ids = [int(x) for x in hero_ids if int(x) in owned]
    if not ids:
        raise ValueError("阵容英雄未拥有")
    return {"heroes": ids}
