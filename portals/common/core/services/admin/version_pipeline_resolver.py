# -*- coding: utf-8 -*-
"""Effective pipeline, Jenkins, iOS signing, and client URL resolution."""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from repositories.admin import versions_repo
from services.admin.version_group_repo import (
    _ensure_version_group_meta,
    _find_group_meta_index,
    _get_group_meta,
    _group_env_key,
    _group_platform,
    _load_version_groups_meta,
    _normalize_group_platform,
    _save_version_groups_meta,
    _version_matches_group_scope,
    _version_row_env_key,
    _version_row_platform,
)
from services.release.env_registry import normalize_release_env_key

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


def resolve_effective_wx_minigame(project_id: str, version_row: Dict[str, Any]) -> dict:
    from services.build.platform_signing_service import normalize_wx_minigame_config

    if not isinstance(version_row, dict):
        return normalize_wx_minigame_config({})
    version_name = str(version_row.get("version_name") or "").strip()
    if not version_name:
        return normalize_wx_minigame_config({})
    env_key = _version_row_env_key(version_row, project_id)
    platform = _version_row_platform(version_row)
    meta = _get_group_meta(project_id, version_name, env_key, platform)
    raw = meta.get("wx_minigame") if isinstance(meta, dict) else {}
    return normalize_wx_minigame_config(raw if isinstance(raw, dict) else {})


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


# Re-export merge helpers so existing imports from this module keep working.
from services.admin.version_pipeline_merge import (  # noqa: E402
    _deep_merge_dict,
    _derive_runtime_paths,
    _merge_version_pipeline,
    _sync_pipeline_release_fields,
)
