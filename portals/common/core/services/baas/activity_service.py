# -*- coding: utf-8 -*-
"""In-game scheduled activities with player gate rules."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled


def _row(row) -> Dict[str, Any]:
    return {
        "activity_id": row["activity_id"],
        "service_id": row["service_id"],
        "title": row["title"],
        "activity_type": row["activity_type"],
        "starts_at": row["starts_at"],
        "ends_at": row["ends_at"],
        "gates": _json_load(row["gates_json"], {}),
        "payload": _json_load(row["payload_json"], {}),
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_active_for_player(service_id: str, player_profile: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "activity"):
        return []
    now = _now_iso()
    profile = player_profile or {}
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT * FROM baas_activities
            WHERE service_id=? AND status='published'
              AND (starts_at='' OR starts_at<=?)
              AND (ends_at='' OR ends_at>?)
            ORDER BY starts_at DESC, updated_at DESC
            """,
            (service_id, now, now),
        ).fetchall()
    out = []
    for row in rows:
        item = _row(row)
        gates = item.get("gates") or {}
        level_min = int(gates.get("level_min") or 0)
        vip_min = int(gates.get("vip_min") or 0)
        recharge_min = int(gates.get("recharge_min") or 0)
        level = int(profile.get("level") or profile.get("Level") or 0)
        vip = int(profile.get("vip_level") or profile.get("vip") or 0)
        recharge = int(profile.get("recharge_total") or profile.get("recharge") or 0)
        if level < level_min or vip < vip_min or recharge < recharge_min:
            continue
        out.append(item)
    return out


def admin_list(service_id: str) -> List[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM baas_activities WHERE service_id=? ORDER BY updated_at DESC",
            (service_id,),
        ).fetchall()
    return [_row(r) for r in rows]


def save_activity(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    aid = str(payload.get("activity_id") or new_id("act_"))
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_activities (
                activity_id, service_id, title, activity_type, starts_at, ends_at,
                gates_json, payload_json, status, created_by, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(activity_id) DO UPDATE SET
                title=excluded.title,
                activity_type=excluded.activity_type,
                starts_at=excluded.starts_at,
                ends_at=excluded.ends_at,
                gates_json=excluded.gates_json,
                payload_json=excluded.payload_json,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                aid,
                service_id,
                str(payload.get("title") or "").strip(),
                str(payload.get("activity_type") or "event").strip(),
                str(payload.get("starts_at") or ""),
                str(payload.get("ends_at") or ""),
                _json_dump(payload.get("gates") if isinstance(payload.get("gates"), dict) else {}),
                _json_dump(payload.get("payload") if isinstance(payload.get("payload"), dict) else {}),
                str(payload.get("status") or "published"),
                actor,
                now,
                now,
            ),
        )
    return next((r for r in admin_list(service_id) if r["activity_id"] == aid), {"activity_id": aid})
