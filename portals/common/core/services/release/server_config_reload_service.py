# -*- coding: utf-8 -*-
"""Server config hot reload dispatch (P2-01 Step 5)."""

from __future__ import annotations

from typing import Any, Dict, List


def apply_config_patch(project_id: str, service_id: str, patch: Dict[str, Any], actor: str) -> Dict[str, Any]:
    from services.ops.agent_registry import _enqueue_agent_job

    sid = str(service_id or "").strip()
    if not sid:
        raise ValueError("service_id 必填")
    payload = {
        "command": "reload_config",
        "project_id": project_id,
        "service_id": sid,
        "patch": dict(patch or {}),
        "actor": str(actor or "system"),
    }
    job = _enqueue_agent_job(sid, "reload_config", sid, payload, {
        "ticket_id": f"CFG-{project_id}-{sid}",
        "reason": "config hot reload",
        "risk": "medium",
        "require_approval": False,
        "approved": True,
    })
    return {"ok": True, "jobs": [job]}
