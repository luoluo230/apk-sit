"""Sample auth/game probe status over time to detect flapping."""
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


def login(s: requests.Session) -> None:
    r = s.get(f"{BASE}/login", timeout=15)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
    s.post(
        f"{BASE}/login",
        data={"username": "admin", "password": "admin123", "csrf_token": m.group(1) if m else ""},
        timeout=15,
    )


def svc_state(agents_payload: dict, sid: str) -> str:
    ag = next((x for x in (agents_payload.get("agents") or []) if x.get("agent_id") == "agent-local-cn-1"), {})
    for svc in ag.get("services") or []:
        if str(svc.get("service_id") or svc.get("node_id")) == sid:
            return "|".join(
                [
                    str(svc.get("probe_status") or "-"),
                    str(svc.get("run_state") or svc.get("status") or "-"),
                    str(svc.get("probe_method") or "-"),
                    str(svc.get("cluster_state") or "-"),
                ]
            )
    return "missing"


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    s = requests.Session()
    login(s)
    print("round live=0 / live=1 for auth-cn-1 and game-cn-1")
    for i in range(rounds):
        parts = [f"#{i+1}"]
        for live in (0, 1):
            d = s.get(
                f"{BASE}/api/ops-platform/agents",
                params={**SCOPE, **({"live": "1"} if live else {})},
                timeout=30,
            ).json()
            parts.append(f"live={live} auth={svc_state(d, 'auth-cn-1')}")
            parts.append(f"game={svc_state(d, 'game-cn-1')}")
        print(" ".join(parts))
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
