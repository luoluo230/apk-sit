#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 管理中心 + 服务器运维 + 拓扑编排 全量 API 回归。

Usage:
  py -3 tools/ops_full_regression.py
  py -3 tools/ops_full_regression.py --strict
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_DEFAULT = "http://127.0.0.1:5003"
PROJECT_DEFAULT = "GomeKu"
AGENT_DEFAULT = "agent-local-cn-1"
ROOT = Path(__file__).resolve().parents[2]


def login(base: str) -> requests.Session:
    s = requests.Session()
    r = s.get(f"{base}/login", timeout=20)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
    s.post(
        f"{base}/login",
        data={"username": "admin", "password": "admin123", "csrf_token": m.group(1) if m else ""},
        timeout=20,
    )
    return s


def record(rows: List[Dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    rows.append({"name": name, "ok": bool(ok), "detail": str(detail)[:500]})


def post(s: requests.Session, base: str, path: str, payload: Dict[str, Any], timeout: int = 120) -> Tuple[int, Dict[str, Any]]:
    r = s.post(f"{base}{path}", json=payload, timeout=timeout)
    body = r.json() if r.content else {}
    return r.status_code, body if isinstance(body, dict) else {}


def get(s: requests.Session, base: str, path: str, timeout: int = 60) -> Tuple[int, Dict[str, Any]]:
    r = s.get(f"{base}{path}", timeout=timeout)
    body = r.json() if r.content else {}
    return r.status_code, body if isinstance(body, dict) else {}


def ensure_infra_and_stack(s: requests.Session, base: str, project: str, rows: List[Dict[str, Any]]) -> None:
    for sid in ("mongo-db-cn-1", "redis-cache-cn-1"):
        st, body = post(s, base, "/api/ops-platform/services/action", {"project_id": project, "service_id": sid, "action": "start"})
        record(rows, f"infra:{sid}:start", st == 200 and body.get("ok"), f"http={st} ok={body.get('ok')} msg={body.get('message', body.get('error', ''))[:80]}")
    for _ in range(15):
        _, detail = get(s, base, f"/api/ops-platform/agent/detail?project_id={project}&agent_id={AGENT_DEFAULT}")
        svcs = {str(x.get("service_id")): x for x in (detail.get("services") or []) if isinstance(x, dict)}
        mongo_ok = str((svcs.get("mongo-db-cn-1") or {}).get("probe_status") or "").upper() == "PASS"
        redis_ok = str((svcs.get("redis-cache-cn-1") or {}).get("probe_status") or "").upper() == "PASS"
        if mongo_ok and redis_ok:
            record(rows, "infra:ready", True, "mongo+redis PASS")
            break
        time.sleep(2)
    else:
        record(rows, "infra:ready", False, "mongo/redis probe timeout")

    st, body = post(
        s,
        base,
        "/api/ops-platform/runtime/flow-control",
        {"project_id": project, "env_key": "production", "topology_id": f"topology-design-{project.lower()}-production", "op": "start"},
        timeout=300,
    )
    run_id = str(body.get("run_id") or "")
    record(rows, "stack:flow-start", st == 200 and body.get("ok"), f"http={st} run_id={run_id}")
    if run_id:
        for _ in range(60):
            _, fs = get(s, base, f"/api/ops-platform/runtime/flow-status?run_id={run_id}")
            status = str(fs.get("status") or "")
            done = fs.get("done_count")
            total = fs.get("total_count")
            if status in ("success", "failed", "cancelled"):
                record(rows, "stack:flow-status", status == "success", f"status={status} done={done}/{total}")
                break
            time.sleep(2)
        else:
            record(rows, "stack:flow-status", False, "flow-status timeout")


def test_agent_center(s: requests.Session, base: str, project: str, rows: List[Dict[str, Any]]) -> None:
    st, body = get(s, base, f"/api/ops-platform/agents?project_id={project}")
    record(rows, "agent:list", st == 200 and body.get("ok") is not False, f"http={st} count={len(body.get('agents') or [])}")

    st, body = get(s, base, f"/api/ops-platform/agents/devices?project_id={project}")
    record(rows, "agent:devices", st == 200, f"http={st}")

    t0 = time.time()
    st, body = get(s, base, f"/api/ops-platform/agent/detail?project_id={project}&agent_id={AGENT_DEFAULT}", timeout=90)
    ms = int((time.time() - t0) * 1000)
    record(rows, "agent:detail", st == 200 and isinstance(body.get("services"), list), f"http={st} ms={ms} svcs={len(body.get('services') or [])}")

    st, body = get(s, base, "/api/ops-platform/agent/jobs?limit=20")
    record(rows, "agent:jobs", st == 200, f"http={st} jobs={len(body.get('jobs') or body.get('items') or [])}")

    st, body = get(s, base, f"/api/ops-platform/agent/audit?project_id={project}&agent_id={AGENT_DEFAULT}&limit=20")
    record(rows, "agent:audit", st == 200, f"http={st}")

    st, body = post(s, base, "/api/ops-platform/agents/probe-all", {"project_id": project, "reason": "full-regression"})
    record(rows, "agent:probe-all", st == 200, f"http={st} ok={body.get('ok')}")

    _, detail_body = get(s, base, f"/api/ops-platform/agent/detail?project_id={project}&agent_id={AGENT_DEFAULT}")
    agent_row = detail_body.get("agent") if isinstance(detail_body.get("agent"), dict) else {}
    probe_host = str(agent_row.get("host_name") or agent_row.get("ip") or "127.0.0.1")
    probe_port = int(agent_row.get("port") or 19100)
    st, body = post(
        s,
        base,
        "/api/ops-platform/agents/probe",
        {"project_id": project, "agent_id": AGENT_DEFAULT, "host_name": probe_host, "port": probe_port},
    )
    record(rows, "agent:probe", st == 200 and body.get("ok"), f"http={st} ok={body.get('ok')} host={probe_host}:{probe_port}")

    st, body = post(s, base, "/api/ops-platform/agents/cleanup-expired", {"project_id": project, "ttl_hours": 720})
    record(rows, "agent:cleanup-expired", st == 200, f"http={st} ok={body.get('ok')}")

    st, body = get(s, base, "/api/ops-platform/agent/policy")
    record(rows, "agent:policy-get", st == 200, f"http={st}")


def test_server_ops(s: requests.Session, base: str, project: str, rows: List[Dict[str, Any]]) -> None:
    st, body = get(s, base, f"/api/ops-platform/services?project_id={project}")
    record(rows, "services:list", st == 200, f"http={st} count={len(body.get('services') or [])}")

    service_ids = [
        "mongo-db-cn-1",
        "redis-cache-cn-1",
        "gateway-cn-1",
        "auth-cn-1",
        "game-cn-1",
        "ops-cn-1",
    ]
    for sid in service_ids:
        st, body = post(s, base, "/api/ops-platform/services/action", {"project_id": project, "service_id": sid, "action": "status"})
        record(rows, f"service:{sid}:status", st == 200 and body.get("ok"), f"http={st} ok={body.get('ok')}")

    st, body = post(s, base, "/api/ops-platform/services/action", {"project_id": project, "service_id": "gateway-cn-1", "action": "probe"})
    record(rows, "service:gateway:probe", st == 200, f"http={st} ok={body.get('ok')}")

    st, body = get(s, base, f"/api/ops-platform/services/logs?project_id={project}&service_id=gateway-cn-1&lines=20")
    record(rows, "service:gateway:logs", st == 200, f"http={st}")


def test_topology_ops(s: requests.Session, base: str, project: str, rows: List[Dict[str, Any]]) -> None:
    scope = {
        "project_id": project,
        "env_key": "production",
        "topology_id": f"topology-design-{project.lower()}-production",
    }

    st, body = get(s, base, f"/api/ops-platform/topology?project_id={project}")
    record(rows, "topology:get", st == 200 and isinstance(body.get("topology"), dict), f"http={st}")
    topo = deepcopy(body.get("topology") or {})
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    node_ids = [str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id")]

    st, wm = post(s, base, "/api/ops-platform/topology/workbench-mode", {**scope, "workbench_mode": "edit", "workbench_locked_mode": ""})
    record(rows, "topology:workbench-mode", st == 200 and wm.get("ok"), f"http={st} mode={wm.get('workbench_mode')}")

    st, body = get(s, base, f"/api/ops-platform/topology/node/bindings?project_id={project}")
    record(rows, "topology:bindings", st == 200, f"http={st}")

    if node_ids:
        st, body = post(
            s,
            base,
            "/api/ops-platform/topology/node/bind-agent",
            {"project_id": project, "node_id": node_ids[0], "agent_id": AGENT_DEFAULT, "reason": "regression"},
        )
        record(rows, "topology:bind-agent", st == 200 and body.get("ok"), f"http={st} node={node_ids[0]}")

    st, body = post(s, base, "/api/ops-platform/topology/auto-bind-agents", {**scope, "reason": "regression"})
    record(rows, "topology:auto-bind-agents", st == 200, f"http={st} ok={body.get('ok')}")

    if len(node_ids) >= 2:
        st, body = post(
            s,
            base,
            "/api/ops-platform/flow-smoke",
            {**scope, "path_nodes": node_ids[:4], "reason": "full-regression"},
            timeout=180,
        )
        record(rows, "topology:flow-smoke", st == 200 and body.get("ok"), f"http={st} ok={body.get('ok')} steps={len(body.get('steps') or [])}")

    if node_ids:
        st, body = post(
            s,
            base,
            "/api/ops-platform/stress-test",
            {**scope, "node_id": node_ids[0], "qps": 5, "duration_sec": 3, "reason": "regression"},
            timeout=60,
        )
        record(rows, "topology:stress-test", st == 200, f"http={st} ok={body.get('ok')}")

    # 非破坏性：边 upsert + delete（与 ops_platform_smoke 相同字段）
    frm = node_ids[0] if node_ids else "gateway-cn-1"
    to = node_ids[1] if len(node_ids) > 1 else "auth-cn-1"
    st, body = post(
        s,
        base,
        "/api/ops-platform/topology/edge/upsert",
        {**scope, "from": frm, "to": to, "from_port": "out-1", "to_port": "in-1", "type": "depends_on", "note": "full-regression"},
    )
    created = ""
    if isinstance(body.get("topology"), dict):
        for edge in body["topology"].get("edges") or []:
            if isinstance(edge, dict) and str(edge.get("from")) == frm and str(edge.get("to")) == to:
                created = str(edge.get("id") or "")
                break
    record(rows, "topology:edge-upsert", st == 200 and body.get("ok"), f"http={st} edge={created or 'n/a'} err={body.get('error', '')}")
    if created:
        st2, body2 = post(s, base, "/api/ops-platform/topology/edge/delete", {"edge_id": created})
        record(rows, "topology:edge-delete", st2 == 200 and body2.get("ok"), f"http={st2}")
    else:
        record(rows, "topology:edge-delete", st in (409, 200), f"skipped delete (upsert err={body.get('error', '')})")

    # node update + save 回滚
    if nodes:
        first = nodes[0]
        nid = str(first.get("id") or "")
        label = str(first.get("label") or first.get("name") or "")
        patch_label = label + "-reg" if label and not label.endswith("-reg") else label
        st, body = post(s, base, "/api/ops-platform/topology/node/update", {"node_id": nid, "patch": {"label": patch_label}})
        record(rows, "topology:node-update", st == 200 and body.get("ok"), f"http={st} node={nid}")
        st2, body2 = post(s, base, "/api/ops-platform/topology/node/update", {"node_id": nid, "patch": {"label": label}})
        record(rows, "topology:node-update-revert", st2 == 200 and body2.get("ok"), f"http={st2}")

    st, body = get(s, base, "/api/ops-platform/topology-blueprints")
    record(rows, "topology:blueprints", st == 200, f"http={st} count={len(body.get('blueprints') or [])}")

    st, body = get(s, base, "/api/ops-platform/runtime/active")
    record(rows, "topology:runtime-active", st == 200, f"http={st}")


def run_subprocess_script(name: str, args: List[str], rows: List[Dict[str, Any]]) -> None:
    cmd = [sys.executable] + args
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
        ok = proc.returncode == 0
        tail = (proc.stdout or proc.stderr or "").strip()[-400:]
        record(rows, name, ok, f"exit={proc.returncode} {tail}")
    except subprocess.TimeoutExpired:
        record(rows, name, False, "timeout 600s")
    except Exception as ex:
        record(rows, name, False, str(ex))


def main() -> int:
    parser = argparse.ArgumentParser(description="Ops 全量回归：Agent + 服务 + 拓扑")
    parser.add_argument("--base", default=BASE_DEFAULT)
    parser.add_argument("--project", default=PROJECT_DEFAULT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-scripts", action="store_true", help="仅跑 HTTP 回归，不跑子脚本")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    rows: List[Dict[str, Any]] = []

    print("[1/4] 登录并拉起基础设施/栈...")
    s = login(base)
    ensure_infra_and_stack(s, base, args.project, rows)

    print("[2/4] Agent 管理中心...")
    test_agent_center(s, base, args.project, rows)

    print("[3/4] 服务器运维...")
    test_server_ops(s, base, args.project, rows)

    print("[4/4] 拓扑编排...")
    test_topology_ops(s, base, args.project, rows)

    if not args.skip_scripts:
        print("[+] 子脚本回归...")
        run_subprocess_script("script:platform-smoke", ["tools/ops_platform_smoke.py", "--project", args.project, "--strict"], rows)
        run_subprocess_script("script:workbench-audit", ["tools/ops_workbench_chain_audit.py", "--project", args.project, "--strict"], rows)
        run_subprocess_script("script:agent-control", ["tools/_verify_agent_control.py"], rows)
        run_subprocess_script("script:pytest-fast", ["-m", "pytest", "tests/ops_distributed", "-m", "fast", "-q"], rows)

    fails = [r for r in rows if not r["ok"]]
    out = {
        "project_id": args.project,
        "strict": args.strict,
        "total": len(rows),
        "failed": len(fails),
        "fails": [r["name"] for r in fails],
        "results": rows,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if fails and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
