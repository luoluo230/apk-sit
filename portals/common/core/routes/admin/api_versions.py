"""Admin versions route adapters."""

from __future__ import annotations

from flask import jsonify, request

from services.authz import admin_required, login_required
from services.admin import version_service


def version_download_stats_response(project_id: str, username: str):
    payload, status = version_service.project_download_stats(project_id, username)
    return jsonify(payload), status


def versions_list_response(project_id: str, username: str):
    payload, status = version_service.list_versions(project_id, username)
    return jsonify(payload), status


def version_downloads_response(project_id: str, version_id: str, username: str):
    payload, status = version_service.get_version_downloads(project_id, version_id, username)
    return jsonify(payload), status


def versions_create_response(project_id: str, username: str):
    payload, status = version_service.create_version(project_id, username, request.get_json(silent=True) or {})
    return jsonify(payload), status


def versions_update_response(project_id: str, username: str):
    payload, status = version_service.update_version(project_id, username, request.get_json(silent=True) or {})
    return jsonify(payload), status


def versions_delete_response(project_id: str, version_id: str, username: str):
    payload, status = version_service.delete_version(project_id, version_id, username)
    return jsonify(payload), status


def register_routes(bp, current_username_getter):
    @login_required
    def _project_download_stats(project_id: str):
        return version_download_stats_response(project_id, current_username_getter())

    @admin_required("projects")
    def _versions_list(project_id: str):
        return versions_list_response(project_id, current_username_getter())

    @login_required
    def _version_downloads(project_id: str, version_id: str):
        return version_downloads_response(project_id, version_id, current_username_getter())

    @admin_required("projects")
    def _versions_create(project_id: str):
        return versions_create_response(project_id, current_username_getter())

    @admin_required("projects")
    def _versions_update(project_id: str):
        return versions_update_response(project_id, current_username_getter())

    @admin_required("projects")
    def _versions_delete(project_id: str, version_id: str):
        return versions_delete_response(project_id, version_id, current_username_getter())

    bp.add_url_rule("/api/projects/<project_id>/download-stats", endpoint="project_download_stats", view_func=_project_download_stats)
    bp.add_url_rule("/admin/projects/<project_id>/versions/list", endpoint="project_versions_list", view_func=_versions_list)
    bp.add_url_rule(
        "/api/projects/<project_id>/versions/<version_id>/downloads",
        endpoint="api_version_downloads",
        view_func=_version_downloads,
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/versions/create",
        endpoint="project_versions_create",
        view_func=_versions_create,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/versions/update",
        endpoint="project_versions_update",
        view_func=_versions_update,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/versions/delete/<version_id>",
        endpoint="project_versions_delete",
        view_func=_versions_delete,
        methods=["DELETE"],
    )
    # 兼容旧前端删除地址，避免缓存旧脚本时出现 404。
    bp.add_url_rule(
        "/admin/projects/<project_id>/versions/<version_id>/delete",
        endpoint="project_versions_delete_legacy",
        view_func=_versions_delete,
        methods=["POST", "DELETE"],
    )
