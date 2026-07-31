"""Version module — row normalization and validation."""

from __future__ import annotations

from services.admin.version_constants import VERSION_STAGES, VERSION_STATUSES, VERSION_STATUS_MAP, STAGE_LABEL_MAP

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

