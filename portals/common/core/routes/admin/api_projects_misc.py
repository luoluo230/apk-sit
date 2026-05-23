"""Admin project misc route adapters (list/upload/files/query)."""

from __future__ import annotations

from flask import jsonify, request, send_from_directory

from services.authz import admin_required
from services.admin import project_misc_service
from services.admin.fs_browse_service import browse_path, native_pick_path


def fs_browse_response():
    path = (request.args.get("path") or "").strip()
    mode = (request.args.get("mode") or "dir").strip()
    return jsonify(browse_path(path, mode=mode))


def fs_native_pick_response():
    data = request.get_json(silent=True) or {}
    path = (data.get("initial_path") or data.get("path") or "").strip()
    mode = (data.get("mode") or "dir").strip()
    return jsonify(native_pick_path(path, mode=mode))


def projects_upload_icon_response():
    payload, status = project_misc_service.upload_project_icon(request.files.get("icon"))
    return jsonify(payload), status


def projects_serve_icon_response(filename: str):
    safe_name = project_misc_service.validate_icon_filename(filename)
    if not safe_name:
        return "", 404
    return send_from_directory(project_misc_service.PROJECT_ICONS_DIR, safe_name)


def project_tasks_upload_response(project_id: str, username: str):
    payload, status = project_misc_service.upload_task_file(project_id, username, request.files.get("file"))
    return jsonify(payload), status


def project_tasks_serve_file_response(project_id: str, filename: str, username: str):
    payload, status = project_misc_service.validate_task_file(project_id, filename, username)
    if status != 200:
        if status == 403:
            return "", 403
        return "", 404
    if payload.get("is_image"):
        return send_from_directory(payload["subdir"], payload["filename"])
    return send_from_directory(
        payload["subdir"],
        payload["filename"],
        as_attachment=True,
        download_name=payload["download_name"],
    )


def projects_user_options_response():
    return jsonify(project_misc_service.project_user_options())


def projects_validate_username_response(username: str):
    return jsonify(project_misc_service.validate_username(username))


def projects_list_response(username: str, status_filter: str, can_edit_lookup=None):
    payload = project_misc_service.list_projects_for_user(username, status_filter)
    if can_edit_lookup:
        for item in payload.get("projects") or []:
            item["can_edit"] = bool(can_edit_lookup(item.get("id") or ""))
    return jsonify(payload)


def register_routes(bp, current_username_getter, can_edit_lookup):
    @admin_required("projects")
    def _upload_icon():
        return projects_upload_icon_response()

    def _serve_icon(filename: str):
        return projects_serve_icon_response(filename)

    @admin_required("projects")
    def _task_upload(project_id: str):
        return project_tasks_upload_response(project_id, current_username_getter())

    @admin_required("projects")
    def _task_file(project_id: str, filename: str):
        return project_tasks_serve_file_response(project_id, filename, current_username_getter())

    @admin_required("projects")
    def _user_options():
        return projects_user_options_response()

    @admin_required("projects")
    def _validate_username():
        return projects_validate_username_response((request.args.get("username") or "").strip())

    @admin_required("projects")
    def _projects_list():
        status_filter = (request.args.get("status") or "active").strip()
        return projects_list_response(current_username_getter(), status_filter, can_edit_lookup=can_edit_lookup)

    @admin_required("projects")
    def _fs_browse():
        return fs_browse_response()

    @admin_required("projects")
    def _fs_native_pick():
        return fs_native_pick_response()

    bp.add_url_rule("/admin/projects/upload-icon", endpoint="admin_projects_upload_icon", view_func=_upload_icon, methods=["POST"])
    bp.add_url_rule("/admin/projects/icon/<filename>", endpoint="admin_projects_serve_icon", view_func=_serve_icon)
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/upload",
        endpoint="project_task_upload",
        view_func=_task_upload,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/file/<filename>",
        endpoint="project_task_serve_file",
        view_func=_task_file,
    )
    bp.add_url_rule("/admin/projects/user-options", endpoint="admin_projects_user_options", view_func=_user_options)
    bp.add_url_rule("/admin/projects/validate-username", endpoint="admin_projects_validate_username", view_func=_validate_username)
    bp.add_url_rule("/admin/projects/list", endpoint="admin_projects_list", view_func=_projects_list)
    bp.add_url_rule("/admin/fs/browse", endpoint="admin_fs_browse", view_func=_fs_browse)
    bp.add_url_rule("/admin/fs/native-pick", endpoint="admin_fs_native_pick", view_func=_fs_native_pick, methods=["POST"])
