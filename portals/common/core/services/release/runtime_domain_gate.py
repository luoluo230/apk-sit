# -*- coding: utf-8 -*-
"""Runtime domain gate: bootstrap + catalog + code/config patch content (HTTP)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from services.release.patch_manifest_probe import probe_catalog, probe_patch_manifest


def _get_json(url: str, *, timeout: float = 20.0) -> Dict[str, Any]:
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def run_runtime_domain_gate(
    *,
    portal_base: str,
    game_id: str,
    game_key: str,
    env_key: str = "development",
    channel: str = "wechat",
    platform: str = "android",
    version_name: str = "",
    version_code: str = "",
    require_prefer_unified_note: bool = True,
) -> Dict[str, Any]:
    """Prove DOMAIN resource/code/config over HTTP (no Unity required)."""
    base = str(portal_base or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "portal_base required"}
    if not game_id or not game_key:
        return {"ok": False, "error": "game_id/game_key required"}

    query = {
        "game_id": game_id,
        "game_key": game_key,
        "env_key": env_key,
        "channel": channel,
        "platform": platform,
    }
    if version_name:
        query["version_name"] = version_name
    if version_code:
        query["version_code"] = version_code
    bootstrap_url = f"{base}/api/public/runtime-bootstrap?{urlencode(query)}"
    try:
        body = _get_json(bootstrap_url)
    except HTTPError as exc:
        return {"ok": False, "error": f"bootstrap HTTP {exc.code}", "bootstrap_url": bootstrap_url}
    except (URLError, Exception) as exc:
        return {"ok": False, "error": f"bootstrap failed: {exc}", "bootstrap_url": bootstrap_url}

    if not body.get("ok"):
        return {"ok": False, "error": body.get("error") or "bootstrap ok=false", "bootstrap": body}

    boot = body.get("bootstrap") if isinstance(body.get("bootstrap"), dict) else {}
    bundle_id = str(body.get("active_bundle_id") or "")
    is_gate_fixture = bundle_id.startswith("rb-gate-")
    catalog_url = str(boot.get("catalog_url") or "").strip()
    config_url = str(boot.get("config_manifest_url") or boot.get("config_url") or "").strip()
    code_url = str(boot.get("code_manifest_url") or boot.get("code_url") or "").strip()

    checks = {
        "resource": probe_catalog(catalog_url) if catalog_url else {"ok": False, "error": "missing catalog_url"},
        "config": probe_patch_manifest(config_url, label="config", is_gate_fixture=is_gate_fixture)
        if config_url
        else {"ok": False, "error": "missing config manifest"},
        "code": probe_patch_manifest(code_url, label="code", is_gate_fixture=is_gate_fixture)
        if code_url
        else {"ok": False, "error": "missing code manifest"},
    }
    identity = {
        "project_id": body.get("project_id"),
        "env_key": body.get("env_key"),
        "channel_id": body.get("channel_id"),
        "channel_key": body.get("channel_key"),
        "platform": body.get("platform") or platform,
        "active_bundle_id": bundle_id,
        "is_gate_fixture": is_gate_fixture,
    }
    prefer_note = {
        "ok": True,
        "hint": "PreferUnifiedBootstrap must be 1 on HotUpdateConfig (verify_hotupdate_config_checksum --contract-v2)",
    }
    if require_prefer_unified_note:
        asset = str(os.environ.get("HOTUPDATE_CONFIG_ASSET") or "").strip()
        if asset and os.path.isfile(asset):
            text = open(asset, encoding="utf-8", errors="replace").read()
            prefer_note["ok"] = "PreferUnifiedBootstrap: 1" in text or "PreferUnifiedBootstrap:1" in text
            if not prefer_note["ok"]:
                prefer_note["error"] = "PreferUnifiedBootstrap not enabled on asset"
        checks["prefer_unified_bootstrap"] = prefer_note

    ok = all(bool(item.get("ok")) for item in checks.values())
    if is_gate_fixture and str(os.environ.get("RUNTIME_DOMAIN_REJECT_FIXTURE") or "").strip() in {
        "1",
        "true",
        "yes",
    }:
        ok = False
        identity["error"] = "active bundle is gate-fixture; set real publish before domain PASS"
    return {
        "ok": ok,
        "bootstrap_url": bootstrap_url,
        "identity": identity,
        "domains": checks,
    }
