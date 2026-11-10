# -*- coding: utf-8 -*-
"""BaaS API node heartbeat registry (decoupled from realms)."""

from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def heartbeat(
    *,
    service_id: str = "",
    node_id: str = "",
    host: str = "",
    port: int = 0,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_db()
    nid = str(node_id or "").strip() or f"node-{socket.gethostname()}-{os.getpid()}"
    h = str(host or os.environ.get("BAAS_HOST") or socket.gethostname())
    p = int(port or os.environ.get("BAAS_PORT") or 5004)
    now = _now()
    import json

    payload = json.dumps(meta or {}, ensure_ascii=False)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_nodes (
                node_id, service_id, host, port, status, last_heartbeat, meta_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
                service_id=excluded.service_id,
                host=excluded.host,
                port=excluded.port,
                status='online',
                last_heartbeat=excluded.last_heartbeat,
                meta_json=excluded.meta_json,
                updated_at=excluded.updated_at
            """,
            (nid, str(service_id or ""), h, p, "online", now, payload, now, now),
        )
    return {"node_id": nid, "host": h, "port": p, "status": "online", "last_heartbeat": now}


def list_nodes(service_id: str = "") -> List[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        if service_id:
            rows = cur.execute(
                "SELECT * FROM baas_nodes WHERE service_id=? OR service_id='' ORDER BY last_heartbeat DESC",
                (str(service_id),),
            ).fetchall()
        else:
            rows = cur.execute("SELECT * FROM baas_nodes ORDER BY last_heartbeat DESC").fetchall()
    out = []
    for r in rows:
        out.append({k: r[k] for k in r.keys()})
    return out
