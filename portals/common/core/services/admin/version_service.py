"""Version API service."""

from __future__ import annotations

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

VERSION_STAGES = [("dev", "开发"), ("test", "测试"), ("production", "线上")]
VERSION_STATUSES = [("draft", "草稿"), ("testing", "测试中"), ("active", "有效"), ("disabled", "失效"), ("archived", "归档")]
VERSION_STATUS_MAP = dict(VERSION_STATUSES)
STAGE_LABEL_MAP = dict(VERSION_STAGES)


def _normalize_rollout_percentage(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 100
    return max(0, min(100, value))


def _resolve_runtime_compat_fields(data: Dict[str, Any], current_row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    version_name = (
        (data.get("version_name") or (current_row or {}).get("version_name") or "").strip() or "1.0.0"
    )
    min_raw = data.get("min_client_version")
    if min_raw is None and current_row is not None:
        min_raw = current_row.get("min_client_version")
    min_client = (str(min_raw).strip() if min_raw is not None else "") or version_name
    # Max 与资源版本线一致；Web 管理端不再暴露 Max，避免与 version_name 重复配置。
    max_client = version_name
    rollout_raw = data.get("rollout_percentage")
    if rollout_raw is None and current_row is not None:
        rollout_raw = current_row.get("rollout_percentage", 100)
    is_revoked = data.get("is_revoked")
    if is_revoked is None and current_row is not None:
        is_revoked = current_row.get("is_revoked", False)
    force_raw = data.get("force_update")
    if force_raw is None and current_row is not None:
        force_raw = current_row.get("force_update", False)
    resource_server = data.get("resource_server_url")
    if resource_server is None and current_row is not None:
        resource_server = current_row.get("resource_server_url")
    catalog_raw = data.get("catalog_file_name")
    if catalog_raw is None and current_row is not None:
        catalog_raw = current_row.get("catalog_file_name")
    catalog_name = str(catalog_raw or "").strip() if catalog_raw is not None else ""
    if not catalog_name:
        catalog_name = f"catalog_{version_name}.bin"
    return {
        "min_client_version": min_client,
        "max_client_version": max_client,
        "rollout_percentage": _normalize_rollout_percentage(rollout_raw),
        "is_revoked": bool(is_revoked),
        "force_update": bool(force_raw),
        "resource_server_url": str(resource_server or "").strip(),
        "catalog_file_name": catalog_name,
    }


def _version_row_labels(channel_id: str, stage_id: str) -> dict[str, str]:
    from models.data import channels_db

    ch_map = {
        (c.get("id") or "").strip(): {
            "label": (c.get("name") or c.get("id") or "").strip(),
            "key": (c.get("apk_subdir") or c.get("build_param") or c.get("id") or "").strip(),
        }
        for c in (channels_db if isinstance(channels_db, list) else [])
        if (c.get("id") or "").strip()
    }
    cid = (channel_id or "").strip()
    sid = (stage_id or "dev").strip() or "dev"
    return {
        "channel_label": (ch_map.get(cid) or {}).get("label") or cid or "-",
        "channel_key": (ch_map.get(cid) or {}).get("key") or cid or "-",
        "stage_label": STAGE_LABEL_MAP.get(sid, sid),
    }


def _normalize_channel_storage_value(project_id: str, raw_channel: Any) -> str:
    channel_text = str(raw_channel or "").strip()
    if not channel_text:
        return ""
    return resolve_channel_id(project_id, channel_text) or channel_text


def _normalize_version_status(raw_status):
    return normalize_version_status(raw_status)


def _normalize_edit_scope(raw_scope):
    return normalize_edit_scope(raw_scope)


def _build_status_audit_tags(old_status, new_status):
    return build_status_audit_tags(old_status, new_status)


def _normalize_distribution_method(platform, distribution_method):
    method = (distribution_method or "").strip().lower()
    allowed = {"direct", "enterprise", "store", "testflight", "internal"}
    if method in allowed:
        return method
    return "testflight" if platform == "ios" else "direct"


def _version_group_key(row: dict) -> tuple:
    if not isinstance(row, dict):
        return ("", "", "dev")
    return (
        str(row.get("version_name") or "").strip(),
        str(row.get("channel") or "").strip(),
        str(row.get("stage") or "dev").strip(),
    )


def _propagate_pipeline_to_version_group(versions: list, anchor: dict, pipeline: dict, updated_at: str) -> None:
    """版本组编辑时，将 pipeline 同步到同 version_name + channel + stage 的所有 version_code。"""
    if not isinstance(pipeline, dict) or not isinstance(anchor, dict):
        return
    synced = _sync_pipeline_release_fields(pipeline)
    key = _version_group_key(anchor)
    if not key[0]:
        return
    for row in versions:
        if not isinstance(row, dict) or _version_group_key(row) != key:
            continue
        row["pipeline"] = copy.deepcopy(synced)
        row["updated_at"] = updated_at
        for legacy_field in ("deprecated", "status", "commercial_release", "jenkins_params"):
            row.pop(legacy_field, None)


GROUP_TEMPLATE_SCALAR_KEYS = (
    "jenkins_instance_id",
    "jenkins_job_id",
    "resource_server_url",
    "catalog_file_name",
    "min_client_version",
    "rollout_percentage",
    "force_update",
    "is_revoked",
)


GROUP_TEMPLATE_BOOTSTRAP_KEYS = (
    "resource_server_url",
    "catalog_file_name",
    "min_client_version",
    "rollout_percentage",
    "force_update",
    "is_revoked",
)


GROUP_TEMPLATE_JENKINS_KEYS = (
    "jenkins_instance_id",
    "jenkins_job_id",
)


VC_PIPELINE_PROTECTED_KEYS = {
    "pipeline",
    "pipeline_template",
    "jenkins_instance_id",
    "jenkins_job_id",
    "jenkins_params",
    "resource_server_url",
    "catalog_file_name",
    "min_client_version",
    "rollout_percentage",
    "force_update",
    "is_revoked",
}


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


def resolve_effective_ios_signing(project_id: str, version_row: Dict[str, Any]) -> dict:
    from services.build.platform_signing_service import normalize_ios_signing

    if not isinstance(version_row, dict):
        return normalize_ios_signing({})
    version_name = str(version_row.get("version_name") or "").strip()
    if not version_name:
        return normalize_ios_signing({})
    env_key = _version_row_env_key(version_row, project_id)
    platform = _version_row_platform(version_row)
    meta = _get_group_meta(project_id, version_name, env_key, platform)
    return normalize_ios_signing(meta.get("ios_signing") if isinstance(meta, dict) else {})


def resolve_effective_pipeline(project_id: str, version_row: Dict[str, Any]) -> Dict[str, Any]:
    """Return the effective build pipeline for a VC.

    The version group's `pipeline_template` is the single source of truth.
    Legacy VC-level `pipeline` is used only as fallback when the group has none yet
    (e.g. for projects created before this refactor).
    """
    if not isinstance(version_row, dict):
        return {}
    version_name = str(version_row.get("version_name") or "").strip()
    env_key = _version_row_env_key(version_row, project_id) if version_name else ""
    platform = _version_row_platform(version_row) if version_name else ""
    meta = _get_group_meta(project_id, version_name, env_key, platform) if version_name else {}
    template = meta.get("pipeline_template") if isinstance(meta, dict) else {}
    if isinstance(template, dict) and template and _pipeline_has_any_content(template):
        return _apply_project_build_defaults_to_pipeline(project_id, copy.deepcopy(template))
    legacy = version_row.get("pipeline")
    if isinstance(legacy, dict) and legacy and _pipeline_has_any_content(legacy):
        return _apply_project_build_defaults_to_pipeline(project_id, copy.deepcopy(legacy))
    if version_name:
        try:
            all_versions = versions_repo.list_versions(project_id)
            stub_meta = {
                "version_name": version_name,
                "env_key": env_key,
                "platform": platform,
            }
            lazy = _lazy_init_pipeline_template_from_siblings(project_id, stub_meta, all_versions)
            if isinstance(lazy, dict) and lazy:
                return _apply_project_build_defaults_to_pipeline(project_id, lazy)
        except Exception:
            pass
    return _apply_project_build_defaults_to_pipeline(project_id, {})


def resolve_effective_bootstrap_fields(project_id: str, version_row: Dict[str, Any]) -> Dict[str, Any]:
    """Return bootstrap scalars (resource_server_url etc.) using the version group as the source.

    Legacy VC-stored values serve as fallback when the group meta has none.
    """
    if not isinstance(version_row, dict):
        return {}
    from services.commercial_release_plan import DEFAULT_RESOURCE_SERVER

    version_name = str(version_row.get("version_name") or "").strip()
    env_key = _version_row_env_key(version_row, project_id) if version_name else ""
    platform = _version_row_platform(version_row) if version_name else ""
    meta = _get_group_meta(project_id, version_name, env_key, platform) if version_name else {}
    out: Dict[str, Any] = {}
    for key in GROUP_TEMPLATE_BOOTSTRAP_KEYS:
        meta_val = meta.get(key) if isinstance(meta, dict) else None
        if meta_val is not None and str(meta_val).strip() != "":
            out[key] = meta_val
        elif version_row.get(key) is not None:
            out[key] = version_row.get(key)
    if not str(out.get("resource_server_url") or "").strip():
        out["resource_server_url"] = DEFAULT_RESOURCE_SERVER
    if not str(out.get("catalog_file_name") or "").strip() and version_name:
        out["catalog_file_name"] = f"catalog_{version_name}.bin"
    if out.get("min_client_version") is None or str(out.get("min_client_version") or "").strip() == "":
        if version_name:
            out["min_client_version"] = version_name
    return out


def enrich_version_client_urls(project_id: str, version_row: Dict[str, Any]) -> Dict[str, Any]:
    """Merge effective bootstrap defaults and derive external URLs from OSS base + paths."""
    if not isinstance(version_row, dict):
        return {}
    row = dict(version_row)
    bootstrap = resolve_effective_bootstrap_fields(project_id, row)
    for key, value in bootstrap.items():
        if value is None:
            continue
        if key in {"rollout_percentage", "force_update", "is_revoked"}:
            if row.get(key) is None:
                row[key] = value
            continue
        if not str(row.get(key) or "").strip() and str(value).strip():
            row[key] = value

    base = str(row.get("resource_server_url") or "").strip().rstrip("/")
    if not base:
        from services.commercial_release_plan import DEFAULT_RESOURCE_SERVER

        base = DEFAULT_RESOURCE_SERVER
        row["resource_server_url"] = base

    derived_paths = _derive_runtime_paths(row, project_id)
    for path_key in ("resource_path", "config_path", "code_path", "apk_path"):
        if not str(row.get(path_key) or "").strip() and derived_paths.get(path_key):
            row[path_key] = derived_paths[path_key]

    def _url_from_path(path_key: str, url_key: str) -> None:
        path = str(row.get(path_key) or "").strip().strip("/")
        if path and not str(row.get(url_key) or "").strip():
            row[url_key] = f"{base}/{path}"

    _url_from_path("apk_path", "apk_url")
    _url_from_path("resource_path", "resource_url")
    _url_from_path("config_path", "config_url")
    _url_from_path("code_path", "code_url")

    version_name = str(row.get("version_name") or "").strip()
    for version_key in ("apk_version", "resource_version", "config_version"):
        if not str(row.get(version_key) or "").strip() and version_name:
            row[version_key] = version_name
    return row


def resolve_effective_jenkins(project_id: str, version_row: Dict[str, Any]) -> Dict[str, str]:
    """Return Jenkins instance/job for a VC, sourced from version group + channel binding."""
    if not isinstance(version_row, dict):
        return {"jenkins_instance_id": "", "jenkins_job_id": ""}
    version_name = str(version_row.get("version_name") or "").strip()
    env_key = _version_row_env_key(version_row, project_id) if version_name else ""
    platform = _version_row_platform(version_row) if version_name else ""
    meta = _get_group_meta(project_id, version_name, env_key, platform) if version_name else {}
    instance = str((meta or {}).get("jenkins_instance_id") or version_row.get("jenkins_instance_id") or "").strip()
    from services.release.release_policy_service import resolve_jenkins_job

    channel_id = str(version_row.get("channel") or version_row.get("channel_id") or "").strip()
    job = resolve_jenkins_job(version_row, meta, channel_id, project_id=project_id)
    return {"jenkins_instance_id": instance, "jenkins_job_id": job}


def _pipeline_has_any_content(pipeline: Any) -> bool:
    """Return True when the pipeline dict has at least one non-empty key."""
    if not isinstance(pipeline, dict) or not pipeline:
        return False
    for step in ("config_export", "resource_build", "hot_release", "apk_build"):
        block = pipeline.get(step)
        if not isinstance(block, dict):
            continue
        if block.get("enabled"):
            return True
        for k, v in block.items():
            if k == "enabled":
                continue
            if v not in (None, "", False):
                return True
    return bool(str(pipeline.get("git_branch") or "").strip())


def _lazy_init_pipeline_template_from_siblings(
    project_id: str,
    meta: dict,
    versions: list,
) -> dict:
    existing = meta.get("pipeline_template")
    if isinstance(existing, dict) and existing:
        return copy.deepcopy(existing)
    vn = str(meta.get("version_name") or "").strip()
    ek = _group_env_key(meta, project_id)
    pk = _group_platform(meta)
    best: dict | None = None
    best_at = ""
    for row in versions:
        if not _version_matches_group_scope(row, vn, ek, pk, project_id):
            continue
        pl = row.get("pipeline")
        if not isinstance(pl, dict) or not pl:
            continue
        at = str(row.get("updated_at") or "")
        if at >= best_at:
            best_at = at
            best = pl
    return copy.deepcopy(best) if isinstance(best, dict) else {}


def _apply_project_build_defaults_to_pipeline(project_id: str, pipeline: dict | None) -> dict:
    from services.admin.project_build_config_service import get_project_build_config

    base = dict(pipeline or {})
    apk_build = base.get("apk_build")
    if not isinstance(apk_build, dict):
        apk_build = {}
    apk_build = dict(apk_build)
    pbc = get_project_build_config(project_id)
    if not str(apk_build.get("app_name") or "").strip():
        apk_build["app_name"] = (pbc.get("app_name") or "").strip()
    if not str(apk_build.get("unity_project_path") or "").strip():
        apk_build["unity_project_path"] = (pbc.get("unity_project_path") or "").strip()
    if not str(apk_build.get("output_base_dir") or "").strip():
        apk_build["output_base_dir"] = (pbc.get("output_base_dir") or "").strip()
    if not str(apk_build.get("git_branch") or "").strip():
        apk_build["git_branch"] = (pbc.get("default_git_branch") or "").strip()
    base["apk_build"] = apk_build
    return _sync_pipeline_release_fields(base)


def _extract_group_template_fields(data: dict) -> dict:
    out: dict = {}
    if not isinstance(data, dict):
        return out
    for key in GROUP_TEMPLATE_SCALAR_KEYS:
        if key in data:
            out[key] = data.get(key)
    return out


def _apply_group_template_fields_to_row(row: dict, template_fields: dict) -> None:
    if not isinstance(row, dict) or not isinstance(template_fields, dict):
        return
    for key in GROUP_TEMPLATE_SCALAR_KEYS:
        if key not in template_fields:
            continue
        value = template_fields.get(key)
        if key in ("force_update", "is_revoked"):
            row[key] = bool(value)
        elif key == "rollout_percentage":
            try:
                row[key] = int(value)
            except (TypeError, ValueError):
                row[key] = row.get(key) or 100
        else:
            row[key] = str(value or "").strip() if value is not None else ""


def _save_pipeline_template_to_meta(
    project_id: str,
    version_name: str,
    env_key: Optional[str],
    platform: Optional[str],
    username: str,
    pipeline: dict,
    template_fields: Optional[dict] = None,
) -> dict:
    vn = str(version_name or "").strip()
    ek = normalize_release_env_key(env_key or "", project_id=project_id) if env_key else ""
    pk = _normalize_group_platform(platform) if platform else ""
    groups = _load_version_groups_meta(project_id)
    idx = _find_group_meta_index(groups, vn, ek, project_id, platform=pk or None)
    if idx < 0:
        _ensure_version_group_meta(project_id, vn, username, env_key=ek or None, platform=pk or None)
        groups = _load_version_groups_meta(project_id)
        idx = _find_group_meta_index(groups, vn, ek, project_id, platform=pk or None)
    if idx < 0:
        return {}
    row = dict(groups[idx])
    row["pipeline_template"] = _sync_pipeline_release_fields(pipeline)
    if isinstance(template_fields, dict):
        for key in GROUP_TEMPLATE_SCALAR_KEYS:
            if key in template_fields:
                row[key] = template_fields[key]
    groups[idx] = row
    _save_version_groups_meta(project_id, groups)
    return row


def _propagate_pipeline_to_group_scope(
    versions: list,
    project_id: str,
    version_name: str,
    env_key: Optional[str],
    platform: Optional[str],
    pipeline: dict,
    template_fields: Optional[dict],
    updated_at: str,
) -> None:
    if not isinstance(pipeline, dict):
        return
    synced = _sync_pipeline_release_fields(pipeline)
    fields = template_fields if isinstance(template_fields, dict) else {}
    for row in versions:
        if not _version_matches_group_scope(row, version_name, env_key or "", platform or "", project_id):
            continue
        row["pipeline"] = copy.deepcopy(synced)
        _apply_group_template_fields_to_row(row, fields)
        derived = _derive_runtime_paths(row, project_id=project_id)
        row.update(derived)
        row.update(_enrich_version_scope_fields(project_id, row))
        if not (row.get("apk_path") or "").strip() and (row.get("version_code") or "").strip():
            try:
                from services.apk_artifact_service import default_version_apk_rel_path

                row["apk_path"] = default_version_apk_rel_path(project_id, row)
            except Exception:
                pass
        enriched = enrich_version_client_urls(project_id, row)
        for url_key in (
            "resource_server_url",
            "catalog_file_name",
            "min_client_version",
            "apk_url",
            "resource_url",
            "config_url",
            "code_url",
            "apk_version",
            "resource_version",
            "config_version",
        ):
            if enriched.get(url_key):
                row[url_key] = enriched[url_key]
        row["updated_at"] = updated_at
        for legacy_field in ("deprecated", "status", "commercial_release", "jenkins_params"):
            row.pop(legacy_field, None)
        meta = _get_group_meta(project_id, version_name, env_key, platform)
        from services.release.release_policy_service import resolve_jenkins_job

        job = resolve_jenkins_job(row, meta, str(row.get("channel") or ""), project_id=project_id)
        if job:
            row["jenkins_job_id"] = job


def _sync_pipeline_release_fields(pipeline: dict | None) -> dict:
    """发布配置 Git 分支写入 pipeline.apk_build.git_branch 与 pipeline.git_branch。"""
    if not isinstance(pipeline, dict):
        return {}
    out = dict(pipeline)
    apk_build = out.get("apk_build")
    if not isinstance(apk_build, dict):
        apk_build = {}
    branch = str(apk_build.get("git_branch") or out.get("git_branch") or "").strip()
    if branch:
        apk_build = dict(apk_build)
        apk_build["git_branch"] = branch
        out["apk_build"] = apk_build
        out["git_branch"] = branch
    elif isinstance(out.get("apk_build"), dict):
        out["apk_build"] = apk_build
    return out


def _deep_merge_dict(base: dict | None, patch: dict | None) -> dict:
    """Recursively merge patch into base; patch values win."""
    result = dict(base or {})
    if not isinstance(patch, dict):
        return result
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _merge_version_pipeline(current: dict | None, patch: dict | None) -> dict:
    """Merge pipeline patch onto stored pipeline without dropping unedited step keys."""
    merged = _deep_merge_dict(current if isinstance(current, dict) else {}, patch)
    return _sync_pipeline_release_fields(merged)


def _clean_version_platform_fields(data, platform, current=None):
    current = current or {}
    cleaned = {
        "distribution_method": _normalize_distribution_method(platform, data.get("distribution_method") or current.get("distribution_method")),
        "package_name": "",
        "min_sdk": "",
        "bundle_id": "",
        "min_ios_version": "",
    }
    if platform == "ios":
        cleaned["bundle_id"] = (data.get("bundle_id") or current.get("bundle_id") or "").strip()
        cleaned["min_ios_version"] = (data.get("min_ios_version") or current.get("min_ios_version") or "").strip()
    else:
        cleaned["package_name"] = (data.get("package_name") or current.get("package_name") or "").strip()
        cleaned["min_sdk"] = (data.get("min_sdk") or current.get("min_sdk") or "").strip()
    return cleaned


def _validate_version_payload(platform, version):
    apk_path = (version.get("apk_path") or "").strip()
    package_name = (version.get("package_name") or "").strip()
    min_sdk = (version.get("min_sdk") or "").strip()
    bundle_id = (version.get("bundle_id") or "").strip()
    min_ios_version = (version.get("min_ios_version") or "").strip()
    if platform == "ios":
        if apk_path and not apk_path.lower().endswith(".ipa"):
            return "iOS 版本的安装包路径必须以 .ipa 结尾"
        if bundle_id and not re.match(r"^[A-Za-z0-9]+(\.[A-Za-z0-9_-]+)+$", bundle_id):
            return "Bundle ID 格式不正确"
        if min_ios_version and not re.match(r"^\d+(\.\d+){0,2}$", min_ios_version):
            return "最低 iOS 版本格式应为 16 或 16.4"
    else:
        if apk_path and not apk_path.lower().endswith((".apk", ".aab")):
            return "Android 版本的安装包路径必须以 .apk 或 .aab 结尾"
        if package_name and not re.match(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$", package_name):
            return "Android 包名格式不正确"
        if min_sdk and not re.match(r"^\d{1,2}$", min_sdk):
            return "最低 Android SDK 应为数字"
    return None


def _enrich_version_scope_fields(project_id: str, row: dict) -> dict:
    enriched = apply_scope_fields_to_version_row(row, project_id)
    env_key = normalize_release_env_key(enriched.get("env_key") or enriched.get("stage"))
    enriched["env_key"] = env_key
    enriched["env"] = env_key_to_gm_env(env_key)
    if not str(enriched.get("scope_id") or "").strip():
        from services.release.scope_ids import build_scope_id, project_slug

        enriched["scope_id"] = build_scope_id(
            project_slug(project_id),
            env_key,
            str(enriched.get("channel") or ""),
            str(enriched.get("platform") or "android").strip().lower(),
        )
    return enriched


def _derive_runtime_paths(version_row: Dict[str, Any], project_id: str = "") -> Dict[str, str]:
    stage_id = str(version_row.get("stage") or "dev").strip()
    channel_raw = str(version_row.get("channel") or "common").strip()
    platform_raw = str(version_row.get("platform") or "android").strip().lower()
    version_name = str(version_row.get("version_name") or "").strip()
    version_code = str(version_row.get("version_code") or "").strip()
    release_env = normalize_release_environment("", stage_id)
    release_channel = normalize_release_channel(channel_raw)
    release_platform = normalize_release_platform(platform_raw)
    runtime_paths = build_runtime_resolve_paths(
        resource_server_url=str(version_row.get("resource_server_url") or ""),
        release_environment=release_env,
        release_channel=release_channel,
        release_platform=release_platform,
        release_version=version_name,
        version_code=version_code,
    )
    rel_base = str(runtime_paths.get("resource_relative_path") or "").strip("/")
    apk_path = ""
    if rel_base and version_code:
        try:
            from services.apk_artifact_service import _expected_archive_filename

            pid = str(project_id or version_row.get("project_id") or "").strip()
            fname = _expected_archive_filename(version_row, pid)
            apk_path = f"{rel_base}/{fname}"
        except Exception:
            apk_path = ""
    out = {
        "resource_path": runtime_paths.get("resource_relative_path") or "",
        "config_path": runtime_paths.get("config_relative_path") or "",
        "code_path": runtime_paths.get("code_relative_path") or "",
    }
    if apk_path:
        out["apk_path"] = apk_path
    return out


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


def project_download_stats(project_id: str, username: str) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403
    total = versions_repo.project_download_count(project_id)
    today = date.today()
    trend = []
    events = versions_repo.load_events()
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        cnt = 0
        for e in events:
            fname = e.get("filename") or ""
            if versions_repo.parse_event_project(fname) != project_id:
                continue
            if (e.get("date") or "")[:10] == d:
                cnt += 1
        trend.append({"date": d, "count": cnt})
    return {"total": total, "trend_7d": trend, "sum_7d": sum(t["count"] for t in trend)}, 200


def list_versions(project_id: str, username: str) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403
    rows = []
    for source in versions_repo.list_versions(project_id):
        row = copy.deepcopy(source)
        labels = _version_row_labels(row.get("channel"), row.get("stage"))
        row.update(_enrich_version_scope_fields(project_id, row))
        row.update(labels)
        row["channel_id"] = str(row.get("channel_id") or source.get("channel") or "")
        row["channel_name"] = labels["channel_label"]
        row["platform_label"] = versions_repo.platform_label(str(row.get("platform") or ""))
        row["version_status"] = _normalize_version_status(row.get("version_status") or "active")
        row["version_status_label"] = VERSION_STATUS_MAP.get(row["version_status"], row["version_status"])
        row["apk_status"] = "found" if versions_repo.has_apk(project_id, source) else "not_found"
        rows.append(row)
    return {"versions": rows}, 200


def get_version_effective_pipeline(project_id: str, version_id: str, username: str) -> Tuple[Dict[str, Any], int]:
    """Return the effective build pipeline + bootstrap + Jenkins binding for a VC.

    Single source of truth is the version group; legacy VC-level values are used only
    as fallback for unmigrated projects. UI uses this to render read-only summaries.
    """
    if not versions_repo.has_project(project_id) or not versions_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403
    versions = versions_repo.list_versions(project_id)
    row = next((x for x in versions if str(x.get("id") or "") == str(version_id)), None)
    if not row:
        return {"error": "版本不存在"}, 404
    pipeline = resolve_effective_pipeline(project_id, row)
    bootstrap = resolve_effective_bootstrap_fields(project_id, row)
    jenkins = resolve_effective_jenkins(project_id, row)
    vn = str(row.get("version_name") or "").strip()
    env_key = _version_row_env_key(row, project_id)
    platform = _version_row_platform(row)
    meta = _get_group_meta(project_id, vn, env_key, platform)
    from services.release.release_policy_service import assess_pipeline_readiness, build_config_href

    readiness = assess_pipeline_readiness(row, meta, str(row.get("channel") or ""), project_id=project_id)
    return (
        {
            "effective_pipeline": pipeline,
            "bootstrap": bootstrap,
            "jenkins": jenkins,
            "version_group": {
                "version_name": vn,
                "env_key": env_key,
                "platform": platform,
            },
            "readiness": readiness,
            "build_config_href": build_config_href(project_id, row),
            "source": readiness.get("source") or "none",
        },
        200,
    )


def get_version_downloads(project_id: str, version_id: str, username: str) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403
    versions = versions_repo.list_versions(project_id)
    v = next((x for x in versions if (x.get("id") or "") == version_id), None)
    if not v:
        return {"error": "版本不存在"}, 404
    from routes.build_routes import _compute_stage_output_base, _get_version_downloads
    from config import Config

    channel_id = (v.get("channel") or "").strip()
    stage_id = (v.get("stage") or "dev").strip()
    scan_dir = _compute_stage_output_base(Config.APK_DIR, channel_id, stage_id)
    files = _get_version_downloads(project_id, v, scan_dir=scan_dir)
    return {"files": files}, 200


def build_version_runtime_preview(
    project_id: str,
    version_row: Dict[str, Any],
    *,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row = dict(version_row)
    if overrides:
        for key, value in overrides.items():
            if value is not None and key != "config_environment":
                row[key] = value
        config_env_override = overrides.get("config_environment")
        if config_env_override:
            pipeline = dict(row.get("pipeline") or {})
            config_export = dict(pipeline.get("config_export") or {})
            config_export["environment"] = str(config_env_override).strip()
            pipeline["config_export"] = config_export
            row["pipeline"] = pipeline
    row = _enrich_version_scope_fields(project_id, row)
    compat = _resolve_runtime_compat_fields(row, row)
    row.update(compat)

    pipeline = row.get("pipeline") if isinstance(row.get("pipeline"), dict) else {}
    config_export = pipeline.get("config_export") if isinstance(pipeline.get("config_export"), dict) else {}
    env_key = normalize_release_env_key(row.get("env_key") or row.get("stage") or "development", project_id=project_id)
    release_env = str(config_export.get("environment") or "").strip()
    if release_env not in ("Development", "Testing", "Staging", "Production"):
        release_env = env_key_to_jenkins_env(env_key)
    release_channel = normalize_release_channel(str(row.get("channel") or "common"))
    release_platform = normalize_release_platform(str(row.get("platform") or "android"))
    version_name = str(row.get("version_name") or "").strip()
    version_code = str(row.get("version_code") or "").strip()

    runtime_paths = build_runtime_resolve_paths(
        resource_server_url=str(row.get("resource_server_url") or ""),
        release_environment=release_env,
        release_channel=release_channel,
        release_platform=release_platform,
        release_version=version_name,
        version_code=version_code,
    )
    resource_base = (str(row.get("resource_server_url") or "").strip() or DEFAULT_RESOURCE_SERVER).rstrip("/")
    resource_relative = str(runtime_paths.get("resource_relative_path") or "").strip("/")
    catalog_file_name = str(row.get("catalog_file_name") or runtime_paths.get("catalog_file_name") or "").strip().lstrip("/")
    catalog_url = ""
    if resource_base and resource_relative and catalog_file_name:
        catalog_url = f"{resource_base}/{resource_relative}/{catalog_file_name}"

    from services.release.release_context import resolve_release_context

    ctx = resolve_release_context(
        project_id,
        env_key,
        str(row.get("channel") or ""),
        version_row=row,
    )

    domain = {
        "config": bool(config_export.get("enabled")),
        "code": bool(
            (pipeline.get("hot_release") or {}).get("enabled")
            and "code" in str((pipeline.get("hot_release") or {}).get("release_targets") or "code,resource").lower()
        ),
        "resource": bool(
            (pipeline.get("resource_build") or {}).get("enabled")
            or (
                (pipeline.get("hot_release") or {}).get("enabled")
                and "resource" in str((pipeline.get("hot_release") or {}).get("release_targets") or "").lower()
            )
        ),
        "apk": bool((pipeline.get("apk_build") or {}).get("enabled")),
    }

    return {
        "scope_id": str(ctx.get("scope_id") or row.get("scope_id") or ""),
        "active_bundle_id": str(ctx.get("active_bundle_id") or ""),
        "resource_server_url": resource_base,
        "resource_relative_path": resource_relative,
        "config_relative_path": runtime_paths.get("config_relative_path") or "",
        "code_relative_path": runtime_paths.get("code_relative_path") or "",
        "catalog_file_name": catalog_file_name,
        "catalog_url": catalog_url,
        "config_manifest_url": runtime_paths.get("config_manifest_path") or "",
        "code_manifest_url": runtime_paths.get("code_manifest_path") or "",
        "min_client_version": compat.get("min_client_version"),
        "max_client_version": compat.get("max_client_version"),
        "rollout_percentage": compat.get("rollout_percentage"),
        "force_update": compat.get("force_update"),
        "is_revoked": compat.get("is_revoked"),
        "domain_status": domain,
    }


def get_version_runtime_preview(
    project_id: str,
    version_id: str,
    username: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403
    versions = versions_repo.list_versions(project_id)
    v = next((x for x in versions if (x.get("id") or "") == version_id), None)
    if not v:
        return {"error": "版本不存在"}, 404
    preview = build_version_runtime_preview(project_id, v, overrides=overrides)
    return {"ok": True, "preview": preview}, 200


def get_apk_download_info(
    project_id: str,
    version_id: str,
    username: str,
    local_base_url: str | None = None,
) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403
    versions = versions_repo.list_versions(project_id)
    v = next((x for x in versions if (x.get("id") or "") == version_id), None)
    if not v:
        return {"error": "版本不存在"}, 404
    from services.apk_artifact_service import build_download_info, version_apk_build_enabled

    info = build_download_info(project_id, v, local_base_url=local_base_url)
    if not info:
        return {"error": "暂无可下载的安装包", "available": False}, 404
    info["apk_build_enabled"] = version_apk_build_enabled(v)
    return info, 200


def _duplicate_version_code_in_group(
    versions: list,
    version_name: str,
    version_code: str,
    project_id: str,
    channel_id: str = "",
    platform: str = "",
    env_key: str = "",
    exclude_id: str | None = None,
):
    vn = (version_name or "").strip()
    vc = str(version_code or "").strip()
    if not vn or not vc:
        return None
    ch = _normalize_channel_storage_value(project_id, channel_id) or ""
    pl = _normalize_group_platform(platform) or "android"
    ek = normalize_release_env_key(env_key or "development", project_id=project_id)
    for row in versions:
        rid = (row.get("id") or "").strip()
        if exclude_id and rid == exclude_id:
            continue
        if (row.get("version_name") or "").strip() != vn:
            continue
        if str(row.get("version_code") or "").strip() != vc:
            continue
        row_ch = _normalize_channel_storage_value(project_id, row.get("channel")) or ""
        if row_ch != ch:
            continue
        if _version_row_platform(row) != pl:
            continue
        if _version_row_env_key(row, project_id) != ek:
            continue
        return row
    return None


def _format_version_output(project_id: str, v: dict, platform: str, ch_text: str = "", ch_rec: bool = False) -> dict:
    labels = _version_row_labels(v.get("channel"), v.get("stage"))
    return {
        **v,
        **labels,
        "channel": labels.get("channel_key") or v.get("channel"),
        "channel_id": v.get("channel"),
        "platform_label": versions_repo.platform_label(platform),
        "version_status": _normalize_version_status(v.get("version_status") or "active"),
        "version_status_label": VERSION_STATUS_MAP.get(_normalize_version_status(v.get("version_status") or "active"), "有效"),
        "version_mode": v.get("version_mode", "general"),
        "pipeline": v.get("pipeline") or None,
        "apk_status": "found" if versions_repo.has_apk(project_id, v) else "not_found",
        "download_count": versions_repo.version_download_count(project_id, v),
        "recommended": versions_repo.is_recommended(project_id, v),
        "changelog_text": ch_text,
        "changelog_recommended": ch_rec,
    }


def _create_version_all_channels(project_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    env_key = normalize_release_env_key(data.get("env_key") or "development", project_id=project_id)
    platform = (data.get("platform") or "").strip().lower()
    if not is_valid_platform_id(platform):
        platform = "android"
    if not is_platform_allowed_for_env(project_id, env_key, platform):
        return {"error": "所选平台不在该环境的交付范围内"}, 400

    channel_ids = [
        str(row.get("id") or "").strip()
        for row in get_channels_for_env(project_id, env_key)
        if str(row.get("id") or "").strip()
    ]
    if not channel_ids:
        return {"error": "该环境未配置可用渠道"}, 400

    versions = versions_repo.list_versions(project_id)
    created_rows: list = []
    skipped_channels: list = []
    ch_text = (data.get("changelog") or "").strip()
    ch_rec = bool(data.get("changelog_recommended"))

    for channel_id in channel_ids:
        if not is_channel_allowed_for_env(project_id, env_key, channel_id):
            continue
        single_data = dict(data)
        single_data.pop("apply_all_channels", None)
        single_data["channel_id"] = channel_id
        row, error, status = _build_new_version_row(project_id, username, single_data, versions)
        if error:
            if status == 409:
                skipped_channels.append(channel_id)
                continue
            return {"error": error}, status
        versions.append(row)
        created_rows.append(row)
        vid = str(row.get("id") or "").strip()
        if ch_text or ch_rec:
            versions_repo.save_changelog_item("version:" + project_id + ":" + vid, {"text": ch_text, "recommended": ch_rec})
        versions_repo.audit("create_project_version", "%s %s" % (project_id, vid))

    if not created_rows:
        return {"error": "所有渠道下均已存在该 VersionCode，或没有可创建的交付线"}, 409

    versions_repo.save_versions(project_id, versions)
    vn = str((created_rows[0] or {}).get("version_name") or "").strip()
    if vn:
        _ensure_version_group_meta(
            project_id,
            vn,
            username,
            created_rows[0].get("version_mode"),
            created_rows[0].get("notes"),
            env_key=env_key,
            platform=platform,
        )

    out_versions = [_format_version_output(project_id, row, platform, ch_text, ch_rec) for row in created_rows]
    return {
        "versions": out_versions,
        "version": out_versions[0],
        "created_count": len(out_versions),
        "skipped_count": len(skipped_channels),
    }, 200


def _build_new_version_row(
    project_id: str,
    username: str,
    data: Dict[str, Any],
    versions: list,
) -> Tuple[Optional[dict], Optional[str], int]:
    vid = str(uuid.uuid4())[:8]
    env_key = normalize_release_env_key(data.get("env_key") or "development", project_id=project_id)
    stage = env_key_to_stage(env_key)
    platform = (data.get("platform") or "").strip().lower()
    if not is_valid_platform_id(platform):
        platform = "ios" if str(data.get("apk_path") or "").lower().endswith(".ipa") else "android"
    if stage not in [s[0] for s in VERSION_STAGES]:
        stage = "dev"

    channel_id = _normalize_channel_storage_value(project_id, data.get("channel_id")) or "default"
    if not is_channel_allowed_for_env(project_id, env_key, channel_id):
        return None, "所选渠道不在该环境的交付范围内", 400
    if not is_platform_allowed_for_env(project_id, env_key, platform):
        return None, "所选平台不在该环境的交付范围内", 400

    v = {
        "id": vid,
        "channel": channel_id,
        "stage": stage,
        "platform": platform,
        "version_status": _normalize_version_status(data.get("version_status") or "active"),
        "version_name": (data.get("version_name") or "").strip(),
        "version_code": (data.get("version_code") or "").strip(),
        "apk_path": (data.get("apk_path") or "").strip(),
        "resource_path": (data.get("resource_path") or "").strip(),
        "config_path": (data.get("config_path") or "").strip(),
        "jenkins_job_id": (data.get("jenkins_job_id") or "").strip(),
        "notes": (data.get("notes") or "").strip(),
        "version_mode": (data.get("version_mode") or "general").strip(),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    pipeline = data.get("pipeline")
    if isinstance(pipeline, dict):
        v["pipeline"] = _merge_version_pipeline(None, pipeline)
    else:
        meta = _get_group_meta(project_id, v.get("version_name") or "", env_key, platform)
        if not meta:
            meta = {
                "version_name": v.get("version_name") or "",
                "env_key": env_key,
                "platform": platform,
            }
        template = _lazy_init_pipeline_template_from_siblings(project_id, meta, versions)
        if template:
            v["pipeline"] = _merge_version_pipeline(None, _apply_project_build_defaults_to_pipeline(project_id, template))
        else:
            v["pipeline"] = _apply_project_build_defaults_to_pipeline(project_id, {})
        for key in GROUP_TEMPLATE_SCALAR_KEYS:
            if data.get(key):
                continue
            meta_val = meta.get(key)
            if meta_val is not None and str(meta_val).strip() != "":
                v[key] = meta_val
        from services.release.release_policy_service import resolve_jenkins_job

        job = resolve_jenkins_job(v, meta, channel_id, project_id=project_id)
        if job:
            v["jenkins_job_id"] = job
    v.update(_clean_version_platform_fields(data, platform))
    v.update(_resolve_runtime_compat_fields(data))
    v.update(_derive_runtime_paths(v, project_id=project_id))
    v = _enrich_version_scope_fields(project_id, v)
    if not v.get("apk_path") and v.get("version_code"):
        try:
            from services.apk_artifact_service import default_version_apk_rel_path

            v["apk_path"] = default_version_apk_rel_path(project_id, v)
        except Exception:
            pass
    validation_error = _validate_version_payload(platform, v)
    if validation_error:
        return None, validation_error, 400

    dup = _duplicate_version_code_in_group(
        versions,
        v.get("version_name"),
        v.get("version_code"),
        project_id,
        channel_id,
        platform,
        env_key,
    )
    if dup:
        return None, (
            "版本 %s 下已存在相同的 Version Code「%s」，请使用其他编号"
            % (v.get("version_name") or "-", v.get("version_code") or "")
        ), 409
    return v, None, 200


def create_version(project_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_edit(project_id, username):
        return {"error": "无权限"}, 403

    if data.get("apply_all_channels"):
        return _create_version_all_channels(project_id, username, data)

    versions = versions_repo.list_versions(project_id)
    v, error, status = _build_new_version_row(project_id, username, data, versions)
    if error:
        return {"error": error}, status

    versions.append(v)
    versions_repo.save_versions(project_id, versions)
    env_key = normalize_release_env_key(data.get("env_key") or "development", project_id=project_id)
    platform = _version_row_platform(v)
    _ensure_version_group_meta(
        project_id,
        v.get("version_name"),
        username,
        v.get("version_mode"),
        v.get("notes"),
        env_key=env_key,
        platform=platform,
    )

    ch_text = (data.get("changelog") or "").strip()
    ch_rec = bool(data.get("changelog_recommended"))
    vid = str(v.get("id") or "").strip()
    if ch_text or ch_rec:
        versions_repo.save_changelog_item("version:" + project_id + ":" + vid, {"text": ch_text, "recommended": ch_rec})

    versions_repo.audit("create_project_version", "%s %s" % (project_id, vid))
    return {"version": _format_version_output(project_id, v, platform, ch_text, ch_rec)}, 200


def update_version(project_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_edit(project_id, username):
        return {"error": "无权限"}, 403

    vid = (data.get("id") or "").strip()
    if not vid:
        return {"error": "缺少版本 ID"}, 400

    versions = versions_repo.list_versions(project_id)
    idx = next((i for i, x in enumerate(versions) if (x.get("id") or "") == vid), -1)
    if idx < 0:
        return {"error": "版本不存在"}, 404

    current_row = versions[idx]
    edit_scope = _normalize_edit_scope(data.get("edit_scope"))

    if edit_scope != "version_group":
        offending = [key for key in VC_PIPELINE_PROTECTED_KEYS if key in data and data.get(key) not in (None, "")]
        if "pipeline" in data and isinstance(data.get("pipeline"), dict) and not data.get("pipeline"):
            offending = [k for k in offending if k != "pipeline"]
        if offending:
            return {
                "error": "构建管线与 Bootstrap 字段只能在版本组层级编辑（edit_scope=version_group）。"
                          "请前往「版本组 - 配置管线」修改后回到这里。",
                "blocked_fields": sorted(offending),
            }, 400

    stage = (data.get("stage") or current_row.get("stage") or "dev").strip() or "dev"
    platform = (data.get("platform") or current_row.get("platform") or "").strip().lower()
    if platform not in ("android", "ios"):
        platform = "ios" if str(data.get("apk_path") or current_row.get("apk_path") or "").lower().endswith(".ipa") else "android"
    if stage not in [s[0] for s in VERSION_STAGES]:
        stage = current_row.get("stage") or "dev"

    update_payload = {
        "channel": _normalize_channel_storage_value(project_id, data.get("channel") or current_row.get("channel") or "dev") or "dev",
        "stage": stage,
        "platform": platform,
        "version_status": _normalize_version_status(data.get("version_status") or current_row.get("version_status") or "active"),
        "version_name": (data.get("version_name") or current_row.get("version_name") or "").strip(),
        "version_code": (data.get("version_code") or current_row.get("version_code") or "").strip(),
        "version_mode": (data.get("version_mode") or current_row.get("version_mode") or "general").strip(),
        "apk_path": (data.get("apk_path") or current_row.get("apk_path") or "").strip(),
        "resource_path": (data.get("resource_path") or current_row.get("resource_path") or "").strip(),
        "config_path": (data.get("config_path") or current_row.get("config_path") or "").strip(),
        "jenkins_job_id": (data.get("jenkins_job_id") or current_row.get("jenkins_job_id") or "").strip(),
        "jenkins_instance_id": (data.get("jenkins_instance_id") or current_row.get("jenkins_instance_id") or "").strip(),
        "notes": (data.get("notes") or current_row.get("notes") or "").strip(),
        "updated_at": datetime.now().isoformat(),
    }
    update_payload.update(_resolve_runtime_compat_fields(data, current_row))
    if edit_scope == "version_group":
        update_payload["version_code"] = (current_row.get("version_code") or "").strip()
    pipeline = data.get("pipeline")
    if isinstance(pipeline, dict):
        update_payload["pipeline"] = _merge_version_pipeline(current_row.get("pipeline"), pipeline)
    update_payload.update(_clean_version_platform_fields(data, platform, current_row))
    update_payload.update(_derive_runtime_paths(update_payload, project_id=project_id))
    update_payload = _enrich_version_scope_fields(project_id, update_payload)
    if not (update_payload.get("apk_path") or "").strip() and (update_payload.get("version_code") or "").strip():
        try:
            from services.apk_artifact_service import default_version_apk_rel_path

            update_payload["apk_path"] = default_version_apk_rel_path(project_id, update_payload)
        except Exception:
            pass
    validation_error = _validate_version_payload(platform, update_payload)
    if validation_error:
        return {"error": validation_error}, 400

    dup = _duplicate_version_code_in_group(
        versions,
        update_payload.get("version_name"),
        update_payload.get("version_code"),
        project_id,
        update_payload.get("channel"),
        platform,
        normalize_release_env_key(
            update_payload.get("env_key") or stage_to_env_key(update_payload.get("stage") or ""),
            project_id=project_id,
        ),
        exclude_id=vid,
    )
    if dup:
        return {
            "error": "版本 %s 下已存在相同的 Version Code「%s」，无法保存"
            % (update_payload.get("version_name") or "-", update_payload.get("version_code") or ""),
        }, 400

    old_status = _normalize_version_status(current_row.get("version_status") or "active")
    versions[idx].update(update_payload)
    for legacy_field in ("deprecated", "status", "commercial_release", "jenkins_params"):
        versions[idx].pop(legacy_field, None)
    if edit_scope == "version_group":
        vn = str(update_payload.get("version_name") or current_row.get("version_name") or "").strip()
        row_ek = normalize_release_env_key(
            update_payload.get("env_key") or stage_to_env_key(update_payload.get("stage") or ""),
            project_id=project_id,
        )
        row_pk = _normalize_group_platform(update_payload.get("platform") or current_row.get("platform") or "")
        template_fields = _extract_group_template_fields(update_payload)
        pipeline_for_group = update_payload.get("pipeline") if isinstance(update_payload.get("pipeline"), dict) else None
        if pipeline_for_group is None:
            existing_meta = _get_group_meta(project_id, vn, row_ek, row_pk)
            pipeline_for_group = existing_meta.get("pipeline_template") if isinstance(existing_meta, dict) else {}
            if not isinstance(pipeline_for_group, dict):
                pipeline_for_group = {}
        if pipeline_for_group or template_fields:
            _save_pipeline_template_to_meta(
                project_id,
                vn,
                row_ek,
                row_pk,
                username,
                pipeline_for_group,
                template_fields,
            )
            _propagate_pipeline_to_group_scope(
                versions,
                project_id,
                vn,
                row_ek,
                row_pk,
                pipeline_for_group,
                template_fields,
                update_payload["updated_at"],
            )
    versions_repo.save_versions(project_id, versions)

    ch_text = (data.get("changelog") or "").strip()
    ch_rec = bool(data.get("changelog_recommended"))
    vkey = "version:" + project_id + ":" + vid
    versions_repo.save_changelog_item(vkey, {"text": ch_text, "recommended": ch_rec} if (ch_text or ch_rec) else None)

    versions_repo.audit("update_project_version", "%s %s scope=%s" % (project_id, vid, edit_scope))
    new_status = _normalize_version_status(versions[idx].get("version_status") or "active")
    for tag in _build_status_audit_tags(old_status, new_status):
        versions_repo.audit("update_project_version_status", "%s %s %s" % (project_id, vid, tag))
    row = versions[idx]
    labels = _version_row_labels(row.get("channel"), row.get("stage"))
    v_out = {
        **row,
        **labels,
        "channel": labels.get("channel_key") or row.get("channel"),
        "channel_id": row.get("channel"),
        "platform_label": versions_repo.platform_label(platform),
        "version_status": _normalize_version_status(row.get("version_status") or "active"),
        "version_status_label": VERSION_STATUS_MAP.get(_normalize_version_status(row.get("version_status") or "active"), "有效"),
        "apk_status": "found" if versions_repo.has_apk(project_id, row) else "not_found",
        "download_count": versions_repo.version_download_count(project_id, row),
        "recommended": versions_repo.is_recommended(project_id, row),
        "changelog_text": ch_text,
        "changelog_recommended": ch_rec,
    }
    return {"version": v_out}, 200


def delete_version(project_id: str, version_id: str, username: str) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_edit(project_id, username):
        return {"error": "无权限"}, 403

    if versions_repo.approval_required_for_delete():
        if not versions_repo.has_approved_delete(project_id, version_id):
            return {"error": "删除版本需先提交审批并通过。请至 审批管理 发起「删除版本」申请，目标 ID 填写：%s:%s" % (project_id, version_id)}, 403

    versions = versions_repo.list_versions(project_id)
    versions = [x for x in versions if (x.get("id") or "") != version_id]
    versions_repo.save_versions(project_id, versions)
    versions_repo.audit("delete_project_version", "%s %s" % (project_id, version_id))
    return {"success": True}, 200


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
