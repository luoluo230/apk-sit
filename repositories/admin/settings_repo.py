"""System settings repository wrappers."""

from __future__ import annotations

from models.data import get_system_config, set_system_config, log_audit


def get(key: str):
    return get_system_config(key)


def set_value(key: str, value: str, vtype: str, desc: str, username: str) -> None:
    set_system_config(key, value, vtype, desc, username)


def audit(action: str, target: str = "") -> None:
    log_audit(action, target)
