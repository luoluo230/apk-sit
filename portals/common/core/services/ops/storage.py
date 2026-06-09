# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from flask import session
from models.data import get_system_config, set_system_config
from services.ops.constants import (
    OPS_AGENT_JOBS_KEY,
    OPS_AGENT_REGISTRY_KEY,
    OPS_AGENT_REGISTRY_V2_KEY,
    OPS_NODE_AGENT_BINDING_KEY,
    OPS_NODE_SERVICE_BINDING_KEY,
    OPS_RUNTIME_RUNS_KEY,
)

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def _load_json_config(key: str, default):
    raw = get_system_config(key, default)
    if isinstance(raw, type(default)):
        return raw
    return default

def _save_json_config(key: str, value, description: str = "") -> None:
    try:
        user = str(session.get("user") or "system")
    except RuntimeError:
        user = "system"
    set_system_config(key, value, value_type="json", description=description, username=user)

def _load_agent_registry() -> Dict[str, Any]:
    raw = _load_json_config(OPS_AGENT_REGISTRY_KEY, {})
    return raw if isinstance(raw, dict) else {}

def _save_agent_registry(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_AGENT_REGISTRY_KEY, data if isinstance(data, dict) else {}, description="Ops Agent registry and heartbeat state")

def _load_agent_registry_v2() -> Dict[str, Any]:
    raw = _load_json_config(OPS_AGENT_REGISTRY_V2_KEY, {})
    return raw if isinstance(raw, dict) else {}

def _save_agent_registry_v2(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_AGENT_REGISTRY_V2_KEY, data if isinstance(data, dict) else {}, description="Ops Agent registry v2")

def _load_node_agent_bindings() -> Dict[str, Any]:
    raw = _load_json_config(OPS_NODE_AGENT_BINDING_KEY, {})
    return raw if isinstance(raw, dict) else {}

def _save_node_agent_bindings(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_NODE_AGENT_BINDING_KEY, data if isinstance(data, dict) else {}, description="Ops node->agent primary binding")

def _load_node_service_bindings() -> Dict[str, Any]:
    raw = _load_json_config(OPS_NODE_SERVICE_BINDING_KEY, {})
    return raw if isinstance(raw, dict) else {}

def _save_node_service_bindings(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_NODE_SERVICE_BINDING_KEY, data if isinstance(data, dict) else {}, description="Ops node->service primary binding")

def _load_agent_jobs() -> List[Dict[str, Any]]:
    raw = _load_json_config(OPS_AGENT_JOBS_KEY, [])
    return raw if isinstance(raw, list) else []

def _save_agent_jobs(rows: List[Dict[str, Any]]) -> None:
    items = rows if isinstance(rows, list) else []
    if len(items) > 1200:
        items = items[-1200:]
    _save_json_config(OPS_AGENT_JOBS_KEY, items, description="Ops Agent job queue and state machine")

def _load_runtime_runs() -> List[Dict[str, Any]]:
    raw = _load_json_config(OPS_RUNTIME_RUNS_KEY, [])
    return raw if isinstance(raw, list) else []

def _save_runtime_runs(rows: List[Dict[str, Any]]) -> None:
    items = rows if isinstance(rows, list) else []
    if len(items) > 80:
        items = items[-80:]
    _save_json_config(OPS_RUNTIME_RUNS_KEY, items, description="Ops runtime start/stop run logs")

def _upsert_runtime_run(run_obj: Dict[str, Any]) -> None:
    rid = str((run_obj or {}).get("run_id") or "").strip()
    if not rid:
        return
    rows = _load_runtime_runs()
    replaced = False
    for idx, row in enumerate(rows):
        if str((row or {}).get("run_id") or "") == rid:
            rows[idx] = run_obj
            replaced = True
            break
    if not replaced:
        rows.insert(0, run_obj)
    _save_runtime_runs(rows)

def _find_runtime_run(run_id: str) -> Optional[Dict[str, Any]]:
    rid = str(run_id or "").strip()
    if not rid:
        return None
    for row in _load_runtime_runs():
        if not isinstance(row, dict):
            continue
        if str(row.get("run_id") or "") == rid:
            return row
    return None

def _runtime_active_for_project(project_id: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    rows = _load_runtime_runs()
    latest_start = None
    latest_stop = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if pid and str(row.get("project_id") or "") != pid:
            continue
        op = str(row.get("op") or "").lower()
        st = str(row.get("status") or "").lower()
        if op == "start" and st in ("running", "success"):
            if latest_start is None:
                latest_start = row
        if op == "stop" and st in ("running", "success"):
            if latest_stop is None:
                latest_stop = row
    if not latest_start:
        return {"active": False, "run_id": "", "status": "", "reason": "no_start_run"}
    start_ts = str(latest_start.get("updated_at") or latest_start.get("created_at") or "")
    stop_ts = str((latest_stop or {}).get("updated_at") or (latest_stop or {}).get("created_at") or "")
    if latest_stop and stop_ts and start_ts and stop_ts >= start_ts:
        return {"active": False, "run_id": str(latest_start.get("run_id") or ""), "status": str(latest_start.get("status") or ""), "reason": "stopped_after_start"}
    return {"active": True, "run_id": str(latest_start.get("run_id") or ""), "status": str(latest_start.get("status") or ""), "reason": "start_alive"}
