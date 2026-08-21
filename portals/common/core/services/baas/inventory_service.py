# -*- coding: utf-8 -*-
"""玩家背包：道具/装备独立存储，供 hero.equip 与商店发放复用。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config


def _item_defs(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in cfg.get("item_defs") or []:
        iid = str(row.get("id") or "").strip()
        if iid:
            out[iid] = dict(row)
    return out


def list_inventory(service_id: str, player_id: str, *, item_type: str = "") -> Dict[str, Any]:
    if not feature_enabled(service_id, "inventory"):
        raise ValueError("背包功能未启用")
    cfg = get_feature_config(service_id, "inventory")
    defs = _item_defs(cfg)
    filter_type = str(item_type or "").strip()
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT item_uid, item_def_id, quantity, meta_json, updated_at
            FROM baas_player_inventory
            WHERE service_id=? AND player_id=? AND quantity > 0
            ORDER BY updated_at DESC
            """,
            (service_id, player_id),
        ).fetchall()
    items = []
    for row in rows:
        def_id = str(row["item_def_id"] or "")
        meta = defs.get(def_id, {})
        itype = str(meta.get("type") or "item")
        if filter_type and itype != filter_type:
            continue
        items.append({
            "item_uid": row["item_uid"],
            "item_def_id": def_id,
            "name": meta.get("name", def_id),
            "type": itype,
            "slot": meta.get("slot", ""),
            "quantity": int(row["quantity"] or 0),
            "meta": _json_load(row["meta_json"], {}),
        })
    return {"items": items, "count": len(items)}


def grant_item(
    cur,
    service_id: str,
    player_id: str,
    item_def_id: str,
    *,
    quantity: int = 1,
    meta: Optional[Dict[str, Any]] = None,
    stack_limit: int = 9999,
) -> Dict[str, Any]:
    """内部发放：商店/IAP/邮件/GM 调用。"""
    cfg = get_feature_config(service_id, "inventory")
    defs = _item_defs(cfg)
    def_id = str(item_def_id or "").strip()
    if def_id not in defs:
        raise ValueError("道具配置不存在")
    qty = max(1, int(quantity or 1))
    limit = int(defs[def_id].get("stack_limit") or stack_limit or 9999)
    now = _now_iso()
    row = cur.execute(
        """
        SELECT item_uid, quantity FROM baas_player_inventory
        WHERE service_id=? AND player_id=? AND item_def_id=? AND meta_json='{}'
        LIMIT 1
        """,
        (service_id, player_id, def_id),
    ).fetchone()
    if row:
        new_qty = min(limit, int(row["quantity"] or 0) + qty)
        cur.execute(
            "UPDATE baas_player_inventory SET quantity=?, updated_at=? WHERE item_uid=?",
            (new_qty, now, row["item_uid"]),
        )
        return {"item_uid": row["item_uid"], "item_def_id": def_id, "quantity": new_qty, "granted": qty}
    uid = new_id("item_")
    cur.execute(
        """
        INSERT INTO baas_player_inventory (item_uid, service_id, player_id, item_def_id, quantity, meta_json, updated_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (uid, service_id, player_id, def_id, min(limit, qty), _json_dump(meta or {}), now),
    )
    return {"item_uid": uid, "item_def_id": def_id, "quantity": min(limit, qty), "granted": qty}


def consume_item(service_id: str, player_id: str, item_uid: str, *, quantity: int = 1) -> Dict[str, Any]:
    if not feature_enabled(service_id, "inventory"):
        raise ValueError("背包功能未启用")
    uid = str(item_uid or "").strip()
    cost = max(1, int(quantity or 1))
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_inventory WHERE item_uid=? AND service_id=? AND player_id=?",
            (uid, service_id, player_id),
        ).fetchone()
        if not row:
            raise ValueError("道具不存在")
        have = int(row["quantity"] or 0)
        if have < cost:
            raise ValueError("道具数量不足")
        remain = have - cost
        now = _now_iso()
        if remain <= 0:
            cur.execute("DELETE FROM baas_player_inventory WHERE item_uid=?", (uid,))
        else:
            cur.execute(
                "UPDATE baas_player_inventory SET quantity=?, updated_at=? WHERE item_uid=?",
                (remain, now, uid),
            )
    return {"item_uid": uid, "consumed": cost, "remaining": max(0, remain)}


def resolve_equipment_item(service_id: str, player_id: str, equipment_ref: str) -> Dict[str, Any]:
    """解析装备引用：item_uid 或 item_def_id（自动取首个可用堆叠）。"""
    ref = str(equipment_ref or "").strip()
    if not ref:
        raise ValueError("装备引用为空")
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_inventory WHERE item_uid=? AND service_id=? AND player_id=? AND quantity > 0",
            (ref, service_id, player_id),
        ).fetchone()
        if row:
            return {"item_uid": row["item_uid"], "item_def_id": row["item_def_id"]}
        row = cur.execute(
            """
            SELECT * FROM baas_player_inventory
            WHERE service_id=? AND player_id=? AND item_def_id=? AND quantity > 0
            ORDER BY updated_at LIMIT 1
            """,
            (service_id, player_id, ref),
        ).fetchone()
        if row:
            return {"item_uid": row["item_uid"], "item_def_id": row["item_def_id"]}
    raise ValueError("背包中未找到该装备")


def validate_equip_slot(service_id: str, player_id: str, equipment_ref: str, slot: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "inventory"):
        return {"item_def_id": str(equipment_ref or ""), "validated": False}
    cfg = get_feature_config(service_id, "inventory")
    defs = _item_defs(cfg)
    resolved = resolve_equipment_item(service_id, player_id, equipment_ref)
    def_id = str(resolved["item_def_id"])
    meta = defs.get(def_id, {})
    if str(meta.get("type") or "") != "equipment":
        raise ValueError("该道具不可装备")
    item_slot = str(meta.get("slot") or "")
    slot_name = str(slot or "").strip()
    if item_slot and slot_name and item_slot != slot_name:
        raise ValueError("装备槽位不匹配")
    return {**resolved, "slot": slot_name or item_slot, "validated": True}
