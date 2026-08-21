# -*- coding: utf-8 -*-
"""英雄背包：拥有、升级、装备（剑与远征式养成基础）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
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
            SELECT hero_id, level, exp, equipment_json, updated_at
            FROM baas_player_heroes WHERE service_id=? AND player_id=?
            ORDER BY hero_id
            """,
            (service_id, player_id),
        ).fetchall()
    heroes = []
    for row in rows:
        hid = int(row["hero_id"])
        meta = defs.get(hid, {})
        heroes.append({
            "hero_id": hid,
            "name": meta.get("name", f"Hero{hid}"),
            "level": int(row["level"] or 1),
            "exp": int(row["exp"] or 0),
            "equipment": _json_load(row["equipment_json"], {}),
            "role": meta.get("role", ""),
            "base_power": int(meta.get("base_power") or 0),
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
        return {"hero_id": hid, "duplicate": True, "shards": shards, "action": "converted_shards"}
    cur.execute(
        """
        INSERT INTO baas_player_heroes (service_id, player_id, hero_id, level, exp, equipment_json, updated_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (service_id, player_id, hid, 1, 0, "{}", now),
    )
    return {"hero_id": hid, "duplicate": False, "level": 1, "action": "granted"}


def level_up(service_id: str, player_id: str, hero_id: int) -> Dict[str, Any]:
    if not feature_enabled(service_id, "hero"):
        raise ValueError("英雄系统未启用")
    cfg = get_feature_config(service_id, "hero")
    max_level = int(cfg.get("max_level") or 100)
    cost_gold = int(cfg.get("level_cost_gold") or 100)
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
        debit_wallet(cur, service_id, player_id, "gold", cost_gold * level)
        level += 1
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_heroes SET level=?, updated_at=? WHERE service_id=? AND player_id=? AND hero_id=?",
            (level, now, service_id, player_id, hid),
        )
    return {"hero_id": hid, "level": level, "spent_gold": cost_gold * (level - 1)}


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
