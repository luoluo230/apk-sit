# -*- coding: utf-8 -*-
"""Promotion approval helpers — QA sign-off before high-env artifact promotion."""

from __future__ import annotations

import uuid
from typing import Any, Dict

from services.release.order_helpers import _decode
from services.release.release_policy_service import get_promotion_approval_tiers


def is_promoted_release_order(order: Dict[str, Any]) -> bool:
    payload = order.get("payload") if isinstance(order.get("payload"), dict) else _decode(order.get("payload"), {})
    promotion = (payload or {}).get("promotion") or {}
    return bool(promotion.get("promoted_from_bundle_id"))


def seed_release_order_promotion_approvals(
    cur,
    order_id: str,
    project_id: str,
    target_env: str,
    actor: str,
    now: str,
) -> None:
    for tier in get_promotion_approval_tiers(project_id, target_env):
        cur.execute(
            """
            INSERT INTO release_approvals (
                approval_id, release_order_id, status, requested_by, approved_by, note, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                f"ra-{uuid.uuid4().hex[:12]}",
                order_id,
                "pending",
                actor,
                "",
                f"tier:{tier}",
                now,
                now,
            ),
        )


def notify_promotion_approval_pending(project_id: str, order_id: str, order: Dict[str, Any], actor: str) -> None:
    from services.release.order_publish_flow import _notify_awaiting_approval

    _notify_awaiting_approval(project_id, order_id, order, actor)
