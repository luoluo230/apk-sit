#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple local agent runtime for ops-platform pull/report loop."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
import uuid
from typing import Any, Dict, List

import requests


def post_json(url: str, payload: Dict[str, Any], token: str, timeout: int = 6) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json", "X-Agent-Token": token}
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=timeout)
        if "application/json" not in (r.headers.get("content-type") or "").lower():
            return {"ok": False, "error": f"non-json:{r.status_code}"}
        body = r.json()
        body["_status"] = r.status_code
        return body
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


def run_job(base: str, node_id: str, token: str, agent_id: str, job: Dict[str, Any], sleep_sec: float = 0.15) -> None:
    job_id = str(job.get("job_id") or "")
    if not job_id:
        return
    running = {
        "node_id": node_id,
        "agent_id": agent_id,
        "job_id": job_id,
        "status": "RUNNING",
        "result": {"message": "job running"},
    }
    post_json(f"{base}/api/ops-platform/agent/report", running, token)
    time.sleep(sleep_sec)
    result = {
        "node_id": node_id,
        "agent_id": agent_id,
        "job_id": job_id,
        "status": "SUCCESS",
        "result": {"message": "job success", "action_type": job.get("action_type"), "target": job.get("target")},
    }
    post_json(f"{base}/api/ops-platform/agent/report", result, token)


def agent_loop(base: str, node_id: str, token: str, project_id: str, agent_name: str, device_id: str, port: int, loops: int, interval: float) -> Dict[str, Any]:
    agent_id = agent_name or f"agent-{node_id}-{uuid.uuid4().hex[:6]}"
    register_payload = {
        "node_id": node_id,
        "agent_id": agent_id,
        "project_id": project_id,
        "device_id": device_id,
        "host_name": socket.gethostname(),
        "display_name": agent_id,
        "port": port,
        "desc": f"local agent for {node_id}",
        "version": "v1-local",
        "run_state": "RUNNING",
        "transport_mode": "local_bus",
        "local_bus_enabled": True,
        "local_bus_endpoint": f"pipe://{device_id}/{agent_id}",
        "local_bus_auth_mode": "token",
        "capabilities": ["health_check", "start", "stop", "restart", "stress_test"],
        "token": token,
    }
    reg = post_json(f"{base}/api/ops-platform/agent/register", register_payload, token)
    if not reg.get("ok"):
        return {"ok": False, "stage": "register", "detail": reg}

    processed = 0
    for _ in range(max(1, loops)):
        hb = post_json(
            f"{base}/api/ops-platform/agent/heartbeat",
            {
                "node_id": node_id,
                "agent_id": agent_id,
                "project_id": project_id,
                "device_id": device_id,
                "host_name": socket.gethostname(),
                "display_name": agent_id,
                "port": port,
                "status": "ONLINE",
                "run_state": "RUNNING",
                "runtime": {"platform": platform.platform(), "ts": time.time()},
                "local_bus_enabled": True,
                "local_bus_endpoint": f"pipe://{device_id}/{agent_id}",
                "local_bus_auth_mode": "token",
                "token": token,
            },
            token,
        )
        if not hb.get("ok"):
            return {"ok": False, "stage": "heartbeat", "detail": hb}

        pull = post_json(
            f"{base}/api/ops-platform/agent/pull",
            {"node_id": node_id, "agent_id": agent_id, "limit": 5, "token": token},
            token,
        )
        jobs: List[Dict[str, Any]] = pull.get("jobs") if isinstance(pull.get("jobs"), list) else []
        for job in jobs:
            run_job(base, node_id, token, agent_id, job)
            processed += 1
        time.sleep(max(0.05, interval))

    return {"ok": True, "agent_id": agent_id, "processed_jobs": processed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5003")
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--project-id", default="GomeKu")
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--device-id", default="local-device-1")
    parser.add_argument("--port", type=int, default=19000)
    parser.add_argument("--loops", type=int, default=40)
    parser.add_argument("--interval", type=float, default=0.4)
    args = parser.parse_args()

    out = agent_loop(
        base=args.base.rstrip("/"),
        node_id=args.node_id,
        token=args.token,
        project_id=args.project_id,
        agent_name=args.agent_id,
        device_id=args.device_id,
        port=args.port,
        loops=args.loops,
        interval=args.interval,
    )
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

