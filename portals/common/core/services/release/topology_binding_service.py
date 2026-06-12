# -*- coding: utf-8 -*-
"""Project-owned topology binding matrix backed by SQLite."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.db import _db_lock, _get_conn, get_cursor, init_db
from services.release.env_registry import normalize_release_env_key


def _now_iso() -> str:
    return datetime.now().isoformat()


def _binding_level(env_key: str, channel_id: str, version_name: str) -> str:
    if version_name:
        return "version"
    if env_key and channel_id:
        return "env_channel"
    return "project_default"


def _level_label(level: str) -> str:
    return {
        "project_default": "项目默认",
        "env_channel": "环境 / 渠道",
        "version": "大版本覆盖",
    }.get(str(level or "").strip(), "未定义")


def normalize_binding_row(payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    row = dict(payload or {})
    env_key = normalize_release_env_key(row.get("env_key") or "") if row.get("env_key") else ""
    channel_id = str(row.get("channel_id") or "").strip()
    version_name = str(row.get("version_name") or "").strip()
    level = _binding_level(env_key, channel_id, version_name)
    return {
        "binding_id": str(row.get("binding_id") or f"tb-{uuid.uuid4().hex[:10]}").strip(),
        "project_id": str(row.get("project_id") or "").strip(),
        "env_key": env_key,
        "channel_id": channel_id,
        "version_name": version_name,
        "topology_id": str(row.get("topology_id") or "").strip(),
        "level": level,
        "level_label": _level_label(level),
        "status": str(row.get("status") or "active").strip() or "active",
        "note": str(row.get("note") or "").strip(),
        "created_at": str(row.get("created_at") or _now_iso()),
        "updated_at": _now_iso(),
        "updated_by": str(actor or row.get("updated_by") or "system").strip() or "system",
    }


def _row_from_db(row) -> Dict[str, Any]:
    return {
        "binding_id": row["binding_id"],
        "project_id": row["project_id"],
        "env_key": row["env_key"],
        "channel_id": row["channel_id"],
        "version_name": row["version_name"],
        "topology_id": row["topology_id"],
        "level": row["level"],
        "level_label": _level_label(row["level"]),
        "status": row["status"],
        "note": row["note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
    }


def list_topology_bindings(project_id: str = "") -> List[Dict[str, Any]]:
    init_db()
    sql = "SELECT * FROM topology_bindings"
    params: List[str] = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(str(project_id).strip())
    sql += """
        ORDER BY CASE level WHEN 'project_default' THEN 0 WHEN 'env_channel' THEN 1 ELSE 2 END,
        env_key, channel_id, version_name, updated_at DESC
    """
    with _db_lock:
        rows = _get_conn().execute(sql, params).fetchall()
    return [_row_from_db(row) for row in rows]


def upsert_topology_binding(payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    row = normalize_binding_row(payload, actor=actor)
    if not row["project_id"]:
        raise ValueError("project_id required")
    if not row["topology_id"]:
        raise ValueError("topology_id required")
    if row["level"] == "env_channel" and (not row["env_key"] or not row["channel_id"]):
        raise ValueError("env_channel binding requires env_key and channel_id")
    if row["level"] == "version" and (not row["env_key"] or not row["channel_id"] or not row["version_name"]):
        raise ValueError("version binding requires env_key, channel_id and version_name")
    init_db()
    with get_cursor() as cur:
        existing = cur.execute(
            """
            SELECT binding_id, created_at FROM topology_bindings
            WHERE project_id=? AND env_key=? AND channel_id=? AND version_name=?
            """,
            (row["project_id"], row["env_key"], row["channel_id"], row["version_name"]),
        ).fetchone()
        if existing:
            row["binding_id"] = existing["binding_id"]
            row["created_at"] = existing["created_at"]
        cur.execute(
            """
            INSERT INTO topology_bindings (
                binding_id, project_id, env_key, channel_id, version_name, topology_id,
                level, status, note, payload, created_at, updated_at, updated_by
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(binding_id) DO UPDATE SET
                topology_id=excluded.topology_id, level=excluded.level, status=excluded.status,
                note=excluded.note, payload=excluded.payload, updated_at=excluded.updated_at,
                updated_by=excluded.updated_by
            """,
            (
                row["binding_id"], row["project_id"], row["env_key"], row["channel_id"],
                row["version_name"], row["topology_id"], row["level"], row["status"],
                row["note"], json.dumps(row, ensure_ascii=False), row["created_at"],
                row["updated_at"], row["updated_by"],
            ),
        )
    return row


def delete_topology_binding(binding_id: str, *, actor: str = "") -> bool:
    del actor
    init_db()
    with get_cursor() as cur:
        cur.execute("DELETE FROM topology_bindings WHERE binding_id=?", (str(binding_id or "").strip(),))
        return cur.rowcount > 0


def resolve_topology_binding(
    project_id: str,
    env_key: str,
    channel_id: str,
    *,
    version_name: str = "",
    fallback_topology_id: str = "",
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    ek = normalize_release_env_key(env_key) if env_key else ""
    cid = str(channel_id or "").strip()
    vname = str(version_name or "").strip()
    rows = [row for row in list_topology_bindings(pid) if row.get("status") == "active"]

    def _match(level: str) -> Optional[Dict[str, Any]]:
        for row in rows:
            if row.get("level") != level:
                continue
            if level == "project_default":
                return row
            if level == "env_channel" and row.get("env_key") == ek and row.get("channel_id") == cid:
                return row
            if level == "version" and row.get("env_key") == ek and row.get("channel_id") == cid and row.get("version_name") == vname:
                return row
        return None

    matched = (_match("version") if vname else None) or _match("env_channel") or _match("project_default")
    if matched:
        return {
            "topology_id": matched["topology_id"],
            "binding_source": matched["level"],
            "binding_source_label": matched["level_label"],
            "binding": matched,
        }
    if fallback_topology_id:
        return {
            "topology_id": str(fallback_topology_id).strip(),
            "binding_source": "scope_default",
            "binding_source_label": "Scope 默认",
            "binding": {},
        }
    return {"topology_id": "", "binding_source": "", "binding_source_label": "", "binding": {}}
