# -*- coding: utf-8 -*-
"""Bootstrap gate E2E: bootstrap → HEAD catalog → scope API platform chain."""

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
DEFAULT_SCOPE = os.environ.get("RELEASE_GATE_SCOPE_ID", "gomeku:development:1001:android")
DEFAULT_PLATFORM = os.environ.get("RELEASE_GATE_PLATFORM", "android")


def _fetch_bootstrap(base_url: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "game_id": DEFAULT_GAME_ID,
            "game_key": DEFAULT_GAME_KEY,
            "env_key": "development",
            "channel": "wechat",
            "platform": DEFAULT_PLATFORM,
            "version_name": DEFAULT_VERSION,
        }
    )
    url = f"{base_url.rstrip('/')}/api/public/runtime-bootstrap?{query}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _head_url(url: str) -> tuple[int, str]:
    if not url:
        return 0, "missing url"
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return int(resp.status or 0), ""
    except Exception as exc:
        return 0, str(exc)


def _fetch_scope(base_url: str, scope_id: str, platform: str) -> dict:
    query = urllib.parse.urlencode({"platform": platform, "version_name": DEFAULT_VERSION})
    url = f"{base_url.rstrip('/')}/api/release/scopes/{urllib.parse.quote(scope_id, safe=':')}?{query}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_gate_fields(payload: dict) -> list[str]:
    from services.release.bootstrap_contract import validate_bootstrap_contract

    errors = validate_bootstrap_contract(payload)
    if errors:
        return errors

    bootstrap = payload.get("bootstrap") or {}
    if os.environ.get("REQUIRE_FORCE_UPDATE", "").strip() in ("1", "true", "yes"):
        if bootstrap.get("force_update") is not True:
            errors.append(f"force_update must be true, got {bootstrap.get('force_update')!r}")

    return errors


def _check_catalog_head(bootstrap: dict) -> list[str]:
    errors: list[str] = []
    catalog_url = str(bootstrap.get("catalog_url") or "").strip()
    if not catalog_url:
        resource_base = str(bootstrap.get("resource_server_url") or "").rstrip("/")
        rel = str(bootstrap.get("resource_relative_path") or "").strip("/")
        catalog_name = str(bootstrap.get("catalog_file_name") or "").lstrip("/")
        if resource_base and rel and catalog_name:
            catalog_url = f"{resource_base}/{rel}/{catalog_name}"
    if not catalog_url:
        errors.append("catalog_url missing (cannot HEAD catalog)")
        return errors
    status, err = _head_url(catalog_url)
    if status < 200 or status >= 400:
        errors.append(f"catalog HEAD failed status={status} url={catalog_url[:120]} err={err}")
    return errors


def _check_scope_api(base_url: str, payload: dict) -> list[str]:
    errors: list[str] = []
    scope_id = str(payload.get("scope_id") or DEFAULT_SCOPE).strip()
    platform = str(DEFAULT_PLATFORM or "android").strip().lower()
    try:
        scope_payload = _fetch_scope(base_url, scope_id, platform)
    except Exception as exc:
        errors.append(f"scope API fetch failed: {exc}")
        return errors
    if not scope_payload.get("ok"):
        errors.append(f"scope API ok=false: {scope_payload.get('error')}")
        return errors
    resolved = scope_payload.get("resolved") if isinstance(scope_payload.get("resolved"), dict) else {}
    if str(resolved.get("platform") or "").lower() != platform:
        errors.append(f"scope API platform mismatch: {resolved.get('platform')}")
    if not str(resolved.get("scope_id") or scope_payload.get("scope_id") or ""):
        errors.append("scope API scope_id empty")
    return errors


def main() -> int:
    base = DEFAULT_BASE
    print("=== Bootstrap Gate E2E (full chain) ===")
    print(f"base_url={base} scope={DEFAULT_SCOPE} platform={DEFAULT_PLATFORM} version={DEFAULT_VERSION}")

    try:
        payload = _fetch_bootstrap(base)
    except Exception as exc:
        print(f"FAIL: bootstrap fetch: {exc}")
        return 1

    errors = _check_gate_fields(payload)
    bootstrap = payload.get("bootstrap") or {}
    errors.extend(_check_catalog_head(bootstrap))
    errors.extend(_check_scope_api(base, payload))

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        try:
            from services.client_telemetry import record_gate_pass

            record_gate_pass(
                "bootstrap_gate_e2e",
                passed=False,
                scope_id=str(payload.get("scope_id") or DEFAULT_SCOPE),
                platform=DEFAULT_PLATFORM,
            )
        except Exception:
            pass
        return 1

    print("PASS: bootstrap fields, catalog HEAD, scope API platform")
    print(
        json.dumps(
            {
                "force_update": bootstrap.get("force_update"),
                "rollout_percentage": bootstrap.get("rollout_percentage"),
                "scope_id": payload.get("scope_id"),
                "active_bundle_id": payload.get("active_bundle_id"),
                "catalog_url": bootstrap.get("catalog_url"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    try:
        from services.client_telemetry import record_gate_pass

        record_gate_pass(
            "bootstrap_gate_e2e",
            passed=True,
            scope_id=str(payload.get("scope_id") or DEFAULT_SCOPE),
            platform=DEFAULT_PLATFORM,
        )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
