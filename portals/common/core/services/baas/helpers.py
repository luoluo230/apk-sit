# -*- coding: utf-8 -*-
"""Shared BaaS helpers."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from models.data import projects_db


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _json_load(raw: Any, default=None):
    if default is None:
        default = {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}") if raw else dict(default)
    except (TypeError, json.JSONDecodeError):
        return dict(default)


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def generate_api_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_api_secret(secret: str) -> str:
    return hashlib.sha256(str(secret or "").encode("utf-8")).hexdigest()


def verify_api_secret(secret: str, stored_hash: str) -> bool:
    if not secret or not stored_hash:
        return False
    return hash_api_secret(secret) == stored_hash


def new_player_token() -> str:
    return secrets.token_urlsafe(24)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}" if prefix else uuid.uuid4().hex


from services.server_mode import is_casual_baas_project, project_server_mode  # noqa: F401 — re-export
from server_frameworks.credentials import resolve_project_id as resolve_project_by_game_credentials  # noqa: F401


def token_expiry(hours: int) -> str:
    return (datetime.utcnow() + timedelta(hours=max(1, int(hours or 168)))).replace(microsecond=0).isoformat() + "Z"


def parse_bearer_token(auth_header: str) -> str:
    raw = str(auth_header or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return ""


def row_to_service(row) -> Dict[str, Any]:
    if not row:
        return {}
    flags = _json_load(row["feature_flags"], {})
    keys = row.keys() if hasattr(row, "keys") else []
    disabled = bool(row["disabled"]) if "disabled" in keys else False
    status = str(row["status"] or "active")
    if disabled and status == "active":
        status = "disabled"
    return {
        "service_id": row["service_id"],
        "project_id": row["project_id"],
        "env_key": row["env_key"],
        "name": row["name"],
        "description": str(row["description"] or "") if "description" in keys else "",
        "icon_url": str(row["icon_url"] or "") if "icon_url" in keys else "",
        "disabled": disabled,
        "status": status,
        "feature_flags": flags,
        "config_version": int(row["config_version"] or 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "has_api_secret": bool(row["api_secret_hash"]),
    }
