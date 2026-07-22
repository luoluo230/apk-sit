# -*- coding: utf-8 -*-
"""Runtime scope activity helpers (extracted from ops.helpers)."""

from __future__ import annotations

from typing import Any, Dict

from services.ops.storage import _load_runtime_runs
from services.ops.topology_service import _normalize_env_key


def _runtime_active_for_scope(project_id: str, env_key: str, topology_id: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    rows = _load_runtime_runs()
    latest_start = None
    latest_stop = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if pid and str(row.get("project_id") or "") != pid:
            continue
        if env and _normalize_env_key(row.get("env_key") or "") != env:
            continue
        if tid and str(row.get("topology_id") or "") != tid:
            continue
        op = str(row.get("op") or "").lower()
        ts = str(row.get("updated_at") or row.get("created_at") or "")
        if op == "start":
            prev_ts = str((latest_start or {}).get("updated_at") or (latest_start or {}).get("created_at") or "")
            if latest_start is None or ts >= prev_ts:
                latest_start = row
        if op == "stop":
            prev_ts = str((latest_stop or {}).get("updated_at") or (latest_stop or {}).get("created_at") or "")
            if latest_stop is None or ts >= prev_ts:
                latest_stop = row
    if not latest_start:
        return {"active": False, "run_id": "", "status": "", "reason": "no_start_run"}
    start_ts = str(latest_start.get("updated_at") or latest_start.get("created_at") or "")
    stop_ts = str((latest_stop or {}).get("updated_at") or (latest_stop or {}).get("created_at") or "")
    stop_st = str((latest_stop or {}).get("status") or "").lower()
    if latest_stop and stop_ts and start_ts and stop_ts >= start_ts:
        if stop_st in ("success", "running", "queued"):
            return {
                "active": False,
                "run_id": str(latest_stop.get("run_id") or latest_start.get("run_id") or ""),
                "status": stop_st,
                "reason": "stopped_after_start" if stop_st == "success" else "stop_in_progress",
            }
        if stop_st in ("failed", "timeout", "canceled"):
            return {
                "active": True,
                "run_id": str(latest_start.get("run_id") or ""),
                "status": str(latest_start.get("status") or ""),
                "reason": "stop_failed",
            }
    start_st = str(latest_start.get("status") or "").lower()
    if start_st in ("failed", "success", "timeout", "canceled"):
        return {"active": False, "run_id": str(latest_start.get("run_id") or ""), "status": start_st, "reason": "start_finished"}
    return {"active": True, "run_id": str(latest_start.get("run_id") or ""), "status": start_st, "reason": "start_alive"}
