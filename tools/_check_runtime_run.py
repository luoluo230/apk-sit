import json
import re
import sys

import requests

BASE = "http://127.0.0.1:5003"
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "run-ff124a154a35"
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


def main() -> int:
    s = requests.Session()
    login(s)
    act = s.get(f"{BASE}/api/ops-platform/runtime/active", params=SCOPE, timeout=30).json()
    print("active:", json.dumps(act, ensure_ascii=False, indent=2)[:2000])
    st = s.get(f"{BASE}/api/ops-platform/runtime/runs/{RUN_ID}", params=SCOPE, timeout=30).json()
    print("run:", json.dumps(st, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
