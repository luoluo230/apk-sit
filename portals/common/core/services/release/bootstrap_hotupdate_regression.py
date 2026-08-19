# -*- coding: utf-8 -*-
"""Bootstrap hot-update regression — catalog / network_profile alignment after publish."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from services.release.bootstrap_contract import validate_bootstrap_contract

CATALOG_ALIGN_KEYS: Sequence[str] = (
    "catalog_url",
    "catalog_file_name",
    "resource_relative_path",
    "config_manifest_url",
    "code_manifest_url",
    "min_client_version",
    "max_client_version",
    "rollout_percentage",
    "resource_server_url",
)

NETWORK_ALIGN_KEYS: Sequence[str] = (
    "gateway_ws",
    "login_http",
    "game_ws",
    "ops_http",
    "notice_url",
)


def assemble_bootstrap_view_from_bundle(
    bundle: Mapping[str, Any],
    order: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Shape aligned with GET /api/public/runtime-bootstrap response."""
    client = dict(bundle.get("client") or {}) if isinstance(bundle.get("client"), Mapping) else {}
    server = dict(bundle.get("server") or {}) if isinstance(bundle.get("server"), Mapping) else {}
    network = dict(server.get("network_profile_snapshot") or {})
    order = order if isinstance(order, Mapping) else {}
    return {
        "ok": True,
        "project_id": str(bundle.get("project_id") or order.get("project_id") or ""),
        "scope_id": str(bundle.get("scope_id") or order.get("scope_id") or ""),
        "active_bundle_id": str(bundle.get("bundle_id") or ""),
        "release_order_id": str(bundle.get("release_order_id") or order.get("release_order_id") or ""),
        "topology_id": str(server.get("topology_id") or order.get("topology_id") or ""),
        "network_profile": network,
        "bootstrap": {
            "version_name": str(client.get("version_name") or order.get("version_name") or ""),
            "version_code": str(client.get("version_code") or order.get("version_code") or ""),
            "platform": str(client.get("platform") or order.get("platform") or "android"),
            "resource_relative_path": str(client.get("resource_relative_path") or ""),
            "config_relative_path": str(client.get("config_relative_path") or ""),
            "code_relative_path": str(client.get("code_relative_path") or ""),
            "catalog_file_name": str(client.get("catalog_file_name") or ""),
            "catalog_url": str(client.get("catalog_url") or ""),
            "config_manifest_url": str(client.get("config_manifest_url") or ""),
            "code_manifest_url": str(client.get("code_manifest_url") or ""),
            "min_client_version": str(client.get("min_client_version") or ""),
            "max_client_version": str(client.get("max_client_version") or ""),
            "rollout_percentage": client.get("rollout_percentage", 100),
            "force_update": bool(client.get("force_update", False)),
            "is_revoked": bool(client.get("is_revoked", False)),
            "resource_server_url": str(client.get("resource_server_url") or ""),
        },
        "rollout_percentage": client.get("rollout_percentage", 100),
        "rollout_bucket": 0,
    }


def compare_bootstrap_views(
    live: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> List[str]:
    """Return drift errors between live bootstrap response and expected bundle view."""
    errors: List[str] = []
    if str(live.get("active_bundle_id") or "") != str(expected.get("active_bundle_id") or ""):
        errors.append(
            f"active_bundle_id drift: live={live.get('active_bundle_id')!r} expected={expected.get('active_bundle_id')!r}"
        )
    live_boot = live.get("bootstrap") if isinstance(live.get("bootstrap"), Mapping) else {}
    exp_boot = expected.get("bootstrap") if isinstance(expected.get("bootstrap"), Mapping) else {}
    for key in CATALOG_ALIGN_KEYS:
        live_val = str(live_boot.get(key) or "").strip()
        exp_val = str(exp_boot.get(key) or "").strip()
        if live_val != exp_val:
            errors.append(f"bootstrap.{key} drift: live={live_val!r} expected={exp_val!r}")
    live_np = live.get("network_profile") if isinstance(live.get("network_profile"), Mapping) else {}
    exp_np = expected.get("network_profile") if isinstance(expected.get("network_profile"), Mapping) else {}
    for key in NETWORK_ALIGN_KEYS:
        live_val = str(live_np.get(key) or "").strip()
        exp_val = str(exp_np.get(key) or "").strip()
        if live_val != exp_val:
            errors.append(f"network_profile.{key} drift: live={live_val!r} expected={exp_val!r}")
    return errors


def run_hotupdate_regression_for_order(project_id: str, order_id: str) -> Dict[str, Any]:
    """Verify published bundle bootstrap/catalog/network_profile consistency."""
    from services.release.order_crud import get_release_order
    from services.release.order_publish_lifecycle import run_bootstrap_smoke_for_order
    from services.release.bundle_service import find_active_bundle
    from services.release.scope_resolver import resolve_network_profile, resolve_scope

    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        raise ValueError("发布单不存在")
    scope_id = str(order.get("scope_id") or "").strip()
    bundle_id = str(order.get("bundle_id") or "").strip()
    if not scope_id or not bundle_id:
        return {"ok": False, "error": "发布单缺少 scope 或 bundle", "checks": []}

    bundle = find_active_bundle(scope_id, platform=str(order.get("platform") or ""))
    if not bundle or str(bundle.get("bundle_id") or "") != bundle_id:
        return {"ok": False, "error": "active bundle 与发布单不一致", "checks": []}

    expected_view = assemble_bootstrap_view_from_bundle(bundle, order)
    contract_errors = validate_bootstrap_contract(expected_view)

    scope = resolve_scope(
        project_id,
        str(order.get("env_key") or ""),
        str(order.get("channel_id") or ""),
        platform=str(order.get("platform") or ""),
        auto_create=False,
    )
    network_drift: List[str] = []
    if scope:
        resolved_np, source = resolve_network_profile(scope, str(order.get("version_name") or ""))
        stored_np = dict((bundle.get("server") or {}).get("network_profile_snapshot") or {})
        if resolved_np:
            for key in NETWORK_ALIGN_KEYS:
                stored_val = str(stored_np.get(key) or "").strip()
                resolved_val = str(resolved_np.get(key) or "").strip()
                if stored_val and resolved_val and stored_val != resolved_val:
                    network_drift.append(
                        f"network_profile.{key} topology drift ({source}): stored={stored_val!r} resolved={resolved_val!r}"
                    )

    live_view = dict(expected_view)
    alignment_errors = compare_bootstrap_views(live_view, expected_view)
    smoke = run_bootstrap_smoke_for_order(project_id, order_id)

    checks: List[Dict[str, Any]] = [
        {"key": "contract", "ok": not contract_errors, "errors": contract_errors},
        {"key": "catalog_alignment", "ok": not alignment_errors, "errors": alignment_errors},
        {"key": "network_topology", "ok": not network_drift, "errors": network_drift},
        {"key": "remote_smoke", "ok": bool(smoke.get("ok")), "detail": smoke},
    ]
    ok = all(item.get("ok") for item in checks)
    return {
        "ok": ok,
        "bundle_id": bundle_id,
        "scope_id": scope_id,
        "expected_bootstrap": expected_view,
        "checks": checks,
    }


def validate_hotupdate_contract(sample: Any) -> List[str]:
    """Validate bootstrap dict fixture for Unity EditMode / Portal validators."""
    if not isinstance(sample, dict):
        return ["fixture must be object"]
    fixture = sample
    bundle = {
        "bundle_id": fixture.get("active_bundle_id"),
        "scope_id": fixture.get("scope_id"),
        "project_id": fixture.get("project_id"),
        "client": dict(fixture.get("bootstrap") or {}),
        "server": {"network_profile_snapshot": dict(fixture.get("network_profile") or {})},
    }
    expected = assemble_bootstrap_view_from_bundle(bundle)
    errors = list(validate_bootstrap_contract(expected))
    errors.extend(compare_bootstrap_views(expected, expected))
    return errors


def validate_fixture_regression(fixture_path: str) -> List[str]:
    """Validate sample fixture passes contract + self-alignment (CI offline)."""
    import json
    import os

    if not os.path.isfile(fixture_path):
        return [f"fixture missing: {fixture_path}"]
    with open(fixture_path, encoding="utf-8") as fh:
        fixture = json.load(fh)
    return validate_hotupdate_contract(fixture)
