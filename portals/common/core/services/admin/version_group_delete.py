# -*- coding: utf-8 -*-
"""Delete version group (split from version_group_service for ≤400 gate)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from repositories.admin import versions_repo
from services.admin.version_group_repo import (
    _find_group_meta_index,
    _load_version_groups_meta,
    _normalize_group_platform,
    _remove_version_group_meta,
    _version_row_env_key,
    _version_row_platform,
)
from services.release.env_registry import normalize_release_env_key


def delete_version_group(
    project_id: str,
    version_name: str,
    username: str,
    env_key: Optional[str] = None,
    platform: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_edit(project_id, username):
        return {"error": "无权限"}, 403

    version_name_text = str(version_name or "").strip()
    if not version_name_text:
        return {"error": "缺少版本组名称"}, 400

    ek = normalize_release_env_key(env_key or "", project_id=project_id) if env_key else ""
    pk = _normalize_group_platform(platform) if platform else ""
    versions = versions_repo.list_versions(project_id)
    matched = [
        row
        for row in versions
        if str((row or {}).get("version_name") or "").strip() == version_name_text
        and (not ek or _version_row_env_key(row, project_id) == ek)
        and (not pk or _version_row_platform(row) == pk)
    ]
    meta_groups = _load_version_groups_meta(project_id)
    has_meta = _find_group_meta_index(meta_groups, version_name_text, ek, project_id, platform=pk or None) >= 0
    if not matched and not has_meta:
        return {"error": "版本组不存在"}, 404

    if matched and versions_repo.approval_required_for_delete():
        blocked = []
        for row in matched:
            version_id = str(row.get("id") or "").strip()
            if version_id and not versions_repo.has_approved_delete(project_id, version_id):
                blocked.append(version_id)
        if blocked:
            return {
                "error": "删除版本组需先完成审批。请先审批该组下所有版本删除申请。",
                "version_name": version_name_text,
                "blocked_version_ids": blocked,
            }, 403

    kept = [
        row
        for row in versions
        if str((row or {}).get("version_name") or "").strip() != version_name_text
        or (ek and _version_row_env_key(row, project_id) != ek)
        or (pk and _version_row_platform(row) != pk)
    ]
    if len(kept) != len(versions):
        versions_repo.save_versions(project_id, kept)
    _remove_version_group_meta(project_id, version_name_text, env_key=ek or None, platform=pk or None)
    versions_repo.audit("delete_project_version_group", "%s %s count=%s" % (project_id, version_name_text, len(matched)))
    return {
        "success": True,
        "version_name": version_name_text,
        "deleted_count": len(matched),
    }, 200
