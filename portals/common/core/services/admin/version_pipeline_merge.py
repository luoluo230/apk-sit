# -*- coding: utf-8 -*-
"""Pipeline merge / sync helpers (split from version_pipeline_resolver for ≤400 gate)."""

from __future__ import annotations

from typing import Any, Dict

from services.commercial_release_plan import (
    build_runtime_resolve_paths,
    normalize_release_channel,
    normalize_release_environment,
    normalize_release_platform,
)


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
