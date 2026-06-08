#!/usr/bin/env python3
import re
import socket
import sys
import time

import requests

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"
IDS = ["gateway-cn-1", "auth-cn-1", "game-cn-1", "ops-cn-1"]


def login():
    s = requests.Session()
    r = s.get(f"{BASE}/login", timeout=15)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
    s.post(
        f"{BASE}/login",
        data={"username": "admin", "password": "admin123", "csrf_token": m.group(1) if m else ""},
        timeout=15,
    )
    return s


def action(s, sid, act):
    t0 = time.time()
    r = s.post(
        f"{BASE}/api/ops-platform/services/action",
        json={"project_id": PROJECT, "service_id": sid, "action": act},
        timeout=180,
    )
    body = r.json() if r.status_code == 200 else {"raw": r.text[:200]}
    print(act, sid, r.status_code, body.get("ok"), f"{time.time()-t0:.1f}s", str(body.get("message") or "")[:160])
    return body


def port_state(port):
    try:
        socket.create_connection(("127.0.0.1", int(port)), timeout=0.5)
        return "OPEN"
    except Exception:
        return "CLOSED"


def main():
    s = login()
    for sid in reversed(IDS):
        action(s, sid, "stop")
        time.sleep(0.8)
    print("--- start gateway + auth ---")
    for sid in ("gateway-cn-1", "auth-cn-1"):
        body = action(s, sid, "start")
        if not body.get("ok"):
            return 1
        time.sleep(2)
    for port in (15050, 5501, 5502, 5504):
        print(f"port {port}", port_state(port))
    action(s, "gateway-cn-1", "stop")
    time.sleep(2)
    print("after gateway stop:", "15050", port_state(15050), "5501", port_state(5501))
    r = s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": PROJECT, "agent_id": "agent-local-cn-1"},
        timeout=60,
    )
    rows = {str(x.get("service_id") or ""): str(x.get("status") or "") for x in (r.json().get("services") or [])}
    print("detail after gw stop gateway", rows.get("gateway-cn-1"), "auth", rows.get("auth-cn-1"))
    if rows.get("gateway-cn-1") != "STOPPED":
        return 1
    if rows.get("auth-cn-1") not in ("RUNNING", "STARTING"):
        return 1
    for sid in IDS:
        action(s, sid, "stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
