# -*- coding: utf-8 -*-
"""Ops platform storage abstraction.

Uses JSON config by default, SQLite when OPS_USE_SQLITE is enabled.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import session
from models.data import get_system_config, set_system_config
from services.ops.constants import (
    OPS_AGENT_JOBS_KEY,
    OPS_AGENT_REGISTRY_KEY,
    OPS_AGENT_REGISTRY_V2_KEY,
    OPS_EVENT_LOG_KEY,
    OPS_NODE_AGENT_BINDING_KEY,
    OPS_NODE_SERVICE_BINDING_KEY,
    OPS_RUNTIME_RUNS_KEY,
)


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _use_sqlite() -> bool:
    try:
        from config import Config

        if getattr(Config, 'USE_SQLITE', False):
            return True
    except ImportError:
        pass
    ops_flag = get_system_config('OPS_USE_SQLITE', '')
    if str(ops_flag).lower() in ('true', '1', 'yes'):
        return True
    if str(ops_flag).lower() in ('false', '0', 'no'):
        return False
    core_flag = get_system_config('USE_SQLITE', '')
    return str(core_flag).lower() in ('true', '1', 'yes')


# ── JSON backend (existing) ─────────────────────────────────────────

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


# ── Agent Registry ───────────────────────────────────────────────────

def _load_agent_registry() -> Dict[str, Any]:
    raw = _load_json_config(OPS_AGENT_REGISTRY_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_agent_registry(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_AGENT_REGISTRY_KEY, data if isinstance(data, dict) else {}, description="Ops Agent registry and heartbeat state")


def _load_agent_registry_v2() -> Dict[str, Any]:
    if _use_sqlite():
        return _sqlite_load_agent_registry_v2()
    raw = _load_json_config(OPS_AGENT_REGISTRY_V2_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_agent_registry_v2(data: Dict[str, Any]) -> None:
    if _use_sqlite():
        _sqlite_save_agent_registry_v2(data)
        return
    _save_json_config(OPS_AGENT_REGISTRY_V2_KEY, data if isinstance(data, dict) else {}, description="Ops Agent registry v2")


# ── Node bindings ────────────────────────────────────────────────────

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


# ── Agent Jobs ───────────────────────────────────────────────────────

def _load_agent_jobs() -> List[Dict[str, Any]]:
    if _use_sqlite():
        return _sqlite_load_agent_jobs()
    raw = _load_json_config(OPS_AGENT_JOBS_KEY, [])
    return raw if isinstance(raw, list) else []


def _save_agent_jobs(rows: List[Dict[str, Any]]) -> None:
    if _use_sqlite():
        _sqlite_save_agent_jobs(rows)
        return
    items = rows if isinstance(rows, list) else []
    if len(items) > 1200:
        items = items[-1200:]
    _save_json_config(OPS_AGENT_JOBS_KEY, items, description="Ops Agent job queue and state machine")


# ── Runtime Runs ─────────────────────────────────────────────────────

def _load_runtime_runs() -> List[Dict[str, Any]]:
    if _use_sqlite():
        return _sqlite_load_runtime_runs()
    raw = _load_json_config(OPS_RUNTIME_RUNS_KEY, [])
    return raw if isinstance(raw, list) else []


def _save_runtime_runs(rows: List[Dict[str, Any]]) -> None:
    if _use_sqlite():
        _sqlite_save_runtime_runs(rows)
        return
    items = rows if isinstance(rows, list) else []
    if len(items) > 80:
        items = items[-80:]
    _save_json_config(OPS_RUNTIME_RUNS_KEY, items, description="Ops runtime start/stop run logs")


def _upsert_runtime_run(run_obj: Dict[str, Any]) -> None:
    rid = str((run_obj or {}).get("run_id") or "").strip()
    if not rid:
        return
    if _use_sqlite():
        _sqlite_upsert_runtime_run(run_obj)
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
    if _use_sqlite():
        return _sqlite_find_runtime_run(rid)
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


# ── Events ───────────────────────────────────────────────────────────

def _load_events(limit: int = 200, project_id: str = "") -> List[Dict[str, Any]]:
    if _use_sqlite():
        return _sqlite_load_events(limit, project_id)
    raw = _load_json_config(OPS_EVENT_LOG_KEY, [])
    if not isinstance(raw, list):
        return []
    if project_id:
        raw = [e for e in raw if isinstance(e, dict) and str(e.get("project_id", "")) == project_id]
    return raw[:limit]


def _append_event(entry: Dict[str, Any]) -> None:
    if _use_sqlite():
        _sqlite_append_event(entry)
        return
    from services.ops.diagnostics import _append_bounded
    _append_bounded(OPS_EVENT_LOG_KEY, entry, limit=800, description="Ops platform event timeline")


# ══════════════════════════════════════════════════════════════════════
# SQLite backend implementations
# ══════════════════════════════════════════════════════════════════════

def _sqlite_load_agent_registry_v2() -> Dict[str, Any]:
    from models.db import init_db, _db_lock, _get_conn
    init_db()
    with _db_lock:
        rows = _get_conn().execute("SELECT * FROM ops_agents ORDER BY updated_at DESC").fetchall()
    result: Dict[str, Any] = {}
    for r in rows:
        d = dict(r)
        aid = d.pop("agent_id", "")
        d["agent_id"] = aid
        for k in ("capabilities",):
            try:
                d[k] = json.loads(d.get(k) or "[]")
            except (json.JSONDecodeError, TypeError):
                d[k] = []
        for k in ("meta",):
            try:
                extra = json.loads(d.get(k) or "{}")
                if isinstance(extra, dict):
                    d.update(extra)
                del d[k]
            except (json.JSONDecodeError, TypeError):
                del d[k]
        result[aid] = d
    return result


def _sqlite_save_agent_registry_v2(data: Dict[str, Any]) -> None:
    from models.db import init_db, get_cursor
    init_db()
    now = _now_iso()
    known_cols = {
        "agent_id", "project_id", "device_id", "display_name",
        "host_ip", "port", "status", "capabilities", "desc", "region",
        "last_heartbeat", "probe_status", "probe_ts",
    }
    with get_cursor() as cur:
        for aid, a in (data if isinstance(data, dict) else {}).items():
            if not isinstance(a, dict):
                continue
            meta = {k: v for k, v in a.items() if k not in known_cols and k not in ("created_at", "updated_at", "meta")}
            cur.execute(
                """INSERT INTO ops_agents (agent_id, project_id, device_id, display_name,
                   host_ip, port, status, capabilities, desc, region,
                   last_heartbeat, probe_status, probe_ts, meta, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(agent_id) DO UPDATE SET
                     project_id=excluded.project_id, device_id=excluded.device_id,
                     display_name=excluded.display_name, host_ip=excluded.host_ip,
                     port=excluded.port, status=excluded.status,
                     capabilities=excluded.capabilities, desc=excluded.desc,
                     region=excluded.region, last_heartbeat=excluded.last_heartbeat,
                     probe_status=excluded.probe_status, probe_ts=excluded.probe_ts,
                     meta=excluded.meta, updated_at=excluded.updated_at""",
                (
                    str(aid),
                    str(a.get("project_id", "")),
                    str(a.get("device_id", "")),
                    str(a.get("display_name", "")),
                    str(a.get("host_ip") or a.get("host", "")),
                    int(a.get("port", 0) or 0),
                    str(a.get("status", "OFFLINE")),
                    json.dumps(a.get("capabilities", []), ensure_ascii=False),
                    str(a.get("desc", "")),
                    str(a.get("region", "")),
                    str(a.get("last_heartbeat", "")),
                    str(a.get("probe_status", "")),
                    str(a.get("probe_ts", "")),
                    json.dumps(meta, ensure_ascii=False),
                    str(a.get("created_at", now)),
                    now,
                ),
            )


def _agent_job_action_type(job: Dict[str, Any]) -> str:
    action = str(job.get("action_type") or job.get("action") or "").strip()
    if action:
        return action
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    return str(payload.get("command") or "").strip()


def _agent_job_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    if payload:
        return payload
    legacy = job.get("params") if isinstance(job.get("params"), dict) else {}
    nested = legacy.get("payload") if isinstance(legacy.get("payload"), dict) else {}
    return nested if nested else legacy


def _normalize_agent_job_for_sqlite(job: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(job)
    action_type = _agent_job_action_type(item)
    payload = _agent_job_payload(item)
    node_id = str(item.get("node_id") or item.get("target") or "").strip()
    project_id = str(
        item.get("project_id")
        or payload.get("project_id")
        or ""
    ).strip()
    item["action_type"] = action_type
    item["action"] = action_type
    item["payload"] = payload
    if node_id:
        item["node_id"] = node_id
    if project_id:
        item["project_id"] = project_id
    if not str(item.get("target") or "").strip() and node_id:
        item["target"] = node_id
    return item


def _normalize_agent_job_from_sqlite(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_params = row.get("params")
    if not isinstance(raw_params, dict):
        try:
            raw_params = json.loads(raw_params or "{}")
        except (json.JSONDecodeError, TypeError):
            raw_params = {}
    job = dict(raw_params) if isinstance(raw_params, dict) and raw_params.get("job_id") else {}
    for key in (
        "job_id",
        "agent_id",
        "project_id",
        "target",
        "status",
        "error",
        "retries",
        "created_at",
        "updated_at",
        "completed_at",
    ):
        val = row.get(key)
        if val not in (None, ""):
            job[key] = val
    raw_result = row.get("result")
    if isinstance(raw_result, dict):
        job["result"] = raw_result
    else:
        try:
            job["result"] = json.loads(raw_result or "{}")
        except (json.JSONDecodeError, TypeError):
            job["result"] = {}
    action_type = str(
        job.get("action_type")
        or job.get("action")
        or row.get("action")
        or ""
    ).strip()
    payload = _agent_job_payload(job)
    if not action_type:
        action_type = str(payload.get("command") or "").strip()
    job["action_type"] = action_type
    job["action"] = action_type
    job["payload"] = payload
    if not str(job.get("node_id") or "").strip():
        job["node_id"] = str(job.get("target") or row.get("target") or "").strip()
    if not str(job.get("project_id") or "").strip():
        job["project_id"] = str(payload.get("project_id") or row.get("project_id") or "").strip()
    return job


def _sqlite_load_agent_jobs() -> List[Dict[str, Any]]:
    from models.db import init_db, _db_lock, _get_conn
    init_db()
    with _db_lock:
        rows = _get_conn().execute(
            "SELECT * FROM ops_agent_jobs ORDER BY created_at ASC LIMIT 1200"
        ).fetchall()
    return [_normalize_agent_job_from_sqlite(dict(r)) for r in rows]


def _sqlite_save_agent_jobs(rows: List[Dict[str, Any]]) -> None:
    from models.db import init_db, get_cursor
    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        for raw in (rows if isinstance(rows, list) else []):
            if not isinstance(raw, dict):
                continue
            j = _normalize_agent_job_for_sqlite(raw)
            jid = str(j.get("job_id", "")).strip()
            if not jid:
                continue
            payload = j.get("payload") if isinstance(j.get("payload"), dict) else {}
            cur.execute(
                """INSERT INTO ops_agent_jobs (job_id, agent_id, project_id, action,
                   target, status, params, result, error, retries,
                   created_at, updated_at, completed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     agent_id=excluded.agent_id,
                     project_id=excluded.project_id,
                     action=excluded.action,
                     target=excluded.target,
                     status=excluded.status,
                     params=excluded.params,
                     result=excluded.result,
                     error=excluded.error,
                     retries=excluded.retries,
                     updated_at=excluded.updated_at,
                     completed_at=excluded.completed_at""",
                (
                    jid,
                    str(j.get("agent_id") or j.get("lease", {}).get("agent_id") or ""),
                    str(j.get("project_id") or payload.get("project_id") or ""),
                    _agent_job_action_type(j),
                    str(j.get("target") or j.get("node_id") or ""),
                    str(j.get("status", "PENDING")),
                    json.dumps(j, ensure_ascii=False),
                    json.dumps(j.get("result", {}), ensure_ascii=False),
                    str(j.get("error", "")),
                    int(j.get("retries", 0) or 0),
                    str(j.get("created_at", now)),
                    now,
                    str(j.get("completed_at", "")),
                ),
            )


def _sqlite_load_runtime_runs() -> List[Dict[str, Any]]:
    from models.db import init_db, _db_lock, _get_conn
    init_db()
    with _db_lock:
        rows = _get_conn().execute(
            "SELECT * FROM ops_runtime_runs ORDER BY updated_at DESC LIMIT 80"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        for k in ("nodes",):
            try:
                d[k] = json.loads(d.get(k) or "[]")
            except (json.JSONDecodeError, TypeError):
                d[k] = []
        for k in ("result",):
            try:
                d[k] = json.loads(d.get(k) or "{}")
            except (json.JSONDecodeError, TypeError):
                d[k] = {}
        result.append(d)
    return result


def _sqlite_save_runtime_runs(rows: List[Dict[str, Any]]) -> None:
    from models.db import init_db, get_cursor
    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        for r in (rows if isinstance(rows, list) else []):
            if not isinstance(r, dict):
                continue
            rid = str(r.get("run_id", "")).strip()
            if not rid:
                continue
            cur.execute(
                """INSERT INTO ops_runtime_runs (run_id, project_id, env_key, topology_id,
                   op, status, nodes, result, error, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(run_id) DO UPDATE SET
                     status=excluded.status, result=excluded.result,
                     error=excluded.error, updated_at=excluded.updated_at""",
                (
                    rid,
                    str(r.get("project_id", "")),
                    str(r.get("env_key", "")),
                    str(r.get("topology_id", "")),
                    str(r.get("op", "")),
                    str(r.get("status", "")),
                    json.dumps(r.get("nodes", []), ensure_ascii=False),
                    json.dumps(r.get("result", {}), ensure_ascii=False),
                    str(r.get("error", "")),
                    str(r.get("created_at", now)),
                    now,
                ),
            )


def _sqlite_upsert_runtime_run(run_obj: Dict[str, Any]) -> None:
    _sqlite_save_runtime_runs([run_obj])


def _sqlite_find_runtime_run(run_id: str) -> Optional[Dict[str, Any]]:
    from models.db import init_db, _db_lock, _get_conn
    init_db()
    with _db_lock:
        row = _get_conn().execute(
            "SELECT * FROM ops_runtime_runs WHERE run_id=?", (run_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("nodes",):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except (json.JSONDecodeError, TypeError):
            d[k] = []
    for k in ("result",):
        try:
            d[k] = json.loads(d.get(k) or "{}")
        except (json.JSONDecodeError, TypeError):
            d[k] = {}
    return d


def _sqlite_load_events(limit: int = 200, project_id: str = "") -> List[Dict[str, Any]]:
    from models.db import init_db, _db_lock, _get_conn
    init_db()
    with _db_lock:
        if project_id:
            rows = _get_conn().execute(
                "SELECT * FROM ops_events WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        else:
            rows = _get_conn().execute(
                "SELECT * FROM ops_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            extra = json.loads(d.pop("details", "{}"))
            if isinstance(extra, dict):
                d.update(extra)
        except (json.JSONDecodeError, TypeError):
            pass
        result.append(d)
    return result


def _sqlite_append_event(entry: Dict[str, Any]) -> None:
    from models.db import init_db, get_cursor
    init_db()
    now = _now_iso()
    known = {"event_type", "type", "project_id", "scope", "message", "severity", "level", "created_at", "timestamp"}
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO ops_events (event_type, project_id, scope, message, severity, details, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                str(entry.get("type") or entry.get("event_type", "")),
                str(entry.get("project_id", "")),
                str(entry.get("scope", "")),
                str(entry.get("message", "")),
                str(entry.get("severity") or entry.get("level", "info")),
                json.dumps({k: v for k, v in entry.items() if k not in known}, ensure_ascii=False),
                str(entry.get("created_at") or entry.get("timestamp", now)),
            ),
        )
