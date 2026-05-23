"""Notification data access wrappers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from models.data import notifications_db, get_notifications_for_user, save_notifications


def list_for_user(username: str, type_filter: str | None = None, limit: int = 200) -> List[Dict[str, Any]]:
    return get_notifications_for_user(username, type_filter or None, limit=limit)


def mark_read(username: str, nid: str) -> bool:
    for item in notifications_db:
        if item.get("id") == nid and item.get("user") == username:
            item["read_at"] = datetime.now().isoformat()
            save_notifications()
            return True
    return False


def mark_all_read(username: str) -> int:
    count = 0
    now = datetime.now().isoformat()
    for item in notifications_db:
        if item.get("user") == username and not item.get("read_at"):
            item["read_at"] = now
            count += 1
    if count:
        save_notifications()
    return count
