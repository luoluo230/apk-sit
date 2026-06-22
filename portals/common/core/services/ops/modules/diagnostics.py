# -*- coding: utf-8 -*-
"""Diagnostics and health-check service layer."""

from __future__ import annotations

from typing import Any, Dict

import services.ops.helpers as ops_helpers


def build_summary(project_id: str = "", env_key: str = "production") -> Dict[str, Any]:
    pid = ops_helpers._resolve_ops_project_id(project_id)
    env = ops_helpers._resolve_ops_env_key(env_key)
    summary = ops_helpers._build_diagnostics_summary(project_id=pid, env_key=env)
    overview = ops_helpers._build_overview(project_id=pid, env_key=env)
    nodes = overview.get("nodes") if isinstance(overview.get("nodes"), list) else []
    summary["nodes"] = nodes
    summary["node_overview"] = overview.get("summary") if isinstance(overview.get("summary"), dict) else {}
    try:
        from flask import session as flask_session
        from services.ops.cluster_health_bridge import collect_cluster_health

        operator = str(flask_session.get("user") or "intranet-ops")
        summary["cluster_health"] = collect_cluster_health(operator=operator)
    except Exception as exc:
        summary["cluster_health"] = {"ok": False, "error": str(exc), "metrics": []}
    return summary


def list_rules() -> Dict[str, Any]:
    """Diagnostic rules derived from cluster health catalog."""
    rules = [
        {"id": name, "label": name.replace("_", " "), "severity": "high", "scope": "cluster"}
        for name in (
            "gateway_port",
            "auth_port",
            "game_port",
            "cross_port",
            "ops_health",
            "ops_ready",
            "mongodb",
            "redis",
            "resource_usage",
        )
    ]
    return {"ok": True, "count": len(rules), "rules": rules}
