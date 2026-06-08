"""Quick verify status-sync fixes: bindings fallback + live agents."""
import re
import sys

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


def main() -> int:
    s = requests.Session()
    login(s)

    for tid in ("topology-design-gomeku-production", "topology-gomeku-production-default"):
        d = s.get(
            f"{BASE}/api/ops-platform/topology/node/bindings",
            params={
                "project_id": "GomeKu",
                "env_key": "production",
                "topology_id": tid,
            },
            timeout=20,
        ).json()
        bindings = d.get("bindings") or {}
        print(f"bindings {tid}: count={len(bindings)}")

    params = {
        "project_id": "GomeKu",
        "env_key": "production",
        "topology_id": "topology-design-gomeku-production",
        "live": "1",
    }
    d = s.get(f"{BASE}/api/ops-platform/agents", params=params, timeout=60).json()
    ag = next(
        (x for x in (d.get("agents") or []) if x.get("agent_id") == "agent-local-cn-1"),
        {},
    )
    print(
        "agent probe:",
        ag.get("probe_status"),
        "eff:",
        ag.get("effective_status"),
        "source:",
        ag.get("probe_source"),
    )
    for svc in ag.get("services") or []:
        sid = svc.get("service_id") or svc.get("node_id")
        print(
            " ",
            sid,
            "probe:",
            svc.get("probe_status"),
            "state:",
            svc.get("run_state") or svc.get("status"),
        )
    print("agents resp bindings:", len(d.get("bindings") or {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
