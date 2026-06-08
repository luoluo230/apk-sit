#!/usr/bin/env python3
"""自测各服务 stop 动作：API 响应 + 端口变化 + detail 状态。"""
import re
import subprocess
import time

import requests

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"
AGENT = "agent-local-cn-1"
SERVICES = (
    ("ops-cn-1", 5504),
    ("gateway-cn-1", 15050),
    ("mongo-db-cn-1", 27017),
    ("redis-cache-cn-1", 6379),
)


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


def detail_service(s: requests.Session, sid: str) -> dict:
    r = s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": PROJECT, "agent_id": AGENT},
        timeout=120,
    )
    body = r.json() if r.content else {}
    for svc in body.get("services") or []:
        if isinstance(svc, dict) and str(svc.get("service_id") or "") == sid:
            return svc
    return {}


def main() -> int:
    fails = []
    s = login()
    for sid, port in SERVICES:
        print(f"\n===== STOP {sid} (port {port}) =====")
        before_port = port_open(port)
        print(f"  port_before={before_port}")
        r = s.post(
            f"{BASE}/api/ops-platform/services/action",
            json={"project_id": PROJECT, "service_id": sid, "action": "stop"},
            timeout=120,
        )
        try:
            body = r.json()
        except Exception:
            body = {"raw": (r.text or "")[:300]}
        print(f"  http={r.status_code} ok={body.get('ok')} msg={str(body.get('message') or '')[:120]}")
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        print(f"  data.status={data.get('status')} nested={((data.get('state') or {}).get('status') if isinstance(data.get('state'), dict) else None)}")
        time.sleep(2)
        after_port = port_open(port)
        svc = detail_service(s, sid)
        print(
            f"  port_after={after_port} detail status={svc.get('status')} "
            f"probe={svc.get('probe_status')} run={svc.get('run_state')}"
        )
        if r.status_code != 200 or not body.get("ok"):
            fails.append(f"{sid}:api-fail")
        elif before_port and after_port and svc.get("probe_status") == "PASS":
            fails.append(f"{sid}:still-running")
    print("\n=== RESULT ===")
    if fails:
        print("FAIL:", ", ".join(fails))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
