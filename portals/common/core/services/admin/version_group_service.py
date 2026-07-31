"""Version module — version group CRUD."""

from __future__ import annotations

from services.admin.version_propagation import _propagate_pipeline_to_group_scope

import copy
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from repositories.admin import projects_repo, versions_repo
from data.delivery_scope import get_channels_for_env, is_channel_allowed_for_env, is_platform_allowed_for_env
from data.platforms import is_valid_platform_id
from services.admin.version_domain import normalize_version_status, normalize_edit_scope, build_status_audit_tags
from services.commercial_release_plan import (
    DEFAULT_RESOURCE_SERVER,
    build_runtime_resolve_paths,
    normalize_release_channel,
    normalize_release_environment,
    normalize_release_platform,
)
from services.release.env_registry import env_key_to_jenkins_env
from services.release.release_context import apply_scope_fields_to_version_row
from services.release.env_registry import normalize_release_env_key, env_key_to_gm_env, env_key_to_stage, stage_to_env_key
from services.release.scope_ids import resolve_channel_id
from services.admin.version_group_repo import (
    VERSION_GROUP_MODES,
    VERSION_GROUP_STATUSES,
    _ensure_version_group_meta,
    _filter_versions_by_env,
    _filter_versions_by_platform,
    _find_group_meta_index,
    _get_group_meta,
    _group_env_key,
    _group_platform,
    _load_version_groups_meta,
    _migrate_version_groups_env_keys,
    _migrate_version_groups_platforms,
    _normalize_group_platform,
    _remove_version_group_meta,
    _save_version_groups_meta,
    _version_matches_group_scope,
    _version_row_env_key,
    _version_row_platform,
    get_version_group_meta,
)
from services.admin.version_pipeline_resolver import (
    GROUP_TEMPLATE_BOOTSTRAP_KEYS,
    GROUP_TEMPLATE_JENKINS_KEYS,
    GROUP_TEMPLATE_SCALAR_KEYS,
    _apply_group_template_fields_to_row,
    _apply_project_build_defaults_to_pipeline,
    _deep_merge_dict,
    _derive_runtime_paths,
    _extract_group_template_fields,
    _lazy_init_pipeline_template_from_siblings,
    _merge_version_pipeline,
    _pipeline_has_any_content,
    _save_pipeline_template_to_meta,
    _sync_pipeline_release_fields,
    enrich_version_client_urls,
    resolve_effective_bootstrap_fields,
    resolve_effective_ios_signing,
    resolve_effective_jenkins,
    resolve_effective_pipeline,
)

def _version_group_row(
    project_id: str,
    version_name: str,
    meta: dict,
    versions: list,
    env_key: Optional[str] = None,
    platform: Optional[str] = None,
) -> dict:
    vn = str(version_name or "").strip()
    ek = normalize_release_env_key(env_key or _group_env_key(meta, project_id) or "", project_id=project_id) if (env_key or _group_env_key(meta, project_id)) else ""
    pk = _normalize_group_platform(platform or _group_platform(meta) or "")
    matched = [row for row in versions if str((row or {}).get("version_name") or "").strip() == vn]
    if ek:
        matched = [row for row in matched if _version_row_env_key(row, project_id) == ek]
    if pk:
        matched = [row for row in matched if _version_row_platform(row) == pk]
    mode = str(meta.get("version_mode") or (matched[0].get("version_mode") if matched else "general") or "general").strip()
    if mode not in VERSION_GROUP_MODES:
        mode = "general"
    status = str(meta.get("status") or "active").strip() or "active"
    if status not in VERSION_GROUP_STATUSES:
        status = "active"
    anchor_id = ""
    anchor_at = ""
    for row in matched:
        at = str(row.get("updated_at") or "")
        if at >= anchor_at:
            anchor_at = at
            anchor_id = str(row.get("id") or "").strip()
    anchor_row = next((r for r in matched if str(r.get("id") or "") == anchor_id), matched[0] if matched else {})
    from services.release.release_policy_service import assess_pipeline_readiness

    readiness = assess_pipeline_readiness(
        anchor_row,
        meta,
        str(anchor_row.get("channel") or ""),
        project_id=project_id,
    )
    return {
        "version_name": vn,
        "env_key": ek,
        "platform": pk,
        "version_mode": mode,
        "notes": str(meta.get("notes") or "").strip(),
        "recommended": bool(meta.get("recommended")),
        "status": status,
        "created_at": meta.get("created_at") or "",
        "created_by": meta.get("created_by") or "",
        "version_code_count": len(matched),
        "has_metadata": bool(meta),
        "pipeline_template": meta.get("pipeline_template") if isinstance(meta.get("pipeline_template"), dict) else {},
        "jenkins_instance_id": str(meta.get("jenkins_instance_id") or "").strip(),
        "jenkins_job_id": str(meta.get("jenkins_job_id") or "").strip(),
        "jenkins_job_overrides": meta.get("jenkins_job_overrides") if isinstance(meta.get("jenkins_job_overrides"), dict) else {},
        "resource_server_url": str(meta.get("resource_server_url") or "").strip(),
        "catalog_file_name": str(meta.get("catalog_file_name") or "").strip(),
        "min_client_version": str(meta.get("min_client_version") or "").strip(),
        "rollout_percentage": meta.get("rollout_percentage"),
        "force_update": bool(meta.get("force_update")),
        "is_revoked": bool(meta.get("is_revoked")),
        "anchor_version_id": anchor_id,
        "pipeline_ready": bool(readiness.get("ready")),
        "pipeline_readiness": readiness,
        "ios_signing": meta.get("ios_signing") if isinstance(meta.get("ios_signing"), dict) else {},
        "wx_minigame": meta.get("wx_minigame") if isinstance(meta.get("wx_minigame"), dict) else {},
        "unity_version": str(meta.get("unity_version") or "").strip(),
    }


def update_version_group_platform_config(
    project_id: str,
    version_name: str,
    env_key: str,
    platform: str,
    patch: Dict[str, Any],
    *,
    actor: str = "admin",
) -> dict:
    from services.build.platform_signing_service import (
        merge_platform_config_into_group_meta,
        normalize_ios_signing,
        sanitize_ios_signing_for_api,
    )

    vn = str(version_name or "").strip()
    if not vn:
        raise ValueError("缺少版本号")
    ek = normalize_release_env_key(env_key or "", project_id=project_id) if env_key else ""
    pk = _normalize_group_platform(platform) if platform else ""
    groups = _load_version_groups_meta(project_id)
    idx = _find_group_meta_index(groups, vn, ek, project_id, platform=pk or None)
    if idx < 0:
        _ensure_version_group_meta(project_id, vn, actor, env_key=ek or None, platform=pk or None)
        groups = _load_version_groups_meta(project_id)
        idx = _find_group_meta_index(groups, vn, ek, project_id, platform=pk or None)
    if idx < 0:
        raise ValueError("版本组不存在")
    row = merge_platform_config_into_group_meta(dict(groups[idx]), patch if isinstance(patch, dict) else {})
    groups[idx] = row
    _save_version_groups_meta(project_id, groups)
    versions_repo.audit("update_version_group_platform_config", "%s %s %s" % (project_id, ek or "-", vn))
    out = dict(row)
    if isinstance(out.get("ios_signing"), dict):
        out["ios_signing"] = sanitize_ios_signing_for_api(out["ios_signing"])
    return out


def list_version_groups(
    project_id: str,
    username: str,
    env_key: Optional[str] = None,
    platform: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403
    _migrate_version_groups_env_keys(project_id)
    _migrate_version_groups_platforms(project_id)
    ek = normalize_release_env_key(env_key, project_id=project_id) if env_key else ""
    pk = _normalize_group_platform(platform) if platform else ""
    meta_list = _load_version_groups_meta(project_id)
    versions = versions_repo.list_versions(project_id)
    if ek:
        meta_list = [row for row in meta_list if _group_env_key(row, project_id) == ek]
        versions = _filter_versions_by_env(versions, ek, project_id)
    if pk:
        meta_list = [row for row in meta_list if _group_platform(row) == pk]
        versions = _filter_versions_by_platform(versions, pk)
    keys_from_vc = {
        (str(row.get("version_name") or "").strip(), _version_row_platform(row))
        for row in versions
        if str(row.get("version_name") or "").strip()
    }
    keys_from_meta = {
        (str(row.get("version_name") or "").strip(), _group_platform(row))
        for row in meta_list
        if str(row.get("version_name") or "").strip()
    }
    all_keys = sorted(keys_from_vc | keys_from_meta, key=lambda item: (item[0], item[1]), reverse=True)
    meta_map = {(str(row.get("version_name") or "").strip(), _group_platform(row)): row for row in meta_list}
    rows = [
        _version_group_row(
            project_id,
            vn,
            meta_map.get((vn, pk_meta)) or meta_map.get((vn, "")) or {},
            versions,
            env_key=ek or None,
            platform=pk_meta or pk or None,
        )
        for vn, pk_meta in all_keys
    ]
    return {"version_groups": rows}, 200


def create_version_group(project_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_edit(project_id, username):
        return {"error": "无权限"}, 403
    vn = str(data.get("version_name") or "").strip()
    if not vn:
        return {"error": "缺少版本号"}, 400
    ek = normalize_release_env_key(data.get("env_key") or "", project_id=project_id) if data.get("env_key") else ""
    pk = _normalize_group_platform(data.get("platform")) if data.get("platform") else ""
    groups = _load_version_groups_meta(project_id)
    if _find_group_meta_index(groups, vn, ek, project_id, platform=pk or None) >= 0:
        return {"error": "该环境与平台下版本组已存在"}, 409
    mode = str(data.get("version_mode") or "general").strip() or "general"
    if mode not in VERSION_GROUP_MODES:
        mode = "general"
    status = str(data.get("status") or "active").strip() or "active"
    if status not in VERSION_GROUP_STATUSES:
        status = "active"
    now = datetime.now().isoformat()
    entry = {
        "version_name": vn,
        "env_key": ek,
        "platform": pk,
        "version_mode": mode,
        "notes": str(data.get("notes") or "").strip(),
        "recommended": bool(data.get("recommended")),
        "status": status,
        "created_at": now,
        "created_by": username,
    }
    pipeline_template = data.get("pipeline_template")
    if isinstance(pipeline_template, dict) and pipeline_template:
        entry["pipeline_template"] = _sync_pipeline_release_fields(pipeline_template)
    for key in GROUP_TEMPLATE_SCALAR_KEYS:
        if key in data:
            entry[key] = data.get(key)
    overrides = data.get("jenkins_job_overrides")
    if isinstance(overrides, dict):
        entry["jenkins_job_overrides"] = {
            str(k).strip(): str(v or "").strip()
            for k, v in overrides.items()
            if str(k).strip() and str(v or "").strip()
        }
    groups.append(entry)
    _save_version_groups_meta(project_id, groups)
    versions_repo.audit("create_project_version_group", "%s %s %s %s" % (project_id, ek or "-", pk or "-", vn))
    scoped_versions = versions_repo.list_versions(project_id)
    if ek:
        scoped_versions = _filter_versions_by_env(scoped_versions, ek, project_id)
    if pk:
        scoped_versions = _filter_versions_by_platform(scoped_versions, pk)
    return {"version_group": _version_group_row(project_id, vn, entry, scoped_versions, env_key=ek or None, platform=pk or None)}, 200


def update_version_group(project_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_edit(project_id, username):
        return {"error": "无权限"}, 403
    vn = str(data.get("version_name") or "").strip()
    if not vn:
        return {"error": "缺少版本号"}, 400
    ek = normalize_release_env_key(data.get("env_key") or "", project_id=project_id) if data.get("env_key") else ""
    pk = _normalize_group_platform(data.get("platform")) if data.get("platform") else ""
    groups = _load_version_groups_meta(project_id)
    idx = _find_group_meta_index(groups, vn, ek, project_id, platform=pk or None)
    versions = versions_repo.list_versions(project_id)
    scoped_versions = versions
    if ek:
        scoped_versions = _filter_versions_by_env(scoped_versions, ek, project_id)
    if pk:
        scoped_versions = _filter_versions_by_platform(scoped_versions, pk)
    has_vc = any(str(row.get("version_name") or "").strip() == vn for row in scoped_versions)
    if idx < 0 and not has_vc:
        return {"error": "版本组不存在"}, 404
    if idx < 0:
        _ensure_version_group_meta(project_id, vn, username, env_key=ek or None, platform=pk or None)
        groups = _load_version_groups_meta(project_id)
        idx = _find_group_meta_index(groups, vn, ek, project_id, platform=pk or None)
    row = dict(groups[idx])
    if "version_mode" in data:
        mode = str(data.get("version_mode") or row.get("version_mode") or "general").strip() or "general"
        row["version_mode"] = mode if mode in VERSION_GROUP_MODES else "general"
    if "notes" in data:
        row["notes"] = str(data.get("notes") or "").strip()
    if "recommended" in data:
        row["recommended"] = bool(data.get("recommended"))
    if "status" in data:
        status = str(data.get("status") or row.get("status") or "active").strip() or "active"
        row["status"] = status if status in VERSION_GROUP_STATUSES else "active"
    pipeline_template = data.get("pipeline_template")
    if isinstance(pipeline_template, dict):
        row["pipeline_template"] = _sync_pipeline_release_fields(pipeline_template)
    for key in GROUP_TEMPLATE_SCALAR_KEYS:
        if key in data:
            row[key] = data.get(key)
    overrides = data.get("jenkins_job_overrides")
    if isinstance(overrides, dict):
        row["jenkins_job_overrides"] = {
            str(k).strip(): str(v or "").strip()
            for k, v in overrides.items()
            if str(k).strip() and str(v or "").strip()
        }
    groups[idx] = row
    _save_version_groups_meta(project_id, groups)
    if isinstance(pipeline_template, dict):
        all_versions = versions_repo.list_versions(project_id)
        updated_at = datetime.now().isoformat()
        _propagate_pipeline_to_group_scope(
            all_versions,
            project_id,
            vn,
            ek or None,
            pk or None,
            row.get("pipeline_template") or {},
            _extract_group_template_fields(row),
            updated_at,
        )
        versions_repo.save_versions(project_id, all_versions)
    versions_repo.audit("update_project_version_group", "%s %s %s" % (project_id, ek or "-", vn))
    return {"version_group": _version_group_row(project_id, vn, row, scoped_versions, env_key=ek or None, platform=pk or None)}, 200


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
        row for row in versions
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
        row for row in versions
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

