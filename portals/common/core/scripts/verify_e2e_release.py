# -*- coding: utf-8 -*-
"""E2E release chain verification: credentials, scope, bootstrap contract."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_BASE = os.environ.get("RELEASE_GATE_BASE_URL", "http://127.0.0.1:5003")
DEFAULT_SCOPE = os.environ.get("RELEASE_GATE_SCOPE_ID", "gomeku:development:1001:android")
DEFAULT_GAME_ID = os.environ.get("RELEASE_GATE_GAME_ID", "gomeku-fb64779f94b161d0")
DEFAULT_GAME_KEY = os.environ.get("RELEASE_GATE_GAME_KEY", "zpf2zNQPoVfiqWjRCSpt70Rx9x4wjTWf")
DEFAULT_VERSION = os.environ.get("RELEASE_GATE_VERSION_NAME", "1.0.0")


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    base = DEFAULT_BASE.rstrip("/")
    errors: list[str] = []

    scope_url = f"{base}/api/release/scopes/{urllib.parse.quote(DEFAULT_SCOPE, safe='')}"
    try:
        scope_payload = _fetch_json(scope_url)
    except Exception as exc:
        print(f"FAIL: scope fetch: {exc}")
        return 1

    if not scope_payload.get("ok"):
        print(json.dumps({"ok": False, "step": "scope", "payload": scope_payload}, ensure_ascii=False))
        return 1

    resolved = scope_payload.get("resolved") or {}
    gateway = str((resolved.get("network_profile_preview") or {}).get("gateway_ws") or "")
    if ":15050" not in gateway:
        errors.append(f"gateway_ws missing :15050 ({gateway})")

    query = urllib.parse.urlencode({
        "game_id": DEFAULT_GAME_ID,
        "game_key": DEFAULT_GAME_KEY,
        "env_key": "development",
        "channel": "wechat",
        "platform": "android",
        "version_name": DEFAULT_VERSION,
    })
    bootstrap_url = f"{base}/api/public/runtime-bootstrap?{query}"
    try:
        bootstrap_payload = _fetch_json(bootstrap_url)
    except Exception as exc:
        errors.append(f"bootstrap fetch failed: {exc}")
        bootstrap_payload = {}

    if not bootstrap_payload.get("ok"):
        errors.append(f"bootstrap ok=false: {bootstrap_payload.get('error')}")
    else:
        bootstrap = bootstrap_payload.get("bootstrap") or {}
        if not bootstrap_payload.get("active_bundle_id"):
            errors.append("active_bundle_id empty")
        rel = str(bootstrap.get("resource_relative_path") or "")
        if rel and "/Android/" in rel:
            errors.append(f"resource_relative_path should use lowercase android: {rel}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    print("PASS: verify_e2e_release")
    print(json.dumps({
        "scope_id": DEFAULT_SCOPE,
        "gateway_ws": gateway,
        "active_bundle_id": bootstrap_payload.get("active_bundle_id"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
