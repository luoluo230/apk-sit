"""Version module — runtime preview and effective pipeline."""

from __future__ import annotations

from services.admin.version_row_helpers import _resolve_runtime_compat_fields, _enrich_version_scope_fields

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

