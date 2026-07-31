"""Version module — version CRUD."""

from __future__ import annotations

from services.admin.version_constants import VERSION_STAGES, VERSION_STATUSES, VERSION_STATUS_MAP, VC_PIPELINE_PROTECTED_KEYS
from services.admin.version_row_helpers import (
    _normalize_channel_storage_value,
    _normalize_version_status,
    _normalize_edit_scope,
    _build_status_audit_tags,
    _clean_version_platform_fields,
    _validate_version_payload,
    _enrich_version_scope_fields,
    _resolve_runtime_compat_fields,
    _duplicate_version_code_in_group,
    _format_version_output,
    _version_row_labels,
)
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

