"""Inspect auth/game service fields from agents API."""
import json
import re

import requests

BASE = "http://127.0.0.1:5003"
SCOPE = {
    "project_id": "GomeKu",
    "env_key": "production",
    "topology_id": "topology-gomeku-production-default",
}


def main() -> None:
    s = requests.Session()
    r = s.get(f"{BASE}/login", timeout=15)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
    s.post(
        f"{BASE}/login",
        data={"username": "admin", "password": "admin123", "csrf_token": m.group(1) if m else ""},
        timeout=15,
    )
    for live in (0, 1):
        d = s.get(
            f"{BASE}/api/ops-platform/agents",
            params={**SCOPE, **({"live": "1"} if live else {})},
            timeout=30,
        ).json()
        ag = next(x for x in d.get("agents", []) if x.get("agent_id") == "agent-local-cn-1")
        print(f"=== live={live} ===")
        for svc in ag.get("services", []):
            sid = str(svc.get("service_id") or svc.get("node_id") or "")
            if "auth" in sid.lower() or "game" in sid.lower():
                print(
                    json.dumps(
                        {k: svc.get(k) for k in [
                            "service_id", "node_id", "service_type", "type", "role",
                            "probe_status", "run_state", "status", "probe_method", "cluster_state",
                        ]},
                        ensure_ascii=False,
                    )
                )


if __name__ == "__main__":
    main()
