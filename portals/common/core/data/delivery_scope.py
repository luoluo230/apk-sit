# -*- coding: utf-8 -*-
"""Per-environment delivery scope: channel and platform subsets within project whitelist."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from data.channels import get_channels_for_project
from data.platforms import get_platforms_for_project, is_valid_platform_id
from services.release.env_registry import get_project_env_defs, normalize_release_env_key


def _env_def(project_id: str, env_key: str) -> Dict[str, Any]:
    key = normalize_release_env_key(env_key, project_id=project_id)
    for row in get_project_env_defs(project_id):
        if str(row.get("env_key") or "").strip().lower() == key:
            return dict(row)
    return {}


def _normalize_id_list(raw: Any, valid_ids: Set[str]) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for item in raw:
        cid = str(item or "").strip()
        if not cid or cid not in valid_ids or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def _normalize_platform_list(raw: Any, valid_ids: Set[str]) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for item in raw:
        pid = str(item or "").strip().lower()
        if not pid or pid not in valid_ids or pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def _project_channel_catalog(project_id: str) -> List[Dict[str, Any]]:
    return get_channels_for_project(project_id, enabled_only=False)


def _project_platform_catalog(project_id: str) -> List[Dict[str, Any]]:
    return get_platforms_for_project(project_id, enabled_only=False)


def get_env_assigned_channel_ids(project_id: str, env_key: str) -> List[str]:
    env = _env_def(project_id, env_key)
    project_ids = {str(c.get("id") or "").strip() for c in _project_channel_catalog(project_id)}
    raw = env.get("channels")
    if isinstance(raw, list) and raw:
        return _normalize_id_list(raw, project_ids)
    return [str(c.get("id") or "").strip() for c in get_channels_for_project(project_id) if str(c.get("id") or "").strip()]


def get_env_disabled_channel_ids(project_id: str, env_key: str) -> List[str]:
    env = _env_def(project_id, env_key)
    raw = env.get("disabled_channels")
    if not isinstance(raw, list):
        return []
    assigned = set(get_env_assigned_channel_ids(project_id, env_key))
    return [str(x).strip() for x in raw if str(x).strip() in assigned]


def get_channels_for_env(project_id: str, env_key: str, enabled_only: bool = True) -> List[Dict[str, Any]]:
    allowed_ids = set(get_env_assigned_channel_ids(project_id, env_key))
    disabled_ids = set(get_env_disabled_channel_ids(project_id, env_key)) if enabled_only else set()
    catalog = _project_channel_catalog(project_id)
    out: List[Dict[str, Any]] = []
    for row in catalog:
        cid = str(row.get("id") or "").strip()
        if not cid or cid not in allowed_ids:
            continue
        if enabled_only and cid in disabled_ids:
            continue
        out.append(dict(row))
    out.sort(key=lambda x: (int(x.get("order") or 0), x.get("id", "")))
    return out


def get_env_assigned_platform_ids(project_id: str, env_key: str) -> List[str]:
    env = _env_def(project_id, env_key)
    project_ids = {str(p.get("id") or "").strip().lower() for p in _project_platform_catalog(project_id)}
    raw = env.get("platforms")
    if isinstance(raw, list) and raw:
        return _normalize_platform_list(raw, project_ids)
    return [str(p.get("id") or "").strip().lower() for p in get_platforms_for_project(project_id)]


def get_env_disabled_platform_ids(project_id: str, env_key: str) -> List[str]:
    env = _env_def(project_id, env_key)
    raw = env.get("disabled_platforms")
    if not isinstance(raw, list):
        return []
    assigned = set(get_env_assigned_platform_ids(project_id, env_key))
    return [str(x).strip().lower() for x in raw if str(x).strip().lower() in assigned]


def get_platforms_for_env(project_id: str, env_key: str, enabled_only: bool = True) -> List[Dict[str, Any]]:
    allowed_ids = set(get_env_assigned_platform_ids(project_id, env_key))
    disabled_ids = set(get_env_disabled_platform_ids(project_id, env_key)) if enabled_only else set()
    catalog = _project_platform_catalog(project_id)
    out: List[Dict[str, Any]] = []
    for row in catalog:
        pid = str(row.get("id") or "").strip().lower()
        if not pid or pid not in allowed_ids:
            continue
        if enabled_only and pid in disabled_ids:
            continue
        out.append(dict(row))
    out.sort(key=lambda x: (int(x.get("order") or 0), x.get("id", "")))
    return out


def get_platform_defs_for_env(project_id: str, env_key: str, enabled_only: bool = True) -> List[Dict[str, str]]:
    return [
        {"value": str(row.get("id") or ""), "label": str(row.get("name") or row.get("id") or "")}
        for row in get_platforms_for_env(project_id, env_key, enabled_only=enabled_only)
    ]


def is_channel_allowed_for_env(project_id: str, env_key: str, channel_id: str) -> bool:
    cid = str(channel_id or "").strip()
    if not cid:
        return False
    return cid in {str(c.get("id") or "").strip() for c in get_channels_for_env(project_id, env_key)}


def is_platform_allowed_for_env(project_id: str, env_key: str, platform_id: str) -> bool:
    pid = str(platform_id or "").strip().lower()
    if not is_valid_platform_id(pid):
        return False
    return pid in {str(p.get("id") or "").strip().lower() for p in get_platforms_for_env(project_id, env_key)}


def get_env_delivery_scope(project_id: str, env_key: str) -> Dict[str, Any]:
    key = normalize_release_env_key(env_key, project_id=project_id)
    env = _env_def(project_id, key)
    project_channels = _project_channel_catalog(project_id)
    project_platforms = _project_platform_catalog(project_id)
    assigned_channel_ids = get_env_assigned_channel_ids(project_id, key)
    assigned_platform_ids = get_env_assigned_platform_ids(project_id, key)
    disabled_channels = set(get_env_disabled_channel_ids(project_id, key))
    disabled_platforms = set(get_env_disabled_platform_ids(project_id, key))
    env_has_explicit_channels = isinstance(env.get("channels"), list) and bool(env.get("channels"))
    env_has_explicit_platforms = isinstance(env.get("platforms"), list) and bool(env.get("platforms"))

    def _channel_rows(ids: List[str], disabled: Set[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cid in ids:
            row = next((c for c in project_channels if str(c.get("id") or "").strip() == cid), None)
            name = str((row or {}).get("name") or cid)
            rows.append({"channel_id": cid, "channel_name": name, "enabled": cid not in disabled})
        return rows

    def _platform_rows(ids: List[str], disabled: Set[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for pid in ids:
            row = next((p for p in project_platforms if str(p.get("id") or "").strip().lower() == pid), None)
            name = str((row or {}).get("name") or pid)
            rows.append({"platform_id": pid, "platform_name": name, "enabled": pid not in disabled})
        return rows

    return {
        "env_key": key,
        "inherits_project_channels": not env_has_explicit_channels,
        "inherits_project_platforms": not env_has_explicit_platforms,
        "assigned_channels": _channel_rows(assigned_channel_ids, disabled_channels),
        "assigned_platforms": _platform_rows(assigned_platform_ids, disabled_platforms),
        "project_channel_catalog": [
            {"channel_id": str(c.get("id") or ""), "channel_name": str(c.get("name") or c.get("id") or "")}
            for c in project_channels
        ],
        "project_platform_catalog": [
            {"platform_id": str(p.get("id") or "").strip().lower(), "platform_name": str(p.get("name") or p.get("id") or "")}
            for p in project_platforms
        ],
    }
