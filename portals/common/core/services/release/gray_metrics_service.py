# -*- coding: utf-8 -*-
"""Gray rollout metrics snapshots (P3-03 Wave C)."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.release.order_helpers import _decode, _json, _now_iso


def append_gray_metrics_snapshot(
    project_id: str,
    order_id: str,
    *,
    rollout_percentage: int,
    bootstrap_ok: bool | None = None,
    note: str = "",
    actor: str = "",
) -> Dict[str, Any]:
    """Append a gray metrics snapshot onto the release order payload."""
    init_db()
    snap = {
        "at": _now_iso(),
        "rollout_percentage": int(rollout_percentage),
        "bootstrap_ok": bootstrap_ok,
        "note": str(note or "").strip()[:200],
        "actor": str(actor or "").strip()[:80],
    }
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT payload FROM release_orders WHERE project_id=? AND release_order_id=?",
            (project_id, order_id),
        ).fetchone()
        if not row:
            raise ValueError("发布单不存在")
        payload = _decode(row["payload"], {}) or {}
        snaps: List[Dict[str, Any]] = list(payload.get("gray_metrics_snapshots") or [])
        snaps.append(snap)
        # Keep last 50
        payload["gray_metrics_snapshots"] = snaps[-50:]
        cur.execute(
            "UPDATE release_orders SET payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (_json(payload), _now_iso(), project_id, order_id),
        )
    return snap


def list_gray_metrics_snapshots(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = order.get("payload") if isinstance(order.get("payload"), dict) else {}
    rows = payload.get("gray_metrics_snapshots") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]
