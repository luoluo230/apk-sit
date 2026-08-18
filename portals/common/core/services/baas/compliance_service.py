# -*- coding: utf-8 -*-
"""Phase 4: anti-addiction / compliance."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso
from services.baas.service_crud import feature_enabled, get_feature_config


def session_start(service_id: str, player_id: str, *, real_name_verified: bool = False) -> Dict[str, Any]:
    if not feature_enabled(service_id, "compliance"):
        return {"allowed": True, "reason": "compliance_disabled"}
    cfg = get_feature_config(service_id, "compliance")
    if not cfg.get("enabled"):
        return {"allowed": True, "reason": "compliance_disabled"}
    if cfg.get("require_real_name") and not real_name_verified:
        return {"allowed": False, "reason": "real_name_required"}
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_compliance_sessions (service_id, player_id, started_at, last_heartbeat_at, total_minutes, payload_json)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id) DO UPDATE SET
                started_at=excluded.started_at, last_heartbeat_at=excluded.last_heartbeat_at,
                total_minutes=0, payload_json=excluded.payload_json
            """,
            (service_id, player_id, now, now, 0, _json_dump({"real_name_verified": real_name_verified})),
        )
    return {"allowed": True, "session_started_at": now}


def heartbeat(service_id: str, player_id: str, *, minutes_played: int = 1) -> Dict[str, Any]:
    if not feature_enabled(service_id, "compliance"):
        return {"allowed": True}
    cfg = get_feature_config(service_id, "compliance")
    if not cfg.get("enabled"):
        return {"allowed": True}
    limit = int(cfg.get("daily_limit_minutes") or 120)
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_compliance_sessions WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
        total = int(row["total_minutes"] or 0) + int(minutes_played) if row else int(minutes_played)
        if _in_curfew(cfg):
            return {"allowed": False, "reason": "curfew", "total_minutes": total}
        if total >= limit:
            return {"allowed": False, "reason": "daily_limit", "total_minutes": total}
        cur.execute(
            """
            INSERT INTO baas_compliance_sessions (service_id, player_id, started_at, last_heartbeat_at, total_minutes, payload_json)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id) DO UPDATE SET
                last_heartbeat_at=excluded.last_heartbeat_at, total_minutes=excluded.total_minutes
            """,
            (service_id, player_id, now, now, total, row["payload_json"] if row else "{}"),
        )
    return {"allowed": True, "total_minutes": total}


def verify_real_name(service_id: str, player_id: str, *, name: str, id_number: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "compliance"):
        raise ValueError("防沉迷未启用")
    # Simulated verification for dev; production would call third-party API.
    if len(str(id_number or "")) < 6:
        raise ValueError("证件号无效")
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE baas_compliance_sessions SET payload_json=?, last_heartbeat_at=?
            WHERE service_id=? AND player_id=?
            """,
            (_json_dump({"real_name_verified": True, "name": name}), now, service_id, player_id),
        )
    return {"verified": True, "verified_at": now}


def _in_curfew(cfg: Dict[str, Any]) -> bool:
    start = str(cfg.get("curfew_start") or "22:00")
    end = str(cfg.get("curfew_end") or "08:00")
    now = datetime.utcnow().strftime("%H:%M")
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end
