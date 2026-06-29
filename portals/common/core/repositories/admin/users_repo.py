"""User data access wrappers backed by UserRepository."""

from __future__ import annotations

from typing import Any, Dict

from data.repositories.user_repository import get_user_repository
from data.audit import log_audit

_repo = get_user_repository()


def list_users() -> Dict[str, Dict[str, Any]]:
    _repo.reload()
    return dict(_repo.list_all())


def get_user(username: str) -> Dict[str, Any] | None:
    row = _repo.find(username)
    return dict(row) if row else None


def upsert_user(username: str, record: Dict[str, Any]) -> None:
    if _repo.exists(username):
        _repo.update(username, record)
    else:
        _repo.create(username, record)


def remove_user(username: str) -> None:
    _repo.delete(username)


def verify_password(username: str, password: str) -> bool:
    import hashlib

    row = get_user(username)
    if not row or row.get("disabled"):
        return False
    digest = hashlib.sha256(password.encode()).hexdigest()
    return str(row.get("password") or "") == digest


def update_password(username: str, new_password: str) -> None:
    import hashlib

    row = get_user(username)
    if not row:
        raise KeyError(username)
    row = dict(row)
    row["password"] = hashlib.sha256(new_password.encode()).hexdigest()
    upsert_user(username, row)


def record_last_login(username: str, iso_timestamp: str) -> None:
    row = get_user(username)
    if not row:
        return
    row = dict(row)
    row["last_login"] = iso_timestamp
    upsert_user(username, row)


def save() -> None:
    _repo.save()


def audit(action: str, target: str) -> None:
    log_audit(action, target)
