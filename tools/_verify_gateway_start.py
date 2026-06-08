#!/usr/bin/env python3
"""自测 Windows 下 Gateway/GameServer 启动（不走 bash/WSL）。"""
import re
import socket
import sys
import time

import requests

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"


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
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.5):
            return True
    except Exception:
        return False


def main() -> int:
    s = login()
    for sid in ("mongo-db-cn-1", "redis-cache-cn-1"):
        action(s, sid, "start")
    t0 = time.time()
    body = action(s, "gateway-cn-1", "start")
    print("gateway http", body.get("_http"), "ok", body.get("ok"))
    print("message", str(body.get("message") or "")[:300])
    for port in (15050, 5504, 27017, 6379):
        print(f"port {port}", "OPEN" if port_open(port) else "CLOSED")
    print("elapsed_sec", int(time.time() - t0))
    if body.get("_http") != 200 or not body.get("ok"):
        return 1
    if not port_open(15050) or not port_open(5504):
        return 1
    return 0


def action(s: requests.Session, service_id: str, act: str) -> dict:
    r = s.post(
        f"{BASE}/api/ops-platform/services/action",
        json={"project_id": PROJECT, "service_id": service_id, "action": act},
        timeout=180,
    )
    try:
        body = r.json()
    except Exception:
        body = {"raw": (r.text or "")[:300]}
    body["_http"] = r.status_code
    return body


if __name__ == "__main__":
    raise SystemExit(main())
