# -*- coding: utf-8 -*-
"""CI gate for unified release platform."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _fetch(url: str, headers: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(body) if body else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("RELEASE_CI_BASE_URL", "http://127.0.0.1:5003"))
    parser.add_argument("--scope-id", default=os.environ.get("RELEASE_CI_SCOPE_ID", "gomeku:production:1001"))
    parser.add_argument("--ci-token", default=os.environ.get("GM_CI_TOKEN", ""))
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    scope_url = f"{base}/api/release/scopes/{urllib.parse.quote(args.scope_id, safe='')}"
    status, payload = _fetch(scope_url)
    if status != 200 or not payload.get("ok"):
        print(json.dumps({"ok": False, "step": "scope", "status": status, "payload": payload}, ensure_ascii=False))
        return 1

    resolved = payload.get("resolved") or {}
    profile = resolved.get("network_profile_preview") or {}
    gateway = str(profile.get("gateway_ws") or "")
    if ":15050" not in gateway and "gateway" not in gateway.lower():
        print(json.dumps({"ok": False, "step": "gateway", "gateway_ws": gateway}, ensure_ascii=False))
        return 1

    q = urllib.parse.urlencode({"scope_id": args.scope_id})
    if args.ci_token:
        headers = {"X-GM-CI-Token": args.ci_token}
        gate_url = f"{base}/api/gm-ops/quality-gate/ci?project_id=GomeKu&env=prod&channel=1001&platform=android"
        g_status, g_payload = _fetch(gate_url, headers=headers)
        print(json.dumps({"ok": g_payload.get("ok"), "scope": resolved, "quality_gate": g_payload}, ensure_ascii=False))
        return 0 if g_payload.get("ok") else 2

    print(json.dumps({"ok": True, "scope": resolved}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
