# -*- coding: utf-8 -*-
"""Project-owned delivery pages and APIs."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session

from models.data import channels_db, can_edit_project, get_channel_by_id, get_channels_for_project, projects_db
from services.admin import project_env_service, project_service
from services.release.env_registry import get_project_env_defs, list_project_env_keys, normalize_release_env_key
from services.authz import admin_required
from services.ops.helpers import _render_ops_page
from services.release.release_order_service import (
    approve_release_order,
    cancel_release_order,
    context_options,
    create_release_order,
    environment_detail,
    get_release_order,
    list_release_orders,
    precheck_release_order,
    project_overview,
    publish_release_order,
    request_build,
    rollback_release_order,
    update_release_order,
    verify_release_order,
)
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.storage import find_scope

bp = Blueprint("project_delivery", __name__)


def _actor() -> str:
    return str(session.get("user") or session.get("username") or "admin")


def _filters() -> dict:
    return {
        key: str(request.args.get(key) or "").strip()
        for key in ("env_key", "channel_id", "platform", "version_name", "version_code", "status")
    }


def _page(template_name: str, title: str, project_id: str, active_page: str, **context):
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
    return _render_ops_page(
        content,
        title,
        active_page=active_page,
        project_id=project_id,
        env_key=env_key,
        extra_css='<link rel="stylesheet" href="/static/project_delivery.css?v=20260623-overview1">',
        extra_js='<script src="/static/project_delivery.js?v=20260623-overview1"></script>',
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


@bp.route("/admin/projects/<project_id>/overview")
@admin_required("projects")
def project_overview_page(project_id: str):
    return _page(
        "project_overview.html",
        "项目总览",
        project_id,
        "project-home",
        **_channel_panel_context(project_id),
    )


@bp.route("/admin/projects/<project_id>/release-orders")
@admin_required("projects")
def release_orders_page(project_id: str):
    return _page("release_orders.html", "发布单", project_id, "release-orders")


@bp.route("/admin/projects/<project_id>/release-orders/new")
@admin_required("projects")
def release_order_new_page(project_id: str):
    return _page("release_order_form.html", "新建发布单", project_id, "release-orders", order_id="")


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


@bp.route("/api/projects/context-catalog")
@admin_required("projects")
def project_context_catalog_api():
    return jsonify({"ok": True, "data": [
        {"project_id": pid, "project_name": str((row or {}).get("name") or pid)}
        for pid, row in projects_db.items()
    ]})


@bp.route("/api/projects/<project_id>/context-options")
@admin_required("projects")
def project_context_options_api(project_id: str):
    if project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    return jsonify({"ok": True, "data": context_options(project_id)})


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
    if not game_id or not game_key or not env_key or not channel or platform not in {"android", "ios"}:
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
