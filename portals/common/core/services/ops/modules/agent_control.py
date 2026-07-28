# -*- coding: utf-8 -*-
"""Agent registry, policy, and queue service layer."""

from __future__ import annotations

from typing import Any, Dict

from services.ops import deps as ops_helpers


def build_control_plane_summary() -> Dict[str, Any]:
    ops_helpers._ensure_probe_bg_started()
    with ops_helpers._probe_cache_lock:
        cached_probe = dict(ops_helpers._probe_cache)
        cached_agents = list(ops_helpers._probe_cache_agents)
    agents = [ops_helpers._normalize_agent_descriptor_v2(x) for x in cached_agents if isinstance(x, dict)]
    agents = [a for a in agents if not a.get("stale")]
    for agent in agents:
        aid = str(agent.get("agent_id") or "")
        probe = cached_probe.get(aid)
        if probe:
            agent["effective_status"] = probe.get("effective_status", "UNKNOWN")
            agent["probe_status"] = "PASS" if probe.get("ok") else "FAIL"
            agent["probe_rtt_ms"] = probe.get("rtt_ms", 0.0)
            agent["probe_source"] = "bg-engine"
        else:
            agent["effective_status"] = "UNKNOWN"
            agent["probe_source"] = "missing"
    jobs = ops_helpers._load_agent_jobs()
    queue = {"PENDING": 0, "RUNNING": 0, "SUCCESS": 0, "FAILED": 0, "CANCELED": 0, "TIMEOUT": 0}
    for item in jobs:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").upper()
        if status in queue:
            queue[status] += 1
    online = sum(
        1 for a in agents
        if str(a.get("effective_status") or a.get("status") or "").upper() in ("ONLINE", "READY", "RUNNING")
    )
    metrics = {
        "agents_total": len(agents),
        "agents_online": online,
        "jobs_pending": queue.get("PENDING") or 0,
        "jobs_running": queue.get("RUNNING") or 0,
        "probe_cache_age_sec": round(max(0, ops_helpers._time_mod.time() - ops_helpers._probe_cache_ts), 1),
    }
    return {"ok": True, "metrics": metrics, "queue": queue, "agents": agents, "policy": ops_helpers._load_agent_policy()}


def get_policy() -> Dict[str, Any]:
    return {"ok": True, "policy": ops_helpers._load_agent_policy()}
