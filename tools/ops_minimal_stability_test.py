#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GomeKu 最小框架全链路稳定性测试：拓扑 + 单 Agent + game-server。

要求：真实进程、真实探活、持续运行不掉线（含 soak 阶段）。

Usage:
  python3 tools/ops_minimal_stability_test.py
  python3 tools/ops_minimal_stability_test.py --soak-seconds 180 --soak-interval 15
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.ops_ecosystem_chain import (  # noqa: E402
    _cluster_agents,
    _essential_ports_ready,
    _is_embedded_cluster_node,
    _load_cluster,
    _resolve_game_server_repo,
    _tcp_ok,
    login,
    resolve_topology_scope,
    step_agent_protocol_register,
    step_auto_bind,
    step_cluster_sync,
    step_flow_control,
    step_flow_status,
    step_probe_all,
)

CANONICAL_ID = "agent-local-cn-1"
REQUIRED_EDGES = [
    ("gateway-cn-1", "auth-cn-1"),
    ("gateway-cn-1", "ops-cn-1"),
    ("auth-cn-1", "game-cn-1"),
    ("ops-cn-1", "game-cn-1"),
    ("game-cn-1", "mongo-db-cn-1"),
    ("game-cn-1", "redis-cache-cn-1"),
]
REQUIRED_NODES = [
    "gateway-cn-1",
    "auth-cn-1",
    "ops-cn-1",
    "game-cn-1",
    "mongo-db-cn-1",
    "redis-cache-cn-1",
]


def _ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S")


def _get(base: str, path: str, cookie: str = "") -> Dict[str, Any]:
    headers = {"Cookie": cookie} if cookie else {}
    r = requests.get(base.rstrip("/") + path, headers=headers, timeout=20)
    body = r.json() if r.content else {}
    body["_status"] = r.status_code
    return body


def _post(base: str, path: str, payload: Dict[str, Any], cookie: str = "") -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    r = requests.post(
        base.rstrip("/") + path,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=30,
    )
    body = r.json() if r.content else {}
    body["_status"] = r.status_code
    return body


def ensure_gameserver(repo: Path) -> Tuple[bool, str]:
    servers = _load_cluster(repo)
    agents = _cluster_agents(servers)
    if _essential_ports_ready(agents, servers):
        return True, "already running"
    script = repo / "scripts" / "Start-GameServer.sh"
    if not script.is_file():
        return False, f"missing {script}"
    proc = subprocess.run(["bash", str(script)], cwd=str(repo), capture_output=True, text=True, timeout=300)
    tail = (proc.stdout or "")[-800:]
    if proc.returncode != 0:
        return False, f"Start-GameServer exit {proc.returncode}\n{tail}"
    time.sleep(2)
    if not _essential_ports_ready(agents, servers):
        return False, f"ports still closed after start\n{tail}"
    return True, tail.splitlines()[-1] if tail else "started"


def ensure_agent_daemon(base: str, project: str, repo: Path) -> Tuple[bool, str]:
    script = ROOT / "tools" / "canonical_local_agent_daemon.py"
    out = subprocess.run(
        [sys.executable, str(script), "--once"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        return False, (out.stdout or "") + (out.stderr or "")
    # start background daemon if not running
    check = subprocess.run(["pgrep", "-f", "canonical_local_agent_daemon.py --daemon"], capture_output=True, text=True)
    if check.returncode != 0:
        log_path = ROOT / "data" / "logs" / "canonical-agent-daemon.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fp:
            subprocess.Popen(
                [sys.executable, str(script), "--daemon", "--interval", "20"],
                stdout=fp,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
            )
        time.sleep(2)
    return True, "daemon ok"


def setup_minimal_topology(base: str, cookie: str) -> Tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "setup_minimal_gomeku_topology.py")],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "OPS_USERNAME": os.getenv("OPS_USERNAME", "admin"), "OPS_PASSWORD": os.getenv("OPS_PASSWORD", "123456")},
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, text[-1200:]
    return True, text[-600:]


def verify_topology_graph(base: str, cookie: str, scope: Dict[str, str]) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    resp = _get(
        base,
        f"/api/ops-platform/topology?project_id={scope['project_id']}&env_key={scope['env_key']}&topology_id={scope['topology_id']}",
        cookie,
    )
    topo = resp.get("topology") if isinstance(resp.get("topology"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    node_ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
    edge_pairs = {(str(e.get("from") or ""), str(e.get("to") or "")) for e in edges if isinstance(e, dict)}
    ok = True
    for nid in REQUIRED_NODES:
        present = nid in node_ids
        logs.append(f"[{_ts()}] node {nid}: {'OK' if present else 'MISSING'}")
        ok = ok and present
    for frm, to in REQUIRED_EDGES:
        present = (frm, to) in edge_pairs
        logs.append(f"[{_ts()}] edge {frm}->{to}: {'OK' if present else 'MISSING'}")
        ok = ok and present
    return ok, logs


def verify_agents_state(base: str, cookie: str, project_id: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    resp = _get(base, f"/api/ops-platform/agents?project_id={project_id}", cookie)
    agents = resp.get("agents") if isinstance(resp.get("agents"), list) else []
    visible = [a for a in agents if isinstance(a, dict) and not a.get("stale") and str(a.get("agent_id") or "") == CANONICAL_ID]
    if len(visible) != 1:
        logs.append(f"[{_ts()}] canonical agent count={len(visible)} (want 1)")
        return False, logs
    ag = visible[0]
    logs.append(f"[{_ts()}] agent {CANONICAL_ID} status={ag.get('status')} probe={ag.get('probe_status')}")
    services = ag.get("services") if isinstance(ag.get("services"), list) else []
    logs.append(f"[{_ts()}] services={len(services)}")
    for svc in services:
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or svc.get("node_id") or "")
        st = str(svc.get("status") or svc.get("run_state") or "")
        logs.append(f"[{_ts()}]   {sid}: {st}")
    stale = [a for a in agents if isinstance(a, dict) and a.get("stale")]
    if stale:
        logs.append(f"[{_ts()}] stale agents={len(stale)} (ignored)")
    ok = str(ag.get("status") or "").upper() in ("ONLINE", "READY", "RUNNING") and len(services) >= 4
    return ok, logs


def verify_cluster_health(repo: Path) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    ok = True
    try:
        r = requests.get("http://127.0.0.1:5504/ops/cluster", timeout=5)
        body = r.json() if r.content else {}
        rows = body.get("data") if isinstance(body.get("data"), list) else body.get("servers") if isinstance(body.get("servers"), list) else []
        if not rows and isinstance(body.get("data"), dict):
            rows = body.get("data", {}).get("servers") or []
        logs.append(f"[{_ts()}] /ops/cluster entries={len(rows) if isinstance(rows, list) else 0}")
        if isinstance(rows, list):
            for row in rows[:6]:
                if isinstance(row, dict):
                    logs.append(f"[{_ts()}]   {row.get('ServerId') or row.get('serverId')}: {row.get('State') or row.get('status')}")
    except Exception as ex:
        logs.append(f"[{_ts()}] /ops/cluster FAIL: {ex}")
        ok = False
    servers = _load_cluster(repo)
    for ag in _cluster_agents(servers):
        embedded = _is_embedded_cluster_node(ag.get("node_id") or "", servers)
        alive = _tcp_ok(ag["host_name"], ag["port"])
        if embedded and not alive:
            logs.append(f"[{_ts()}] port {ag['node_id']}:{ag['port']} embedded OK")
            continue
        logs.append(f"[{_ts()}] port {ag['node_id']}:{ag['port']} {'LISTENING' if alive else 'CLOSED'}")
        ok = ok and alive
    for port, name in ((6379, "redis"), (27017, "mongo")):
        alive = _tcp_ok("127.0.0.1", port)
        logs.append(f"[{_ts()}] {name}:{port} {'LISTENING' if alive else 'CLOSED'}")
        ok = ok and alive
    return ok, logs


def soak_probe(base: str, cookie: str, project_id: str, scope: Dict[str, str], repo: Path, seconds: int, interval: int) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    deadline = time.time() + max(30, seconds)
    round_idx = 0
    ok = True
    while time.time() < deadline:
        round_idx += 1
        logs.append(f"[{_ts()}] soak round {round_idx}")
        p_ok, p_logs = step_probe_all(base, cookie, project_id)
        for line in p_logs:
            logs.append(line.replace("\n", ""))
        c_ok, c_logs = verify_cluster_health(repo)
        logs.extend(c_logs)
        a_ok, a_logs = verify_agents_state(base, cookie, project_id)
        logs.extend(a_logs)
        round_ok = p_ok and c_ok and a_ok
        logs.append(f"[{_ts()}] round {round_idx}: {'PASS' if round_ok else 'FAIL'}")
        ok = ok and round_ok
        if time.time() >= deadline:
            break
        time.sleep(max(5, interval))
    return ok, logs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5003")
    parser.add_argument("--project", default="GomeKu")
    parser.add_argument("--game-server-repo", default="")
    parser.add_argument("--soak-seconds", type=int, default=120)
    parser.add_argument("--soak-interval", type=int, default=15)
    parser.add_argument("--skip-soak", action="store_true")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    repo = _resolve_game_server_repo(args.game_server_repo)
    logs: List[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        logs.append(msg)

    steps: Dict[str, bool] = {}

    log(f"[{_ts()}] ═══ GomeKu 最小框架稳定性测试 ═══")

    gs_ok, gs_msg = ensure_gameserver(repo)
    log(f"[{_ts()}] game-server: {'OK' if gs_ok else 'FAIL'} {gs_msg[:200]}")
    steps["gameserver"] = gs_ok
    if not gs_ok:
        return _finish(steps, logs)

    ag_ok, ag_msg = ensure_agent_daemon(base, args.project, repo)
    log(f"[{_ts()}] canonical agent: {'OK' if ag_ok else 'FAIL'} {ag_msg[:200]}")
    steps["agent_daemon"] = ag_ok

    topo_ok, topo_msg = setup_minimal_topology(base, "")
    log(f"[{_ts()}] minimal topology setup: {'OK' if topo_ok else 'FAIL'}")
    for line in topo_msg.splitlines()[-8:]:
        log(line)
    steps["topology_setup"] = topo_ok

    ok_login, cookie = login(base)
    log(f"[{_ts()}] login: {'OK' if ok_login else 'FAIL'}")
    if not ok_login:
        steps["login"] = False
        return _finish(steps, logs)
    steps["login"] = True

    sync_ok, sync_logs = step_cluster_sync(base, cookie, args.project, repo)
    for line in sync_logs:
        log(line)
    steps["cluster_sync"] = sync_ok

    servers = _load_cluster(repo)
    reg_ok, reg_logs = step_agent_protocol_register(base, _cluster_agents(servers) + [
        {"node_id": "mongo-db-cn-1", "role": "database", "host_name": "127.0.0.1", "port": 27017, "remote_game_server_port": 27017, "desc": "Mongo"},
        {"node_id": "redis-cache-cn-1", "role": "cache", "host_name": "127.0.0.1", "port": 6379, "remote_game_server_port": 6379, "desc": "Redis"},
    ], args.project)
    for line in reg_logs:
        log(line)
    steps["agent_register"] = reg_ok

    probe_ok, probe_logs = step_probe_all(base, cookie, args.project)
    for line in probe_logs:
        log(line)
    steps["probe"] = probe_ok

    scope = resolve_topology_scope(base, cookie, args.project)
    bind_ok, bind_logs = step_auto_bind(base, cookie, scope)
    for line in bind_logs:
        log(line)
    steps["auto_bind"] = bind_ok

    graph_ok, graph_logs = verify_topology_graph(base, cookie, scope)
    for line in graph_logs:
        log(line)
    steps["topology_graph"] = graph_ok

    state_ok, state_logs = verify_agents_state(base, cookie, args.project)
    for line in state_logs:
        log(line)
    steps["agent_state"] = state_ok

    health_ok, health_logs = verify_cluster_health(repo)
    for line in health_logs:
        log(line)
    steps["cluster_health"] = health_ok

    if probe_ok and bind_ok:
        fc_ok, run_id, fc_logs = step_flow_control(base, cookie, scope, "start")
        for line in fc_logs:
            log(line)
        fs_ok, fs_logs = step_flow_status(base, cookie, run_id, timeout_sec=90)
        for line in fs_logs:
            log(line)
        steps["flow_run"] = fc_ok and fs_ok
    else:
        steps["flow_run"] = False

    if not args.skip_soak and all(steps.get(k) for k in ("gameserver", "probe", "auto_bind", "topology_graph")):
        log(f"\n[{_ts()}] ── soak {args.soak_seconds}s / interval {args.soak_interval}s ──")
        soak_ok, soak_logs = soak_probe(base, cookie, args.project, scope, repo, args.soak_seconds, args.soak_interval)
        for line in soak_logs:
            log(line)
        steps["soak"] = soak_ok
    else:
        steps["soak"] = False
        log(f"[{_ts()}] skip soak (preflight failed or --skip-soak)")

    return _finish(steps, logs)


def _finish(steps: Dict[str, bool], logs: List[str]) -> int:
    print(f"\n[{_ts()}] ═══ 结果 ═══", flush=True)
    for name, ok in steps.items():
        print(f"  {'✅' if ok else '❌'} {name}", flush=True)
    fails = [k for k, v in steps.items() if not v]
    report = ROOT / "data" / "logs" / f"minimal-stability-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(logs), encoding="utf-8")
    print(f"\n报告: {report}", flush=True)
    if fails:
        print(f"❌ 失败: {', '.join(fails)}", flush=True)
        return 1
    print("✅ 全链路稳定通过", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
