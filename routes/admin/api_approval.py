"""Admin approval route adapters."""

from __future__ import annotations

from flask import jsonify, request

from models.data import resolve_project_id
from services.authz import admin_required, has_scope
from services.admin import approval_service


def approval_create_response(username: str, project_id: str):
    payload, status = approval_service.create_approval_request(request.get_json(silent=True) or {}, username, project_id=project_id)
    return jsonify(payload), status


def approval_do_response(aid: str, action: str, username: str):
    data = request.get_json(silent=True) or {}
    payload, status = approval_service.decide_approval(aid, action, username, str(data.get("comment") or "").strip())
    return jsonify(payload), status


def register_routes(bp, current_username_getter):
    @admin_required("approval")
    def _approval_create():
        data = request.get_json(silent=True) or {}
        project_id = resolve_project_id((data.get("project_id") or "").strip()) or ""
        return approval_create_response(current_username_getter(), project_id)

    @admin_required("approval")
    def _approval_do(aid: str, action: str):
        if action not in ("approve", "reject"):
            return jsonify({"error": "无效操作"}), 400
        if not has_scope("approval.manage"):
            return jsonify({"error": "无权限执行审批操作"}), 403
        return approval_do_response(aid, action, current_username_getter())

    bp.add_url_rule("/admin/approval/create", endpoint="admin_approval_create", view_func=_approval_create, methods=["POST"])
    bp.add_url_rule(
        "/admin/approval/<aid>/<action>",
        endpoint="admin_approval_do",
        view_func=_approval_do,
        methods=["POST"],
    )
