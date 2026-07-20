# -*- coding: utf-8 -*-
"""Project-owned delivery pages and APIs."""

from __future__ import annotations

from typing import List

from flask import Blueprint, jsonify, redirect, render_template, request, session

from data.platforms import get_platform_by_id, get_project_assigned_platform_ids, is_valid_platform_id, list_platform_catalog
from models.data import channels_db, can_edit_project, get_channel_by_id, get_channels_for_project, projects_db
from services.admin import project_env_service, project_service
from services.release.env_registry import get_project_env_defs, list_project_env_keys, normalize_release_env_key, project_env_label
from services.authz import admin_required
from services.ops.environment_runtime_service import build_environment_runtime_overview
from services.ops.helpers import _render_ops_page
from services.release.release_order_service import (
    activate_bundle_on_scope,
    approve_release_order,
    cancel_release_order,
    context_options,
    create_release_order,
    ensure_draft_release_order,
    environment_detail,
    find_draft_release_order,
    get_release_order,
    list_release_orders,
    precheck_release_order,
    project_overview,
    publish_release_order,
    quick_build_version,
    quick_publish_delivery,
    resolve_channel_build_journey,
    resolve_channel_release_journey,
    resolve_delivery_actions,
    resolve_release_order_next_action,
    request_build,
    rollback_release_order,
    rollback_scope_to_bundle,
    sync_building_release_orders,
    unpublish_scope,
    update_release_order,
    verify_release_order,
)
from services.release.bundle_service import list_publishable_bundles
from services.release.release_policy_service import release_order_form_context
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.storage import find_scope

DELIVERY_ASSET_VER = "20260720-release-pipeline-v1"

bp = Blueprint("project_delivery", __name__)

BREADCRUMB_BY_PAGE = {
    "project-home": "总览",
    "environment-overview": "总览",
    "environment-runtime": "总览",
    "environment-config": "项目设置",
    "project-channels": "项目设置",
    "versions": "交付管理",
    "release-orders": "交付管理",
    "builds": "交付管理",
    "download-center": "交付管理",
    "test-devices": "交付管理",
    "topology": "运行管理",
    "topology-bindings": "运行管理",
    "agent-control": "运行管理",
    "actions": "运行管理",
    "diagnostics": "运行管理",
    "approval-center": "治理与审计",
    "change-governance": "治理与审计",
    "audit-log": "治理与审计",
    "project-tasks": "协作",
    "project-docs": "协作",
    "project-settings": "项目设置",
}


def _actor() -> str:
    return str(session.get("user") or session.get("username") or "admin")


def _filters() -> dict:
    return {
        key: str(request.args.get(key) or "").strip()
        for key in ("env_key", "channel_id", "platform", "version_name", "version_code", "status")
    }


def _page(template_name: str, title: str, project_id: str, active_page: str, breadcrumb_module: str = "", **context):
    if project_id not in projects_db:
        return "项目不存在", 404
    env_key = str(context.pop("page_env_key", "") or request.args.get("env_key") or "production")
    content = render_template(
        template_name,
        project_id=project_id,
        project=projects_db.get(project_id) or {},
        env_key=env_key,
        context_filters=_filters(),
        **context,
    )
    js = (
        f'<script src="/static/delivery_scope.js?v={DELIVERY_ASSET_VER}"></script>'
        f'<script src="/static/project_overview.js?v={DELIVERY_ASSET_VER}"></script>'
        f'<script src="/static/project_delivery.js?v={DELIVERY_ASSET_VER}"></script>'
    )
    if template_name == "project_overview.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_ui/pm-filter-bar.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-kpi.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-right-rail.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_overview.css?v={DELIVERY_ASSET_VER}">'
        )
    elif template_name == "project_environment_runtime.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_ui/pm-shell.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-filter-bar.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-kpi.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-table.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-right-rail.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_environment_runtime.css?v={DELIVERY_ASSET_VER}">'
        )
        js = f'<script src="/static/project_environment_runtime.js?v={DELIVERY_ASSET_VER}"></script>'
    elif template_name == "release_order_form.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_ui/pm-stepper.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/release_order_form.css?v={DELIVERY_ASSET_VER}">'
        )
        js = (
            f'<script src="/static/delivery_scope.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/project_delivery.js?v={DELIVERY_ASSET_VER}"></script>'
        )
    elif template_name in ("project_channel_build_journey.html", "project_channel_release_journey.html"):
        css = (
            f'<link rel="stylesheet" href="/static/project_ui/pm-stepper.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_channel_journey.css?v={DELIVERY_ASSET_VER}">'
        )
        js_name = (
            "project_channel_build_journey.js"
            if template_name == "project_channel_build_journey.html"
            else "project_channel_release_journey.js"
        )
        js = f'<script src="/static/{js_name}?v={DELIVERY_ASSET_VER}"></script>'
    elif template_name == "project_environment_detail.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_environment_detail.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/release_focus.css?v={DELIVERY_ASSET_VER}">'
        )
        js = (
            f'<script src="/static/delivery_scope.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/topology_binding_drawer.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/project_delivery.js?v={DELIVERY_ASSET_VER}"></script>'
        )
    elif template_name == "release_order_detail.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/release_order_detail.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/release_order_form.css?v={DELIVERY_ASSET_VER}">'
        )
        js = (
            f'<script src="/static/delivery_scope.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/project_delivery.js?v={DELIVERY_ASSET_VER}"></script>'
        )
    else:
        css = f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
        js = (
            f'<script src="/static/delivery_scope.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/project_delivery.js?v={DELIVERY_ASSET_VER}"></script>'
        )
    return _render_ops_page(
        content,
        title,
        active_page=active_page,
        project_id=project_id,
        env_key=env_key,
        breadcrumb_module=breadcrumb_module or BREADCRUMB_BY_PAGE.get(active_page, "项目工作区"),
        extra_css=css,
        extra_js=js,
    )


@bp.route("/admin/projects/<project_id>/overview/runtime")
@admin_required("projects")
def project_runtime_overview_redirect(project_id: str):
    if project_id not in projects_db:
        return "项目不存在", 404
    env_key = normalize_release_env_key(str(request.args.get("env_key") or "production"), project_id=project_id)
    parts = []
    for key in ("channel_id", "platform"):
        val = str(request.args.get(key) or "").strip()
        if val:
            parts.append(f"{key}={val}")
    target = f"/admin/projects/{project_id}/environments/{env_key}/runtime"
    if parts:
        target += "?" + "&".join(parts)
    return redirect(target)


@bp.route("/admin/projects/<project_id>/environments/<env_key>/runtime")
@admin_required("projects")
def environment_runtime_page(project_id: str, env_key: str):
    if project_id not in projects_db:
        return "项目不存在", 404
    ek = normalize_release_env_key(env_key, project_id=project_id)
    allowed = {str(row.get("env_key") or "").strip().lower() for row in get_project_env_defs(project_id)}
    if ek not in allowed:
        return "环境不存在", 404
    env_options = [
        {
            "env_key": str(row.get("env_key") or "").strip().lower(),
            "env_label": project_env_label(project_id, row.get("env_key")),
        }
        for row in get_project_env_defs(project_id)
        if row.get("enabled") is not False
    ]
    return _page(
        "project_environment_runtime.html",
        "环境运行概览",
        project_id,
        "environment-runtime",
        breadcrumb_module="总览",
        page_env_key=ek,
        env_options=env_options,
    )


@bp.route("/api/projects/<project_id>/environments/<env_key>/runtime-overview")
@admin_required("projects")
def environment_runtime_overview_api(project_id: str, env_key: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    filters = {
        key: str(request.args.get(key) or "").strip()
        for key in (
            "channel_id",
            "platform",
            "service_q",
            "service_cluster",
            "service_category",
            "service_health",
            "service_status",
            "service_page",
            "service_page_size",
        )
    }
    try:
        data = build_environment_runtime_overview(project_id, env_key, filters)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "data": data})


@bp.route("/admin/projects/<project_id>/environments/<env_key>")
@admin_required("projects")
def environment_detail_page(project_id: str, env_key: str):
    if project_id not in projects_db:
        return "项目不存在", 404
    ek = normalize_release_env_key(env_key, project_id=project_id)
    allowed = {str(row.get("env_key") or "").strip().lower() for row in get_project_env_defs(project_id)}
    if ek not in allowed:
        return "环境不存在", 404
    return _page(
        "project_environment_detail.html",
        "环境详情",
        project_id,
        "project-home",
        page_env_key=env_key,
    )


def _normalize_channel_route_id(project_id: str, channel_id: str) -> str:
    raw = str(channel_id or "").strip()
    return resolve_channel_id(project_id, raw) or raw


@bp.route("/admin/projects/<project_id>/environments/<env_key>/channels/<channel_id>/build")
@admin_required("projects")
def channel_build_journey_page(project_id: str, env_key: str, channel_id: str):
    if project_id not in projects_db:
        return "项目不存在", 404
    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = _normalize_channel_route_id(project_id, channel_id)
    return _page(
        "project_channel_build_journey.html",
        "构建流程",
        project_id,
        "project-home",
        breadcrumb_module="交付管理",
        page_env_key=ek,
        channel_id=cid,
    )


@bp.route("/admin/projects/<project_id>/environments/<env_key>/channels/<channel_id>/release")
@admin_required("projects")
def channel_release_journey_page(project_id: str, env_key: str, channel_id: str):
    if project_id not in projects_db:
        return "项目不存在", 404
    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = _normalize_channel_route_id(project_id, channel_id)
    return _page(
        "project_channel_release_journey.html",
        "发版流程",
        project_id,
        "project-home",
        breadcrumb_module="交付管理",
        page_env_key=ek,
        channel_id=cid,
    )


@bp.route("/api/projects/<project_id>/environments/<env_key>")
@admin_required("projects")
def environment_detail_api(project_id: str, env_key: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    return jsonify({"ok": True, "data": environment_detail(project_id, env_key)})


def _channel_panel_context(project_id: str) -> dict:
    proj = projects_db.get(project_id) or {}
    raw_ids = proj.get("channels")
    if isinstance(raw_ids, list) and raw_ids:
        assigned_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
    else:
        assigned_ids = [
            str(c.get("id") or "").strip()
            for c in (channels_db if isinstance(channels_db, list) else [])
            if str(c.get("id") or "").strip()
        ]
    raw_disabled = proj.get("disabled_channels")
    disabled_ids = (
        {str(x).strip() for x in raw_disabled if str(x).strip()}
        if isinstance(raw_disabled, list)
        else set()
    )
    assigned = []
    enabled_count = 0
    for cid in assigned_ids:
        row = get_channel_by_id(cid) or {}
        enabled = cid not in disabled_ids
        if enabled:
            enabled_count += 1
        assigned.append({
            "channel_id": cid,
            "channel_name": str(row.get("name") or cid),
            "enabled": enabled,
        })
    catalog = []
    for row in channels_db if isinstance(channels_db, list) else []:
        cid = str(row.get("id") or "").strip()
        if not cid:
            continue
        catalog.append({"channel_id": cid, "channel_name": str(row.get("name") or cid)})
    return {
        "assigned_channels": assigned,
        "assigned_channel_ids": assigned_ids,
        "channel_catalog": catalog,
        "channel_count": len(assigned),
        "channel_enabled_count": enabled_count,
        "channel_disabled_count": len(assigned) - enabled_count,
    }


def _platform_panel_context(project_id: str) -> dict:
    assigned_ids = get_project_assigned_platform_ids(project_id)
    proj = projects_db.get(project_id) or {}
    raw_disabled = proj.get("disabled_platforms")
    disabled_ids = (
        {str(x).strip().lower() for x in raw_disabled if str(x).strip()}
        if isinstance(raw_disabled, list)
        else set()
    )
    assigned = []
    enabled_count = 0
    for pid in assigned_ids:
        row = get_platform_by_id(pid) or {}
        enabled = pid not in disabled_ids
        if enabled:
            enabled_count += 1
        assigned.append({
            "platform_id": pid,
            "platform_name": str(row.get("name") or pid),
            "enabled": enabled,
        })
    catalog = []
    for row in list_platform_catalog():
        pid = str(row.get("id") or "").strip().lower()
        if not pid:
            continue
        catalog.append({"platform_id": pid, "platform_name": str(row.get("name") or pid)})
    return {
        "assigned_platforms": assigned,
        "assigned_platform_ids": assigned_ids,
        "platform_catalog": catalog,
        "platform_count": len(assigned),
        "platform_enabled_count": enabled_count,
        "platform_disabled_count": len(assigned) - enabled_count,
    }


def _project_members_context(project_id: str) -> dict:
    proj = projects_db.get(project_id) or {}
    roles = proj.get("member_roles") if isinstance(proj.get("member_roles"), dict) else {}
    created_by = str(proj.get("created_by") or "").strip()
    members: List[dict] = []
    seen: set[str] = set()

    def _append(username: str, default_role: str, kind: str) -> None:
        user = str(username or "").strip()
        if not user or user in seen:
            return
        members.append({
            "username": user,
            "role_label": str(roles.get(user) or default_role),
            "kind": kind,
        })
        seen.add(user)

    if created_by:
        _append(created_by, "项目负责人", "owner")
    for username in proj.get("editors") or []:
        _append(username, "编辑者", "editor")
    for username in proj.get("viewers") or []:
        _append(username, "查看者", "viewer")
    return {"project_members": members}


@bp.route("/api/release/platform-catalog")
@admin_required("projects")
def platform_catalog_api():
    catalog = []
    for row in list_platform_catalog():
        catalog.append({
            "id": str(row.get("id") or "").strip().lower(),
            "name": str(row.get("name") or row.get("id") or ""),
            "description": str(row.get("description") or ""),
            "unity_build_target": str(row.get("unity_build_target") or ""),
        })
    return jsonify({"ok": True, "data": catalog})


@bp.route("/admin/projects/<project_id>/overview")
@admin_required("projects")
def project_overview_page(project_id: str):
    tab = str(request.args.get("tab") or "").strip().lower()
    if tab == "environments":
        active_page = "environment-config"
        title = "环境配置"
    elif tab == "channels":
        active_page = "project-channels"
        title = "渠道管理"
    elif tab == "platforms":
        active_page = "project-channels"
        title = "平台管理"
    else:
        active_page = "project-home"
        title = "项目总览"
    return _page(
        "project_overview.html",
        title,
        project_id,
        active_page,
        breadcrumb_module="总览",
        **_channel_panel_context(project_id),
        **_platform_panel_context(project_id),
        **_project_members_context(project_id),
    )


@bp.route("/admin/projects/<project_id>/release-orders")
@admin_required("projects")
def release_orders_page(project_id: str):
    return _page("release_orders.html", "发布单", project_id, "release-orders")


@bp.route("/admin/projects/<project_id>/release-orders/start")
@admin_required("projects")
def release_order_start_page(project_id: str):
    """从 VersionCode 快捷进入：打开已有草稿或自动创建并预填默认值。"""
    from urllib.parse import urlencode
    from models.data import project_versions_db

    if project_id not in projects_db:
        return "项目不存在", 404
    version_id = str(request.args.get("version_id") or "").strip()
    intent = str(request.args.get("intent") or "").strip().lower()
    if not version_id:
        qs = urlencode({"hint": "pick_vc", "env_key": str(request.args.get("env_key") or "").strip()})
        return redirect(f"/admin/projects/{project_id}/versions?{qs}")
    versions = project_versions_db.get(project_id) or []
    version = next((row for row in versions if str(row.get("id") or "") == version_id), None)
    if not version:
        return "VersionCode 不存在", 404
    if intent in ("build", "release"):
        from services.release.release_context import apply_scope_fields_to_version_row

        vrow = apply_scope_fields_to_version_row(dict(version), project_id)
        ch_raw = str(vrow.get("channel_id") or vrow.get("channel") or "").strip()
        channel_id = resolve_channel_id(project_id, ch_raw) or ch_raw
        env_key = normalize_release_env_key(vrow.get("env_key") or "development", project_id=project_id)
        platform = str(vrow.get("platform") or "android").strip().lower()
        qs = urlencode({"platform": platform, "version_id": version_id})
        journey = "build" if intent == "build" else "release"
        return redirect(
            f"/admin/projects/{project_id}/environments/{env_key}/channels/{channel_id}/{journey}?{qs}"
        )
    draft = find_draft_release_order(project_id, version_id)
    if not draft:
        from services.release.release_context import apply_scope_fields_to_version_row

        vrow = apply_scope_fields_to_version_row(dict(version), project_id)
        ch_raw = str(vrow.get("channel_id") or vrow.get("channel") or "").strip()
        channel_id = resolve_channel_id(project_id, ch_raw) or ch_raw
        payload = {
            "env_key": normalize_release_env_key(vrow.get("env_key") or "development", project_id=project_id),
            "channel_id": channel_id,
            "platform": str(vrow.get("platform") or "android").strip().lower(),
            "version_id": version_id,
            "version_code": str(vrow.get("version_code") or "").strip(),
            "reason": "",
            "owner": session.get("user") or "",
        }
        try:
            draft = create_release_order(project_id, payload, _actor())
        except ValueError as exc:
            return redirect(
                f"/admin/projects/{project_id}/versions?"
                f"{urlencode({'hint': 'pick_vc', 'error': str(exc), 'version_id': version_id, 'env_key': payload.get('env_key') or ''})}"
            )
    qs = urlencode(
        {
            "env_key": draft.get("env_key") or "",
            "channel_id": draft.get("channel_id") or "",
            "platform": draft.get("platform") or "",
            "version_name": draft.get("version_name") or "",
            "version_code": draft.get("version_code") or "",
            "version_id": draft.get("version_id") or version_id,
            "release_order_id": draft.get("release_order_id") or "",
        }
    )
    return redirect(f"/admin/projects/{project_id}/release-orders/{draft['release_order_id']}/edit?{qs}")


@bp.route("/admin/projects/<project_id>/release-orders/new")
@admin_required("projects")
def release_order_new_page(project_id: str):
    from urllib.parse import urlencode

    version_id = str(request.args.get("version_id") or "").strip()
    if not version_id:
        params = {"hint": "pick_vc"}
        env_key = str(request.args.get("env_key") or "").strip()
        if env_key:
            params["env_key"] = env_key
        return redirect(f"/admin/projects/{project_id}/versions?{urlencode(params)}")
    extra = {key: str(request.args.get(key) or "").strip() for key in ("env_key", "channel_id", "platform") if request.args.get(key)}
    extra["version_id"] = version_id
    return redirect(f"/admin/projects/{project_id}/release-orders/start?{urlencode(extra)}")


@bp.route("/admin/projects/<project_id>/release-orders/<order_id>/edit")
@admin_required("projects")
def release_order_edit_page(project_id: str, order_id: str):
    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        return "发布单不存在", 404
    return _page(
        "release_order_form.html",
        "编辑发布单",
        project_id,
        "release-orders",
        order_id=order_id,
        page_env_key=order["env_key"],
    )


@bp.route("/admin/projects/<project_id>/release-orders/<order_id>")
@admin_required("projects")
def release_order_detail_page(project_id: str, order_id: str):
    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        return "发布单不存在", 404
    return _page(
        "release_order_detail.html",
        "发布单详情",
        project_id,
        "release-orders",
        order_id=order_id,
        page_env_key=order["env_key"],
    )


@bp.route("/admin/projects/<project_id>/download-center")
@admin_required("projects")
def project_download_center_page(project_id: str):
    return _page("project_download_center.html", "下载中心", project_id, "download-center")


@bp.route("/admin/projects/<project_id>/test-devices")
@admin_required("projects")
def project_test_devices_page(project_id: str):
    return _page("project_test_devices.html", "测试设备", project_id, "test-devices")


@bp.route("/admin/projects/<project_id>/settings")
@admin_required("projects")
def project_settings_page(project_id: str):
    return _page("project_settings.html", "项目设置", project_id, "project-settings")


@bp.route("/admin/projects/<project_id>/tasks")
@admin_required("projects")
def project_tasks_page(project_id: str):
    return _page("project_placeholder.html", "项目任务", project_id, "project-tasks", placeholder_title="项目任务", placeholder_desc="任务协作功能即将上线，当前可通过发布单与变更治理跟踪交付事项。")


@bp.route("/admin/projects/<project_id>/docs")
@admin_required("projects")
def project_docs_page(project_id: str):
    return _page("project_placeholder.html", "项目文档", project_id, "project-docs", placeholder_title="项目文档", placeholder_desc="文档中心即将上线，当前可访问帮助中心查看通用说明。")


@bp.route("/admin/projects/<project_id>/audit-log")
@admin_required("projects")
def project_audit_log_page(project_id: str):
    from urllib.parse import urlencode

    qs = urlencode({"keyword": project_id})
    return redirect(f"/admin/audit-log?{qs}")


@bp.route("/api/projects/context-catalog")
@admin_required("projects")
def project_context_catalog_api():
    return jsonify({"ok": True, "data": [
        {"project_id": pid, "project_name": str((row or {}).get("name") or pid)}
        for pid, row in projects_db.items()
    ]})


@bp.route("/api/projects/<project_id>/release-order-form-context")
@admin_required("projects")
def release_order_form_context_api(project_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    ctx = release_order_form_context(
        project_id,
        version_id=str(request.args.get("version_id") or "").strip(),
        env_key=str(request.args.get("env_key") or "").strip(),
        channel_id=str(request.args.get("channel_id") or "").strip(),
        platform=str(request.args.get("platform") or "").strip(),
    )
    return jsonify({"ok": True, "data": ctx})


@bp.route("/api/projects/<project_id>/context-options")
@admin_required("projects")
def project_context_options_api(project_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    return jsonify({"ok": True, "data": context_options(project_id, str(request.args.get("env_key") or "").strip())})


@bp.route("/api/projects/<project_id>/overview")
@admin_required("projects")
def project_overview_api(project_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    filters = {
        key: str(request.args.get(key) or "").strip()
        for key in ("env_key", "channel_id", "platform", "health")
    }
    return jsonify({"ok": True, "data": project_overview(project_id, filters)})


def _project_channel_mutation(project_id: str, action: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_edit_project(project_id, _actor()):
        return jsonify({"ok": False, "error": "无权限"}), 403
    data = request.get_json(silent=True) or {}
    cid = (data.get("channel_id") or data.get("channel") or "").strip()
    handlers = {
        "add": project_service.add_channel,
        "remove": project_service.remove_channel,
        "disable": project_service.disable_channel,
        "enable": project_service.enable_channel,
    }
    payload, status = handlers[action](project_id, cid)
    return jsonify(payload), status


@bp.route("/api/projects/<project_id>/channels/add", methods=["POST"])
@admin_required("projects")
def project_channel_add_api(project_id: str):
    return _project_channel_mutation(project_id, "add")


@bp.route("/api/projects/<project_id>/channels/remove", methods=["POST"])
@admin_required("projects")
def project_channel_remove_api(project_id: str):
    return _project_channel_mutation(project_id, "remove")


@bp.route("/api/projects/<project_id>/channels/disable", methods=["POST"])
@admin_required("projects")
def project_channel_disable_api(project_id: str):
    return _project_channel_mutation(project_id, "disable")


@bp.route("/api/projects/<project_id>/channels/enable", methods=["POST"])
@admin_required("projects")
def project_channel_enable_api(project_id: str):
    return _project_channel_mutation(project_id, "enable")


def _project_platform_mutation(project_id: str, action: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_edit_project(project_id, _actor()):
        return jsonify({"ok": False, "error": "无权限"}), 403
    data = request.get_json(silent=True) or {}
    pid = (data.get("platform_id") or data.get("platform") or "").strip().lower()
    handlers = {
        "add": project_service.add_platform,
        "remove": project_service.remove_platform,
        "disable": project_service.disable_platform,
        "enable": project_service.enable_platform,
    }
    payload, status = handlers[action](project_id, pid)
    return jsonify(payload), status


@bp.route("/api/projects/<project_id>/platforms/add", methods=["POST"])
@admin_required("projects")
def project_platform_add_api(project_id: str):
    return _project_platform_mutation(project_id, "add")


@bp.route("/api/projects/<project_id>/platforms/remove", methods=["POST"])
@admin_required("projects")
def project_platform_remove_api(project_id: str):
    return _project_platform_mutation(project_id, "remove")


@bp.route("/api/projects/<project_id>/platforms/disable", methods=["POST"])
@admin_required("projects")
def project_platform_disable_api(project_id: str):
    return _project_platform_mutation(project_id, "disable")


@bp.route("/api/projects/<project_id>/platforms/enable", methods=["POST"])
@admin_required("projects")
def project_platform_enable_api(project_id: str):
    return _project_platform_mutation(project_id, "enable")


@bp.route("/api/projects/<project_id>/environments", methods=["GET", "POST"])
@admin_required("projects")
def project_environments_api(project_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if request.method == "GET":
        payload, status = project_env_service.list_environments(project_id)
        return jsonify(payload), status
    if not can_edit_project(project_id, _actor()):
        return jsonify({"ok": False, "error": "无权限"}), 403
    payload, status = project_env_service.add_environment(project_id, request.get_json(silent=True) or {})
    return jsonify(payload), status


@bp.route("/api/projects/<project_id>/environments/<env_key>", methods=["PATCH", "DELETE"])
@admin_required("projects")
def project_environment_api(project_id: str, env_key: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_edit_project(project_id, _actor()):
        return jsonify({"ok": False, "error": "无权限"}), 403
    if request.method == "PATCH":
        payload, status = project_env_service.update_environment(project_id, env_key, request.get_json(silent=True) or {})
    else:
        payload, status = project_env_service.delete_environment(project_id, env_key)
    return jsonify(payload), status


@bp.route("/api/projects/<project_id>/environments/<env_key>/delivery-scope", methods=["GET", "PATCH"])
@admin_required("projects")
def project_environment_delivery_scope_api(project_id: str, env_key: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if request.method == "GET":
        payload, status = project_env_service.get_delivery_scope(project_id, env_key)
        return jsonify(payload), status
    if not can_edit_project(project_id, _actor()):
        return jsonify({"ok": False, "error": "无权限"}), 403
    payload, status = project_env_service.update_delivery_scope(
        project_id, env_key, request.get_json(silent=True) or {}
    )
    return jsonify(payload), status


@bp.route("/api/projects/<project_id>/environments/<env_key>/channels/<channel_id>/build-journey")
@admin_required("projects")
def channel_build_journey_api(project_id: str, env_key: str, channel_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    try:
        data = resolve_channel_build_journey(
            project_id,
            env_key,
            _normalize_channel_route_id(project_id, channel_id),
            platform=str(request.args.get("platform") or "").strip().lower(),
            version_id=str(request.args.get("version_id") or "").strip(),
        )
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/environments/<env_key>/channels/<channel_id>/release-journey")
@admin_required("projects")
def channel_release_journey_api(project_id: str, env_key: str, channel_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    try:
        data = resolve_channel_release_journey(
            project_id,
            env_key,
            _normalize_channel_route_id(project_id, channel_id),
            platform=str(request.args.get("platform") or "").strip().lower(),
            version_id=str(request.args.get("version_id") or "").strip(),
            bundle_id=str(request.args.get("bundle_id") or "").strip(),
        )
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/versions/<version_id>/delivery-actions", methods=["GET"])
@admin_required("projects")
def version_delivery_actions_api(project_id: str, version_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    try:
        data = resolve_delivery_actions(project_id, version_id)
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/versions/<version_id>/quick-build", methods=["POST"])
@admin_required("projects")
def version_quick_build_api(project_id: str, version_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    try:
        data = quick_build_version(project_id, version_id, _actor())
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/versions/<version_id>/ensure-release-order", methods=["POST"])
@admin_required("projects")
def version_ensure_release_order_api(project_id: str, version_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    try:
        data = ensure_draft_release_order(project_id, version_id, _actor(), reason="发版流程创建发布单")
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/delivery-attempts/quick-publish", methods=["POST"])
@admin_required("projects")
def delivery_quick_publish_api(project_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        data = quick_publish_delivery(
            project_id,
            str(payload.get("env_key") or "").strip(),
            str(payload.get("channel_id") or "").strip(),
            str(payload.get("platform") or "").strip(),
            str(payload.get("version_id") or "").strip(),
            _actor(),
            skip_build=bool(payload.get("skip_build")),
            force_build=bool(payload.get("force_build")),
            auto_verify=payload.get("auto_verify", True) is not False,
        )
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/release-orders/sync-building", methods=["POST"])
@admin_required("projects")
def release_orders_sync_building_api(project_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    rows = sync_building_release_orders(project_id, actor=_actor())
    return jsonify({"ok": True, "data": {"updated": rows, "count": len(rows)}})


@bp.route("/api/projects/<project_id>/scopes/<scope_id>/publishable-bundles")
@admin_required("projects")
def scope_publishable_bundles_api(project_id: str, scope_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    bundles = list_publishable_bundles(
        scope_id,
        platform=str(request.args.get("platform") or "").strip().lower(),
    )
    return jsonify({"ok": True, "data": bundles})


@bp.route("/api/projects/<project_id>/scopes/<scope_id>/publish-bundle", methods=["POST"])
@admin_required("projects")
def scope_publish_bundle_api(project_id: str, scope_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        data = activate_bundle_on_scope(
            project_id,
            scope_id,
            str(payload.get("bundle_id") or "").strip(),
            _actor(),
            mode=str(payload.get("mode") or "full"),
            gray_ratio=str(payload.get("gray_ratio") or ""),
            reason=str(payload.get("reason") or ""),
        )
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/scopes/<scope_id>/rollback", methods=["POST"])
@admin_required("projects")
def scope_rollback_api(project_id: str, scope_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        data = rollback_scope_to_bundle(
            project_id,
            scope_id,
            str(payload.get("bundle_id") or "").strip(),
            _actor(),
            reason=str(payload.get("reason") or ""),
        )
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/scopes/<scope_id>/unpublish", methods=["POST"])
@admin_required("projects")
def scope_unpublish_api(project_id: str, scope_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        data = unpublish_scope(
            project_id,
            scope_id,
            _actor(),
            reason=str(payload.get("reason") or ""),
        )
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/release-orders", methods=["GET", "POST"])
@admin_required("projects")
def release_orders_api(project_id: str):
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_release_orders(project_id, _filters())})
        row = create_release_order(project_id, request.get_json(silent=True) or {}, _actor())
        return jsonify({"ok": True, "data": row}), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/release-orders/<order_id>/next-action")
@admin_required("projects")
def release_order_next_action_api(project_id: str, order_id: str):
    try:
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        return jsonify({"ok": True, "data": resolve_release_order_next_action(project_id, order_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/projects/<project_id>/release-orders/<order_id>", methods=["GET", "PATCH"])
@admin_required("projects")
def release_order_api(project_id: str, order_id: str):
    try:
        if request.method == "PATCH":
            return jsonify({"ok": True, "data": update_release_order(project_id, order_id, request.get_json(silent=True) or {}, _actor())})
        row = get_release_order(project_id, order_id)
        if not row:
            return jsonify({"ok": False, "error": "发布单不存在"}), 404
        return jsonify({"ok": True, "data": row})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def _order_action(project_id: str, order_id: str, action: str):
    payload = request.get_json(silent=True) or {}
    handlers = {
        "build": lambda: request_build(project_id, order_id, _actor()),
        "precheck": lambda: precheck_release_order(project_id, order_id, _actor()),
        "approve": lambda: approve_release_order(project_id, order_id, _actor(), str(payload.get("note") or "")),
        "publish": lambda: publish_release_order(project_id, order_id, _actor()),
        "verify": lambda: verify_release_order(project_id, order_id, _actor(), bool(payload.get("ok", True))),
        "rollback": lambda: rollback_release_order(project_id, order_id, _actor()),
        "cancel": lambda: cancel_release_order(project_id, order_id, _actor()),
    }
    try:
        return jsonify({"ok": True, "data": handlers[action]()})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


for _action in ("build", "precheck", "approve", "publish", "verify", "rollback", "cancel"):
    bp.add_url_rule(
        f"/api/projects/<project_id>/release-orders/<order_id>/{_action}",
        endpoint=f"release_order_{_action}",
        view_func=admin_required("projects")(lambda project_id, order_id, action=_action: _order_action(project_id, order_id, action)),
        methods=["POST"],
    )


@bp.route("/api/public/runtime-bootstrap")
def runtime_bootstrap():
    game_id = str(request.args.get("game_id") or "").strip()
    game_key = str(request.args.get("game_key") or "").strip()
    env_key = str(request.args.get("env_key") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "").strip().lower()
    if not game_id or not game_key or not env_key or not channel or not is_valid_platform_id(platform):
        return jsonify({"ok": False, "error": "game_id、game_key、env_key、channel、platform 必填"}), 400
    project_id = next((
        pid for pid, project in projects_db.items()
        if str(project.get("game_id") or "") == game_id and str(project.get("game_key") or "") == game_key
    ), "")
    if not project_id:
        return jsonify({"ok": False, "error": "项目凭证无效"}), 401
    resolved_channel_id = resolve_channel_id(project_id, channel)
    channel_row = get_channel_by_id(resolved_channel_id) or {}
    channel_name = str(channel_row.get("apk_subdir") or channel_row.get("name") or channel).strip()
    scope_id = build_scope_id(project_slug(project_id), env_key, resolved_channel_id, platform)
    scope = find_scope(scope_id)
    if not scope:
        legacy_scope_id = build_scope_id(project_slug(project_id), env_key, resolved_channel_id)
        if legacy_scope_id != scope_id:
            scope = find_scope(legacy_scope_id)
    if not scope:
        return jsonify({"ok": False, "error": "发布作用域不存在"}), 404
    from services.release.bundle_service import find_active_bundle
    bundle = find_active_bundle(scope_id, platform=platform) or find_active_bundle(str(scope.get("scope_id") or ""), platform=platform)
    if not bundle:
        return jsonify({"ok": False, "error": "当前作用域没有已发布 Bundle"}), 404
    client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
    server = bundle.get("server") if isinstance(bundle.get("server"), dict) else {}
    if str(client.get("platform") or "").lower() != platform:
        return jsonify({"ok": False, "error": "已发布 Bundle 平台不匹配"}), 404
    return jsonify({
        "ok": True,
        "project_id": project_id,
        "channel": channel_name,
        "scope_id": bundle.get("scope_id"),
        "active_bundle_id": bundle.get("bundle_id"),
        "release_order_id": bundle.get("release_order_id"),
        "topology_id": server.get("topology_id"),
        "runtime_run_id": server.get("runtime_run_id"),
        "network_profile": server.get("network_profile_snapshot") or {},
        "server_snapshot": server,
        "bootstrap": client,
    })
