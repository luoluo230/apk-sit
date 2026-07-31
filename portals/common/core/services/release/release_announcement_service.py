# -*- coding: utf-8 -*-
"""Sync release batch announcements to legacy GM console."""

from __future__ import annotations

import os
from typing import Any, Dict

from services.release.env_registry import env_key_to_gm_env
from services.release.release_batch_service import get_release_batch


def maybe_sync_batch_announcement(project_id: str, batch_id: str, actor: str) -> Dict[str, Any]:
    batch = get_release_batch(project_id, batch_id)
    if not batch:
        return {"synced": False, "reason": "batch_not_found"}
    announcement = dict(batch.get("announcement") or {})
    env_key = str(batch.get("env_key") or "production")
    return _sync_announcement_payload(project_id, announcement, env_key, actor, batch_id=batch_id)


def maybe_sync_order_announcement(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    from services.release.order_crud import get_release_order

    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        return {"synced": False, "reason": "order_not_found"}
    plan = dict(order.get("payload") or {})
    announcement = {
        "title": str(plan.get("announcement_title") or "").strip(),
        "body": str(plan.get("announcement_body") or "").strip(),
        "effective_at": str(plan.get("announcement_effective_at") or "").strip(),
        "audience": str(plan.get("announcement_audience") or "all").strip() or "all",
        "sync_to_gm": bool(plan.get("sync_announcement")),
    }
    env_key = str(order.get("env_key") or "production")
    return _sync_announcement_payload(project_id, announcement, env_key, actor, release_order_id=order_id)


def _sync_announcement_payload(
    project_id: str,
    announcement: Dict[str, Any],
    env_key: str,
    actor: str,
    *,
    batch_id: str = "",
    release_order_id: str = "",
) -> Dict[str, Any]:
    if not announcement.get("sync_to_gm"):
        return {"synced": False, "reason": "sync_disabled"}
    title = str(announcement.get("title") or "").strip()
    body = str(announcement.get("body") or announcement.get("content") or "").strip()
    if not title and not body:
        return {"synced": False, "reason": "empty_announcement"}
    base_url = str(os.getenv("GM_LEGACY_BASE_URL") or os.getenv("OPS_GM_BASE_URL") or "").strip()
    username = str(os.getenv("GM_LEGACY_USERNAME") or os.getenv("OPS_GM_USERNAME") or "").strip()
    password = str(os.getenv("GM_LEGACY_PASSWORD") or os.getenv("OPS_GM_PASSWORD") or "").strip()
    if not base_url:
        return {"synced": False, "reason": "gm_base_url_not_configured", "skipped": True}
    from services.legacy_gm_bridge_client import LegacyGmBridgeClient

    client = LegacyGmBridgeClient()
    form = {
        "title": title,
        "content": body,
        "effectiveTime": str(announcement.get("effective_at") or ""),
        "audience": str(announcement.get("audience") or "all"),
        "env": env_key_to_gm_env(env_key),
        "operator": actor,
        "batch_id": batch_id,
        "release_order_id": release_order_id,
        "project_id": project_id,
    }
    result = client.submit_form(
        base_url=base_url,
        username=username,
        password=password,
        path="/gm/save-announcement",
        form=form,
    )
    return {
        "synced": bool(result.get("success")),
        "message": result.get("message") or "",
        "status": result.get("status"),
        "data": result.get("data") or {},
    }
