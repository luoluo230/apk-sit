"""Admin project route adapters."""

from __future__ import annotations

from flask import jsonify, request

from models.data import can_edit_project, can_view_project, get_system_config, projects_db
from services.authz import admin_required
from services.admin import project_service


def projects_create_response(created_by: str, tenant_id: str):
    payload, status = project_service.create_project(request.get_json(force=True, silent=True) or {}, created_by, tenant_id)
    return jsonify(payload), status


def projects_generate_credentials_response(project_id: str):
    payload, status = project_service.generate_credentials(project_id)
    return jsonify(payload), status


def projects_get_response(project_id: str):
    payload, status = project_service.get_project(project_id)
    return jsonify(payload), status


def projects_update_response():
    payload, status = project_service.update_project(request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def projects_channels_add_response(project_id: str):
    data = request.get_json(force=True, silent=True) or {}
    cid = (data.get("channel_id") or data.get("channel") or "").strip()
    payload, status = project_service.add_channel(project_id, cid)
    return jsonify(payload), status


def projects_channels_remove_response(project_id: str):
    data = request.get_json(force=True, silent=True) or {}
    cid = (data.get("channel_id") or data.get("channel") or "").strip()
    payload, status = project_service.remove_channel(project_id, cid)
    return jsonify(payload), status


def projects_archive_response(project_id: str):
    data = request.get_json(silent=True) or {}
    payload, status = project_service.set_archive(project_id, bool(data.get("archive", True)))
    return jsonify(payload), status


def projects_delete_response(project_id: str, require_approval_for_delete: bool):
    payload, status = project_service.delete_project(project_id, require_approval_for_delete)
    return jsonify(payload), status


def register_routes(bp, current_username_getter, tenant_id_getter):
    @admin_required("projects")
    def _projects_create():
        created_by = current_username_getter()
        tenant_id = tenant_id_getter()
        return projects_create_response(created_by, tenant_id)

    @admin_required("projects")
    def _projects_generate_credentials():
        data = request.get_json(force=True, silent=True) or {}
        project_id = (data.get("id") or data.get("project_id") or "").strip() or "project"
        return projects_generate_credentials_response(project_id)

    @admin_required("projects")
    def _projects_get(project_id: str):
        if project_id not in projects_db:
            return jsonify({"error": "项目不存在"})
        if not can_view_project(project_id, current_username_getter()):
            return jsonify({"error": "无权限查看该项目"}), 403
        return projects_get_response(project_id)

    @admin_required("projects")
    def _projects_update():
        data = request.get_json(force=True, silent=True) or {}
        project_id = (data.get("id") or "").strip()
        if not project_id or project_id not in projects_db:
            return jsonify({"error": "项目不存在"})
        if not can_edit_project(project_id, current_username_getter()):
            return jsonify({"error": "无权限编辑该项目"}), 403
        return projects_update_response()

    @admin_required("projects")
    def _projects_channels_add(project_id: str):
        if project_id not in projects_db or not can_edit_project(project_id, current_username_getter()):
            return jsonify({"error": "无权限"}), 403
        return projects_channels_add_response(project_id)

    @admin_required("projects")
    def _projects_channels_remove(project_id: str):
        if project_id not in projects_db or not can_edit_project(project_id, current_username_getter()):
            return jsonify({"error": "无权限"}), 403
        return projects_channels_remove_response(project_id)

    @admin_required("projects")
    def _projects_archive(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在", "error_text": "项目不存在", "error_legacy": "项目不存在"}), 404
        if not can_edit_project(project_id, current_username_getter()):
            return jsonify({"error": "无权限操作"}), 403
        return projects_archive_response(project_id)

    @admin_required("projects")
    def _projects_delete(project_id: str):
        if project_id not in projects_db:
            return jsonify({"error": "项目不存在"})
        if not can_edit_project(project_id, current_username_getter()):
            return jsonify({"error": "无权限删除该项目"}), 403
        require_approval = str(get_system_config("REQUIRE_APPROVAL_FOR_DELETE") or "").lower() in ("true", "1", "yes")
        return projects_delete_response(project_id, require_approval)

    bp.add_url_rule("/admin/projects/create", endpoint="admin_projects_create", view_func=_projects_create, methods=["POST"])
    bp.add_url_rule(
        "/admin/projects/generate-credentials",
        endpoint="admin_projects_generate_credentials",
        view_func=_projects_generate_credentials,
        methods=["POST"],
    )
    bp.add_url_rule("/admin/projects/get/<project_id>", endpoint="admin_projects_get", view_func=_projects_get)
    bp.add_url_rule("/admin/projects/update", endpoint="admin_projects_update", view_func=_projects_update, methods=["POST"])
    bp.add_url_rule(
        "/admin/projects/<project_id>/channels/add",
        endpoint="admin_projects_channels_add",
        view_func=_projects_channels_add,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/channels/remove",
        endpoint="admin_projects_channels_remove",
        view_func=_projects_channels_remove,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/archive",
        endpoint="admin_projects_archive",
        view_func=_projects_archive,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/delete/<project_id>",
        endpoint="admin_projects_delete",
        view_func=_projects_delete,
        methods=["DELETE"],
    )
