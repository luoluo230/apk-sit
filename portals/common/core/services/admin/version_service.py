"""Version API service."""

from __future__ import annotations

import copy
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from repositories.admin import versions_repo
from services.admin.version_domain import normalize_version_status, normalize_edit_scope, build_status_audit_tags
from services.commercial_release_plan import (
    build_runtime_resolve_paths,
    normalize_release_channel,
    normalize_release_environment,
)

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
    return {
        "min_client_version": min_client,
        "max_client_version": max_client,
        "rollout_percentage": _normalize_rollout_percentage(rollout_raw),
        "is_revoked": bool(is_revoked),
    }


def _version_row_labels(channel_id: str, stage_id: str) -> dict[str, str]:
    from models.data import channels_db

    ch_map = {
        (c.get("id") or "").strip(): (c.get("name") or c.get("id") or "").strip()
        for c in (channels_db if isinstance(channels_db, list) else [])
        if (c.get("id") or "").strip()
    }
    cid = (channel_id or "").strip()
    sid = (stage_id or "dev").strip() or "dev"
    return {
        "channel_label": ch_map.get(cid, cid or "-"),
        "stage_label": STAGE_LABEL_MAP.get(sid, sid),
    }


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
        if apk_path and not apk_path.lower().endswith(".apk"):
            return "Android 版本的安装包路径必须以 .apk 结尾"
        if package_name and not re.match(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$", package_name):
            return "Android 包名格式不正确"
        if min_sdk and not re.match(r"^\d{1,2}$", min_sdk):
            return "最低 Android SDK 应为数字"
    return None


def _derive_runtime_paths(version_row: Dict[str, Any]) -> Dict[str, str]:
    stage_id = str(version_row.get("stage") or "dev").strip()
    channel_raw = str(version_row.get("channel") or "common").strip()
    platform_raw = str(version_row.get("platform") or "android").strip().lower()
    version_name = str(version_row.get("version_name") or "").strip()
    version_code = str(version_row.get("version_code") or "").strip()
    release_env = normalize_release_environment("", stage_id)
    release_channel = normalize_release_channel(channel_raw)
    release_platform = "ios" if platform_raw == "ios" else "android"
    runtime_paths = build_runtime_resolve_paths(
        resource_server_url=str(version_row.get("resource_server_url") or ""),
        release_environment=release_env,
        release_channel=release_channel,
        release_platform=release_platform,
        release_version=version_name,
        version_code=version_code,
    )
    return {
        "resource_path": runtime_paths.get("resource_relative_path") or "",
        "config_path": runtime_paths.get("config_relative_path") or "",
    }


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
    return {"versions": versions_repo.list_versions(project_id)}, 200


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


def get_apk_download_info(project_id: str, version_id: str, username: str) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403
    versions = versions_repo.list_versions(project_id)
    v = next((x for x in versions if (x.get("id") or "") == version_id), None)
    if not v:
        return {"error": "版本不存在"}, 404
    from services.apk_artifact_service import build_download_info, version_apk_build_enabled

    info = build_download_info(project_id, v)
    if not info:
        return {"error": "暂无可下载的安装包", "available": False}, 404
    info["apk_build_enabled"] = version_apk_build_enabled(v)
    return info, 200


def _duplicate_version_code_in_group(
    versions: list,
    version_name: str,
    version_code: str,
    exclude_id: str | None = None,
):
    vn = (version_name or "").strip()
    vc = str(version_code or "").strip()
    if not vn or not vc:
        return None
    for row in versions:
        rid = (row.get("id") or "").strip()
        if exclude_id and rid == exclude_id:
            continue
        if (row.get("version_name") or "").strip() == vn and str(row.get("version_code") or "").strip() == vc:
            return row
    return None


def create_version(project_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not versions_repo.has_project(project_id) or not versions_repo.can_edit(project_id, username):
        return {"error": "无权限"}, 403

    vid = str(uuid.uuid4())[:8]
    stage = (data.get("stage") or "dev").strip() or "dev"
    platform = (data.get("platform") or "").strip().lower()
    if platform not in ("android", "ios"):
        platform = "ios" if str(data.get("apk_path") or "").lower().endswith(".ipa") else "android"
    if stage not in [s[0] for s in VERSION_STAGES]:
        stage = "dev"

    v = {
        "id": vid,
        "channel": (data.get("channel") or "dev").strip() or "dev",
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
        v["pipeline"] = _sync_pipeline_release_fields(pipeline)
    v.update(_clean_version_platform_fields(data, platform))
    v.update(_resolve_runtime_compat_fields(data))
    v.update(_derive_runtime_paths(v))
    validation_error = _validate_version_payload(platform, v)
    if validation_error:
        return {"error": validation_error}, 400

    versions = versions_repo.list_versions(project_id)
    dup = _duplicate_version_code_in_group(versions, v.get("version_name"), v.get("version_code"))
    if dup:
        return {
            "error": "版本 %s 下已存在相同的 Version Code「%s」，请使用其他编号"
            % (v.get("version_name") or "-", v.get("version_code") or ""),
        }, 400
    versions.append(v)
    versions_repo.save_versions(project_id, versions)

    ch_text = (data.get("changelog") or "").strip()
    ch_rec = bool(data.get("changelog_recommended"))
    if ch_text or ch_rec:
        versions_repo.save_changelog_item("version:" + project_id + ":" + vid, {"text": ch_text, "recommended": ch_rec})

    versions_repo.audit("create_project_version", "%s %s" % (project_id, vid))
    labels = _version_row_labels(v.get("channel"), v.get("stage"))
    v_out = {
        **v,
        **labels,
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
    return {"version": v_out}, 200


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
    stage = (data.get("stage") or current_row.get("stage") or "dev").strip() or "dev"
    platform = (data.get("platform") or current_row.get("platform") or "").strip().lower()
    if platform not in ("android", "ios"):
        platform = "ios" if str(data.get("apk_path") or current_row.get("apk_path") or "").lower().endswith(".ipa") else "android"
    if stage not in [s[0] for s in VERSION_STAGES]:
        stage = current_row.get("stage") or "dev"

    update_payload = {
        "channel": (data.get("channel") or current_row.get("channel") or "dev").strip() or "dev",
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
        "notes": (data.get("notes") or current_row.get("notes") or "").strip(),
        "updated_at": datetime.now().isoformat(),
    }
    update_payload.update(_resolve_runtime_compat_fields(data, current_row))
    if edit_scope == "version_group":
        update_payload["version_code"] = (current_row.get("version_code") or "").strip()
    pipeline = data.get("pipeline")
    if isinstance(pipeline, dict):
        update_payload["pipeline"] = _sync_pipeline_release_fields(pipeline)
    update_payload.update(_clean_version_platform_fields(data, platform, current_row))
    update_payload.update(_derive_runtime_paths(update_payload))
    validation_error = _validate_version_payload(platform, update_payload)
    if validation_error:
        return {"error": validation_error}, 400

    dup = _duplicate_version_code_in_group(
        versions,
        update_payload.get("version_name"),
        update_payload.get("version_code"),
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
    if edit_scope == "version_group" and isinstance(update_payload.get("pipeline"), dict):
        _propagate_pipeline_to_version_group(
            versions,
            versions[idx],
            update_payload["pipeline"],
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
    v_out = {
        **row,
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
