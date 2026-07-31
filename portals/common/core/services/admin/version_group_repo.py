# -*- coding: utf-8 -*-
"""Version group metadata persistence and lookup."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from repositories.admin import projects_repo, versions_repo
from services.release.env_registry import normalize_release_env_key

VERSION_GROUP_MODES = ("general", "commercial")
VERSION_GROUP_STATUSES = ("active", "archived")


def _load_version_groups_meta(project_id: str) -> list:
    proj = projects_repo.get_project(project_id) or {}
    raw = proj.get("version_groups")
    if not isinstance(raw, list):
        return []
    return [dict(row) for row in raw if isinstance(row, dict) and str(row.get("version_name") or "").strip()]


def _save_version_groups_meta(project_id: str, groups: list) -> None:
    proj = projects_repo.get_project(project_id) or {}
    proj["version_groups"] = groups
    projects_repo.upsert_project(project_id, proj)


def _migrate_version_groups_env_keys(project_id: str) -> None:
    groups = _load_version_groups_meta(project_id)
    versions = versions_repo.list_versions(project_id)
    changed = False
    migrated: list = []
    for meta in groups:
        vn = str(meta.get("version_name") or "").strip()
        if not vn:
            continue
        ek = _group_env_key(meta, project_id)
        if ek:
            migrated.append(meta)
            continue
        matched = [row for row in versions if str(row.get("version_name") or "").strip() == vn]
        envs = {_version_row_env_key(row, project_id) for row in matched}
        if not envs:
            migrated.append(meta)
            continue
        changed = True
        for env in sorted(envs):
            entry = dict(meta)
            entry["env_key"] = env
            migrated.append(entry)
    if not changed:
        return
    deduped: list = []
    seen: set = set()
    for row in migrated:
        vn = str(row.get("version_name") or "").strip()
        row_ek = _group_env_key(row, project_id)
        key = (vn, row_ek, _group_platform(row))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    _save_version_groups_meta(project_id, deduped)


def _migrate_version_groups_platforms(project_id: str) -> None:
    groups = _load_version_groups_meta(project_id)
    versions = versions_repo.list_versions(project_id)
    changed = False
    migrated: list = []
    for meta in groups:
        vn = str(meta.get("version_name") or "").strip()
        if not vn:
            continue
        pk = _group_platform(meta)
        if pk:
            migrated.append(meta)
            continue
        ek = _group_env_key(meta, project_id)
        matched = [
            row for row in versions
            if str(row.get("version_name") or "").strip() == vn
            and (not ek or _version_row_env_key(row, project_id) == ek)
        ]
        platforms = {_version_row_platform(row) for row in matched}
        if not platforms:
            migrated.append(meta)
            continue
        changed = True
        for platform in sorted(platforms):
            entry = dict(meta)
            entry["platform"] = platform
            migrated.append(entry)
    if not changed:
        return
    deduped: list = []
    seen: set = set()
    for row in migrated:
        vn = str(row.get("version_name") or "").strip()
        key = (vn, _group_env_key(row, project_id), _group_platform(row))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    _save_version_groups_meta(project_id, deduped)


def _group_env_key(meta: dict, project_id: str) -> str:
    raw = str(meta.get("env_key") or "").strip().lower()
    if not raw:
        return ""
    return normalize_release_env_key(raw, project_id=project_id)


def _normalize_group_platform(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _group_platform(meta: dict) -> str:
    return _normalize_group_platform(meta.get("platform"))


def _version_row_platform(row: dict) -> str:
    return _normalize_group_platform(row.get("platform") or "android")


def _filter_versions_by_platform(versions: list, platform: str) -> list:
    if not platform:
        return versions
    pk = _normalize_group_platform(platform)
    return [row for row in versions if _version_row_platform(row) == pk]


def _version_row_env_key(row: dict, project_id: str) -> str:
    return normalize_release_env_key(
        row.get("env_key") or row.get("stage") or "development",
        project_id=project_id,
    )


def _filter_versions_by_env(versions: list, env_key: str, project_id: str) -> list:
    if not env_key:
        return versions
    ek = normalize_release_env_key(env_key, project_id=project_id)
    return [row for row in versions if _version_row_env_key(row, project_id) == ek]


def _find_group_meta_index(
    groups: list,
    version_name: str,
    env_key: str,
    project_id: str,
    platform: Optional[str] = None,
) -> int:
    vn = str(version_name or "").strip()
    if not vn:
        return -1
    ek = normalize_release_env_key(env_key or "", project_id=project_id) if env_key else ""
    pk = _normalize_group_platform(platform) if platform else ""
    for i, row in enumerate(groups):
        if str(row.get("version_name") or "").strip() != vn:
            continue
        row_ek = _group_env_key(row, project_id)
        row_pk = _group_platform(row)
        if ek and row_ek != ek:
            continue
        if pk and row_pk != pk:
            continue
        if not ek and row_ek:
            continue
        if not pk and row_pk:
            continue
        return i
    return -1


def _remove_version_group_meta(
    project_id: str,
    version_name: str,
    env_key: Optional[str] = None,
    platform: Optional[str] = None,
) -> None:
    vn = str(version_name or "").strip()
    if not vn:
        return
    groups = _load_version_groups_meta(project_id)
    ek = normalize_release_env_key(env_key or "", project_id=project_id) if env_key else ""
    pk = _normalize_group_platform(platform) if platform else ""
    kept: list = []
    for row in groups:
        if str(row.get("version_name") or "").strip() != vn:
            kept.append(row)
            continue
        if ek and _group_env_key(row, project_id) != ek:
            kept.append(row)
            continue
        if pk and _group_platform(row) != pk:
            kept.append(row)
            continue
        if not ek and _group_env_key(row, project_id):
            kept.append(row)
            continue
        if not pk and _group_platform(row):
            kept.append(row)
            continue
    if len(kept) != len(groups):
        _save_version_groups_meta(project_id, kept)


def _ensure_version_group_meta(
    project_id: str,
    version_name: str,
    actor: str,
    version_mode: str = "general",
    notes: str = "",
    env_key: Optional[str] = None,
    platform: Optional[str] = None,
) -> None:
    vn = str(version_name or "").strip()
    if not vn:
        return
    ek = normalize_release_env_key(env_key or "", project_id=project_id) if env_key else ""
    pk = _normalize_group_platform(platform) if platform else ""
    groups = _load_version_groups_meta(project_id)
    if _find_group_meta_index(groups, vn, ek, project_id, platform=pk or None) >= 0:
        return
    mode = str(version_mode or "general").strip() or "general"
    if mode not in VERSION_GROUP_MODES:
        mode = "general"
    now = datetime.now().isoformat()
    entry = {
        "version_name": vn,
        "env_key": ek,
        "platform": pk,
        "version_mode": mode,
        "notes": str(notes or "").strip(),
        "recommended": False,
        "status": "active",
        "created_at": now,
        "created_by": actor,
    }
    groups.append(entry)
    _save_version_groups_meta(project_id, groups)


def _version_matches_group_scope(
    row: dict,
    version_name: str,
    env_key: str,
    platform: str,
    project_id: str,
) -> bool:
    if not isinstance(row, dict):
        return False
    vn = str(version_name or "").strip()
    if str(row.get("version_name") or "").strip() != vn:
        return False
    ek = normalize_release_env_key(env_key or "", project_id=project_id) if env_key else ""
    if ek and _version_row_env_key(row, project_id) != ek:
        return False
    pk = _normalize_group_platform(platform) if platform else ""
    if pk and _version_row_platform(row) != pk:
        return False
    return True


def _get_group_meta(
    project_id: str,
    version_name: str,
    env_key: Optional[str] = None,
    platform: Optional[str] = None,
) -> dict:
    groups = _load_version_groups_meta(project_id)
    idx = _find_group_meta_index(groups, version_name, env_key or "", project_id, platform=platform or None)
    if idx < 0:
        return {}
    return dict(groups[idx])


def get_version_group_meta(
    project_id: str,
    version_name: str,
    env_key: str = "",
    platform: str = "android",
) -> dict:
    """Public accessor for version-group metadata (ios_signing, wx_minigame, etc.)."""
    vn = str(version_name or "").strip()
    if not vn:
        return {}
    ek = normalize_release_env_key(env_key or "", project_id=project_id) if env_key else ""
    pk = _normalize_group_platform(platform) if platform else ""
    return _get_group_meta(project_id, vn, ek or None, pk or None)
