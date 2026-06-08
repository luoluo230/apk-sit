"""Benchmark agents API with/without live probe."""
import re
import sys
import time

import requests

BASE = "http://127.0.0.1:5003"


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


def bench(session: requests.Session, path: str, params: dict) -> float:
    t0 = time.time()
    r = session.get(f"{BASE}{path}", params=params, timeout=120)
    dt = time.time() - t0
    print(f"{path} params={params} status={r.status_code} sec={dt:.2f}")
    return dt


def main() -> int:
    s = requests.Session()
    login(s)
    scope = {
        "project_id": "GomeKu",
        "env_key": "production",
        "topology_id": "topology-gomeku-production-default",
    }
    bench(s, "/api/ops-platform/topology/node/bindings", scope)
    bench(s, "/api/ops-platform/agents", scope)
    bench(s, "/api/ops-platform/agents", {**scope, "live": "1"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
