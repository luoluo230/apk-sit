# -*- coding: utf-8 -*-
"""ReleaseBundle CRUD and publish state machine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.release.storage import find_scope, load_bundles, save_bundles
from services.release.scope_resolver import resolve_network_profile, resolve_topology_id


def _now_iso() -> str:
    return datetime.now().isoformat()


def _gen_bundle_id(scope_id: str) -> str:
    slug = str(scope_id or "scope").replace(":", "-")[:48]
    return f"rb-{datetime.now().strftime('%Y%m%d')}-{slug}-{uuid.uuid4().hex[:6]}"


def list_bundles(
    project_id: str = "",
    scope_id: str = "",
    status: str = "",
) -> List[Dict[str, Any]]:
    rows = load_bundles()
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if project_id and str(row.get("project_id") or "").strip() != project_id:
            continue
        if scope_id and str(row.get("scope_id") or "").strip() != scope_id:
            continue
        if status and str(row.get("publish_status") or "").strip() != status:
            continue
        out.append(row)
    out.sort(key=lambda x: str(x.get("published_at") or x.get("created_at") or ""), reverse=True)
    return out


def get_bundle(bundle_id: str) -> Dict[str, Any]:
    bid = str(bundle_id or "").strip()
    for row in load_bundles():
        if isinstance(row, dict) and str(row.get("bundle_id") or "").strip() == bid:
            return row
    return {}


def find_active_bundle(scope_id: str) -> Dict[str, Any]:
    sid = str(scope_id or "").strip()
    for row in list_bundles(scope_id=sid, status="published"):
        return row
    return {}


def _supersede_published(scope_id: str, except_bundle_id: str = "") -> None:
    rows = load_bundles()
    changed = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("scope_id") or "").strip() != scope_id:
            continue
        if str(row.get("publish_status") or "") != "published":
            continue
        if except_bundle_id and str(row.get("bundle_id") or "") == except_bundle_id:
            continue
        row["publish_status"] = "superseded"
        row["updated_at"] = _now_iso()
        changed = True
    if changed:
        save_bundles(rows)


def create_bundle_from_publish(
    scope: Dict[str, Any],
    version_row: Dict[str, Any],
    *,
    published_by: str = "",
    gateway_probe: Optional[Dict[str, Any]] = None,
    runtime_run_id: str = "",
    topology_version_label: str = "cluster-v1",
) -> Dict[str, Any]:
    scope_id = str(scope.get("scope_id") or "")
    network_profile, profile_source = resolve_network_profile(scope)
    topology_id = resolve_topology_id(scope)
    prev = find_active_bundle(scope_id)
    bundle = {
        "bundle_id": _gen_bundle_id(scope_id),
        "project_id": str(scope.get("project_id") or ""),
        "scope_id": scope_id,
        "env_key": str(scope.get("env_key") or ""),
        "channel_id": str(scope.get("channel_id") or ""),
        "client": {
            "version_id": str(version_row.get("id") or ""),
            "version_name": str(version_row.get("version_name") or ""),
            "version_code": str(version_row.get("version_code") or ""),
            "platform": str(version_row.get("platform") or "android"),
            "apk_path": str(version_row.get("apk_path") or ""),
            "resource_version": str(version_row.get("resource_version") or version_row.get("apk_version") or ""),
            "config_version": str(version_row.get("config_version") or ""),
        },
        "server": {
            "topology_id": topology_id,
            "topology_version_label": topology_version_label,
            "runtime_run_id": runtime_run_id,
            "cluster_sync_at": _now_iso(),
            "network_profile_snapshot": dict(network_profile or {}),
            "profile_source": profile_source,
            "gateway_probe": gateway_probe or {},
        },
        "publish_status": "published",
        "published_at": _now_iso(),
        "published_by": published_by,
        "supersedes_bundle_id": str(prev.get("bundle_id") or ""),
        "rollback_of_bundle_id": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    rows = load_bundles()
    _supersede_published(scope_id, except_bundle_id=bundle["bundle_id"])
    rows.append(bundle)
    save_bundles(rows)
    return bundle


def rollback_bundle(scope_id: str, target_bundle_id: str, *, rolled_by: str = "") -> Dict[str, Any]:
    sid = str(scope_id or "").strip()
    target = get_bundle(target_bundle_id)
    if not target or str(target.get("scope_id") or "") != sid:
        return {}
    _supersede_published(sid)
    target = dict(target)
    target["publish_status"] = "published"
    target["published_at"] = _now_iso()
    target["published_by"] = rolled_by
    target["rollback_of_bundle_id"] = str(find_active_bundle(sid).get("bundle_id") or "")
    target["updated_at"] = _now_iso()
    rows = load_bundles()
    for i, row in enumerate(rows):
        if str(row.get("bundle_id") or "") == target_bundle_id:
            rows[i] = target
            break
    save_bundles(rows)
    return target


def bind_active_bundle_on_step4_activate(project_id: str, version_row: Dict[str, Any]) -> Dict[str, Any]:
    """Link VersionRow to ReleaseBundle after commercial Step4 / OSS activate."""
    from services.release.release_context import apply_scope_fields_to_version_row
    from services.release.scope_resolver import resolve_scope_by_inputs

    row = apply_scope_fields_to_version_row(dict(version_row or {}), project_id)
    scope_id = str(row.get("scope_id") or "").strip()
    if str(row.get("active_bundle_id") or "").strip():
        return row
    active = find_active_bundle(scope_id)
    if active.get("bundle_id"):
        row["active_bundle_id"] = str(active.get("bundle_id") or "")
        return row
    env = str(row.get("env_key") or row.get("env") or row.get("stage") or "")
    channel = str(row.get("channel") or "")
    scope = resolve_scope_by_inputs(project_id, env, channel)
    if not scope:
        return row
    bundle = create_bundle_from_publish(scope, row, published_by="step4-activate")
    row["active_bundle_id"] = str(bundle.get("bundle_id") or "")
    return row


def run_scope_precheck(scope: Dict[str, Any], version_row: Dict[str, Any]) -> Dict[str, Any]:
    scope_id = str(scope.get("scope_id") or "")
    network_profile, profile_source = resolve_network_profile(scope)
    topology_id = resolve_topology_id(scope)
    client_keys = ["apk_url", "resource_url", "config_url", "apk_version", "resource_version", "config_version"]
    missing_client = [k for k in client_keys if not str(version_row.get(k) or "").strip()]
    profile_keys = ("gateway_ws", "login_http", "game_ws", "ops_http")
    missing_profile = [k for k in profile_keys if not str((network_profile or {}).get(k) or "").strip()]
    runtime_aligned = True
    runtime_topology_id = ""
    try:
        from services.ops.helpers import _resolve_topology_context

        ctx = _resolve_topology_context(str(scope.get("project_id") or ""), str(scope.get("env_key") or ""), topology_id)
        runtime_topology_id = str((ctx.get("row") or {}).get("topology_id") or ctx.get("topology_id") or "")
        if runtime_topology_id and runtime_topology_id != topology_id:
            runtime_aligned = False
    except Exception:
        runtime_aligned = True

    ok = not missing_client and not missing_profile and runtime_aligned
    return {
        "ok": ok,
        "scope_id": scope_id,
        "topology_id": topology_id,
        "runtime_topology_id": runtime_topology_id,
        "topology_runtime_aligned": runtime_aligned,
        "profile_source": profile_source,
        "missing_client_fields": missing_client,
        "missing_profile_fields": missing_profile,
        "network_profile_preview": network_profile,
        "checked_at": _now_iso(),
    }
