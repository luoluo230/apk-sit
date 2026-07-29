# -*- coding: utf-8 -*-
"""SQLite repository for unified infra_nodes registry (P1-05)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _decode_row(row: dict) -> Dict[str, Any]:
    out = dict(row)
    for key in ("capabilities", "payload"):
        raw = out.get(key)
        if isinstance(raw, str):
            try:
                out[key] = json.loads(raw or "{}")
            except json.JSONDecodeError:
                out[key] = {} if key == "payload" else {}
        elif raw is None:
            out[key] = {} if key == "payload" else {}
    return out


def upsert_node(row: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    node_id = str(row.get("node_id") or row.get("id") or "").strip()
    if not node_id:
        raise ValueError("node_id 必填")
    now = _now_iso()
    created_at = str(row.get("created_at") or now)
    capabilities = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO infra_nodes (
                node_id, project_id, role, display_name, host, port,
                jenkins_label, jenkins_instance_id, capabilities, agent_ws_url,
                status, last_heartbeat_at, payload, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
                project_id=excluded.project_id,
                role=excluded.role,
                display_name=excluded.display_name,
                host=excluded.host,
                port=excluded.port,
                jenkins_label=excluded.jenkins_label,
                jenkins_instance_id=excluded.jenkins_instance_id,
                capabilities=excluded.capabilities,
                agent_ws_url=excluded.agent_ws_url,
                status=excluded.status,
                last_heartbeat_at=excluded.last_heartbeat_at,
                payload=excluded.payload,
                updated_at=excluded.updated_at
            """,
            (
                node_id,
                str(row.get("project_id") or ""),
                str(row.get("role") or ""),
                str(row.get("display_name") or ""),
                str(row.get("host") or row.get("hostname") or ""),
                int(row.get("port") or 0),
                str(row.get("jenkins_label") or ""),
                str(row.get("jenkins_instance_id") or ""),
                json.dumps(capabilities, ensure_ascii=False),
                str(row.get("agent_ws_url") or ""),
                str(row.get("status") or "unknown"),
                str(row.get("last_heartbeat_at") or row.get("last_heartbeat") or ""),
                json.dumps(payload, ensure_ascii=False),
                created_at,
                now,
            ),
        )
    saved = get_node(node_id)
    return saved or {"node_id": node_id}


def get_node(node_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    nid = str(node_id or "").strip()
    if not nid:
        return None
    with get_cursor() as cur:
        cur.execute("SELECT * FROM infra_nodes WHERE node_id=?", (nid,))
        row = cur.fetchone()
    return _decode_row(dict(row)) if row else None


def list_nodes(
    *,
    role: str = "",
    role_prefix: str = "",
    project_id: str = "",
    status: str = "",
) -> List[Dict[str, Any]]:
    init_db()
    clauses: List[str] = []
    params: List[Any] = []
    if role:
        clauses.append("role=?")
        params.append(str(role).strip())
    if role_prefix:
        clauses.append("role LIKE ?")
        params.append(f"{str(role_prefix).strip()}%")
    if project_id:
        clauses.append("project_id=?")
        params.append(str(project_id).strip())
    if status:
        clauses.append("status=?")
        params.append(str(status).strip())
    sql = "SELECT * FROM infra_nodes"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY updated_at DESC"
    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_decode_row(dict(r)) for r in rows]


def delete_node(node_id: str) -> bool:
    init_db()
    nid = str(node_id or "").strip()
    if not nid:
        return False
    with get_cursor() as cur:
        cur.execute("DELETE FROM infra_nodes WHERE node_id=?", (nid,))
        return cur.rowcount > 0
