"""Audit log repository wrappers."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import audit_log_db


def list_entries() -> List[Dict[str, Any]]:
    return audit_log_db
