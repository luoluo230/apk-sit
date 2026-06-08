#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地直接写入最小拓扑（绕过 HTTP 登录），并启动 game-server + canonical agent。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "portals" / "common" / "core"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CORE))
os.environ.setdefault("APP_PORTAL_MODE", "admin")

from tools.setup_minimal_gomeku_topology import build_minimal_topology  # noqa: E402
from tools.ops_ecosystem_chain import (  # noqa: E402
    _cluster_agents,
    _essential_ports_ready,
    _load_cluster,
    _resolve_game_server_repo,
    _tcp_ok,
    step_agent_protocol_register,
    step_probe_all,
)
from routes import gm_legacy as gm  # noqa: E402

PROJECT = "GomeKu"
ENV_KEY = "production"
BASE = "http://127.0.0.1:5003"


def apply_topology() -> dict:
    ctx = gm._resolve_topology_context(PROJECT, ENV_KEY, "")
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    topology_id = str(row.get("topology_id") or "").strip()
    if not topology_id:
        row = gm._ensure_topology_for_scope(PROJECT, ENV_KEY)
        topology_id = str(row.get("topology_id") or "")
    topo = build_minimal_topology()
    saved = gm._save_topology_scoped(PROJECT, ENV_KEY, topology_id, topo)
    agent_stat = gm._upsert_agents_from_topology(PROJECT, saved.get("nodes") if isinstance(saved.get("nodes"), list) else [])
    purge_stat = gm._purge_design_demo_project_state(PROJECT, topology_id)
    sync_result = gm._sync_topology_to_game_server(PROJECT, ENV_KEY, topology_id, "local-script")
    canonical_stat = gm._consolidate_runtime_agents_to_canonical(PROJECT)
    return {
        "topology_id": topology_id,
        "nodes": len(saved.get("nodes") or []),
        "edges": len(saved.get("edges") or []),
        "agents": agent_stat,
        "purge": purge_stat,
        "sync": sync_result,
        "canonical": canonical_stat,
    }


def register_agents(repo: Path) -> bool:
    cluster_rows = _load_cluster(repo)
    cluster_agents = [
        a for a in _cluster_agents(cluster_rows)
        if a["node_id"] in {"gateway-cn-1", "auth-cn-1", "game-cn-1", "ops-cn-1"}
    ]
    infra_agents = [
        {
            "node_id": "mongo-db-cn-1",
            "agent_id": "agent-mongo-db-cn-1",
            "role": "database",
            "host_name": "127.0.0.1",
            "port": 27017,
            "remote_game_server_port": 27017,
            "desc": "Mongo 主存储",
        },
        {
            "node_id": "redis-cache-cn-1",
            "agent_id": "agent-redis-cache-cn-1",
            "role": "cache",
            "host_name": "127.0.0.1",
            "port": 6379,
            "remote_game_server_port": 6379,
            "desc": "Redis 缓存",
        },
    ]
    ok, logs = step_agent_protocol_register(BASE, cluster_agents + infra_agents, PROJECT)
    for line in logs:
        print(line)
    return ok


def start_gameserver(repo: Path) -> tuple[bool, str]:
    servers = _load_cluster(repo)
    agents = _cluster_agents(servers)
    if _essential_ports_ready(agents, servers) and _tcp_ok("127.0.0.1", 6379) and _tcp_ok("127.0.0.1", 27017):
        return True, "game-server already running"
    script = repo / "scripts" / "Start-GameServer.ps1"
    if not script.is_file():
        return False, f"missing {script}"
    proc = subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-SkipInstall",
        ],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        out, _ = proc.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, "Start-GameServer timeout"
    tail = (out or "")[-1200:]
    if proc.returncode != 0:
        return False, f"exit {proc.returncode}\n{tail}"
    time.sleep(3)
    if not _essential_ports_ready(agents, servers):
        return False, f"ports not ready after start\n{tail}"
    return True, "started"


def start_agent_daemon() -> tuple[bool, str]:
    script = ROOT / "tools" / "canonical_local_agent_daemon.py"
    once = subprocess.run(
        [sys.executable, str(script), "--once", "--game-server-repo", os.environ.get("GAME_SERVER_REPO", "")],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )
    if once.returncode != 0:
        return False, (once.stdout or "") + (once.stderr or "")
    log_path = ROOT / "data" / "logs" / "canonical-agent-daemon.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    check = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*canonical_local_agent_daemon.py*--daemon*' } | Select-Object -First 1 ProcessId"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if "ProcessId" not in (check.stdout or ""):
        with open(log_path, "a", encoding="utf-8") as fp:
            subprocess.Popen(
                [sys.executable, str(script), "--daemon", "--interval", "20"],
                stdout=fp,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT),
            )
        time.sleep(2)
    return True, "daemon running"


def main() -> int:
    repo = _resolve_game_server_repo(os.environ.get("GAME_SERVER_REPO", ""))
    os.environ["GAME_SERVER_REPO"] = str(repo)
    print(f"game-server repo: {repo}")

    stat = apply_topology()
    print(f"topology saved: id={stat['topology_id']} nodes={stat['nodes']} edges={stat['edges']}")
    print(f"sync: {stat['sync']}")
    print(f"canonical: {stat['canonical']}")

    if not register_agents(repo):
        print("agent register failed")
        return 1

    gs_ok, gs_msg = start_gameserver(repo)
    print(f"game-server: {'OK' if gs_ok else 'FAIL'}")
    print(gs_msg[-800:] if len(gs_msg) > 800 else gs_msg)
    if not gs_ok:
        return 1

    ag_ok, ag_msg = start_agent_daemon()
    print(f"agent daemon: {'OK' if ag_ok else 'FAIL'} {ag_msg}")

    probe_ok, probe_logs = step_probe_all(BASE, "", PROJECT)
    for line in probe_logs:
        print(line)
    print(f"probe-all: {'OK' if probe_ok else 'PARTIAL'}")

    print(f"\n拓扑编排: {BASE}/admin/ops-platform/topology?project_id={PROJECT}&env_key=production&topology_id={stat['topology_id']}")
    print(f"Agent 管控: {BASE}/admin/ops-platform/agent-control?project_id={PROJECT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
