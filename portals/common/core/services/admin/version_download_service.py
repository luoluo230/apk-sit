"""Version module — list, stats, downloads."""

from __future__ import annotations

from services.admin.version_constants import VERSION_STATUS_MAP
from services.admin.version_row_helpers import _version_row_labels, _normalize_version_status, _enrich_version_scope_fields

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

