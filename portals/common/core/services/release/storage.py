# -*- coding: utf-8 -*-
"""Transactional storage for the unified project delivery domain."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from config import DATA_DIR
from models.db import _db_lock, _get_conn, get_cursor, init_db
from utils import load_json, save_json

MANIFESTS_FILE = os.path.join(DATA_DIR, "project_release_manifests.json")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _decode(payload: str) -> Dict[str, Any]:
    try:
        value = json.loads(payload or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def load_manifests() -> List[Dict[str, Any]]:
    raw = load_json(MANIFESTS_FILE, [])
    return raw if isinstance(raw, list) else []


def save_manifests(rows: List[Dict[str, Any]]) -> None:
    save_json(MANIFESTS_FILE, rows)


def _scope_from_row(row) -> Dict[str, Any]:
    payload = _decode(row["payload"])
    payload.update(
        {
            "scope_id": row["scope_id"],
            "project_id": row["project_id"],
            "env_key": row["env_key"],
            "channel_id": row["channel_id"],
            "channel_key": row["channel_key"],
            "default_topology_id": row["default_topology_id"],
            "active_bundle_id": row["active_bundle_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    return payload


def load_scopes() -> List[Dict[str, Any]]:
    init_db()
    with _db_lock:
        rows = _get_conn().execute("SELECT * FROM release_scopes ORDER BY updated_at DESC").fetchall()
    return [_scope_from_row(row) for row in rows]


def save_scopes(rows: List[Dict[str, Any]]) -> None:
    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute("DELETE FROM release_scopes")
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("scope_id") or "").strip():
                continue
            _insert_scope(cur, row, now)


def _insert_scope(cur, row: Dict[str, Any], now: str = "") -> None:
    timestamp = now or _now_iso()
    cur.execute(
        """
        INSERT INTO release_scopes (
            scope_id, project_id, env_key, channel_id, channel_key,
            default_topology_id, active_bundle_id, status, payload, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(scope_id) DO UPDATE SET
            project_id=excluded.project_id,
            env_key=excluded.env_key,
            channel_id=excluded.channel_id,
            channel_key=excluded.channel_key,
            default_topology_id=excluded.default_topology_id,
            active_bundle_id=excluded.active_bundle_id,
            status=excluded.status,
            payload=excluded.payload,
            updated_at=excluded.updated_at
        """,
        (
            str(row.get("scope_id") or ""),
            str(row.get("project_id") or ""),
            str(row.get("env_key") or ""),
            str(row.get("channel_id") or ""),
            str(row.get("channel_key") or row.get("channel_id") or ""),
            str(row.get("default_topology_id") or ""),
            str(row.get("active_bundle_id") or ""),
            str(row.get("status") or "active"),
            json.dumps(row, ensure_ascii=False),
            str(row.get("created_at") or timestamp),
            timestamp,
        ),
    )


def _bundle_columns(row: Dict[str, Any]) -> tuple:
    client = row.get("client") if isinstance(row.get("client"), dict) else {}
    server = row.get("server") if isinstance(row.get("server"), dict) else {}
    return (
        str(row.get("bundle_id") or ""),
        str(row.get("release_order_id") or ""),
        str(row.get("project_id") or ""),
        str(row.get("scope_id") or ""),
        str(row.get("env_key") or ""),
        str(row.get("channel_id") or ""),
        str(row.get("publish_status") or ""),
        str(server.get("topology_id") or row.get("topology_id") or ""),
        str(server.get("runtime_run_id") or row.get("runtime_run_id") or ""),
        str(client.get("version_name") or row.get("version_name") or ""),
        str(client.get("version_code") or row.get("version_code") or ""),
        str(client.get("platform") or row.get("platform") or ""),
        json.dumps(row, ensure_ascii=False),
        str(row.get("published_at") or ""),
        str(row.get("published_by") or ""),
        str(row.get("created_at") or _now_iso()),
        str(row.get("updated_at") or _now_iso()),
    )


def _upsert_bundle(cur, row: Dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO release_bundles (
            bundle_id, release_order_id, project_id, scope_id, env_key, channel_id,
            publish_status, topology_id, runtime_run_id, version_name, version_code,
            platform, payload, published_at, published_by, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(bundle_id) DO UPDATE SET
            release_order_id=excluded.release_order_id,
            publish_status=excluded.publish_status,
            topology_id=excluded.topology_id,
            runtime_run_id=excluded.runtime_run_id,
            payload=excluded.payload,
            published_at=excluded.published_at,
            published_by=excluded.published_by,
            updated_at=excluded.updated_at
        """,
        _bundle_columns(row),
    )


def load_bundles() -> List[Dict[str, Any]]:
    init_db()
    with _db_lock:
        rows = _get_conn().execute(
            "SELECT payload FROM release_bundles ORDER BY COALESCE(published_at, created_at) DESC"
        ).fetchall()
    return [_decode(row["payload"]) for row in rows]


def find_manifest(project_id: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    for row in load_manifests():
        if isinstance(row, dict) and str(row.get("project_id") or "").strip() == pid:
            return row
    return {}


def find_scope(scope_id: str) -> Dict[str, Any]:
    sid = str(scope_id or "").strip()
    if not sid:
        return {}
    init_db()
    with _db_lock:
        row = _get_conn().execute("SELECT * FROM release_scopes WHERE scope_id=?", (sid,)).fetchone()
    return _scope_from_row(row) if row else {}


def upsert_scope(row: Dict[str, Any]) -> Dict[str, Any]:
    if not str(row.get("scope_id") or "").strip():
        return {}
    init_db()
    with get_cursor() as cur:
        _insert_scope(cur, row)
    return find_scope(str(row.get("scope_id") or ""))
