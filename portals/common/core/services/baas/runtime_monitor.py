# -*- coding: utf-8 -*-
"""BaaS runtime health snapshot for Portal monitor panel (Wave A4)."""

from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.request import urlopen

from models.data import projects_db
from services.baas.service_crud import get_service, list_services
from services.server_mode import project_server_mode


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _probe(url: str, timeout: float = 2.0) -> Dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as resp:
            return {"ok": int(resp.status) == 200, "status": int(resp.status)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _db_ok() -> Dict[str, Any]:
    try:
        from models.db import get_cursor, init_db

        init_db()
        with get_cursor() as cur:
            cur.execute("SELECT 1 AS x")
            cur.fetchone()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def project_runtime_status(project_id: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    proj = projects_db.get(pid) or {}
    mode = project_server_mode(pid)
    service_id = str(proj.get("baas_service_id") or "").strip()
    services = list_services(project_id=pid) if mode == "casual_baas" else []
    if not service_id and services:
        service_id = str(services[0].get("service_id") or "")
    svc = get_service(service_id) if service_id else None
    port = int(os.environ.get("BAAS_PORT") or os.environ.get("PORT") or 5004)
    host = str(os.environ.get("BAAS_HOST") or "127.0.0.1")
    base = f"http://{host}:{port}"
    health = _probe(f"{base}/health")
    ready = _probe(f"{base}/health/ready")
    redis_url = str(os.environ.get("REDIS_URL") or "").strip()
    return {
        "project_id": pid,
        "server_mode": mode,
        "at": _now(),
        "hostname": socket.gethostname(),
        "listen": {"host": host, "port": port},
        "health": health,
        "ready": ready,
        "database": _db_ok(),
        "redis": {"configured": bool(redis_url), "url_set": bool(redis_url)},
        "workers_env": str(os.environ.get("BAAS_WORKERS") or "1"),
        "service_id": service_id,
        "service": svc,
        "gm_href": f"/admin/projects/{pid}/baas-gm/{service_id}" if service_id else f"/admin/projects/{pid}/baas-gm",
        "casual_href": f"/admin/projects/{pid}/casual-services",
        "services_count": len(services),
    }
