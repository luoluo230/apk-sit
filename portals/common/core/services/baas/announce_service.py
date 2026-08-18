# -*- coding: utf-8 -*-
"""Announcement feature."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config


def list_active(service_id: str) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "announce"):
        return []
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT * FROM baas_announcements
            WHERE service_id=? AND status='published'
              AND (effective_at='' OR effective_at<=?)
              AND (expires_at='' OR expires_at>?)
            ORDER BY effective_at DESC, updated_at DESC
            """,
            (service_id, now, now),
        ).fetchall()
    return [_row(r) for r in rows]


def admin_list(service_id: str) -> List[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM baas_announcements WHERE service_id=? ORDER BY updated_at DESC",
            (service_id,),
        ).fetchall()
    return [_row(r) for r in rows]


def save_announcement(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    ann_id = str(payload.get("announcement_id") or new_id("ann_"))
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_announcements (
                announcement_id, service_id, title, body, audience, effective_at, expires_at,
                status, created_by, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(announcement_id) DO UPDATE SET
                title=excluded.title, body=excluded.body, audience=excluded.audience,
                effective_at=excluded.effective_at, expires_at=excluded.expires_at,
                status=excluded.status, updated_at=excluded.updated_at
            """,
            (
                ann_id,
                service_id,
                str(payload.get("title") or "").strip(),
                str(payload.get("body") or "").strip(),
                str(payload.get("audience") or get_feature_config(service_id, "announce").get("audience") or "all"),
                str(payload.get("effective_at") or ""),
                str(payload.get("expires_at") or ""),
                str(payload.get("status") or "published"),
                actor,
                now,
                now,
            ),
        )
    rows = admin_list(service_id)
    return next((r for r in rows if r["announcement_id"] == ann_id), {})


def _row(row) -> Dict[str, Any]:
    return {
        "announcement_id": row["announcement_id"],
        "title": row["title"],
        "body": row["body"],
        "audience": row["audience"],
        "effective_at": row["effective_at"],
        "expires_at": row["expires_at"],
        "status": row["status"],
        "updated_at": row["updated_at"],
    }
