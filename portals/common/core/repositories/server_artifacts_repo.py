# -*- coding: utf-8 -*-
"""Server artifact persistence (P2-01)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db


def _decode_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def upsert_artifact(row: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    artifact_id = str(row.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("artifact_id 必填")
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO server_artifacts (
                artifact_id, project_id, version_label, bundle_path, checksum,
                protocol_version, payload, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                project_id=excluded.project_id,
                version_label=excluded.version_label,
                bundle_path=excluded.bundle_path,
                checksum=excluded.checksum,
                protocol_version=excluded.protocol_version,
                payload=excluded.payload
            """,
            (
                artifact_id,
                str(row.get("project_id") or ""),
                str(row.get("version_label") or ""),
                str(row.get("bundle_path") or ""),
                str(row.get("checksum") or ""),
                str(row.get("protocol_version") or ""),
                json.dumps(payload, ensure_ascii=False),
                str(row.get("created_at") or ""),
            ),
        )
    saved = get_artifact(artifact_id)
    return saved or {"artifact_id": artifact_id}


def get_artifact(artifact_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    aid = str(artifact_id or "").strip()
    if not aid:
        return None
    with get_cursor() as cur:
        cur.execute("SELECT * FROM server_artifacts WHERE artifact_id=?", (aid,))
        row = cur.fetchone()
    if not row:
        return None
    out = dict(row)
    out["payload"] = _decode_payload(out.get("payload"))
    return out


def list_artifacts(project_id: str = "", *, limit: int = 100) -> List[Dict[str, Any]]:
    init_db()
    sql = "SELECT * FROM server_artifacts"
    params: List[Any] = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(str(project_id).strip())
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["payload"] = _decode_payload(item.get("payload"))
        out.append(item)
    return out
