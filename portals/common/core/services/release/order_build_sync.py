# -*- coding: utf-8 -*-
"""Release order submodule."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from models.data import get_channel_by_id, get_channels_for_project, project_versions_db, projects_db
from data.delivery_scope import get_channels_for_env, get_platform_defs_for_env, is_channel_allowed_for_env
from data.platforms import get_platform_defs_for_project, is_platform_enabled_for_project, is_valid_platform_id
from models.db import _db_lock, _get_conn, get_cursor, init_db
from services.release.bundle_service import find_active_bundle, list_publishable_bundles, run_scope_precheck
from services.release.env_registry import list_project_env_keys, normalize_release_env_key, project_env_label
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.scope_resolver import resolve_network_profile, resolve_scope, resolve_topology_binding_for_scope
from services.release.topology_binding_service import resolve_topology_binding, upsert_topology_binding
from services.release.storage import find_manifest
from services.release.order_constants import EDITABLE_PLAN_FIELDS, PUBLISHABLE_STATUSES, TERMINAL_STATUSES
from services.release.order_diagnostics import _build_pipeline_snapshot, _pipeline_build_ready, summarize_order_diagnostic_issues
from services.release.order_helpers import (
    _artifact_rows,
    _bundle_id,
    _channel_name,
    _decode,
    _event,
    _find_version,
    _json,
    _now_iso,
    _order_id,
)


def _order_crud():
    import services.release.order_crud as mod
    return mod

def _order_publish_flow():
    import services.release.order_publish_flow as mod
    return mod
def quick_build_version(project_id: str, version_id: str, actor: str, *, force: bool = False) -> Dict[str, Any]:
    """Ensure a draft release order and trigger Jenkins (Dev fast path).

    Returns the updated order. If artifacts are already ready, returns the draft
    without re-triggering unless ``force=True``.
    """
    draft = _order_crud().ensure_draft_release_order(
        project_id,
        version_id,
        actor,
        reason=f"快速构建 - {actor}",
    )
    status = str(draft.get("status") or "")
    order_id = str(draft.get("release_order_id") or "")
    if status == "building":
        return _order_crud().get_release_order(project_id, order_id) or draft
    if status in TERMINAL_STATUSES:
        raise ValueError("当前发布单已结束，请从版本代码发起新的交付尝试")
    if status == "artifacts_ready" and not force:
        return draft
    if status == "artifacts_ready" and force:
        return request_build(project_id, order_id, actor)
    env_key = normalize_release_env_key(draft.get("env_key") or "development", project_id=project_id)
    from services.release.release_policy_service import (
        FORM_DEPTH_MINIMAL,
        get_env_release_policy,
        get_required_plan_fields,
    )

    policy = get_env_release_policy(project_id, env_key)
    if str(policy.get("form_depth") or "") != FORM_DEPTH_MINIMAL:
        payload = dict(draft.get("payload") or {})
        missing: List[str] = []
        for field in get_required_plan_fields(project_id, env_key):
            if field in {"reason", "owner"}:
                val = draft.get("reason") if field == "reason" else payload.get("owner") or draft.get("created_by")
            else:
                val = payload.get(field)
            if not str(val or "").strip():
                missing.append(field)
        if missing:
            raise ValueError("请先完善发布计划后再触发构建")
    return request_build(project_id, order_id, actor)


def quick_publish_delivery(
    project_id: str,
    env_key: str,
    channel_id: str,
    platform: str,
    version_id: str,
    actor: str,
    *,
    skip_build: bool = False,
    force_build: bool = False,
    auto_verify: bool = True,
) -> Dict[str, Any]:
    """Dev/prod unified shortcut: ensure order → (optional) build → precheck → publish → verify.

    Returns early with ``phase`` when waiting on build or production approval.
    """
    vid = str(version_id or "").strip()
    plat = str(platform or "").strip().lower()
    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = str(channel_id or "").strip()
    if not vid or not plat or not cid:
        raise ValueError("env_key、channel_id、platform、version_id 必填")
    order = _order_crud().ensure_draft_release_order(project_id, vid, actor, reason="一键发版")
    order_id = str(order.get("release_order_id") or "")
    status = str(order.get("status") or "")
    if status == "building":
        return {"phase": "building", "release_order_id": order_id, "order": order}
    if status == "build_failed":
        if skip_build:
            raise ValueError("构建已失败，请重新触发构建")
        order = request_build(project_id, order_id, actor)
        return {"phase": "building", "release_order_id": order_id, "order": order}
    if status in {"draft", "precheck_failed"} and not skip_build:
        order = quick_build_version(project_id, vid, actor, force=force_build)
        status = str(order.get("status") or "")
        order_id = str(order.get("release_order_id") or order_id)
        if status == "building":
            return {"phase": "building", "release_order_id": order_id, "order": order}
    if status not in {"artifacts_ready", "ready", "approved", "awaiting_approval", "precheck_failed", "published"}:
        if status == "draft" and skip_build:
            raise ValueError("产物未就绪，无法跳过构建直接发布")
    order = _order_crud().get_release_order(project_id, order_id) or order
    status = str(order.get("status") or "")
    if status in {"draft", "artifacts_ready", "precheck_failed"}:
        from services.release.release_policy_service import should_auto_ensure_runtime

        order = _order_publish_flow().precheck_release_order(
            project_id,
            order_id,
            actor,
            auto_ensure_runtime=should_auto_ensure_runtime(project_id, ek),
        )
        status = str(order.get("status") or "")
    if status == "awaiting_approval":
        return {"phase": "awaiting_approval", "release_order_id": order_id, "order": order}
    if status in {"ready", "approved"}:
        order = _order_publish_flow().publish_release_order(project_id, order_id, actor)
        status = str(order.get("status") or "")
    if status == "published" and auto_verify:
        order = _order_publish_flow().verify_release_order(project_id, order_id, actor, ok=True)
    return {"phase": str(order.get("status") or status), "release_order_id": order_id, "order": order}

def request_build(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = _order_crud().get_release_order(project_id, order_id, include_details=False)
    if not order:
        raise ValueError("发布单不存在")
    if order.get("status") in TERMINAL_STATUSES:
        raise ValueError("当前发布单不可重新构建")
    version = _find_version(project_id, order["version_id"], order["version_code"])
    platform = str(order.get("platform") or version.get("platform") or "android").strip().lower()
    from services.build.build_node_service import assert_build_ready

    assert_build_ready(platform)
    if platform == "ios":
        from services.admin.version_service import resolve_effective_ios_signing
        from services.build.platform_signing_service import assess_ios_signing_setup, validate_ios_signing_for_build

        signing = resolve_effective_ios_signing(project_id, version)
        release_env = str(order.get("env_key") or version.get("env_key") or "")
        assessment = assess_ios_signing_setup(
            signing,
            project_id=project_id,
            release_environment=release_env,
        )
        if not assessment.get("ready"):
            err = validate_ios_signing_for_build(signing)
            guide = "请前往版本组「配置管线 → 安装包 → iOS 签名」完成引导步骤并校验通过。"
            raise ValueError(f"{err or 'iOS 签名配置未就绪'}。{guide}")
    plan = dict(order.get("payload") or {})
    from services.admin.version_service import (
        resolve_effective_pipeline,
        resolve_effective_jenkins,
    )

    effective_pipeline = resolve_effective_pipeline(project_id, version)
    if not effective_pipeline:
        raise ValueError("版本组管线模板尚未配置；请前往版本组「配置管线」完成 Jenkins 实例、Job 与四步流水线后再触发构建。")
    version_for_build = dict(version)
    version_for_build["pipeline"] = effective_pipeline
    from services.commercial_release_plan import plan_defaults_from_pipeline, plan_to_jenkins_params

    plan_defaults = plan_defaults_from_pipeline(version_for_build, project_id=project_id)
    plan_filepath = str(plan.get("release_plan_file") or "release_order_inline.json")
    params, _ = plan_to_jenkins_params(plan_defaults, plan_filepath, version_for_build, project_id=project_id)
    if not params:
        raise ValueError("无法从版本组管线推导 Jenkins 构建参数；请检查管线配置是否完整。")
    jenkins_binding = resolve_effective_jenkins(project_id, version_for_build)
    instance_id = jenkins_binding.get("jenkins_instance_id") or ""
    if not instance_id:
        raise ValueError("当前版本组未配置 Jenkins 实例。请在「配置管线」选择 Jenkins 实例后再触发构建。")
    resolved_job = jenkins_binding.get("jenkins_job_id") or ""
    params["VERSION_NAME"] = str(order["version_name"])
    params["VERSION_CODE"] = str(order["version_code"])
    params["CHANNEL"] = str(order["channel_name"])
    from services import jenkins as jenkins_svc
    from services import jenkins_manager as jm
    ok, prep_error = jm.prepare_instance_for_project_build(
        instance_id,
        project_id,
        git_branch=str(params.get("GIT_BRANCH") or ""),
    )
    if not ok:
        raise ValueError(prep_error or "同步项目构建配置到 Jenkins 失败")
    base_url = jm.get_jenkins_url_for_instance(instance_id=instance_id)
    builds_dir = jm.get_builds_dir_for_instance(instance_id=instance_id)
    success, build_number, error = jenkins_svc.trigger_build(
        params,
        base_url=base_url,
        builds_dir=builds_dir,
        instance_id=instance_id,
    )
    if not success:
        raise ValueError(error or "触发 Jenkins 构建失败")
    from models.data import record_build_version
    record_build_version(instance_id, int(build_number), order["version_id"], project_id)
    payload = dict(order.get("payload") or {})
    payload.update({
        "build_job_id": str(build_number),
        "jenkins_instance_id": instance_id,
        "jenkins_job": resolved_job,
        "jenkins_params": params,
        "pipeline_source": "version_group",
    })
    now = _now_iso()
    from services.release.order_state_machine import assert_transition

    assert_transition(str(order.get("status") or "draft"), "building")
    with get_cursor() as cur:
        cur.execute(
            "UPDATE release_orders SET status='building', payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (_json(payload), now, project_id, order_id),
        )
        _event(
            cur,
            order_id,
            "build_requested",
            actor,
            order["status"],
            "building",
            {"build_number": build_number, "jenkins_instance_id": instance_id},
        )
    return _order_crud().get_release_order(project_id, order_id)


def find_release_order_for_build(
    instance_id: str,
    build_number: int | str,
    *,
    project_id: str = "",
) -> Optional[Tuple[str, str]]:
    """Resolve (project_id, release_order_id) for a Jenkins build webhook/poll."""
    iid = str(instance_id or "").strip()
    bn = str(build_number or "").strip()
    if not iid or not bn:
        return None
    init_db()
    sql = "SELECT project_id, release_order_id, payload FROM release_orders WHERE status='building'"
    params: List[str] = []
    if project_id:
        sql += " AND project_id=?"
        params.append(str(project_id).strip())
    with _db_lock:
        rows = _get_conn().execute(sql, params).fetchall()
    for row in rows:
        payload = _decode(row["payload"], {}) or {}
        if str(payload.get("jenkins_instance_id") or "").strip() != iid:
            continue
        if str(payload.get("build_job_id") or "").strip() != bn:
            continue
        return (str(row["project_id"] or ""), str(row["release_order_id"] or ""))
    return None


def sync_release_order_build_status(project_id: str, order_id: str, *, actor: str = "system") -> Dict[str, Any]:
    """When Jenkins build finishes, advance building → artifacts_ready and refresh artifacts."""
    init_db()
    with _db_lock:
        row = _get_conn().execute(
            "SELECT * FROM release_orders WHERE project_id=? AND release_order_id=?",
            (project_id, order_id),
        ).fetchone()
    if not row or str(row["status"] or "") != "building":
        return _order_crud()._order_from_row(row, include_details=False) if row else {}
    order = _order_crud()._order_from_row(row, include_details=False)
    payload = dict(order.get("payload") or {})
    build_number = str(payload.get("build_job_id") or "").strip()
    instance_id = str(payload.get("jenkins_instance_id") or "").strip()
    if not build_number or not instance_id:
        return order
    try:
        from services import jenkins as jenkins_svc
        from services import jenkins_manager as jm

        base_url = jm.get_jenkins_url_for_instance(instance_id=instance_id)
        builds_dir = jm.get_builds_dir_for_instance(instance_id=instance_id)
        st = jenkins_svc.get_build_status(
            int(build_number),
            base_url=base_url,
            builds_dir=builds_dir,
            instance_id=instance_id,
        )
    except Exception:
        return order
    if st.get("building"):
        return order
    result = str(st.get("status") or "").upper()
    if result != "SUCCESS":
        fail_status = "build_failed"
        fail_payload = {
            "build_number": build_number,
            "jenkins_result": result,
            "failure_summary": str(st.get("error") or result or "BUILD_FAILED"),
            "retry_hint": "检查 Jenkins 控制台与 commercial_android_pipeline 日志；OSS 上传失败可重试构建",
        }
        from services.release.order_state_machine import assert_transition

        assert_transition("building", fail_status)
        now = _now_iso()
        with get_cursor() as cur:
            cur.execute(
                "UPDATE release_orders SET status=?, updated_at=? WHERE project_id=? AND release_order_id=?",
                (fail_status, now, project_id, order_id),
            )
            _event(cur, order_id, "build_failed", actor, "building", fail_status, fail_payload)
        return _order_crud().get_release_order(project_id, order_id, include_details=False)
    try:
        from services.apk_artifact_service import finalize_apk_from_jenkins_build

        finalize_apk_from_jenkins_build(instance_id, int(build_number))
    except Exception as exc:
        fail_status = "build_failed"
        fail_payload = {
            "build_number": build_number,
            "jenkins_result": "SUCCESS",
            "failure_summary": f"构建产物登记失败: {exc}",
            "finalize_error": str(exc)[:500],
            "retry_hint": "请检查 Jenkins 归档脚本与 APK 路径，修复后重新触发构建",
        }
        from services.release.order_state_machine import assert_transition

        assert_transition("building", fail_status)
        now = _now_iso()
        with get_cursor() as cur:
            cur.execute(
                "UPDATE release_orders SET status=?, updated_at=? WHERE project_id=? AND release_order_id=?",
                (fail_status, now, project_id, order_id),
            )
            _event(cur, order_id, "build_finalize_failed", actor, "building", fail_status, fail_payload)
        return _order_crud().get_release_order(project_id, order_id, include_details=False)
    version = _find_version(project_id, order["version_id"], order["version_code"])
    if not version:
        return order
    artifacts = _artifact_rows(version)
    from services.release.order_state_machine import assert_transition

    assert_transition("building", "artifacts_ready")
    now = _now_iso()
    with get_cursor() as cur:
        for artifact_type, url, path in artifacts:
            cur.execute(
                """
                UPDATE release_order_artifacts
                SET artifact_url=?, artifact_path=?, status=?, updated_at=?
                WHERE release_order_id=? AND artifact_type=?
                """,
                (
                    url,
                    path,
                    "registered" if url or path else "missing",
                    now,
                    order_id,
                    artifact_type,
                ),
            )
        cur.execute(
            "UPDATE release_orders SET status='artifacts_ready', updated_at=? WHERE project_id=? AND release_order_id=?",
            (now, project_id, order_id),
        )
        _event(cur, order_id, "build_completed", actor, "building", "artifacts_ready", {"build_number": build_number})
    return _order_crud().get_release_order(project_id, order_id, include_details=False)


def sync_building_release_orders(project_id: str = "", *, actor: str = "system") -> List[Dict[str, Any]]:
    """Poll Jenkins for all in-flight release-order builds (proactive sync)."""
    init_db()
    sql = "SELECT project_id, release_order_id FROM release_orders WHERE status='building'"
    params: List[str] = []
    if project_id:
        sql += " AND project_id=?"
        params.append(str(project_id).strip())
    with _db_lock:
        rows = _get_conn().execute(sql, params).fetchall()
    updated: List[Dict[str, Any]] = []
    for row in rows:
        pid = str(row["project_id"] or "")
        oid = str(row["release_order_id"] or "")
        if not pid or not oid:
            continue
        synced = sync_release_order_build_status(pid, oid, actor=actor)
        if synced:
            updated.append(synced)
    return updated


def _scope_query_suffix(order: Dict[str, Any]) -> str:
    from urllib.parse import urlencode

    params = {
        key: str(order.get(key) or "").strip()
        for key in ("env_key", "channel_id", "platform", "version_id", "version_name", "version_code", "release_order_id")
        if str(order.get(key) or "").strip()
    }
    qs = urlencode(params)
    return f"?{qs}" if qs else ""


def _channel_journey_href(project_id: str, order: Dict[str, Any], *, phase: str) -> str:
    from urllib.parse import urlencode

    env_key = str(order.get("env_key") or "development").strip()
    channel_id = str(order.get("channel_id") or "").strip()
    platform = str(order.get("platform") or "android").strip().lower()
    version_id = str(order.get("version_id") or "").strip()
    qs = urlencode({k: v for k, v in {
        "env_key": env_key,
        "channel_id": channel_id,
        "version_id": version_id,
        "platform": platform,
        "action": "edit_release",
    }.items() if v})
    return f"/admin/projects/{project_id}/versions?{qs}"


def _order_needs_jenkins_build(order: Dict[str, Any]) -> bool:
    for row in order.get("artifacts") or []:
        status = str(row.get("status") or "").lower()
        if status in {"missing", "unreachable", "invalid"}:
            return True
        if not str(row.get("artifact_path") or row.get("artifact_url") or "").strip():
            artifact_type = str(row.get("artifact_type") or "").lower()
            if artifact_type in {"code", "apk", "resource", "config"}:
                return True
    return False


def resolve_release_order_next_action(project_id: str, order_id: str) -> Dict[str, Any]:
    order = _order_crud().get_release_order(project_id, order_id, include_details=True)
    if not order:
        raise ValueError("发布单不存在")
    status = str(order.get("status") or "")
    ctx = _scope_query_suffix(order)
    base = f"/admin/projects/{project_id}/release-orders/{order_id}"
    edit_href = f"{base}/edit{ctx}"
    build_history_href = (
        f"/admin/projects/{project_id}/build-history"
        f"?env_key={order.get('env_key')}&channel_id={order.get('channel_id')}"
        f"&platform={order.get('platform')}&version_id={order.get('version_id')}&scoped=1"
    )
    phase_map = {
        "draft": 0,
        "cancelled": 0,
        "building": 1,
        "artifacts_ready": 1,
        "prechecking": 2,
        "precheck_failed": 2,
        "ready": 2,
        "awaiting_approval": 2,
        "approved": 2,
        "publishing": 2,
        "published": 2,
        "verifying": 2,
        "verified": 2,
        "verify_failed": 2,
        "rolled_back": 2,
        "publish_failed": 2,
    }
    phase_index = phase_map.get(status, 0)
    more: List[Dict[str, Any]] = []
    terminal = status in TERMINAL_STATUSES or status in {"published", "verified", "cancelled"}

    def _primary(action: str, label: str, *, api_action: str = "", href: str = "", disabled: bool = False, reason: str = ""):
        return {
            "action": action,
            "label": label,
            "api_action": api_action,
            "href": href,
            "disabled": disabled,
            "reason": reason,
        }

    if status == "draft":
        primary = _primary(
            "build_journey",
            "下一步：打开版本管理",
            href=_channel_journey_href(project_id, order, phase="build"),
        )
        more.extend([
            {"action": "edit", "label": "编辑计划", "href": edit_href},
            {"action": "cancel", "label": "取消发布单", "api_action": "cancel"},
        ])
    elif status == "artifacts_ready":
        primary = _primary(
            "release_journey",
            "下一步：继续发版",
            href=_channel_journey_href(project_id, order, phase="release"),
        )
        more.extend([
            {"action": "build", "label": "重新构建", "api_action": "build"},
            {"action": "edit", "label": "编辑计划", "href": edit_href},
            {"action": "precheck", "label": "执行预检", "api_action": "precheck"},
            {"action": "cancel", "label": "取消发布单", "api_action": "cancel"},
        ])
    elif status == "building":
        primary = _primary("view_build", "下一步：查看构建日志", href=build_history_href)
        more.append({"action": "cancel", "label": "取消发布单", "api_action": "cancel"})
    elif status == "precheck_failed":
        pipeline_snapshot = _build_pipeline_snapshot(project_id, str(order.get("version_id") or ""), str(order.get("channel_id") or ""))
        if _order_needs_jenkins_build(order) and _pipeline_build_ready(pipeline_snapshot):
            primary = _primary("build", "下一步：触发构建", api_action="build")
        else:
            primary = _primary("edit", "下一步：编辑计划", href=edit_href)
        more.extend([
            {"action": "precheck", "label": "重新预检", "api_action": "precheck"},
            {"action": "cancel", "label": "取消发布单", "api_action": "cancel"},
        ])
    elif status in {"ready", "approved"}:
        primary = _primary(
            "release_journey",
            "下一步：继续发版",
            href=_channel_journey_href(project_id, order, phase="release"),
        )
        more.extend([
            {"action": "precheck", "label": "重新预检", "api_action": "precheck"},
            {"action": "cancel", "label": "取消发布单", "api_action": "cancel"},
        ])
    elif status == "awaiting_approval":
        primary = _primary("approve", "下一步：审批通过", api_action="approve")
        more.append({"action": "cancel", "label": "取消发布单", "api_action": "cancel"})
    elif status == "published":
        primary = _primary("verify", "下一步：执行验证", api_action="verify")
        more.append({"action": "rollback", "label": "回滚", "api_action": "rollback"})
    elif status == "verify_failed":
        primary = _primary("verify", "下一步：重新验证", api_action="verify")
        if order.get("bundle_id") and order.get("active_bundle_id") and order.get("bundle_id") != order.get("active_bundle_id"):
            more.append({"action": "rollback", "label": "回滚", "api_action": "rollback"})
    elif status == "verified":
        primary = _primary("view", "已完成", disabled=True, reason="发布与验证已完成")
        if order.get("bundle_id") and order.get("active_bundle_id") and order.get("bundle_id") != order.get("active_bundle_id"):
            more.append({"action": "rollback", "label": "回滚", "api_action": "rollback"})
    elif status == "prechecking":
        primary = _primary("wait", "预检进行中…", disabled=True, reason="请等待预检完成")
    elif status == "publishing":
        primary = _primary("wait", "发布执行中…", disabled=True, reason="请等待发布完成")
    elif status == "verifying":
        primary = _primary("wait", "验证进行中…", disabled=True, reason="请等待验证完成")
    elif status == "cancelled":
        primary = _primary("view", "已取消", disabled=True, reason="发布单已取消")
    elif status == "rolled_back":
        primary = _primary("view", "已回滚", disabled=True, reason="已回滚到上一 Bundle")
    else:
        primary = _primary("view", "查看详情", disabled=True)

    if status in {"draft", "artifacts_ready", "precheck_failed", "ready"} and not terminal:
        more.insert(0, {"action": "precheck", "label": "执行预检", "api_action": "precheck"})

    return {
        "release_order_id": order_id,
        "status": status,
        "phase_index": phase_index,
        "phases": ["准备", "构建", "发版"],
        "primary": primary,
        "more": [item for item in more if item.get("action") != primary.get("action")],
    }


def find_release_order_for_version(project_id: str, version_id: str) -> Optional[Dict[str, Any]]:
    """Latest non-terminal release order for a VersionCode (for hub/matrix actions)."""
    return _order_crud().find_release_order_for_version(project_id, version_id)


def resolve_delivery_actions(project_id: str, version_id: str) -> Dict[str, Any]:
    """BFF: primary/secondary actions for a VersionCode (versions hub + env matrix)."""
    from urllib.parse import urlencode
    from services.build.platform_capability import can_build, resolve_platform_capability
    from services.release.release_policy_service import (
        FORM_DEPTH_FULL,
        FORM_DEPTH_MINIMAL,
        assess_delivery_readiness,
        build_config_href,
        get_env_release_policy,
    )

    version = _find_version(project_id, version_id)
    if not version:
        raise ValueError("VersionCode 不存在")
    env_key = normalize_release_env_key(
        version.get("env_key") or version.get("stage") or "development",
        project_id=project_id,
    )
    ch_raw = str(version.get("channel_id") or version.get("channel") or "").strip()
    channel_id = resolve_channel_id(project_id, ch_raw) or ch_raw
    platform = str(version.get("platform") or "android").strip().lower()
    version_name = str(version.get("version_name") or "")
    version_code = str(version.get("version_code") or "")

    policy = get_env_release_policy(project_id, env_key)
    form_depth = str(policy.get("form_depth") or "")
    readiness = assess_delivery_readiness(project_id, version, env_key, channel_id, platform)
    pipeline_ready = bool(readiness.get("pipeline_ready"))
    artifact_ready = str(version.get("apk_status") or "") == "found"

    order = find_release_order_for_version(project_id, version_id) or _order_crud().find_draft_release_order(project_id, version_id)
    order_status = str(order.get("status") or "") if order else ""
    order_id = str(order.get("release_order_id") or "") if order else ""

    scope_params = {
        "env_key": env_key,
        "channel_id": channel_id,
        "platform": platform,
        "version_id": version_id,
        "version_name": version_name,
        "version_code": version_code,
    }
    if order_id:
        scope_params["release_order_id"] = order_id
    scope_qs = urlencode({k: v for k, v in scope_params.items() if v})

    pipeline_config_href = build_config_href(project_id, version)
    build_history_href = (
        f"/admin/projects/{project_id}/build-history?"
        f"{urlencode({'env_key': env_key, 'channel_id': channel_id, 'platform': platform, 'version_id': version_id, 'scoped': '1'})}"
    )
    detail_href = f"/admin/projects/{project_id}/release-orders/{order_id}?{scope_qs}" if order_id else ""
    edit_href = (
        f"/admin/projects/{project_id}/release-orders/{order_id}/edit?{scope_qs}"
        if order_id
        else f"/admin/projects/{project_id}/release-orders/start?{urlencode({**scope_params, 'intent': 'release'})}"
    )
    versions_href = f"/admin/projects/{project_id}/versions?{urlencode({'env_key': env_key, 'channel_id': channel_id, 'platform': platform})}"

    release_continue_statuses = {
        "artifacts_ready",
        "precheck_failed",
        "ready",
        "awaiting_approval",
        "approved",
        "published",
        "prechecking",
        "publishing",
        "verifying",
        "verify_failed",
        "publish_failed",
    }

    def _action(action: str, label: str, **extra: Any) -> Dict[str, Any]:
        row = {"action": action, "label": label}
        row.update({k: v for k, v in extra.items() if v is not None and v != ""})
        return row

    primary: Dict[str, Any]
    secondary: List[Dict[str, Any]] = []
    status_hint = ""

    if order_status == "building":
        primary = _action("view_build", "查看构建", href=detail_href or build_history_href)
        status_hint = "构建进行中 · 查看日志"
        secondary = [
            _action("build_history", "构建日志", href=build_history_href),
            _action("rebuild", "重新构建", api_action="rebuild", release_order_id=order_id, version_id=version_id),
        ]
    elif artifact_ready or order_status in release_continue_statuses:
        primary = _action(
            "continue_release",
            "继续发版",
            href=detail_href or f"/admin/projects/{project_id}/release-orders/start?{urlencode({**scope_params, 'intent': 'release'})}",
        )
        status_hint = "产物就绪 · 可继续发版"
        secondary = [
            _action("rebuild", "重新构建", api_action="rebuild", release_order_id=order_id, version_id=version_id),
            _action("build_history", "构建日志", href=build_history_href),
        ]
    elif not pipeline_ready:
        primary = _action("configure_pipeline", "配置管线", href=pipeline_config_href)
        status_hint = "管线未配置 · 先配置管线"
        secondary = [_action("versions", "版本代码", href=versions_href)]
    elif form_depth == FORM_DEPTH_FULL:
        primary = _action("edit_plan", "填写计划", href=edit_href)
        status_hint = "生产环境 · 请先填写发布计划"
        secondary = [_action("build_history", "构建产物", href=build_history_href)]
    elif form_depth == FORM_DEPTH_MINIMAL or pipeline_ready:
        if can_build(platform):
            primary = _action("trigger_build", "触发构建", api_action="quick_build", version_id=version_id)
            status_hint = "管线就绪 · 可触发构建"
        else:
            cap = resolve_platform_capability(platform)
            primary = _action(
                "configure_pipeline",
                "暂不支持构建",
                disabled=True,
                reason=f"平台 {cap.get('name') or platform} 未接入构建网格",
            )
            status_hint = primary.get("reason") or "平台未接入构建网格"
        secondary = [
            _action("build_history", "构建产物", href=build_history_href),
            _action("versions", "版本代码", href=versions_href),
        ]
    else:
        primary = _action("edit_plan", "填写计划", href=edit_href)
        status_hint = "请先填写发布计划"
        secondary = [_action("build_history", "构建产物", href=build_history_href)]

    return {
        "version_id": version_id,
        "release_order_id": order_id,
        "release_order_status": order_status,
        "pipeline_ready": pipeline_ready,
        "artifact_ready": artifact_ready,
        "form_depth": form_depth,
        "status_hint": status_hint,
        "primary": primary,
        "secondary": secondary,
        "build_entry": {
            "label": "版本管理",
            "href": f"/admin/projects/{project_id}/versions?{urlencode({'env_key': env_key, 'channel_id': channel_id, 'platform': platform, 'version_id': version_id, 'action': 'edit_release'})}",
            "enabled": True,
        },
        "release_entry": {
            "label": "版本管理",
            "href": f"/admin/projects/{project_id}/versions?{urlencode({'env_key': env_key, 'channel_id': channel_id, 'platform': platform, 'version_id': version_id, 'action': 'edit_release'})}",
            "enabled": bool(artifact_ready or order_status in release_continue_statuses or order_id),
        },
        "scope": scope_params,
        "links": {
            "detail": detail_href,
            "edit": edit_href,
            "build_history": build_history_href,
            "build_config": pipeline_config_href,
            "versions": versions_href,
        },
    }


from services.release.order_delivery_line_enrich import enrich_delivery_line_actions  # noqa: F401
