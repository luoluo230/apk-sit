# -*- coding: utf-8 -*-
"""Verify/publish incident notifications and optional auto-rollback (P2-03 Step 2)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.db import get_cursor, init_db
from services.notify.outbound_webhook import (
    EVENT_AUTO_ROLLBACK_EXECUTED,
    EVENT_BOOTSTRAP_SMOKE_FAILED,
    EVENT_PUBLISH_FAILED,
    EVENT_VERIFY_FAILED,
    notify_release_event,
)
from services.release.release_policy_service import should_auto_rollback_on_verify_fail, should_auto_pause_gray_on_verify_fail


def _base_order_fields(order: Dict[str, Any], project_id: str = "") -> Dict[str, Any]:
    return {
        "project_id": project_id or str(order.get("project_id") or ""),
        "release_order_id": str(order.get("release_order_id") or ""),
        "env_key": str(order.get("env_key") or ""),
        "version_name": str(order.get("version_name") or ""),
        "version_code": str(order.get("version_code") or ""),
        "channel_id": str(order.get("channel_id") or ""),
        "platform": str(order.get("platform") or ""),
        "scope_id": str(order.get("scope_id") or ""),
        "bundle_id": str(order.get("bundle_id") or ""),
    }


def find_rollback_target_order(project_id: str, scope_id: str, failed_order_id: str) -> Optional[Dict[str, Any]]:
    sid = str(scope_id or "").strip()
    if not sid:
        return None
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            """
            SELECT release_order_id, bundle_id, version_name, version_code, published_at
            FROM release_orders
            WHERE project_id=? AND scope_id=? AND release_order_id!=?
              AND bundle_id IS NOT NULL AND bundle_id != ''
              AND status IN ('verified', 'published', 'rolled_back')
            ORDER BY published_at DESC
            LIMIT 1
            """,
            (project_id, sid, failed_order_id),
        ).fetchone()
    if not row:
        return None
    return {
        "release_order_id": str(row["release_order_id"] or ""),
        "bundle_id": str(row["bundle_id"] or ""),
        "version_name": str(row["version_name"] or ""),
        "version_code": str(row["version_code"] or ""),
        "published_at": str(row["published_at"] or ""),
    }


def attempt_auto_rollback_after_verify_fail(
    project_id: str,
    failed_order: Dict[str, Any],
    actor: str,
) -> Dict[str, Any]:
    order_id = str(failed_order.get("release_order_id") or "")
    target = find_rollback_target_order(project_id, str(failed_order.get("scope_id") or ""), order_id)
    if not target:
        return {"ok": False, "reason": "no_previous_bundle", "target_order_id": ""}
    from services.release.order_publish_flow import rollback_release_order

    rollback_release_order(project_id, target["release_order_id"], actor or "system:auto-rollback")
    notify_release_event(
        EVENT_AUTO_ROLLBACK_EXECUTED,
        {
            **_base_order_fields(failed_order, project_id),
            "failed_order_id": order_id,
            "rollback_target_order": target["release_order_id"],
            "rollback_target_bundle": target.get("bundle_id") or "",
            "actor": actor or "system:auto-rollback",
        },
    )
    return {
        "ok": True,
        "target_order_id": target["release_order_id"],
        "target_bundle_id": target.get("bundle_id") or "",
    }


def handle_verify_failure(
    project_id: str,
    order: Dict[str, Any],
    actor: str,
    *,
    smoke_report: Optional[Dict[str, Any]] = None,
    validation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    fields = _base_order_fields(order, project_id)
    smoke_report = smoke_report if isinstance(smoke_report, dict) else {}
    validation = validation if isinstance(validation, dict) else {}
    if smoke_report and not smoke_report.get("ok"):
        fields["smoke_error"] = str(smoke_report.get("error") or "bootstrap smoke failed")[:300]
        notify_release_event(EVENT_BOOTSTRAP_SMOKE_FAILED, {**fields, "smoke": smoke_report})
    if validation and not validation.get("ok", True):
        fields["validation_error"] = str(validation.get("error") or "validation plan failed")[:300]
    notify_release_event(EVENT_VERIFY_FAILED, {**fields, "smoke": smoke_report, "validation": validation})

    gray_pause = {"attempted": False}
    if should_auto_pause_gray_on_verify_fail(project_id, str(order.get("env_key") or "")):
        try:
            from services.release.order_publish_lifecycle import pause_gray_rollout_for_order

            reason = fields.get("smoke_error") or fields.get("validation_error") or "verify_failed"
            gray_pause = {
                "attempted": True,
                **pause_gray_rollout_for_order(project_id, order, actor, reason=str(reason)),
            }
        except Exception:
            pass

    rollback_result = {"attempted": False}
    if should_auto_rollback_on_verify_fail(project_id, str(order.get("env_key") or "")):
        rollback_result = {"attempted": True, **attempt_auto_rollback_after_verify_fail(project_id, order, actor)}
    return {
        "gray_pause": gray_pause,
        "rollback": rollback_result,
        "attempted": rollback_result.get("attempted"),
        "ok": rollback_result.get("ok"),
    }


def handle_publish_failure(project_id: str, order: Dict[str, Any], actor: str, error: str) -> None:
    notify_release_event(
        EVENT_PUBLISH_FAILED,
        {**_base_order_fields(order, project_id), "error": str(error or "")[:500], "actor": actor},
    )
