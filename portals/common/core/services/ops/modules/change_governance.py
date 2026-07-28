# -*- coding: utf-8 -*-
"""Change window and freeze governance service layer."""

from __future__ import annotations

from typing import Any, Dict

from models.data import approvals_db
from services.ops import deps as ops_helpers
from services.ops.constants import OPS_EVENT_LOG_KEY


def build_summary(project_id: str = "", env_key: str = "production") -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = ops_helpers._resolve_ops_env_key(env_key)
    events = ops_helpers._load_json_config(OPS_EVENT_LOG_KEY, [])
    if not isinstance(events, list):
        events = []
    recent = [x for x in events if isinstance(x, dict)][:200]
    if pid:
        recent = [
            x for x in recent
            if not str(x.get("project_id") or "").strip() or str(x.get("project_id") or "") == pid
        ]
    high_risk = failed = change_evt = 0
    for item in recent:
        level = str(item.get("level") or item.get("risk") or "").lower()
        action = str(item.get("action") or "").lower()
        ok = bool(item.get("ok", True))
        if level in ("high", "critical"):
            high_risk += 1
        if not ok:
            failed += 1
        if any(k in action for k in ("deploy", "migration", "release", "rollback")):
            change_evt += 1
    pending_approvals = 0
    for item in approvals_db:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").lower() in ("pending", "open"):
            if pid and str(item.get("project_id") or "") not in ("", pid):
                continue
            pending_approvals += 1
    metrics = {
        "pending_approvals": pending_approvals,
        "high_risk_actions_24h": high_risk,
        "failed_actions_24h": failed,
        "change_events_24h": change_evt,
    }
    freeze = ops_helpers._change_freeze_for_project(pid)
    ctx = ops_helpers._resolve_topology_context(pid, env, "") if pid else {}
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    tid = str(row.get("topology_id") or "")
    window = {
        "freeze_active": bool(freeze.get("active")),
        "freeze_reason": str(freeze.get("reason") or ""),
        "freeze_updated_at": str(freeze.get("updated_at") or ""),
        "topology_id": tid,
        "env_key": str(row.get("env_key") or env),
    }
    return {"ok": True, "project_id": pid, "metrics": metrics, "events": recent[:20], "window": window}


def set_freeze(project_id: str, active: bool, reason: str, actor: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_project_id"}
    saved = ops_helpers._save_change_freeze(pid, active, reason, actor)
    return {"ok": True, "project_id": pid, "window": saved}
