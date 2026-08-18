# -*- coding: utf-8 -*-
"""Live-server release hub E2E (optional; used when RUN_RELEASE_HUB_LIVE_E2E=1)."""

from __future__ import annotations

import json
import os
import re
import sys

import requests

BASE = os.environ.get("RELEASE_GATE_BASE_URL", "http://127.0.0.1:5003").rstrip("/")


def login(session: requests.Session) -> None:
    r = session.get(f"{BASE}/login", timeout=20)
    r.raise_for_status()
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("csrf_token not found on login page")
    session.post(
        f"{BASE}/login",
        data={"username": "admin", "password": "admin123", "csrf_token": m.group(1)},
        timeout=20,
    )


def pick_project_id(session: requests.Session) -> str:
    r = session.get(f"{BASE}/admin/projects", timeout=20)
    r.raise_for_status()
    m = re.search(r"/admin/projects/([^\"'/]+)/overview", r.text)
    return m.group(1) if m else "GomeKu"


def main() -> int:
    s = requests.Session()
    login(s)
    pid = pick_project_id(s)
    checks: dict[str, bool] = {}

    hub_page = s.get(f"{BASE}/admin/projects/{pid}/release-hub", timeout=30)
    checks["release_hub_page_200"] = hub_page.status_code == 200
    checks["release_hub_title"] = "发版中心" in hub_page.text

    console_page = s.get(f"{BASE}/admin/projects/{pid}/release?env_key=development", timeout=30)
    checks["release_console_page_200"] = console_page.status_code == 200
    checks["release_console_title"] = "发版控制台" in console_page.text

    hub_api = s.get(f"{BASE}/api/projects/{pid}/release-hub?env_key=development", timeout=20)
    checks["release_hub_api_200"] = hub_api.status_code == 200 and hub_api.json().get("ok") is True

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"project_id": pid, "checks": checks}, ensure_ascii=False, indent=2))
    if failed:
        print("FAILED:", ", ".join(failed))
        return 2
    print("release_hub_live_e2e PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
