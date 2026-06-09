import re
import sys

import requests

BASE = "http://127.0.0.1:5003"


def main() -> int:
    s = requests.Session()
    r = s.get(f"{BASE}/login", timeout=15)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
    s.post(
        f"{BASE}/login",
        data={"username": "admin", "password": "admin123", "csrf_token": m.group(1) if m else ""},
        timeout=15,
    )
    resp = s.post(
        f"{BASE}/api/ops-platform/services/ops-cn-1/action",
        json={
            "project_id": "GomeKu",
            "env_key": "production",
            "topology_id": "topology-gomeku-production-default",
            "topology_node_id": "ops-cn-1",
            "action": "start",
        },
        timeout=120,
    )
    print(resp.status_code, resp.text[:800])
    return 0 if resp.ok else 1


if __name__ == "__main__":
    sys.exit(main())
