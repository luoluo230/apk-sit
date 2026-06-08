#!/usr/bin/env python3
"""自测 Mongo/Redis 启动、状态、日志 API。"""
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"
ROOT = Path(__file__).resolve().parents[1]


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


def action(s: requests.Session, service_id: str, act: str) -> dict:
    r = s.post(
        f"{BASE}/api/ops-platform/services/action",
        json={"project_id": PROJECT, "service_id": service_id, "action": act},
        timeout=90,
    )
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:300]}
    body["_http"] = r.status_code
    return body


def logs(s: requests.Session, service_id: str) -> dict:
    r = s.get(
        f"{BASE}/api/ops-platform/services/logs",
        params={"project_id": PROJECT, "service_id": service_id, "tail": 20, "current_session": "0"},
        timeout=30,
    )
    return r.json() if r.content else {}


def detail(s: requests.Session) -> dict:
    r = s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": PROJECT, "agent_id": "agent-local-cn-1"},
        timeout=30,
    )
    return r.json() if r.content else {}


def main() -> int:
    fails = []
    s = login()
    for sid in ("mongo-db-cn-1", "redis-cache-cn-1"):
        print(f"\n===== {sid} =====")
        st = action(s, sid, "status")
        print("status", st.get("_http"), st.get("ok"), st.get("message", "")[:120])
        data = st.get("data") if isinstance(st.get("data"), dict) else {}
        print("  daemon", data.get("status"), "pid", data.get("pid"))

        start = action(s, sid, "start")
        print("start", start.get("_http"), start.get("ok"), start.get("message", "")[:120])
        if start.get("_http") != 200 or not start.get("ok"):
            fails.append(f"{sid}:start")

        st2 = action(s, sid, "status")
        data2 = st2.get("data") if isinstance(st2.get("data"), dict) else {}
        print("after", data2.get("status"), st2.get("message", "")[:80])

        lg = logs(s, sid)
        sources = lg.get("sources") or []
        total = int(lg.get("total") or 0)
        print("logs sources", sources, "total", total)
        lines = lg.get("lines") or []
        if lines:
            last = (lines[-1].get("raw") or lines[-1].get("message") or "")[:200]
            print("  last", last)
            if f"{sid}.log" not in str(sources):
                fails.append(f"{sid}:logs-not-daemon-only")
            if "2026-06-07" in last and "already listening" not in last and "daemon start" not in last:
                fails.append(f"{sid}:logs-stale")
            log_path = ROOT / "data" / "logs" / "daemons" / f"{sid}.log"
            if log_path.is_file():
                file_lines = [ln.strip() for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
                if file_lines:
                    newest = file_lines[-1][:200]
                    if newest and newest not in last and last not in newest:
                        fails.append(f"{sid}:logs-not-newest")
                        print("  newest_on_disk", newest[:200])
        else:
            fails.append(f"{sid}:logs-empty")

    for attempt in range(8):
        d = detail(s)
        agent = d.get("agent") if isinstance(d.get("agent"), dict) else {}
        pending = []
        for svc in agent.get("services") or []:
            if not isinstance(svc, dict):
                continue
            sid = str(svc.get("service_id") or "")
            if sid not in ("mongo-db-cn-1", "redis-cache-cn-1"):
                continue
            if str(svc.get("probe_status") or "").upper() != "PASS":
                pending.append(sid)
        if not pending:
            break
        time.sleep(2)

    agent = d.get("agent") if isinstance(d.get("agent"), dict) else {}
    for svc in agent.get("services") or []:
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or "")
        if sid not in ("mongo-db-cn-1", "redis-cache-cn-1"):
            continue
        print(
            f"detail {sid}: status={svc.get('status')} run={svc.get('run_state')} "
            f"probe={svc.get('probe_status')} port={svc.get('service_port')}"
        )
        if str(svc.get("probe_status") or "").upper() != "PASS":
            fails.append(f"{sid}:probe-not-pass")
        if str(svc.get("status") or "").upper() not in ("RUNNING", "STARTING"):
            fails.append(f"{sid}:ui-status")

    print("\n=== RESULT ===")
    if fails:
        print("FAIL:", ", ".join(fails))
        return 1
    print("PASS: mongo/redis start + logs + detail all OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
