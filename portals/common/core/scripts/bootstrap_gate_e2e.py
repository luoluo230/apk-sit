# -*- coding: utf-8 -*-
"""Bootstrap gate E2E: force_update and rollout_percentage checks."""

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
DEFAULT_GAME_ID = os.environ.get("RELEASE_GATE_GAME_ID", "gomeku-fb64779f94b161d0")
DEFAULT_GAME_KEY = os.environ.get("RELEASE_GATE_GAME_KEY", "zpf2zNQPoVfiqWjRCSpt70Rx9x4wjTWf")
DEFAULT_VERSION = os.environ.get("RELEASE_GATE_VERSION_NAME", "1.0.0")


def _fetch_bootstrap(base_url: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "game_id": DEFAULT_GAME_ID,
            "game_key": DEFAULT_GAME_KEY,
            "env_key": "development",
            "channel": "wechat",
            "platform": "android",
            "version_name": DEFAULT_VERSION,
        }
    )
    url = f"{base_url.rstrip('/')}/api/public/runtime-bootstrap?{query}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_gate_fields(payload: dict) -> list[str]:
    errors: list[str] = []
    if not payload.get("ok"):
        errors.append(f"bootstrap ok=false: {payload.get('error')}")
        return errors

    bootstrap = payload.get("bootstrap") or {}
    if "force_update" not in bootstrap:
        errors.append("bootstrap missing force_update")
    if "rollout_percentage" not in bootstrap:
        errors.append("bootstrap missing rollout_percentage")

    rollout = bootstrap.get("rollout_percentage")
    try:
        rollout_val = int(rollout)
        if rollout_val < 0 or rollout_val > 100:
            errors.append(f"rollout_percentage out of range: {rollout_val}")
    except (TypeError, ValueError):
        errors.append(f"rollout_percentage not int: {rollout}")

    if not isinstance(bootstrap.get("force_update"), bool):
        errors.append("force_update must be boolean")

    if os.environ.get("REQUIRE_FORCE_UPDATE", "").strip() in ("1", "true", "yes"):
        if bootstrap.get("force_update") is not True:
            errors.append(f"force_update must be true, got {bootstrap.get('force_update')!r}")

    return errors


def main() -> int:
    base = DEFAULT_BASE
    print("=== Bootstrap Gate E2E ===")
    print(f"base_url={base} version={DEFAULT_VERSION}")

    try:
        payload = _fetch_bootstrap(base)
    except Exception as exc:
        print(f"FAIL: bootstrap fetch: {exc}")
        return 1

    errors = _check_gate_fields(payload)
    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        try:
            from services.client_telemetry import record_gate_pass

            record_gate_pass("bootstrap_gate_e2e", passed=False)
        except Exception:
            pass
        return 1

    bootstrap = payload.get("bootstrap") or {}
    print("PASS: force_update and rollout_percentage present")
    print(
        json.dumps(
            {
                "force_update": bootstrap.get("force_update"),
                "rollout_percentage": bootstrap.get("rollout_percentage"),
                "scope_id": payload.get("scope_id"),
                "active_bundle_id": payload.get("active_bundle_id"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    try:
        from services.client_telemetry import record_gate_pass

        record_gate_pass("bootstrap_gate_e2e", passed=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
