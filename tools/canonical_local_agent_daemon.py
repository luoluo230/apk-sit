#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机 canonical Agent 守护进程：单 Agent 管理全部拓扑服务节点。

与 ops_ecosystem_chain.step_agent_protocol_register 对齐：
  agent_id=agent-local-cn-1, node_id=ops-cn-1, token=ops-write-key-2026

Usage:
  python3 tools/canonical_local_agent_daemon.py --daemon
  python3 tools/canonical_local_agent_daemon.py --once
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from gameserver_agent_exec import execute_ops_job  # noqa: E402
from tools.ops_ecosystem_chain import (  # noqa: E402
    AGENT_TOKEN,
    _cluster_agents,
    _load_cluster,
    _resolve_game_server_repo,
    step_agent_protocol_register,
)

CANONICAL_ID = "agent-local-cn-1"
DEVICE_ID = "local-game-server"
DEFAULT_BASE = "http://127.0.0.1:5003"
DEFAULT_PROJECT = "GomeKu"


def _post(base: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json", "X-Agent-Token": AGENT_TOKEN}
    r = requests.post(
        base.rstrip("/") + path,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=15,
    )
    body = r.json() if r.content else {}
    body["_status"] = r.status_code
    return body


def _collect_metrics() -> Dict[str, Any]:
    try:
        import psutil

        return {
            "control": {
                "cpu_percent": round(float(psutil.cpu_percent(interval=0.1)), 1),
                "mem_percent": round(float(psutil.virtual_memory().percent), 1),
                "disk_percent": round(float(psutil.disk_usage("/").percent), 1),
                "qps": 0,
                "rtt_ms": 0.0,
                "source": "runtime.sample",
            }
        }
    except Exception:
        return {
            "control": {
                "cpu_percent": 0.0,
                "mem_percent": 0.0,
                "disk_percent": 0.0,
                "qps": 0,
                "rtt_ms": 0.0,
                "source": "runtime.sample",
            }
        }


def heartbeat_once(base: str, project_id: str, ops_port: int) -> bool:
    host = socket.gethostname() or "127.0.0.1"
    resp = _post(
        base,
        "/api/ops-platform/agent/heartbeat",
        {
            "node_id": "ops-cn-1",
            "agent_id": CANONICAL_ID,
            "project_id": project_id,
            "device_id": DEVICE_ID,
            "host_name": host,
            "status": "ONLINE",
            "run_state": "RUNNING",
            "port": ops_port,
            "remote_game_server_port": ops_port,
            "metrics": _collect_metrics(),
            "token": AGENT_TOKEN,
        },
    )
    if not resp.get("ok"):
        print(f"[heartbeat] FAIL: {resp.get('error') or resp.get('message')}", flush=True)
        return False
    pull = _post(
        base,
        "/api/ops-platform/agent/pull",
        {
            "node_id": "ops-cn-1",
            "agent_id": CANONICAL_ID,
            "limit": 5,
            "token": AGENT_TOKEN,
        },
    )
    jobs = pull.get("jobs") if isinstance(pull.get("jobs"), list) else []
    if jobs:
        print(f"[pull] jobs={len(jobs)}", flush=True)
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("job_id") or "").strip()
        if not job_id:
            continue
        _post(
            base,
            "/api/ops-platform/agent/report",
            {
                "node_id": "ops-cn-1",
                "agent_id": CANONICAL_ID,
                "job_id": job_id,
                "status": "RUNNING",
                "result": {"message": "job running"},
            },
        )
        exec_result = execute_ops_job(job)
        _post(
            base,
            "/api/ops-platform/agent/report",
            {
                "node_id": "ops-cn-1",
                "agent_id": CANONICAL_ID,
                "job_id": job_id,
                "status": "SUCCESS" if exec_result.get("ok") else "FAILED",
                "result": {
                    "message": exec_result.get("message") or "job done",
                    "action_type": job.get("action_type"),
                    "target": job.get("target"),
                    "exec": exec_result,
                },
            },
        )
        print(
            f"[job] {job_id} action={job.get('action_type')} target={job.get('target')} ok={exec_result.get('ok')}",
            flush=True,
        )
    return True


def register_once(base: str, project_id: str, repo: Path) -> bool:
    servers = _load_cluster(repo)
    cluster_agents = _cluster_agents(servers)
    infra = [
        {
            "node_id": "mongo-db-cn-1",
            "role": "database",
            "host_name": "127.0.0.1",
            "port": 27017,
            "remote_game_server_port": 27017,
            "desc": "Mongo 主存储",
        },
        {
            "node_id": "redis-cache-cn-1",
            "role": "cache",
            "host_name": "127.0.0.1",
            "port": 6379,
            "remote_game_server_port": 6379,
            "desc": "Redis 缓存",
        },
    ]
    ok, logs = step_agent_protocol_register(base, cluster_agents + infra, project_id)
    for line in logs:
        print(line, flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.getenv("OPS_BASE", DEFAULT_BASE))
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--game-server-repo", default="")
    parser.add_argument("--interval", type=float, default=20.0)
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    repo = _resolve_game_server_repo(args.game_server_repo)
    ops_port = 5504
    for srv in _load_cluster(repo):
        if str(srv.get("ServerId") or "") == "ops-cn-1":
            ops_port = int(srv.get("Port") or 5504)
            break

    if not register_once(base, args.project, repo):
        return 1

    running = True

    def stop(*_a: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    if args.once:
        return 0 if heartbeat_once(base, args.project, ops_port) else 1

    print(f"[daemon] canonical agent {CANONICAL_ID} interval={args.interval}s", flush=True)
    while running:
        heartbeat_once(base, args.project, ops_port)
        if not args.daemon:
            break
        time.sleep(max(5.0, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
