#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拓扑工作台核心链路审计：运行/测试/模式持久化/API 对齐。

Usage:
  python3 tools/ops_workbench_chain_audit.py
  python3 tools/ops_workbench_chain_audit.py --project GomeKu --strict
"""

from __future__ import annotations

from pathlib import Path

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple


def _bootstrap_app():
    root = str(Path(__file__).resolve().parents[2])
    core = os.path.join(root, "portals", "common", "core")
    if core not in sys.path:
        sys.path.insert(0, core)
    os.environ["APP_PORTAL_MODE"] = "admin"
    from app_new import app  # type: ignore

    return app


def _session_client(app):
    client = app.test_client()
    with client.session_transaction() as s:
        s["user"] = "admin"
        s["permissions"] = ["gm_ops", "ops.platform.view", "ops.platform.execute"]
    return client


def _scope(project_id: str) -> Dict[str, str]:
    return {
        "project_id": project_id,
        "env_key": "production",
        "topology_id": f"topology-design-{project_id.lower()}-production",
    }


def _check(name: str, ok: bool, detail: str, rows: List[Dict[str, Any]], strict: bool) -> None:
    level = "ok" if ok else ("fail" if strict else "warn")
    rows.append({"name": name, "ok": ok, "level": level, "detail": detail})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="GomeKu")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    app = _bootstrap_app()
    client = _session_client(app)
    scope = _scope(args.project)
    rows: List[Dict[str, Any]] = []

    # API route existence
    rules = {str(r.rule): r for r in app.url_map.iter_rules()}
    for path in (
        "/api/ops-platform/runtime/flow-control",
        "/api/ops-platform/runtime/flow-status",
        "/api/ops-platform/runtime/active",
        "/api/ops-platform/topology/workbench-mode",
        "/api/ops-platform/flow-smoke",
        "/api/ops-platform/stress-test",
        "/api/ops-platform/topology/node/start-remote",
    ):
        _check(f"route:{path}", path in rules, "registered" if path in rules else "missing", rows, True)

    # workbench-mode persistence
    wm = client.post("/api/ops-platform/topology/workbench-mode", json={**scope, "workbench_mode": "run", "workbench_locked_mode": ""})
    wm_j = wm.get_json() or {}
    _check("workbench-mode", wm.status_code == 200 and wm_j.get("ok") is True, f"status={wm.status_code} mode={wm_j.get('workbench_mode')}", rows, True)

    # stop then start cluster lifecycle
    client.post("/api/ops-platform/runtime/flow-control", json={**scope, "op": "stop"})
    st = client.post("/api/ops-platform/runtime/flow-control", json={**scope, "op": "start"})
    st_j = st.get_json() or {}
    _check(
        "flow-control:start",
        st.status_code == 200 and st_j.get("ok") is not False and bool(st_j.get("run_id")),
        f"status={st.status_code} run={st_j.get('run_id')} run_status={st_j.get('status')} items={len(st_j.get('items') or [])}",
        rows,
        args.strict,
    )

    run_id = str(st_j.get("run_id") or "")
    if run_id:
        fs_j = {}
        for _ in range(90):
            fs = client.get(f"/api/ops-platform/runtime/flow-status?run_id={run_id}")
            fs_j = fs.get_json() or {}
            if fs.status_code == 200 and str(fs_j.get("status") or "").lower() in ("success", "failed"):
                break
            time.sleep(1)
        _check("flow-status", fs.status_code == 200 and fs_j.get("ok") is True, f"status={fs_j.get('status')} done={fs_j.get('done')}/{fs_j.get('total')}", rows, args.strict)

    sp = client.post("/api/ops-platform/runtime/flow-control", json={**scope, "op": "stop"})
    sp_j = sp.get_json() or {}
    stop_run_id = str(sp_j.get("run_id") or "")
    if stop_run_id:
        for _ in range(60):
            fs2 = client.get(f"/api/ops-platform/runtime/flow-status?run_id={stop_run_id}")
            fs2_j = fs2.get_json() or {}
            if fs2.status_code == 200 and str(fs2_j.get("status") or "").lower() in ("success", "failed"):
                break
            time.sleep(1)
    _check("flow-control:stop", sp.status_code == 200 and sp_j.get("ok") is True, f"status={sp_j.get('status')}", rows, args.strict)

    # flow-smoke resolves topology nodes (not legacy fallback)
    topo = client.get(f"/api/ops-platform/topology?project_id={args.project}").get_json() or {}
    node_ids = [str(n.get("id") or "") for n in ((topo.get("topology") or {}).get("nodes") or []) if isinstance(n, dict)][:4]
    if len(node_ids) >= 2:
        sm = client.post("/api/ops-platform/flow-smoke", json={**scope, "path_nodes": node_ids})
        sm_j = sm.get_json() or {}
        step_ids = [str(s.get("node_id") or "") for s in (sm_j.get("steps") or []) if isinstance(s, dict)]
        unique_ok = len(set(step_ids)) == len(step_ids) and step_ids == node_ids[: len(step_ids)]
        _check("flow-smoke:node-resolution", unique_ok, f"steps={step_ids}", rows, True)
        _check("flow-smoke:execute", sm.status_code in (200, 502), f"http={sm.status_code} ok={sm_j.get('ok')}", rows, False)

    if node_ids:
        pr = client.post("/api/ops-platform/stress-test", json={**scope, "node_id": node_ids[0], "qps": 10, "duration_sec": 5, "reason": "audit"})
        pr_j = pr.get_json() or {}
        _check("stress-test", pr.status_code in (200, 502) and pr.status_code != 400, f"http={pr.status_code} msg={str(pr_j.get('message') or '')[:80]}", rows, False)

    fails = [r for r in rows if not r["ok"] and r["level"] == "fail"]
    warns = [r for r in rows if not r["ok"] and r["level"] == "warn"]
    summary = {
        "project_id": args.project,
        "strict": args.strict,
        "total": len(rows),
        "failed": len(fails),
        "warn": len(warns),
        "results": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
