# -*- coding: utf-8 -*-
"""Dev delivery: ensure topology runtime is active before precheck/publish."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict

DEFAULT_ENSURE_POLL_SEC = 30.0
POLL_INTERVAL_SEC = 2.0


def ensure_runtime_for_scope(
    project_id: str,
    env_key: str,
    topology_id: str,
    actor: str,
    *,
    poll_sec: float = DEFAULT_ENSURE_POLL_SEC,
) -> Dict[str, Any]:
    """Start runtime when inactive and poll until active or timeout.

    Idempotent: returns immediately when runtime is already active for the scope.
    """
    from services.ops.runtime_service import _runtime_active_for_scope
    from services.ops.storage import _now_iso, _upsert_runtime_run
    from services.ops.topology_registry import (
        _load_scope_agent_bindings,
        _load_scope_service_bindings,
        _load_topology_scoped,
        _project_uses_runtime_topology,
    )
    from services.ops.runtime_orchestrator import _spawn_runtime_start_orchestration
    from services.ops.topology_service import _normalize_env_key

    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    if not pid or not tid:
        return {"active": False, "run_id": "", "started": False, "error": "缺少 project_id 或 topology_id"}

    current = _runtime_active_for_scope(pid, env, tid)
    if current.get("active"):
        return {
            "active": True,
            "run_id": str(current.get("run_id") or ""),
            "started": False,
            "error": "",
        }

    if not _project_uses_runtime_topology(pid):
        return {
            "active": False,
            "run_id": "",
            "started": False,
            "error": "项目未启用 Runtime 拓扑编排",
        }

    try:
        topo = _load_topology_scoped(pid, env, tid)
        topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
        topo_edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
        if not topo_nodes:
            return {"active": False, "run_id": "", "started": False, "error": "拓扑无可用节点"}

        run_id = "run-" + uuid.uuid4().hex[:12]
        now = _now_iso()
        _upsert_runtime_run(
            {
                "run_id": run_id,
                "project_id": pid,
                "env_key": env,
                "topology_id": tid,
                "op": "start",
                "status": "running",
                "created_at": now,
                "updated_at": now,
                "items": [],
                "logs": [],
            }
        )
        _spawn_runtime_start_orchestration(
            run_id,
            pid,
            env,
            tid,
            topo_nodes,
            topo_edges,
            _load_scope_service_bindings(tid),
            _load_scope_agent_bindings(tid),
            str(actor or "system"),
        )
    except Exception as exc:
        return {"active": False, "run_id": "", "started": False, "error": str(exc)}

    deadline = time.time() + max(5.0, float(poll_sec or DEFAULT_ENSURE_POLL_SEC))
    last_run_id = run_id
    while time.time() < deadline:
        current = _runtime_active_for_scope(pid, env, tid)
        last_run_id = str(current.get("run_id") or last_run_id)
        if current.get("active"):
            return {"active": True, "run_id": last_run_id, "started": True, "error": ""}
        time.sleep(POLL_INTERVAL_SEC)

    return {
        "active": False,
        "run_id": last_run_id,
        "started": True,
        "error": f"Runtime 启动超时（{int(poll_sec)}s）",
    }
