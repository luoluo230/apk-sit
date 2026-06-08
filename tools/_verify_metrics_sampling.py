#!/usr/bin/env python3
import re
import time

import requests

BASE = "http://127.0.0.1:5003"


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


def fetch(s, include):
    return s.get(
        f"{BASE}/api/ops-platform/agent/detail",
        params={"project_id": "GomeKu", "agent_id": "agent-local-cn-1", "include": include},
        timeout=120,
    ).json()


def main():
    s = login()
    for label, include in (("all", "all"), ("core1", "core"), ("core2", "core")):
        if label == "core2":
            time.sleep(6)
        body = fetch(s, include)
        agent = body.get("agent") or {}
        metrics = agent.get("metrics") or {}
        control = metrics.get("control") if isinstance(metrics.get("control"), dict) else metrics
        hist = body.get("metrics_history") or {}
        points = hist.get("points") or []
        print(
            label,
            "metrics_live",
            agent.get("metrics_live"),
            "cpu",
            control.get("cpu_percent"),
            "mem",
            control.get("mem_percent"),
            "disk",
            control.get("disk_percent"),
            "points",
            len(points),
            "has_history",
            hist.get("has_history"),
        )
    body = fetch(s, "core")
    points = (body.get("metrics_history") or {}).get("points") or []
    control = (body.get("agent") or {}).get("metrics") or {}
    if isinstance(control.get("control"), dict):
        control = control["control"]
    if control.get("cpu_percent") is None:
        return 1
    if len(points) < 1:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
