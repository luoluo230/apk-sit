# -*- coding: utf-8 -*-
"""Server release order persistence (P2-01)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db


def _decode_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default
    return default


def upsert_release(row: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    rid = str(row.get("server_release_id") or "").strip()
    if not rid:
        raise ValueError("server_release_id 必填")
    target_services = row.get("target_services") if isinstance(row.get("target_services"), list) else []
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO server_release_orders (
                server_release_id, project_id, env_key, topology_id, artifact_id,
                status, target_services, payload, created_by, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(server_release_id) DO UPDATE SET
                project_id=excluded.project_id,
                env_key=excluded.env_key,
                topology_id=excluded.topology_id,
                artifact_id=excluded.artifact_id,
                status=excluded.status,
                target_services=excluded.target_services,
                payload=excluded.payload,
                updated_at=excluded.updated_at
            """,
            (
                rid,
                str(row.get("project_id") or ""),
                str(row.get("env_key") or ""),
                str(row.get("topology_id") or ""),
                str(row.get("artifact_id") or ""),
                str(row.get("status") or "draft"),
                json.dumps(target_services, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                str(row.get("created_by") or ""),
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
            ),
        )
    return get_release(rid) or {"server_release_id": rid}


def get_release(server_release_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    rid = str(server_release_id or "").strip()
    if not rid:
        return None
    with get_cursor() as cur:
        cur.execute("SELECT * FROM server_release_orders WHERE server_release_id=?", (rid,))
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def list_releases(project_id: str = "", *, env_key: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    clauses: List[str] = []
    params: List[Any] = []
    if project_id:
        clauses.append("project_id=?")
        params.append(str(project_id).strip())
    if env_key:
        clauses.append("env_key=?")
        params.append(str(env_key).strip())
    sql = "SELECT * FROM server_release_orders"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def update_release_fields(server_release_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    init_db()
    rid = str(server_release_id or "").strip()
    if not rid:
        return None
    allowed = {
        "artifact_id", "status", "topology_id", "env_key", "payload",
        "target_services", "updated_at",
    }
    sets: List[str] = []
    params: List[Any] = []
    for key, val in fields.items():
        if key not in allowed:
            continue
        if key in ("payload",):
            val = json.dumps(val if isinstance(val, dict) else {}, ensure_ascii=False)
        elif key == "target_services":
            val = json.dumps(val if isinstance(val, list) else [], ensure_ascii=False)
        sets.append(f"{key}=?")
        params.append(val)
    if not sets:
        return get_release(rid)
    params.append(rid)
    with get_cursor() as cur:
        cur.execute(f"UPDATE server_release_orders SET {', '.join(sets)} WHERE server_release_id=?", params)
    return get_release(rid)


def _row_to_dict(row: Any) -> Dict[str, Any]:
    out = dict(row)
    out["target_services"] = _decode_json(out.get("target_services"), [])
    out["payload"] = _decode_json(out.get("payload"), {})
    return out
