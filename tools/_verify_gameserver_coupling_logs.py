#!/usr/bin/env python3
"""自测 GameServer 独立进程启停与日志新鲜度。"""
import re
import socket
import sys
import time
from datetime import datetime, timezone

import requests

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"
GS_IDS = ("gateway-cn-1", "auth-cn-1", "game-cn-1", "ops-cn-1")


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


def detail_services(s: requests.Session) -> dict:
    r = s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": PROJECT, "agent_id": "agent-local-cn-1"},
        timeout=60,
    )
    body = r.json() if r.status_code == 200 else {}
    rows = {}
    for row in body.get("services") or []:
        sid = str(row.get("service_id") or "")
        rows[sid] = str(row.get("status") or row.get("run_state") or "").upper()
    return rows


def fetch_logs(s: requests.Session, service_id: str) -> dict:
    r = s.get(
        f"{BASE}/api/ops-platform/services/logs",
        params={
            "project_id": PROJECT,
            "service_id": service_id,
            "tail": 50,
            "current_session": "0",
            "hide_lifecycle": "0",
        },
        timeout=30,
    )
    return r.json() if r.status_code == 200 else {}


def parse_log_ts(text: str):
    m = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", text or "")
    if not m:
        return None
    raw = m.group(1).replace(" ", "T") + "Z"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    s = login()
    for sid in ("mongo-db-cn-1", "redis-cache-cn-1"):
        action(s, sid, "start")
        time.sleep(1)

    for sid in reversed(GS_IDS):
        action(s, sid, "stop")
    time.sleep(2)

    for sid in GS_IDS:
        body = action(s, sid, "start")
        print("start", sid, body.get("_http"), body.get("ok"), str(body.get("message") or "")[:100])
        if not body.get("ok"):
            return 1
        time.sleep(1.5)

    running = detail_services(s)
    for sid in GS_IDS:
        st = running.get(sid, "MISSING")
        print("after start all", sid, st)
        if st not in ("RUNNING", "STARTING"):
            print("FAIL: expected RUNNING/STARTING for", sid)
            return 1

    log_payload = fetch_logs(s, "gateway-cn-1")
    lines = log_payload.get("lines") or []
    print("log total", log_payload.get("total"), "sources", log_payload.get("sources"))
    if not lines:
        print("WARN: no log lines (GameServer may not have written cluster log yet)")
    else:
        last = lines[-1]
        ts = parse_log_ts(str(last.get("time") or last.get("raw") or ""))
        if ts:
            age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
            print("last log age_hours", round(age_h, 2), "line", str(last.get("raw") or "")[:100])
            if age_h > 6:
                print("FAIL: latest log older than 6h")
                return 1

    mongo_before = port_open(27017)
    redis_before = port_open(6379)
    stop_body = action(s, "gateway-cn-1", "stop")
    print("stop gateway", stop_body.get("_http"), stop_body.get("ok"), str(stop_body.get("message") or "")[:120])
    time.sleep(2)

    stopped = detail_services(s)
    print("after stop gateway", "gateway", stopped.get("gateway-cn-1"), "auth", stopped.get("auth-cn-1"))
    if stopped.get("gateway-cn-1") != "STOPPED":
        print("FAIL: gateway should be STOPPED")
        return 1
    if stopped.get("auth-cn-1") not in ("RUNNING", "STARTING"):
        print("FAIL: auth should remain RUNNING after gateway stop, got", stopped.get("auth-cn-1"))
        return 1

    if not port_open(15050):
        print("gateway port closed OK")
    else:
        print("FAIL: gateway port still open")
        return 1
    if stopped.get("auth-cn-1") in ("RUNNING", "STARTING"):
        print("auth still running after gateway stop OK")
    else:
        print("FAIL: auth should remain running after gateway stop")
        return 1

    if mongo_before and not port_open(27017):
        print("FAIL: mongo stopped with gateway")
        return 1
    if redis_before and not port_open(6379):
        print("FAIL: redis stopped with gateway")
        return 1
    print("mongo/redis unchanged OK")

    for sid in GS_IDS:
        action(s, sid, "stop")
    print("PASS independent process stop/start")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
