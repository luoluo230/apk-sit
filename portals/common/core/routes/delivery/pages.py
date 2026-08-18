# -*- coding: utf-8 -*-
"""Delivery HTML page routes."""

from __future__ import annotations

from typing import List

from flask import redirect, request, session

from data.platforms import get_platform_by_id, get_project_assigned_platform_ids, list_platform_catalog
from models.data import channels_db, get_channel_by_id, projects_db
from services.admin import project_env_service
from services.authz import admin_required
from services.release.env_registry import get_project_env_defs, normalize_release_env_key, project_env_label
from services.release.release_order_service import create_release_order, find_draft_release_order, get_release_order
from services.release.scope_ids import resolve_channel_id

from routes.delivery.helpers import (
    actor as _actor,
    normalize_channel_route_id as _normalize_channel_route_id,
    render_delivery_page as _page,
)


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


def register_page_routes(bp) -> None:
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

    @bp.route("/admin/projects/<project_id>/release-hub")
    @admin_required("projects")
    def project_release_hub_page(project_id: str):
        if project_id not in projects_db:
            return "项目不存在", 404
        env_key = str(request.args.get("env_key") or "development").strip()
        return _page(
            "project_release_hub.html",
            "发版中心",
            project_id,
            "release-hub",
            breadcrumb_module="交付发版",
            page_env_key=env_key,
        )

    @bp.route("/admin/projects/<project_id>/release")
    @admin_required("projects")
    def project_release_console_page(project_id: str):
        if project_id not in projects_db:
            return "项目不存在", 404
        env_key = str(request.args.get("env_key") or request.args.get("env") or "development").strip()
        return _page(
            "project_release_console.html",
            "发版控制台",
            project_id,
            "release-console",
            breadcrumb_module="交付发版",
            page_env_key=env_key,
        )

    @bp.route("/admin/projects/<project_id>/environments/<env_key>/channels/<channel_id>/build")
    @admin_required("projects")
    def channel_build_journey_page(project_id: str, env_key: str, channel_id: str):
        from urllib.parse import urlencode

        if project_id not in projects_db:
            return "项目不存在", 404
        ek = normalize_release_env_key(env_key, project_id=project_id)
        cid = _normalize_channel_route_id(project_id, channel_id)
        qs = urlencode({
            "env_key": ek,
            "channel_id": cid,
            "platform": str(request.args.get("platform") or "android").strip().lower(),
            "version_id": str(request.args.get("version_id") or "").strip(),
            "action": "create_vc",
        })
        return redirect(f"/admin/projects/{project_id}/versions?{qs}")

    @bp.route("/admin/projects/<project_id>/environments/<env_key>/channels/<channel_id>/release")
    @admin_required("projects")
    def channel_release_journey_page(project_id: str, env_key: str, channel_id: str):
        from urllib.parse import urlencode

        if project_id not in projects_db:
            return "项目不存在", 404
        ek = normalize_release_env_key(env_key, project_id=project_id)
        cid = _normalize_channel_route_id(project_id, channel_id)
        qs = urlencode({
            "env_key": ek,
            "channel_id": cid,
            "platform": str(request.args.get("platform") or "android").strip().lower(),
            "version_id": str(request.args.get("version_id") or "").strip(),
            "action": "edit_release",
        })
        return redirect(f"/admin/projects/{project_id}/versions?{qs}")

    @bp.route("/admin/projects/<project_id>/activities")
    @admin_required("projects")
    def project_activities_page(project_id: str):
        if project_id not in projects_db:
            return "项目不存在", 404
        return _page(
            "project_activities.html",
            "项目动态",
            project_id,
            "project-home",
            breadcrumb_module="总览",
        )

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
        return _page("release_orders.html", "发布单", project_id, "release-orders", breadcrumb_module="交付发版")

    @bp.route("/admin/projects/<project_id>/release-orders/start")
    @admin_required("projects")
    def release_order_start_page(project_id: str):
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
            qs = urlencode({
                "env_key": env_key,
                "channel_id": channel_id,
                "platform": platform,
                "version_id": version_id,
                "action": "edit_release",
            })
            return redirect(f"/admin/projects/{project_id}/versions?{qs}")
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
                "version_id": draft.get("version_id") or version_id,
                "action": "edit_release",
            }
        )
        return redirect(f"/admin/projects/{project_id}/versions?{qs}")

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
        from models.data import can_edit_project

        can_edit = can_edit_project(project_id, _actor())
        return _page(
            "project_test_devices.html",
            "测试设备",
            project_id,
            "test-devices",
            can_edit=can_edit,
        )

    @bp.route("/admin/projects/<project_id>/tasks")
    @admin_required("projects")
    def project_tasks_page(project_id: str):
        from routes.admin.views.project_tasks import render_project_tasks_page
        from routes.delivery.helpers import _render_ops_page, BREADCRUMB_BY_PAGE, DELIVERY_ASSET_VER

        content, title, err = render_project_tasks_page(project_id, _actor())
        if err:
            return err, 403
        return _render_ops_page(
            content,
            title,
            active_page="project-tasks",
            project_id=project_id,
            env_key=str(request.args.get("env_key") or "production"),
            breadcrumb_module=BREADCRUMB_BY_PAGE.get("project-tasks", "协作"),
            extra_css=f'<link rel="stylesheet" href="/static/tailwind.css?v={DELIVERY_ASSET_VER}">',
        )

    @bp.route("/admin/projects/<project_id>/docs")
    @admin_required("projects")
    def project_docs_page(project_id: str):
        from routes.delivery.page_context import project_docs_embed_context

        ctx = project_docs_embed_context(project_id)
        return _page(
            "project_docs_embed.html",
            "项目文档",
            project_id,
            "project-docs",
            **ctx,
        )

    @bp.route("/admin/projects/<project_id>/settings")
    @admin_required("projects")
    def project_settings_page(project_id: str):
        return _page("project_settings.html", "项目设置", project_id, "project-settings")

    @bp.route("/admin/projects/<project_id>/audit-log")
    @admin_required("projects")
    def project_audit_log_page(project_id: str):
        from urllib.parse import urlencode

        qs = urlencode({"keyword": project_id})
        return redirect(f"/admin/audit-log?{qs}")
