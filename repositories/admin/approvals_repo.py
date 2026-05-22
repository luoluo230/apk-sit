"""Approval and notification repository wrappers."""

from __future__ import annotations

from typing import Tuple, Any

from models.data import (
    approvals_db,
    APPROVAL_TYPES,
    create_approval,
    approve_or_reject,
    add_notification,
    log_audit,
)
from services.player_content import (
    set_news_publish_state,
    set_welfare_publish_state,
    set_forum_post_publish_state,
)


def list_approval_types():
    return APPROVAL_TYPES


def create(atype: str, username: str, target_type: str, target_id: str, reason: str, project_id: str = "") -> str:
    return create_approval(atype, username, target_type, target_id, reason, project_id=project_id)


def decide(aid: str, username: str, action: str, comment: str) -> Tuple[bool, str | None]:
    return approve_or_reject(aid, username, action, comment)


def find_approval(aid: str) -> Any:
    for a in approvals_db:
        if a.get("id") == aid:
            return a
    return None


def notify(user: str, kind: str, title: str, content: str, link: str, ref_id: str, domain: str) -> None:
    add_notification(user, kind, title, content, link, ref_id, domain)


def sync_publish_state(approval_type: str, target_id: str, status: str, approval_id: str) -> None:
    if approval_type == "news_publish":
        set_news_publish_state(target_id, status, approval_id)
    elif approval_type == "welfare_publish":
        set_welfare_publish_state(target_id, status, approval_id)
    elif approval_type == "forum_post_publish":
        set_forum_post_publish_state(target_id, status, approval_id)


def audit(action: str, target: str) -> None:
    log_audit(action, target)
