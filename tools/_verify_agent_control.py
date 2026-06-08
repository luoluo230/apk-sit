#!/usr/bin/env python3
"""Agent 管控一体化自测：详情耗时、infra 启动、GameServer 启动、stop/start。"""
import re
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"
AGENT = "agent-local-cn-1"
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


def detail_ms(s: requests.Session) -> tuple[int, dict]:
    t0 = time.time()
    r = s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": PROJECT, "agent_id": AGENT},
        timeout=60,
    )
    ms = int((time.time() - t0) * 1000)
    return ms, r.json() if r.content else {}


def action(s: requests.Session, service_id: str, act: str) -> dict:
    r = s.post(
        f"{BASE}/api/ops-platform/services/action",
        json={"project_id": PROJECT, "service_id": service_id, "action": act},
        timeout=180,
    )
    body = r.json() if r.content else {}
    body["_http"] = r.status_code
    return body


def svc_row(body: dict, sid: str) -> dict:
    for svc in body.get("services") or []:
        if isinstance(svc, dict) and str(svc.get("service_id") or "") == sid:
            return svc
    return {}


def main() -> int:
    fails = []
    s = login()

    ms, body = detail_ms(s)
    print(f"detail_load_ms={ms}")
    if ms > 2500:
        fails.append(f"detail-slow:{ms}ms")

    for sid in ("mongo-db-cn-1", "redis-cache-cn-1"):
        st = action(s, sid, "start")
        print(f"{sid} start http={st.get('_http')} ok={st.get('ok')} msg={str(st.get('message') or '')[:80]}")
        if st.get("_http") != 200 or not st.get("ok"):
            fails.append(f"{sid}:start")

    for _ in range(12):
        _, body = detail_ms(s)
        mongo = svc_row(body, "mongo-db-cn-1")
        redis = svc_row(body, "redis-cache-cn-1")
        if str(mongo.get("probe_status") or "").upper() == "PASS" and str(redis.get("probe_status") or "").upper() == "PASS":
            break
        time.sleep(2)
    else:
        fails.append("infra-not-ready")

    print(
        "infra",
        "mongo",
        mongo.get("status"),
        mongo.get("probe_status"),
        "redis",
        redis.get("status"),
        redis.get("probe_status"),
    )

    gs = action(s, "gateway-cn-1", "start")
    print(f"gateway start http={gs.get('_http')} ok={gs.get('ok')} msg={str(gs.get('message') or '')[:100]}")
    if gs.get("_http") != 200 or not gs.get("ok"):
        fails.append("gateway:start")

    for _ in range(20):
        _, body = detail_ms(s)
        gw = svc_row(body, "gateway-cn-1")
        if str(gw.get("probe_status") or "").upper() == "PASS":
            break
        time.sleep(3)
    else:
        fails.append("gateway-not-ready")

    st = action(s, "redis-cache-cn-1", "status")
    if st.get("_http") != 200:
        fails.append("redis:status-http")
    print(f"redis status http={st.get('_http')} ok={st.get('ok')}")

    stop = action(s, "redis-cache-cn-1", "stop")
    print(f"redis stop http={stop.get('_http')} ok={stop.get('ok')}")
    if stop.get("_http") != 200 or not stop.get("ok"):
        fails.append("redis:stop")

    time.sleep(2)
    _, body = detail_ms(s)
    redis = svc_row(body, "redis-cache-cn-1")
    if str(redis.get("status") or "").upper() not in ("STOPPED", "OFFLINE") and str(redis.get("run_state") or "").upper() != "STOPPED":
        fails.append("redis:not-stopped-after-stop")

    print("\n=== RESULT ===")
    if fails:
        print("FAIL:", ", ".join(fails))
        return 1
    print("PASS: agent control end-to-end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
