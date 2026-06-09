#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migrate ops platform data from JSON config to SQLite tables.

Idempotent: safe to run multiple times. Existing SQLite rows are updated (upsert).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from models.data import get_system_config
from models.db import init_db, get_cursor, _db_lock, _get_conn


def _now():
    return datetime.utcnow().isoformat() + "Z"


def migrate_agents():
    """Migrate OPS_PLATFORM_AGENT_REGISTRY_V2 → ops_agents."""
    raw = get_system_config("OPS_PLATFORM_AGENT_REGISTRY_V2", {})
    if not isinstance(raw, dict):
        print("  agents: no data")
        return 0
    count = 0
    now = _now()
    with get_cursor() as cur:
        for aid, a in raw.items():
            if not isinstance(a, dict):
                continue
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
                    json.dumps({k: v for k, v in a.items() if k not in (
                        "agent_id", "project_id", "device_id", "display_name",
                        "host_ip", "host", "port", "status", "capabilities",
                        "desc", "region", "last_heartbeat", "probe_status", "probe_ts",
                    )}, ensure_ascii=False),
                    str(a.get("created_at", now)),
                    str(a.get("updated_at", now)),
                ),
            )
            count += 1
    print(f"  agents: {count} rows migrated")
    return count


def migrate_agent_jobs():
    """Migrate OPS_PLATFORM_AGENT_JOBS → ops_agent_jobs."""
    raw = get_system_config("OPS_PLATFORM_AGENT_JOBS", [])
    if not isinstance(raw, list):
        print("  jobs: no data")
        return 0
    count = 0
    now = _now()
    with get_cursor() as cur:
        for j in raw:
            if not isinstance(j, dict):
                continue
            jid = str(j.get("job_id", "")).strip()
            if not jid:
                continue
            cur.execute(
                """INSERT INTO ops_agent_jobs (job_id, agent_id, project_id, action,
                   target, status, params, result, error, retries,
                   created_at, updated_at, completed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     status=excluded.status, result=excluded.result,
                     error=excluded.error, retries=excluded.retries,
                     updated_at=excluded.updated_at, completed_at=excluded.completed_at""",
                (
                    jid,
                    str(j.get("agent_id", "")),
                    str(j.get("project_id", "")),
                    str(j.get("action", "")),
                    str(j.get("target", "")),
                    str(j.get("status", "PENDING")),
                    json.dumps(j.get("params", {}), ensure_ascii=False),
                    json.dumps(j.get("result", {}), ensure_ascii=False),
                    str(j.get("error", "")),
                    int(j.get("retries", 0) or 0),
                    str(j.get("created_at", now)),
                    str(j.get("updated_at", now)),
                    str(j.get("completed_at", "")),
                ),
            )
            count += 1
    print(f"  jobs: {count} rows migrated")
    return count


def migrate_events():
    """Migrate OPS_PLATFORM_EVENT_LOGS → ops_events."""
    raw = get_system_config("OPS_PLATFORM_EVENT_LOGS", [])
    if not isinstance(raw, list):
        print("  events: no data")
        return 0
    count = 0
    now = _now()
    with get_cursor() as cur:
        for e in raw:
            if not isinstance(e, dict):
                continue
            cur.execute(
                """INSERT INTO ops_events (event_type, project_id, scope, message,
                   severity, details, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    str(e.get("type") or e.get("event_type", "")),
                    str(e.get("project_id", "")),
                    str(e.get("scope", "")),
                    str(e.get("message", "")),
                    str(e.get("severity") or e.get("level", "info")),
                    json.dumps({k: v for k, v in e.items() if k not in (
                        "type", "event_type", "project_id", "scope", "message",
                        "severity", "level", "created_at", "timestamp",
                    )}, ensure_ascii=False),
                    str(e.get("created_at") or e.get("timestamp", now)),
                ),
            )
            count += 1
    print(f"  events: {count} rows migrated")
    return count


def migrate_runtime_runs():
    """Migrate OPS_PLATFORM_RUNTIME_RUNS → ops_runtime_runs."""
    raw = get_system_config("OPS_PLATFORM_RUNTIME_RUNS", [])
    if not isinstance(raw, list):
        print("  runs: no data")
        return 0
    count = 0
    now = _now()
    with get_cursor() as cur:
        for r in raw:
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
                    str(r.get("updated_at", now)),
                ),
            )
            count += 1
    print(f"  runs: {count} rows migrated")
    return count


def migrate_topologies():
    """Migrate OPS_PLATFORM_TOPOLOGY_REGISTRY + CONTENTS → ops_topologies."""
    registry = get_system_config("OPS_PLATFORM_TOPOLOGY_REGISTRY", [])
    contents = get_system_config("OPS_PLATFORM_TOPOLOGY_CONTENTS", {})
    if not isinstance(registry, list):
        registry = []
    if not isinstance(contents, dict):
        contents = {}
    count = 0
    now = _now()
    with get_cursor() as cur:
        for reg in registry:
            if not isinstance(reg, dict):
                continue
            tid = str(reg.get("topology_id", "")).strip()
            if not tid:
                continue
            topo_data = contents.get(tid, {})
            if not isinstance(topo_data, dict):
                topo_data = {}
            cur.execute(
                """INSERT INTO ops_topologies (topology_id, project_id, env_key, name,
                   status, is_default, nodes, edges, meta, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(topology_id) DO UPDATE SET
                     name=excluded.name, status=excluded.status,
                     is_default=excluded.is_default,
                     nodes=excluded.nodes, edges=excluded.edges,
                     meta=excluded.meta, updated_at=excluded.updated_at""",
                (
                    tid,
                    str(reg.get("project_id", "")),
                    str(reg.get("env_key", "production")),
                    str(reg.get("name") or tid),
                    str(reg.get("status", "active")),
                    1 if reg.get("is_default") else 0,
                    json.dumps(topo_data.get("nodes", []), ensure_ascii=False),
                    json.dumps(topo_data.get("edges", []), ensure_ascii=False),
                    json.dumps(topo_data.get("meta", {}), ensure_ascii=False),
                    str(reg.get("created_at", now)),
                    str(reg.get("updated_at", now)),
                ),
            )
            count += 1
    print(f"  topologies: {count} rows migrated")
    return count


def main():
    print("Ops JSON → SQLite migration")
    print("=" * 40)
    init_db()
    total = 0
    total += migrate_agents()
    total += migrate_agent_jobs()
    total += migrate_events()
    total += migrate_runtime_runs()
    total += migrate_topologies()
    print(f"\nTotal: {total} rows migrated")
    print("Done. Set OPS_USE_SQLITE=true to switch ops storage to SQLite.")


if __name__ == "__main__":
    main()
