#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run a complete minimal-framework e2e on local machine.

Flow:
1) login admin
2) apply minimal blueprint
3) align gm nodes (ops_base_url + token)
4) start mock ops server (optional external, default local 5054)
5) ensure agent daemons running for all topology nodes
6) approve+execute start actions in agent mode
7) run flow-smoke and stress-test
8) approve+execute stop actions in agent mode
9) print summary
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import requests


ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / "venv" / "Scripts" / "python.exe")
AGENT_SCRIPT = str(ROOT / "tools" / "local_ops_agent.py")
MOCK_OPS_SCRIPT = str(ROOT / "tools" / "mock_ops_server.py")


@dataclass
class Ctx:
    base: str
    project: str
    username: str
    password: str
    session: requests.Session
    csrf: str = ""
    approval_csrf: str = ""


def _must_json(resp: requests.Response) -> Dict[str, Any]:
    if "application/json" not in (resp.headers.get("content-type") or "").lower():
        raise RuntimeError(f"non-json response: {resp.status_code}")
    return resp.json()


def login(ctx: Ctx) -> None:
    r = ctx.session.get(f"{ctx.base}/login", timeout=8)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("csrf token not found in login page")
    ctx.csrf = m.group(1)
    r2 = ctx.session.post(
        f"{ctx.base}/login",
        data={"username": ctx.username, "password": ctx.password, "csrf_token": ctx.csrf},
        allow_redirects=False,
        timeout=8,
    )
    if r2.status_code not in (302, 303):
        raise RuntimeError(f"login failed: {r2.status_code}")
    p = ctx.session.get(f"{ctx.base}/admin/approval", timeout=8).text
    m2 = re.search(r'meta name="csrf-token" content="([^"]+)"', p)
    if not m2:
        raise RuntimeError("approval csrf token missing")
    ctx.approval_csrf = m2.group(1)


def start_mock_ops(host: str, port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [PY, MOCK_OPS_SCRIPT, "--host", host, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def apply_minimal(ctx: Ctx) -> List[str]:
    r = ctx.session.post(
        f"{ctx.base}/api/ops-platform/topology/apply-blueprint",
        json={"project_id": ctx.project, "blueprint_id": "minimal_framework", "replace_existing": True},
        timeout=15,
    )
    d = _must_json(r)
    if not d.get("ok"):
        raise RuntimeError(f"apply blueprint failed: {d}")
    # Read back once to avoid transient/template response drift in repeated runs.
    fresh = _must_json(ctx.session.get(f"{ctx.base}/api/ops-platform/topology?project_id={ctx.project}", timeout=10))
    topo = fresh.get("topology") if isinstance(fresh.get("topology"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    return [str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id")]


def save_nodes_config(ctx: Ctx, node_ids: List[str]) -> None:
    topo = _must_json(ctx.session.get(f"{ctx.base}/api/ops-platform/topology?project_id={ctx.project}", timeout=10))
    nodes = (topo.get("topology") or {}).get("nodes") or []
    role_map = {str(n.get("id")): str(n.get("role") or "business") for n in nodes if isinstance(n, dict)}
    rows = []
    for nid in node_ids:
        tok = f"tok-{nid}"
        rows.append(
            {
                "id": nid,
                "name": nid,
                "base_url": "http://127.0.0.1:5054",
                "ops_base_url": "http://127.0.0.1:5054",
                "ops_read_key": tok,
                "ops_write_key": tok,
                "ops_actor": "local-ops",
                "ops_role": "SuperAdmin",
                "server_id": nid,
                "project_id": ctx.project,
                "owner": "ops-admin",
                "role": role_map.get(nid, "business"),
                "description": "local minimal e2e",
                "biz_status": "normal",
                "enabled": True,
                "env": "prod",
                "channel": "1001",
                "tags": ["minimal", "e2e"],
            }
        )
    r = ctx.session.post(f"{ctx.base}/api/gm-legacy/nodes", json={"nodes": rows}, timeout=15)
    d = _must_json(r)
    if not d.get("ok"):
        raise RuntimeError(f"save nodes failed: {d}")


def ensure_policy(ctx: Ctx) -> None:
    ctx.session.post(
        f"{ctx.base}/api/ops-platform/agent/policy",
        json={"mtls_required": False, "lease_timeout_sec": 30, "max_retries": 1, "default_node_concurrency": 2},
        timeout=8,
    )


def start_agents(ctx: Ctx, node_ids: List[str]) -> List[subprocess.Popen[str]]:
    procs: List[subprocess.Popen[str]] = []
    for i, nid in enumerate(node_ids):
        agent_id = f"agent-{nid}"
        if os.name == "nt":
            probe = (
                "$self=$PID; "
                f"$hit = Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -ne $self -and $_.CommandLine -match 'local_ops_agent.py' -and $_.CommandLine -match '--agent-id {agent_id}' }}; "
                "if($hit){'1'} else {'0'}"
            )
            exists = subprocess.run(["powershell", "-NoProfile", "-Command", probe], capture_output=True, text=True)
            if exists.returncode == 0 and (exists.stdout or "").strip() == "1":
                continue
        tok = f"tok-{nid}"
        p = subprocess.Popen(
            [
                PY,
                AGENT_SCRIPT,
                "--base",
                ctx.base,
                "--node-id",
                nid,
                "--token",
                tok,
                "--project-id",
                ctx.project,
                "--agent-id",
                agent_id,
                "--device-id",
                "local-device-1",
                "--port",
                str(22000 + i),
                "--loops",
                "999999",
                "--interval",
                "1.0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(p)
    return procs


def stop_existing_local_agents() -> int:
    if os.name != "nt":
        return 0
    cmd = (
        "$self=$PID; "
        "$procs = Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $self -and $_.CommandLine -match 'local_ops_agent.py' }; "
        "$ids=@($procs | ForEach-Object { $_.ProcessId }); "
        "if($ids.Count -gt 0){ $ids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }; "
        "Write-Output $ids.Count"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    if r.returncode != 0:
        return 0
    try:
        return int((r.stdout or "0").strip() or "0")
    except ValueError:
        return 0


def bind_nodes(ctx: Ctx, node_ids: List[str]) -> None:
    for nid in node_ids:
        r = ctx.session.post(
            f"{ctx.base}/api/ops-platform/topology/node/bind-agent",
            json={"project_id": ctx.project, "node_id": nid, "agent_id": f"agent-{nid}"},
            timeout=10,
        )
        d = _must_json(r)
        if not d.get("ok"):
            raise RuntimeError(f"bind failed for {nid}: {d}")


def _approve_action(ctx: Ctx, node_id: str, action_type: str, ticket: str, reason: str) -> str:
    r = ctx.session.post(
        f"{ctx.base}/api/ops-platform/actions/approval",
        json={
            "project_id": ctx.project,
            "node_id": node_id,
            "action_type": action_type,
            "target": node_id,
            "ticket_id": ticket,
            "reason": reason,
            "approver": "admin",
        },
        timeout=10,
    )
    d = _must_json(r)
    aid = str(d.get("approval_id") or "")
    if not aid:
        raise RuntimeError(f"approval create failed: {d}")
    r2 = ctx.session.post(
        f"{ctx.base}/admin/approval/{aid}/approve",
        json={"comment": f"auto-approve {action_type}"},
        headers={"X-CSRFToken": ctx.approval_csrf},
        timeout=10,
    )
    d2 = _must_json(r2)
    if not d2.get("ok"):
        raise RuntimeError(f"approval approve failed: {d2}")
    return aid


def enqueue_agent_action(ctx: Ctx, node_id: str, action_type: str, approval_id: str, ticket: str, reason: str) -> None:
    r = ctx.session.post(
        f"{ctx.base}/api/ops-platform/actions/execute",
        json={
            "project_id": ctx.project,
            "node_id": node_id,
            "action_type": action_type,
            "target": node_id,
            "ticket_id": ticket,
            "reason": reason,
            "approver": "admin",
            "approval_id": approval_id,
            "run_mode": "agent",
            "via_agent": True,
            "payload": {"run_mode": "agent"},
        },
        timeout=10,
    )
    d = _must_json(r)
    if not d.get("ok"):
        raise RuntimeError(f"execute enqueue failed for {node_id}/{action_type}: {d}")


def wait_queue_empty(ctx: Ctx, timeout_sec: int = 45) -> Dict[str, int]:
    deadline = time.time() + timeout_sec
    last_status: Dict[str, int] = {}
    while time.time() < deadline:
        jobs = (_must_json(ctx.session.get(f"{ctx.base}/api/ops-platform/agent/jobs?limit=1000", timeout=10)).get("jobs") or [])
        status: Dict[str, int] = {}
        pending = 0
        for j in jobs:
            if not isinstance(j, dict):
                continue
            st = str(j.get("status") or "UNKNOWN")
            status[st] = status.get(st, 0) + 1
            if st in ("PENDING", "RUNNING"):
                pending += 1
        last_status = status
        if pending == 0:
            return status
        time.sleep(1)
    return last_status


def run_smoke_and_stress(ctx: Ctx, node_ids: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if len(node_ids) >= 2:
        r = ctx.session.post(f"{ctx.base}/api/ops-platform/flow-smoke", json={"path_nodes": node_ids[:2]}, timeout=15)
        out["flow_smoke"] = {"status": r.status_code, "body": _must_json(r)}
    if node_ids:
        r2 = ctx.session.post(
            f"{ctx.base}/api/ops-platform/stress-test",
            json={"node_id": node_ids[0], "qps": 30, "duration_sec": 8, "reason": "minimal e2e stress"},
            timeout=15,
        )
        out["stress_test"] = {"status": r2.status_code, "body": _must_json(r2)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5003")
    parser.add_argument("--project", default="GomeKu")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--start-mock-ops", action="store_true")
    parser.add_argument("--keep-existing-agents", action="store_true")
    args = parser.parse_args()

    ctx = Ctx(base=args.base.rstrip("/"), project=args.project, username=args.username, password=args.password, session=requests.Session())
    mock_proc: subprocess.Popen[str] | None = None
    agent_procs: List[subprocess.Popen[str]] = []

    try:
        if not args.keep_existing_agents:
            stop_existing_local_agents()
        if args.start_mock_ops:
            mock_proc = start_mock_ops("127.0.0.1", 5054)
            time.sleep(1)
        login(ctx)
        node_ids = apply_minimal(ctx)
        save_nodes_config(ctx, node_ids)
        ensure_policy(ctx)
        agent_procs = start_agents(ctx, node_ids)
        time.sleep(2)
        bind_nodes(ctx, node_ids)

        for nid in node_ids:
            aid = _approve_action(ctx, nid, "start", "OPS-E2E-START", "e2e start")
            enqueue_agent_action(ctx, nid, "start", aid, "OPS-E2E-START-EXEC", "e2e start execute")
        start_status = wait_queue_empty(ctx, timeout_sec=60)

        checks = run_smoke_and_stress(ctx, node_ids)

        for nid in node_ids:
            aid = _approve_action(ctx, nid, "stop", "OPS-E2E-STOP", "e2e stop")
            enqueue_agent_action(ctx, nid, "stop", aid, "OPS-E2E-STOP-EXEC", "e2e stop execute")
        stop_status = wait_queue_empty(ctx, timeout_sec=60)

        agents = _must_json(ctx.session.get(f"{ctx.base}/api/ops-platform/agents?project_id={ctx.project}", timeout=10)).get("agents") or []
        live_agent_ids = {f"agent-{nid}" for nid in node_ids}
        summary = {
            "project": ctx.project,
            "nodes": node_ids,
            "agents_online": len(
                [
                    a
                    for a in agents
                    if str((a or {}).get("status") or "").upper() == "ONLINE"
                    and str((a or {}).get("agent_id") or "") in live_agent_ids
                ]
            ),
            "queue_after_start": start_status,
            "queue_after_stop": stop_status,
            **checks,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        # keep agents running intentionally for live platform usage
        if mock_proc is not None and mock_proc.poll() is None:
            pass
        for p in agent_procs:
            if p.poll() is not None:
                continue


if __name__ == "__main__":
    raise SystemExit(main())
