"""Notification service layer."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from repositories.admin import notifications_repo
from services.admin.envelope import ok, fail, attach_legacy_error


def list_user_notifications(username: str, type_filter: str = "", limit: int = 200) -> Tuple[Dict[str, Any], int]:
    rows = notifications_repo.list_for_user(username, type_filter.strip() or None, limit=limit)
    return ok({"notifications": rows}, legacy={"notifications": rows}), 200


def mark_read(username: str, nid: str) -> Tuple[Dict[str, Any], int]:
    if notifications_repo.mark_read(username, nid):
        return ok({"id": nid}, legacy={"success": True}), 200
    return attach_legacy_error(fail("未找到", code="not_found", legacy={"error": "未找到"})), 404


def mark_all_read(username: str) -> Tuple[Dict[str, Any], int]:
    count = notifications_repo.mark_all_read(username)
    return ok({"updated": count}, legacy={"success": True}), 200
