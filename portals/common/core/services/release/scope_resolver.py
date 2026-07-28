# -*- coding: utf-8 -*-
"""ReleaseScope resolution."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from data.platforms import is_valid_platform_id
from services.release.env_registry import normalize_release_env_key
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.profile_builder import build_network_profile_from_topology
from services.release.topology_binding_service import resolve_topology_binding
from services.release.storage import find_scope, load_scopes, upsert_scope, find_manifest


def _default_topology_id(project_id: str, env_key: str, scope: Optional[Dict[str, Any]] = None) -> str:
    if isinstance(scope, dict):
        override_tid = str((scope.get("override") or {}).get("topology_id") or "").strip()
        if override_tid:
            return override_tid
        default_tid = str(scope.get("default_topology_id") or "").strip()
        if default_tid:
            return default_tid
    manifest = find_manifest(project_id)
    slug = str((manifest or {}).get("project_slug") or project_slug(project_id)).strip()
    pattern = str((manifest or {}).get("topology_pattern") or "topology-{project_slug}-{env_key}-default").strip()
    return pattern.format(project_slug=slug, env_key=normalize_release_env_key(env_key), project_id=project_id)


def resolve_scope(
    project_id: str,
    env_key: str,
    channel_id: str,
    *,
    platform: str = "",
    auto_create: bool = True,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    ek = normalize_release_env_key(env_key)
    cid = str(channel_id or "").strip()
    plat = str(platform or "").strip().lower()
    if not pid or not cid:
        return {}
    sid = build_scope_id(project_slug(pid), ek, cid, plat if is_valid_platform_id(plat) else "")
    scope = find_scope(sid)
    if scope:
        return scope
    if is_valid_platform_id(plat):
        legacy_sid = build_scope_id(project_slug(pid), ek, cid)
        if legacy_sid != sid:
            legacy = find_scope(legacy_sid)
            if legacy:
                legacy["scope_id"] = sid
                legacy["platform"] = plat
                if auto_create:
                    return upsert_scope(legacy)
                return legacy
    if not auto_create:
        return {}
    slug = project_slug(pid)
    scope = {
        "scope_id": sid,
        "project_id": pid,
        "env_key": ek,
        "channel_id": cid,
        "channel_key": cid,
        "platform": plat if is_valid_platform_id(plat) else "",
        "default_topology_id": _default_topology_id(pid, ek),
        "override": {"topology_id": ""},
        "status": "active",
        "updated_at": datetime.now().isoformat(),
    }
    return upsert_scope(scope)


def resolve_topology_binding_for_scope(scope: Dict[str, Any], version_name: str = "") -> Dict[str, Any]:
    if not isinstance(scope, dict):
        return {"topology_id": "", "binding_source": "", "binding_source_label": "", "binding": {}}
    override = scope.get("override") if isinstance(scope.get("override"), dict) else {}
    tid = str(override.get("topology_id") or "").strip()
    if tid:
        return {
            "topology_id": tid,
            "binding_source": "scope_override",
            "binding_source_label": "Scope 覆盖",
            "binding": {},
        }
    fallback = str(scope.get("default_topology_id") or "").strip() or _default_topology_id(
        str(scope.get("project_id") or ""),
        str(scope.get("env_key") or "production"),
        scope,
    )
    return resolve_topology_binding(
        str(scope.get("project_id") or ""),
        str(scope.get("env_key") or ""),
        str(scope.get("channel_id") or ""),
        platform=str(scope.get("platform") or "").strip().lower(),
        version_name=version_name,
        fallback_topology_id=fallback,
    )


def resolve_topology_id(scope: Dict[str, Any], version_name: str = "") -> str:
    return str(resolve_topology_binding_for_scope(scope, version_name).get("topology_id") or "").strip()


def _load_topology_for_scope(scope: Dict[str, Any], version_name: str = "") -> Dict[str, Any]:
    from services.ops.topology_registry import _load_topology_scoped

    project_id = str(scope.get("project_id") or "").strip()
    env_key = normalize_release_env_key(scope.get("env_key"))
    topology_id = resolve_topology_id(scope, version_name)
    loaded = _load_topology_scoped(project_id, env_key, topology_id)
    if not isinstance(loaded, dict):
        return {}
    nested = loaded.get("topology")
    if isinstance(nested, dict) and nested.get("nodes"):
        return nested
    if loaded.get("nodes"):
        return loaded
    return {}


def resolve_network_profile(scope: Dict[str, Any], version_name: str = "") -> Tuple[Dict[str, Any], str]:
    if not isinstance(scope, dict) or not scope:
        return {}, "topology"
    topo = _load_topology_for_scope(scope, version_name)
    if not topo.get("nodes"):
        return {}, "topology"
    manifest = find_manifest(str(scope.get("project_id") or ""))
    notice = str((manifest or {}).get("notice_url") or "").strip()
    return build_network_profile_from_topology(topo, notice_url=notice), "topology"


def resolve_scope_by_inputs(project_id: str, env_raw: str, channel_raw: str) -> Dict[str, Any]:
    env_key = normalize_release_env_key(env_raw)
    channel_id = resolve_channel_id(project_id, channel_raw)
    if not channel_id:
        channel_id = str(channel_raw or "").strip()
    return resolve_scope(project_id, env_key, channel_id)


def resolve_existing_scope_by_inputs(project_id: str, env_raw: str, channel_raw: str) -> Dict[str, Any]:
    env_key = normalize_release_env_key(env_raw)
    channel_id = resolve_channel_id(project_id, channel_raw)
    if not channel_id:
        channel_id = str(channel_raw or "").strip()
    return resolve_scope(project_id, env_key, channel_id, auto_create=False)


def list_scopes(project_id: str = "") -> List[Dict[str, Any]]:
    pid = str(project_id or "").strip()
    rows = load_scopes()
    if not pid:
        return [r for r in rows if isinstance(r, dict)]
    return [r for r in rows if isinstance(r, dict) and str(r.get("project_id") or "").strip() == pid]
