"""Benchmark all loadAuxiliaryData endpoints."""
import re
import sys
import time

import requests

BASE = "http://127.0.0.1:5003"
SCOPE = {
    "project_id": "GomeKu",
    "env_key": "production",
    "topology_id": "topology-gomeku-production-default",
}


def login(session: requests.Session) -> None:
    r = session.get(f"{BASE}/login", timeout=15)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
    session.post(
        f"{BASE}/login",
        data={
            "username": "admin",
            "password": "admin123",
            "csrf_token": m.group(1) if m else "",
        },
        timeout=15,
    )


def bench_one(session: requests.Session, name: str, path: str, params: dict | None = None) -> float:
    t0 = time.time()
    r = session.get(f"{BASE}{path}", params=params or {}, timeout=120)
    dt = time.time() - t0
    print(f"{name:24} {dt:6.2f}s  status={r.status_code}")
    return dt


def main() -> int:
    s = requests.Session()
    login(s)
    endpoints = [
        ("nodes", "/api/gm-legacy/nodes", None),
        ("overview", "/api/ops-platform/overview", {"project_id": "GomeKu"}),
        ("blueprints", "/api/ops-platform/topology-blueprints", None),
        ("bindings", "/api/ops-platform/topology/node/bindings", SCOPE),
        ("agents-cache", "/api/ops-platform/agents", SCOPE),
        ("agents-live", "/api/ops-platform/agents", {**SCOPE, "live": "1"}),
        ("services", "/api/ops-platform/services", {"project_id": "GomeKu"}),
    ]
    print("--- sequential ---")
    for name, path, params in endpoints:
        bench_one(s, name, path, params)
    print("--- parallel (6 aux) ---")
    import concurrent.futures

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = []
        for name, path, params in endpoints[:6]:
            futs.append(ex.submit(bench_one, s, name, path, params))
        concurrent.futures.wait(futs)
    print(f"wall parallel sec={time.time()-t0:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
