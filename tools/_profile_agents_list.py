"""Profile ops_platform_agents_list hot path."""
import re
import sys
import time

sys.path.insert(0, r"E:\web\apk-site\portals\common\core")

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


def profile_internal() -> None:
    from routes import gm_legacy as g

    project_id = "GomeKu"
    topology_id = "topology-gomeku-production-default"
    env_key = "production"

    def step(name, fn):
        t0 = time.perf_counter()
        out = fn()
        print(f"{name:40} {(time.perf_counter()-t0)*1000:8.1f} ms")
        return out

    rows = step("logical_agents", lambda: g._logical_agents_for_project(project_id))
    bindings = step("resolve_bindings", lambda: g._resolve_scope_agent_bindings_for_scope(topology_id, project_id, env_key))
    cluster = step("cluster_cached", lambda: g._fetch_cluster_runtime_status_cached(rows))
    svc = rows[0].get("services") if rows else []
    if svc:
        step("refresh_services_live x1", lambda: g._refresh_services_live_state(svc[:1], project_id=project_id, cluster_status=cluster, agent=rows[0]))
        step("refresh_services_live all", lambda: g._refresh_services_live_state(svc, project_id=project_id, cluster_status=cluster, agent=rows[0]))


def profile_http(session: requests.Session) -> None:
    for live in (0, 1):
        t0 = time.perf_counter()
        session.get(f"{BASE}/api/ops-platform/agents", params={**SCOPE, **({"live": "1"} if live else {})}, timeout=120)
        print(f"HTTP agents live={live} {(time.perf_counter()-t0)*1000:8.1f} ms")


def main() -> int:
    profile_internal()
    s = requests.Session()
    login(s)
    profile_http(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
