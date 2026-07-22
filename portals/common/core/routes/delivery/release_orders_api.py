# -*- coding: utf-8 -*-
"""Release order API routes."""

from __future__ import annotations

from flask import jsonify, request

from models.data import projects_db
from services.authz import admin_required
from services.release.release_order_service import (
    approve_release_order,
    cancel_release_order,
    create_release_order,
    get_release_order,
    list_release_orders,
    precheck_release_order,
    publish_release_order,
    request_build,
    resolve_release_order_next_action,
    rollback_release_order,
    update_release_order,
    verify_release_order,
)

from routes.delivery.helpers import actor as _actor, filters as _filters


def register_release_order_routes(bp) -> None:
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
                return jsonify({
                    "ok": True,
                    "data": update_release_order(
                        project_id, order_id, request.get_json(silent=True) or {}, _actor()
                    ),
                })
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
            "approve": lambda: approve_release_order(
                project_id, order_id, _actor(), str(payload.get("note") or "")
            ),
            "publish": lambda: publish_release_order(project_id, order_id, _actor()),
            "verify": lambda: verify_release_order(
                project_id, order_id, _actor(), bool(payload.get("ok", True))
            ),
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
            view_func=admin_required("projects")(
                lambda project_id, order_id, action=_action: _order_action(project_id, order_id, action)
            ),
            methods=["POST"],
        )
