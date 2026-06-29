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


def version_apk_download_info_response(project_id: str, version_id: str, username: str):
    local_base = (request.host_url or "").strip().rstrip("/")
    payload, status = version_service.get_apk_download_info(
        project_id,
        version_id,
        username,
        local_base_url=local_base or None,
    )
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


def versions_delete_group_response(project_id: str, username: str):
    payload = request.get_json(silent=True) or {}
    version_name = str(payload.get("version_name") or "").strip()
    env_key = str(payload.get("env_key") or "").strip() or None
    platform = str(payload.get("platform") or "").strip() or None
    result, status = version_service.delete_version_group(
        project_id, version_name, username, env_key=env_key, platform=platform
    )
    return jsonify(result), status


def version_groups_list_response(project_id: str, username: str):
    env_key = str(request.args.get("env_key") or "").strip()
    platform = str(request.args.get("platform") or "").strip()
    payload, status = version_service.list_version_groups(
        project_id,
        username,
        env_key=env_key or None,
        platform=platform or None,
    )
    return jsonify(payload), status


def version_groups_create_response(project_id: str, username: str):
    payload, status = version_service.create_version_group(project_id, username, request.get_json(silent=True) or {})
    return jsonify(payload), status


def version_groups_update_response(project_id: str, username: str):
    payload, status = version_service.update_version_group(project_id, username, request.get_json(silent=True) or {})
    return jsonify(payload), status


def version_effective_pipeline_response(project_id: str, version_id: str, username: str):
    payload, status = version_service.get_version_effective_pipeline(project_id, version_id, username)
    return jsonify(payload), status


def version_runtime_preview_response(project_id: str, version_id: str, username: str):
    overrides = {}
    for key in (
        "resource_server_url",
        "catalog_file_name",
        "min_client_version",
        "rollout_percentage",
        "force_update",
        "is_revoked",
        "config_environment",
    ):
        raw = request.args.get(key)
        if raw is None:
            continue
        if key in ("force_update", "is_revoked"):
            overrides[key] = str(raw).lower() in ("1", "true", "yes", "on")
        elif key == "rollout_percentage":
            try:
                overrides[key] = int(raw)
            except ValueError:
                pass
        else:
            overrides[key] = raw
    payload, status = version_service.get_version_runtime_preview(
        project_id,
        version_id,
        username,
        overrides=overrides or None,
    )
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

    @login_required
    def _version_apk_download_info(project_id: str, version_id: str):
        return version_apk_download_info_response(project_id, version_id, current_username_getter())

    @admin_required("projects")
    def _versions_create(project_id: str):
        return versions_create_response(project_id, current_username_getter())

    @admin_required("projects")
    def _versions_update(project_id: str):
        return versions_update_response(project_id, current_username_getter())

    @admin_required("projects")
    def _versions_delete(project_id: str, version_id: str):
        return versions_delete_response(project_id, version_id, current_username_getter())

    @admin_required("projects")
    def _versions_delete_group(project_id: str):
        return versions_delete_group_response(project_id, current_username_getter())

    @admin_required("projects")
    def _version_groups_list(project_id: str):
        return version_groups_list_response(project_id, current_username_getter())

    @admin_required("projects")
    def _version_groups_create(project_id: str):
        return version_groups_create_response(project_id, current_username_getter())

    @admin_required("projects")
    def _version_groups_update(project_id: str):
        return version_groups_update_response(project_id, current_username_getter())

    @admin_required("projects")
    def _version_runtime_preview(project_id: str, version_id: str):
        return version_runtime_preview_response(project_id, version_id, current_username_getter())

    @login_required
    def _version_effective_pipeline(project_id: str, version_id: str):
        return version_effective_pipeline_response(project_id, version_id, current_username_getter())

    bp.add_url_rule("/api/projects/<project_id>/download-stats", endpoint="project_download_stats", view_func=_project_download_stats)
    bp.add_url_rule("/admin/projects/<project_id>/versions/list", endpoint="project_versions_list", view_func=_versions_list)
    bp.add_url_rule(
        "/api/projects/<project_id>/versions/<version_id>/downloads",
        endpoint="api_version_downloads",
        view_func=_version_downloads,
    )
    bp.add_url_rule(
        "/api/projects/<project_id>/versions/<version_id>/apk-download-info",
        endpoint="api_version_apk_download_info",
        view_func=_version_apk_download_info,
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
    bp.add_url_rule(
        "/admin/projects/<project_id>/versions/delete-group",
        endpoint="project_versions_delete_group",
        view_func=_versions_delete_group,
        methods=["POST", "DELETE"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/version-groups",
        endpoint="project_version_groups_list",
        view_func=_version_groups_list,
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/version-groups/create",
        endpoint="project_version_groups_create",
        view_func=_version_groups_create,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/versions/<version_id>/runtime-preview",
        endpoint="project_version_runtime_preview",
        view_func=_version_runtime_preview,
    )
    bp.add_url_rule(
        "/api/projects/<project_id>/versions/<version_id>/effective-pipeline",
        endpoint="api_version_effective_pipeline",
        view_func=_version_effective_pipeline,
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/version-groups/update",
        endpoint="project_version_groups_update",
        view_func=_version_groups_update,
        methods=["POST"],
    )
