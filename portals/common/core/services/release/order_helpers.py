# -*- coding: utf-8 -*-
"""Shared helpers for release order modules."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple

from models.data import get_channel_by_id, project_versions_db


def _now_iso() -> str:
    return datetime.now().isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _decode(value: str, default=None):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


def _order_id() -> str:
    return f"ro-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _bundle_id(scope_id: str) -> str:
    slug = str(scope_id or "scope").replace(":", "-")[:40]
    return f"rb-{datetime.now().strftime('%Y%m%d')}-{slug}-{uuid.uuid4().hex[:6]}"


def _event(cur, order_id: str, event_type: str, actor: str, from_status: str = "", to_status: str = "", payload=None):
    cur.execute(
        """
        INSERT INTO release_order_events (
            release_order_id, event_type, from_status, to_status, actor, payload, created_at
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (order_id, event_type, from_status, to_status, actor, _json(payload or {}), _now_iso()),
    )


def _find_version(project_id: str, version_id: str = "", version_code: str = "") -> Dict[str, Any]:
    rows = project_versions_db.get(project_id) or []
    vid = str(version_id or "").strip()
    vcode = str(version_code or "").strip()
    if vid:
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("id") or "") == vid:
                return dict(row)
        return {}
    if vcode:
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("version_code") or "") == vcode:
                return dict(row)
    return {}


def _artifact_rows(version: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    mapping = [
        ("apk", "apk_url", "apk_path"),
        ("resource", "resource_url", "resource_path"),
        ("config", "config_url", "config_path"),
        ("code", "code_url", "code_path"),
    ]
    rows = []
    for artifact_type, url_key, path_key in mapping:
        url = str(version.get(url_key) or "")
        path = str(version.get(path_key) or "")
        rows.append((artifact_type, url, path))
    return rows


def _channel_name(channel_id: str) -> str:
    row = get_channel_by_id(channel_id) or {}
    return str(row.get("name") or row.get("apk_subdir") or channel_id)
