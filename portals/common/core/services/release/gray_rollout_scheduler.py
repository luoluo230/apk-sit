# -*- coding: utf-8 -*-
"""Background gray rollout automation: auto-expand after observation window."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        return None


def _plan(order: Dict[str, Any]) -> Dict[str, Any]:
    payload = order.get("payload") if isinstance(order.get("payload"), dict) else {}
    return payload if isinstance(payload, dict) else {}


def _should_auto_expand(order: Dict[str, Any], bundle: Dict[str, Any]) -> bool:
    if str(order.get("status") or "") != "published":
        return False
    plan = _plan(order)
    if str(plan.get("release_strategy") or bundle.get("release_strategy") or "standard").lower() != "gray":
        return False
    action = str(plan.get("gray_success_action") or bundle.get("gray_success_action") or "manual").strip().lower()
    if action != "automatic":
        return False
    client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
    try:
        rollout = int(
            client.get("rollout_percentage")
            if client.get("rollout_percentage") is not None
            else bundle.get("rollout_percentage")
            if bundle.get("rollout_percentage") is not None
            else plan.get("gray_ratio")
            if plan.get("gray_ratio") not in (None, "")
            else 100
        )
    except (TypeError, ValueError):
        rollout = 100
    if rollout >= 100:
        return False
    duration_raw = plan.get("gray_duration") or bundle.get("gray_duration") or ""
    try:
        minutes = max(1, int(duration_raw))
    except (TypeError, ValueError):
        minutes = 30
    published_at = _parse_iso(str(order.get("published_at") or bundle.get("published_at") or ""))
    if not published_at:
        return False
    return datetime.now() >= published_at + timedelta(minutes=minutes)


def run_gray_rollout_tick(*, actor: str = "system:gray-scheduler") -> Dict[str, Any]:
    """Scan published gray orders and auto-expand to 100% when due."""
    from models.db import get_cursor, init_db
    from services.release.order_publish_flow import expand_gray_rollout
    from services.release.order_helpers import _decode

    init_db()
    expanded: List[str] = []
    skipped_hold = 0
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT project_id, release_order_id, status, payload, published_at, bundle_id
            FROM release_orders
            WHERE status='published' AND bundle_id IS NOT NULL AND bundle_id != ''
            """
        ).fetchall()
    for row in rows or []:
        order = {
            "project_id": row["project_id"],
            "release_order_id": row["release_order_id"],
            "status": row["status"],
            "payload": _decode(row["payload"], {}) or {},
            "published_at": row["published_at"],
            "bundle_id": row["bundle_id"],
        }
        plan = _plan(order)
        action = str(plan.get("gray_success_action") or "manual").strip().lower()
        if action == "hold":
            skipped_hold += 1
            continue
        bundle_row = None
        with get_cursor() as cur:
            bundle_row = cur.execute(
                "SELECT payload FROM release_bundles WHERE bundle_id=?",
                (str(order.get("bundle_id") or ""),),
            ).fetchone()
        bundle = _decode(bundle_row["payload"], {}) if bundle_row else {}
        if not _should_auto_expand(order, bundle):
            continue
        try:
            expand_gray_rollout(
                str(order["project_id"]),
                str(order["release_order_id"]),
                actor,
                target_ratio=100,
            )
            expanded.append(str(order["release_order_id"]))
        except Exception as exc:
            logger.warning("gray auto-expand failed for %s: %s", order.get("release_order_id"), exc)
    return {"expanded": expanded, "expanded_count": len(expanded), "skipped_hold": skipped_hold}
