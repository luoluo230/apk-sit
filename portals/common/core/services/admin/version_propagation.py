"""Version module — pipeline propagation helpers."""

from __future__ import annotations

from services.admin.version_row_helpers import _enrich_version_scope_fields

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

