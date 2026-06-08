"""Measure topology workbench critical path: bindings + agents live."""
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
        data={"username": "admin", "password": "admin123", "csrf_token": m.group(1) if m else ""},
        timeout=15,
    )


def main() -> int:
    s = requests.Session()
    login(s)
    t0 = time.perf_counter()
    b = s.get(f"{BASE}/api/ops-platform/topology/node/bindings", params=SCOPE, timeout=30).json()
    tb = time.perf_counter()
    a = s.get(f"{BASE}/api/ops-platform/agents", params={**SCOPE, "live": "1"}, timeout=30).json()
    ta = time.perf_counter()
    print(f"bindings {int((tb - t0) * 1000)} ms count={len(b.get('bindings') or {})}")
    print(f"agents live {int((ta - tb) * 1000)} ms count={len(a.get('agents') or [])}")
    print(f"critical parallel wall {int((ta - t0) * 1000)} ms (sequential sum)")
    import concurrent.futures

    t1 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fb = ex.submit(s.get, f"{BASE}/api/ops-platform/topology/node/bindings", params=SCOPE, timeout=30)
        fa = ex.submit(
            s.get,
            f"{BASE}/api/ops-platform/agents",
            params={**SCOPE, "live": "1"},
            timeout=30,
        )
        concurrent.futures.wait([fb, fa])
    print(f"critical actual parallel wall {int((time.perf_counter() - t1) * 1000)} ms")
    ag = next((x for x in (a.get("agents") or []) if x.get("agent_id") == "agent-local-cn-1"), {})
    for svc in ag.get("services") or []:
        print(
            " ",
            svc.get("service_id"),
            svc.get("probe_status"),
            svc.get("run_state") or svc.get("status"),
            svc.get("probe_method"),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
