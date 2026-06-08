#!/usr/bin/env python3
"""阶段2性能验收：对比 include=all vs include=core 耗时与状态准确性。"""
import json
import re
import time

import requests

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"
AGENT = "agent-local-cn-1"


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


def bench(s, include):
    t0 = time.time()
    r = s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": PROJECT, "agent_id": AGENT, "include": include},
        timeout=120,
    )
    ms = int((time.time() - t0) * 1000)
    body = r.json() if r.content else {}
    keys = sorted(body.keys())
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    services = body.get("services") or []
    running = sum(1 for x in services if str((x or {}).get("status") or "").upper() == "RUNNING")
    return ms, keys, meta, running, len(services)


def main():
    s = login()
    results = []
    for label, include in (("warmup", "core"), ("wait", "core"), ("all", "all"), ("core", "core"), ("core2", "core")):
        if label == "wait":
            time.sleep(8)
            continue
        ms, keys, meta, running, total = bench(s, include)
        results.append((label, ms, meta, running, total, keys))
        print(
            label,
            ms,
            "ms",
            "running",
            running,
            "/",
            total,
            "cache",
            meta.get("services_from_cache"),
            "probe_age",
            meta.get("probe_cache_age_sec"),
        )
    all_row = next((r for r in results if r[0] == "all"), None)
    core_row = next((r for r in results if r[0] == "core2"), None)
    if not all_row or not core_row:
        return 1
    if all_row[3] < all_row[4] or core_row[3] < core_row[4]:
        return 1
    if core_row[3] != all_row[3]:
        return 1
    if "jobs" in all_row[5] and "jobs" in core_row[5]:
        return 1
    if core_row[1] > all_row[1] + 50:
        print("WARN: core2 slower than all by >50ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
