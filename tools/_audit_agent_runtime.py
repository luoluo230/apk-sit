#!/usr/bin/env python3
"""Agent 模块运行时快照：端口、API 耗时、各服务状态。"""
import json
import re
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"
AGENT = "agent-local-cn-1"


def login() -> requests.Session:
    s = requests.Session()
    r = s.get(f"{BASE}/login", timeout=15)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
    s.post(
        f"{BASE}/login",
        data={"username": "admin", "password": "admin123", "csrf_token": m.group(1) if m else ""},
        timeout=15,
    )
    return s


def port_open(port: int) -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.5):
            return True
    except Exception:
        return False


def main() -> None:
    print("=== PORTS ===")
    for name, port in (("mongo", 27017), ("redis", 6379), ("gateway", 15050), ("ops", 5504)):
        print(f"  {name}:{port} -> {'OPEN' if port_open(port) else 'CLOSED'}")

    s = login()
    t0 = time.time()
    r = s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": PROJECT, "agent_id": AGENT},
        timeout=120,
    )
    ms = int((time.time() - t0) * 1000)
    body = r.json() if r.content else {}
    print(f"\n=== AGENT DETAIL ({ms} ms) ===")
    agent = body.get("agent") if isinstance(body.get("agent"), dict) else {}
    print(
        f"  agent effective={agent.get('effective_status')} probe={agent.get('probe_status')} "
        f"metrics_live={agent.get('metrics_live')}"
    )
    summary = body.get("service_summary") if isinstance(body.get("service_summary"), dict) else {}
    print(f"  summary: {json.dumps(summary, ensure_ascii=False)}")

    print("\n=== SERVICES (API view) ===")
    mismatches = []
    for svc in body.get("services") or []:
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or "")
        port = int(svc.get("service_port") or 0)
        live = port_open(port) if port > 0 else None
        probe = str(svc.get("probe_status") or "").upper()
        print(
            f"  {sid}: status={svc.get('status')} run={svc.get('run_state')} "
            f"probe={probe} host={svc.get('probe_host')} port={port} tcp={live} "
            f"updated={str(svc.get('updated_at') or '')[:19]}"
        )
        if sid in ("mongo-db-cn-1", "redis-cache-cn-1") and live and probe != "PASS":
            mismatches.append(sid)
    if mismatches:
        print(f"\n  MISMATCH (port open but probe!=PASS): {', '.join(mismatches)}")

    log_dir = Path(__file__).resolve().parents[1] / "data" / "logs" / "daemons"
    print("\n=== DAEMON LOG TAIL ===")
    for sid in ("mongo-db-cn-1", "redis-cache-cn-1"):
        p = log_dir / f"{sid}.log"
        if not p.is_file():
            print(f"  {sid}: no log file")
            continue
        lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        print(f"  {sid}: lines={len(lines)} last={lines[-1][:100] if lines else 'EMPTY'}")


if __name__ == "__main__":
    main()
