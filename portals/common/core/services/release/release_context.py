# -*- coding: utf-8 -*-
"""High-level release context for bootstrap / release-config APIs."""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.commercial_release_plan import (
    build_runtime_resolve_paths,
    normalize_release_channel,
    normalize_release_environment,
    normalize_release_platform,
)
from services.release.bundle_service import find_active_bundle
from services.release.env_registry import env_key_to_gm_env, env_key_to_jenkins_env, normalize_release_env_key
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.scope_resolver import (
    resolve_network_profile,
    resolve_scope,
    resolve_scope_by_inputs,
    resolve_topology_binding_for_scope,
    resolve_topology_id,
)


def apply_scope_fields_to_version_row(row: Dict[str, Any], project_id: str) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return row
    out = dict(row)
    stage = str(row.get("stage") or "dev").strip()
    env_key = normalize_release_env_key(row.get("env_key") or stage)
    channel_id = str(row.get("channel") or "").strip()

    out["env_key"] = env_key
    out["scope_id"] = str(row.get("scope_id") or build_scope_id(project_slug(project_id), env_key, channel_id))
    out["env"] = str(row.get("env") or env_key_to_gm_env(env_key))
    return out


def resolve_release_context(
    project_id: str,
    env_raw: str = "",
    channel_raw: str = "",
    *,
    version_row: Optional[Dict[str, Any]] = None,
    auto_create_scope: bool = True,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if version_row and isinstance(version_row, dict):
        env_key = normalize_release_env_key(version_row.get("env_key") or version_row.get("stage") or env_raw)
        channel_id = str(version_row.get("channel") or resolve_channel_id(pid, channel_raw) or channel_raw).strip()
    else:
        scope_probe = resolve_scope_by_inputs(pid, env_raw, channel_raw)
        env_key = normalize_release_env_key(scope_probe.get("env_key") or env_raw)
        channel_id = str(scope_probe.get("channel_id") or resolve_channel_id(pid, channel_raw) or channel_raw).strip()

    scope = resolve_scope(pid, env_key, channel_id, auto_create=auto_create_scope)
    version_name = str((version_row or {}).get("version_name") or "").strip() if isinstance(version_row, dict) else ""
    network_profile, profile_source = resolve_network_profile(scope, version_name=version_name) if scope else ({}, "legacy")
    topology_binding = resolve_topology_binding_for_scope(scope, version_name=version_name) if scope else {}
    topology_id = str(topology_binding.get("topology_id") or resolve_topology_id(scope, version_name=version_name) or "")
    active_bundle = find_active_bundle(str(scope.get("scope_id") or "")) if scope else {}

    server_snapshot = {
        "topology_id": topology_id,
        "topology_version_label": str((active_bundle.get("server") or {}).get("topology_version_label") or ""),
        "runtime_run_id": str((active_bundle.get("server") or {}).get("runtime_run_id") or ""),
    }

    bootstrap_paths = {}
    if version_row and isinstance(version_row, dict):
        release_env = env_key_to_jenkins_env(env_key)
        row_channel = normalize_release_channel(str(version_row.get("channel") or channel_id))
        platform_raw = str(version_row.get("platform") or "android").strip().lower()
        platform_segment = normalize_release_platform(platform_raw)
        runtime_paths = build_runtime_resolve_paths(
            resource_server_url=str(version_row.get("resource_server_url") or ""),
            release_environment=release_env,
            release_channel=row_channel,
            release_platform=platform_segment,
            release_version=str(version_row.get("version_name") or ""),
            version_code=str(version_row.get("version_code") or ""),
        )
        bootstrap_paths = {
            "resource_relative_path": str(version_row.get("resource_path") or runtime_paths.get("resource_relative_path") or ""),
            "config_relative_path": runtime_paths.get("config_relative_path") or "",
            "code_relative_path": runtime_paths.get("code_relative_path") or "",
            "catalog_file_name": str(version_row.get("catalog_file_name") or runtime_paths.get("catalog_file_name") or ""),
        }

    return {
        "project_id": pid,
        "scope": scope,
        "scope_id": str(scope.get("scope_id") or ""),
        "env_key": env_key,
        "channel_id": channel_id,
        "channel_key": str(scope.get("channel_key") or channel_id),
        "network_profile": network_profile,
        "profile_source": profile_source,
        "topology_binding_source": str(topology_binding.get("binding_source") or ""),
        "topology_binding_source_label": str(topology_binding.get("binding_source_label") or ""),
        "server_snapshot": server_snapshot,
        "active_bundle_id": str(
            active_bundle.get("bundle_id")
            or ((version_row or {}).get("active_bundle_id") if version_row else "")
            or ""
        ),
        "bootstrap_paths": bootstrap_paths,
    }


def release_matches_env(row: Dict[str, Any], env_raw: str) -> bool:
    if not env_raw:
        return True
    env_key = normalize_release_env_key(env_raw)
    row_env_key = normalize_release_env_key(row.get("env_key") or row.get("stage") or row.get("env"))
    if row_env_key == env_key:
        return True
    gm = str(row.get("env") or "").strip()
    return gm == env_key_to_gm_env(env_key) or normalize_release_env_key(gm) == env_key
