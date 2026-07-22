# -*- coding: utf-8 -*-
"""商业手游标准冷启动时序 Web 侧门禁（T2–T3）。

顺序：
  1. release_platform_ci_gate（scope / gateway / profile_source）
  2. verify_e2e_release（凭据 / manifest / scope / bootstrap 解析）
  3. runtime-bootstrap 契约抽检（门禁字段 + active_bundle_id）

Unity PlayMode（T4–T7）请另跑 unity_client_hotupdate_runner：
  - smoke：快速冒烟（Editor 跳过 config/code OSS）
  - basic：完整热更路径（需 OSS manifest 齐全）
"""

from __future__ import annotations

import json
import os
import subprocess
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


def _run_script(name: str, extra_args: list[str] | None = None) -> int:
    script = os.path.join(os.path.dirname(__file__), name)
    cmd = [sys.executable, script] + (extra_args or [])
    print(f"\n>>> {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=ROOT)


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


def _check_bootstrap_contract(payload: dict) -> list[str]:
    errors: list[str] = []
    if not payload.get("ok"):
        errors.append("bootstrap ok=false")
        return errors

    bootstrap = payload.get("bootstrap") or {}
    profile = payload.get("network_profile") or {}
    required_bootstrap = (
        "resource_relative_path",
        "catalog_file_name",
        "min_client_version",
        "rollout_percentage",
        "force_update",
        "is_revoked",
    )
    for key in required_bootstrap:
        if key not in bootstrap:
            errors.append(f"bootstrap missing field: {key}")

    gw = str(profile.get("gateway_ws") or "")
    if ":15050" not in gw:
        errors.append(f"gateway_ws missing :15050 ({gw})")

    if not str(payload.get("scope_id") or ""):
        errors.append("scope_id empty")

    rel = str(bootstrap.get("resource_relative_path") or "")
    if rel and "/Android/" in rel:
        errors.append(f"resource_relative_path should use lowercase android: {rel}")

    return errors


def main() -> int:
    base = DEFAULT_BASE
    print("=== Commercial Startup Sequence Gate (Web T2–T3) ===")
    print(f"base_url={base} scope={DEFAULT_SCOPE} version={DEFAULT_VERSION}")

    rc = _run_script(
        "release_platform_ci_gate.py",
        ["--base-url", base, "--scope-id", DEFAULT_SCOPE],
    )
    if rc != 0:
        print("FAIL: release_platform_ci_gate")
        return rc

    rc = _run_script("verify_e2e_release.py")
    if rc != 0:
        print("FAIL: verify_e2e_release")
        return rc

    try:
        payload = _fetch_bootstrap(base)
    except Exception as exc:
        print(f"FAIL: bootstrap fetch: {exc}")
        return 1

    errors = _check_bootstrap_contract(payload)
    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    print("PASS: runtime-bootstrap contract")
    print(json.dumps(
        {
            "scope_id": payload.get("scope_id"),
            "active_bundle_id": payload.get("active_bundle_id"),
            "gateway_ws": (payload.get("network_profile") or {}).get("gateway_ws"),
            "force_update": (payload.get("bootstrap") or {}).get("force_update"),
        },
        ensure_ascii=False,
        indent=2,
    ))
    print("\n=== ALL WEB GATES PASSED ===")
    print("Unity T4–T7: run unity_client_hotupdate_runner (scenario=smoke|basic|session)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
