# -*- coding: utf-8 -*-
"""Delivery route helpers shared by page and API modules."""

from __future__ import annotations

from flask import render_template, request, session

from models.data import projects_db
from services.ops.helpers import _render_ops_page

DELIVERY_ASSET_VER = "20260724-closure-e2e"

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


def delivery_js_bundle(*extra: str) -> str:
    parts = [
        f'<script src="/static/delivery_common.js?v={DELIVERY_ASSET_VER}"></script>',
        f'<script src="/static/delivery_scope.js?v={DELIVERY_ASSET_VER}"></script>',
    ]
    for name in extra:
        parts.append(f'<script src="/static/{name}?v={DELIVERY_ASSET_VER}"></script>')
    parts.append(f'<script src="/static/project_delivery.js?v={DELIVERY_ASSET_VER}"></script>')
    return "".join(parts)


def normalize_channel_route_id(project_id: str, channel_id: str) -> str:
    from services.release.scope_ids import resolve_channel_id

    raw = str(channel_id or "").strip()
    return resolve_channel_id(project_id, raw) or raw


def actor() -> str:
    return str(session.get("user") or session.get("username") or "admin")


def filters() -> dict:
    return {
        key: str(request.args.get(key) or "").strip()
        for key in ("env_key", "channel_id", "platform", "version_name", "version_code", "status")
    }


def render_delivery_page(template_name: str, title: str, project_id: str, active_page: str, breadcrumb_module: str = "", **context):
    if project_id not in projects_db:
        return "项目不存在", 404
    env_key = str(context.pop("page_env_key", "") or request.args.get("env_key") or "production")
    content = render_template(
        template_name,
        project_id=project_id,
        project=projects_db.get(project_id) or {},
        env_key=env_key,
        context_filters=filters(),
        **context,
    )
    js = delivery_js_bundle("project_overview.js")
    if template_name == "project_overview.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_ui/pm-filter-bar.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-kpi.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-right-rail.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_overview.css?v={DELIVERY_ASSET_VER}">'
        )
    elif template_name == "project_activities.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_ui/pm-filter-bar.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_overview.css?v={DELIVERY_ASSET_VER}">'
        )
        js = (
            f'<script src="/static/delivery_common.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/project_activities.js?v={DELIVERY_ASSET_VER}"></script>'
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
    elif template_name == "project_test_devices.html":
        css = f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
        js = (
            f'<script src="/static/delivery_common.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/project_test_devices.js?v={DELIVERY_ASSET_VER}"></script>'
        )
    elif template_name == "project_docs_embed.html":
        css = f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
        js = delivery_js_bundle()
    elif template_name == "release_order_form.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_ui/pm-stepper.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/release_order_form.css?v={DELIVERY_ASSET_VER}">'
        )
        js = delivery_js_bundle()
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
        js = (
            f'<script src="/static/journey_common.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/{js_name}?v={DELIVERY_ASSET_VER}"></script>'
        )
    elif template_name == "project_environment_detail.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_environment_detail.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/release_focus.css?v={DELIVERY_ASSET_VER}">'
        )
        js = delivery_js_bundle("topology_binding_drawer.js")
    elif template_name == "release_order_detail.html":
        css = (
            f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/release_order_detail.css?v={DELIVERY_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/release_order_form.css?v={DELIVERY_ASSET_VER}">'
        )
        js = (
            f'<script src="/static/delivery_common.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/delivery_scope.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/journey_common.js?v={DELIVERY_ASSET_VER}"></script>'
            f'<script src="/static/delivery_order_detail.js?v={DELIVERY_ASSET_VER}"></script>'
        )
    else:
        css = f'<link rel="stylesheet" href="/static/project_delivery.css?v={DELIVERY_ASSET_VER}">'
        js = delivery_js_bundle()
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
