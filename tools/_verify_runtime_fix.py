#!/usr/bin/env python3
import re
import socket

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
    r = s.post(
        f"{BASE}/api/ops-platform/services/action",
        json={"project_id": PROJECT, "service_id": sid, "action": act},
        timeout=180,
    )
    body = r.json() if r.status_code == 200 else {"raw": r.text[:200]}
    print(act, sid, body.get("ok"), str(body.get("message") or "")[:160])
    return body


def detail_map(s):
    d = s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": PROJECT, "agent_id": "agent-local-cn-1"},
        timeout=60,
    ).json()
    return {str(x.get("service_id") or ""): str(x.get("status") or "") for x in (d.get("services") or [])}


def logs_sample(s, sid):
    r = s.post(
        f"{BASE}/api/ops-platform/services/action",
        json={
            "project_id": PROJECT,
            "service_id": sid,
            "action": "logs",
            "current_session_only": True,
        },
        timeout=60,
    )
    body = r.json() if r.status_code == 200 else {}
    lines = (body.get("data") or {}).get("lines") or []
    sample = ""
    for row in lines[-5:]:
        sample += str(row.get("message") or row.get("raw") or "") + "\n"
    bad = sample.count("\ufffd") + sample.count("?")
    print("logs", sid, "lines", len(lines), "bad_chars", bad)
    if sample.strip():
        print(sample.strip()[:240])
    return bad < 8


def main():
    s = login()
    rows = detail_map(s)
    print("detail", rows)
    ok = all(rows.get(sid) == "RUNNING" for sid in IDS)
    if not ok:
        return 1
    body = action(s, "ops-cn-1", "start")
    if not body.get("ok"):
        return 1
    if "已在运行" not in str(body.get("message") or ""):
        return 1
    logs_ok = logs_sample(s, "ops-cn-1")
    action(s, "ops-cn-1", "stop")
    import time

    time.sleep(2)
    rows = detail_map(s)
    print("after stop", rows.get("ops-cn-1"))
    body = action(s, "ops-cn-1", "start")
    if not body.get("ok"):
        return 1
    time.sleep(2)
    try:
        socket.create_connection(("127.0.0.1", 5504), timeout=1)
        port_ok = True
    except Exception:
        port_ok = False
    print("port5504", port_ok)
    return 0 if port_ok and logs_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
