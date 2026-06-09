"""Verify embedded auth/game orchestration probe uses gateway/ops, not 5501/5502."""
import re
import sys

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
                ]
            )
    return "missing"


def main() -> int:
    s = requests.Session()
    login(s)
    d = s.get(
        f"{BASE}/api/ops-platform/agents",
        params={**SCOPE, "live": "1"},
        timeout=30,
    ).json()
    auth = svc_state(d, "auth-cn-1")
    game = svc_state(d, "game-cn-1")
    print("auth-cn-1:", auth)
    print("game-cn-1:", game)
    ok = "PASS" in auth and "RUNNING" in auth and "PASS" in game and "RUNNING" in game
    if not ok:
        print("FAIL: embedded services should be PASS|RUNNING when gateway/ops up")
        return 1
    print("PASS: embedded probe stable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
