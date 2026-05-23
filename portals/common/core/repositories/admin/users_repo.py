"""User data access wrappers."""

from __future__ import annotations

from typing import Dict, Any

from models.data import users_db, save_users, log_audit


def list_users() -> Dict[str, Dict[str, Any]]:
    return users_db


def get_user(username: str) -> Dict[str, Any] | None:
    return users_db.get(username)


def upsert_user(username: str, record: Dict[str, Any]) -> None:
    users_db[username] = record
    save_users()


def remove_user(username: str) -> None:
    users_db.pop(username, None)
    save_users()


def save() -> None:
    save_users()


def audit(action: str, target: str) -> None:
    log_audit(action, target)
