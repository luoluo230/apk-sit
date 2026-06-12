# -*- coding: utf-8 -*-
"""Unified project delivery pages and APIs."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session

from models.data import projects_db
from services.authz import admin_required
from services.ops.helpers import _render_ops_page
from services.release.release_order_service import (
    approve_release_order,
    cancel_release_order,
    context_options,
    create_release_order,
    get_release_order,
    list_release_orders,
    precheck_release_order,
    project_overview,
    publish_release_order,
    request_build,
    rollback_release_order,
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
    env_key = str(request.args.get("env_key") or "production")
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
        extra_css='<link rel="stylesheet" href="/static/project_delivery.css?v=20260612-v1">',
        extra_js='<script src="/static/project_delivery.js?v=20260612-v1"></script>',
    )


@bp.route("/admin/projects/<project_id>/overview")
@admin_required("projects")
def project_overview_page(project_id: str):
    return _page("project_overview.html", "项目总览", project_id, "project-home")


@bp.route("/admin/projects/<project_id>/release-orders")
@admin_required("projects")
def release_orders_page(project_id: str):
    return _page("release_orders.html", "发布单中心", project_id, "release-orders")


@bp.route("/admin/projects/<project_id>/release-orders/<order_id>")
@admin_required("projects")
def release_order_detail_page(project_id: str, order_id: str):
    return _page("release_order_detail.html", "发布单详情", project_id, "release-orders", order_id=order_id)


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
    return jsonify({"ok": True, "data": project_overview(project_id)})


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


@bp.route("/api/projects/<project_id>/release-orders/<order_id>")
@admin_required("projects")
def release_order_api(project_id: str, order_id: str):
    row = get_release_order(project_id, order_id)
    if not row:
        return jsonify({"ok": False, "error": "发布单不存在"}), 404
    return jsonify({"ok": True, "data": row})


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
    channel_raw = str(request.args.get("channel_id") or request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    if not game_id or not game_key or not env_key or not channel_raw:
        return jsonify({"ok": False, "error": "game_id, game_key, env_key and channel_id required"}), 400
    project_id = ""
    for pid, project in projects_db.items():
        if str(project.get("game_id") or "") == game_id and str(project.get("game_key") or "") == game_key:
            project_id = pid
            break
    if not project_id:
        return jsonify({"ok": False, "error": "invalid game credentials"}), 401
    channel_id = resolve_channel_id(project_id, channel_raw)
    scope_id = ""
    for row in context_options(project_id)["channels"]:
        if row["channel_id"] == channel_id:
            scope_id = build_scope_id(project_slug(project_id), env_key, channel_id)
            break
    scope = find_scope(scope_id)
    if not scope:
        return jsonify({"ok": False, "error": "release scope not found"}), 404
    from services.release.bundle_service import find_active_bundle
    bundle = find_active_bundle(scope_id)
    if not bundle:
        return jsonify({"ok": False, "error": "published bundle not found"}), 404
    client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
    server = bundle.get("server") if isinstance(bundle.get("server"), dict) else {}
    if str(client.get("platform") or "").lower() != platform:
        return jsonify({"ok": False, "error": "published bundle platform mismatch"}), 404
    return jsonify(
        {
            "ok": True,
            "project_id": project_id,
            "scope_id": bundle.get("scope_id"),
            "active_bundle_id": bundle.get("bundle_id"),
            "release_order_id": bundle.get("release_order_id"),
            "topology_id": server.get("topology_id"),
            "runtime_run_id": server.get("runtime_run_id"),
            "network_profile": server.get("network_profile_snapshot") or {},
            "server_snapshot": server,
            "bootstrap": client,
        }
    )
