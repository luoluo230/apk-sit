# -*- coding: utf-8
"""Project workspace pages: versions, build config, build history, test devices."""

from __future__ import annotations

from urllib.parse import urlencode

from flask import abort, jsonify, redirect, render_template, request, session

from models.data import (
    can_edit_project,
    can_view_project,
    project_versions_db,
    projects_db,
)
from services.authz import admin_required, admin_required_any


def register_routes(bp, *, current_username):
    @bp.route("/api/admin/projects/<project_id>/test-devices", methods=["GET", "POST"])
    @admin_required("projects")
    def project_test_devices_api(project_id):
        if project_id not in projects_db:
            return jsonify({"error": "项目不存在"}), 404
        if not can_edit_project(project_id, current_username()):
            return jsonify({"error": "无权限"}), 403
        from services.test_device_service import list_devices, save_device

        if request.method == "GET":
            return jsonify({"devices": list_devices(project_id)})
        data = request.get_json(silent=True) or {}
        row, err = save_device(project_id, data)
        if err:
            return jsonify({"error": err}), 400
        return jsonify({"device": row})

    @bp.route("/api/admin/projects/<project_id>/test-devices/<record_id>", methods=["DELETE"])
    @admin_required("projects")
    def project_test_device_delete(project_id, record_id):
        if project_id not in projects_db:
            return jsonify({"error": "项目不存在"}), 404
        if not can_edit_project(project_id, current_username()):
            return jsonify({"error": "无权限"}), 403
        from services.test_device_service import delete_device

        err = delete_device(project_id, record_id)
        if err:
            return jsonify({"error": err}), 400
        return jsonify({"success": True})

    @bp.route("/admin/projects/<project_id>")
    @admin_required("projects")
    def project_detail_page(project_id):
        """项目详情页：进入统一项目交付总览。"""
        if project_id not in projects_db:
            abort(404)
        if not can_view_project(project_id, current_username()):
            abort(403)
        return redirect(f"/admin/projects/{project_id}/overview")

    @bp.route("/api/admin/unity-versions/detect")
    @admin_required_any("projects", "jenkins")
    def api_admin_detect_unity_versions():
        """兼容旧接口：返回版本库中有效项（version/path/category/note）。"""
        from services.unity_version_catalog_service import list_active_for_selectors

        versions = list_active_for_selectors()
        return jsonify({"success": True, "versions": versions})

    @bp.route("/admin/projects/<project_id>/versions")
    @admin_required("projects")
    def project_versions_page(project_id):
        """Project-owned VersionCode workspace."""
        if project_id not in projects_db:
            abort(404)
        if not can_view_project(project_id, current_username()):
            abort(403)

        env_key = str(request.args.get("env_key") or "").strip()
        channel_filter = str(request.args.get("channel_id") or "").strip()
        platform_filter = str(request.args.get("platform") or "").strip().lower()
        can_edit = can_edit_project(project_id, current_username())
        from services.ops.helpers import _render_ops_page

        from services.baas.helpers import project_server_mode

        content = render_template(
            "project_versions_workspace.html",
            project_id=project_id,
            env_key=env_key,
            platform_filter=platform_filter,
            channel_filter=channel_filter,
            can_edit=can_edit,
            server_mode=project_server_mode(project_id),
        )
        return _render_ops_page(
            content,
            "版本管理",
            active_page="versions",
            project_id=project_id,
            env_key=env_key or "development",
            breadcrumb_module="交付发版",
        )

    @bp.route("/admin/projects/<project_id>/version-groups/build-config")
    @admin_required("projects")
    def project_version_group_build_config_page(project_id):
        """版本组管线模板配置（无 anchor VersionCode 时）。"""
        if project_id not in projects_db:
            abort(404)
        if not can_view_project(project_id, current_username()):
            abort(403)

        from services.commercial_release_plan import DEFAULT_RESOURCE_SERVER
        from services.ops.helpers import _render_ops_page
        from services.release.env_registry import normalize_release_env_key

        entry_from = (request.args.get("from") or "").strip().lower()
        if entry_from not in ("version-group", "release-order"):
            entry_from = "version-group"

        version_name = (request.args.get("version_name") or "").strip()
        if not version_name:
            abort(404)
        env_key = normalize_release_env_key(request.args.get("env_key") or "development", project_id=project_id)
        platform = (request.args.get("platform") or "android").strip().lower()

        versions = project_versions_db.get(project_id) or []
        if not isinstance(versions, list):
            versions = []
        anchor = None
        anchor_at = ""
        for row in versions:
            if str(row.get("version_name") or "").strip() != version_name:
                continue
            row_ek = normalize_release_env_key(
                row.get("env_key") or row.get("stage") or "development",
                project_id=project_id,
            )
            if row_ek != env_key:
                continue
            if str(row.get("platform") or "").strip().lower() != platform:
                continue
            at = str(row.get("updated_at") or "")
            if at >= anchor_at:
                anchor_at = at
                anchor = row
        if anchor and anchor.get("id"):
            qs = urlencode({k: v for k, v in request.args.items() if v})
            return redirect(
                f"/admin/projects/{project_id}/versions/{anchor['id']}/build-config{f'?{qs}' if qs else ''}"
            )

        return_params = {
            "env_key": env_key,
            "platform": platform,
            "version_name": version_name,
        }
        if entry_from == "release-order":
            release_order_id = (request.args.get("release_order_id") or "").strip()
            if release_order_id:
                return_params["release_order_id"] = release_order_id
                return_params["version_id"] = (request.args.get("version_id") or "").strip()
                return_params["channel_id"] = (request.args.get("channel_id") or "").strip()
                return_params["version_code"] = (request.args.get("version_code") or "").strip()
                return_url = (
                    f"/admin/projects/{project_id}/release-orders/{release_order_id}/edit?"
                    f"{urlencode({k: v for k, v in return_params.items() if v})}"
                )
                return_label = "返回编辑发布单"
            else:
                return_url = (
                    f"/admin/projects/{project_id}/release-orders/new?"
                    f"{urlencode({k: v for k, v in return_params.items() if v})}"
                )
                return_label = "返回新建发布单"
            active_page = "versions"
        else:
            return_url = (
                f"/admin/projects/{project_id}/versions?"
                f"{urlencode({k: v for k, v in return_params.items() if v})}"
            )
            return_label = "返回版本工作台"
            active_page = "versions"

        can_edit = can_edit_project(project_id, current_username())
        content = render_template(
            "project_version_build_config.html",
            project_id=project_id,
            version_id="",
            version_label=f"{version_name} / 版本组管线模板",
            env_key=env_key,
            can_edit=can_edit,
            return_url=return_url,
            return_label=return_label,
            entry_from=entry_from,
            edit_scope_mode="version_group",
            version_name=version_name,
            platform=platform,
            workflow_url="",
            default_resource_server_url=DEFAULT_RESOURCE_SERVER,
        )
        return _render_ops_page(
            content,
            "版本组管线模板",
            active_page=active_page,
            project_id=project_id,
            env_key=env_key,
            extra_css=(
                '<link rel="stylesheet" href="/static/project_delivery.css?v=20260625-layered1">'
                '<link rel="stylesheet" href="/static/release_focus.css?v=20260706-focus-v1">'
                '<link rel="stylesheet" href="/static/project_version_build_config.css?v=20260625-bc-layered1">'
            ),
        )

    @bp.route("/admin/projects/<project_id>/versions/<version_id>/build-config")
    @admin_required("projects")
    def project_version_build_config_page(project_id, version_id):
        """VersionCode / 版本组管线模板构建参数配置。"""
        if project_id not in projects_db:
            abort(404)
        if not can_view_project(project_id, current_username()):
            abort(403)

        from services.commercial_release_plan import DEFAULT_RESOURCE_SERVER
        from services.ops.helpers import _render_ops_page
        from services.release.env_registry import normalize_release_env_key, stage_to_env_key

        versions = project_versions_db.get(project_id) or []
        if not isinstance(versions, list):
            versions = []
        version = next((row for row in versions if str(row.get("id") or "") == str(version_id)), None)
        if not version:
            abort(404)

        env_key = normalize_release_env_key(
            version.get("env_key") or stage_to_env_key(version.get("stage") or ""),
            project_id=project_id,
        )

        entry_from = (request.args.get("from") or "").strip().lower()
        if entry_from not in ("version-group", "release-order"):
            return redirect(
                f"/admin/projects/{project_id}/versions?"
                + urlencode(
                    {
                        "env_key": env_key,
                        "platform": (version.get("platform") or "").strip(),
                        "version_name": (version.get("version_name") or "").strip(),
                    }
                )
            )

        return_keys = (
            "env_key",
            "channel_id",
            "platform",
            "version_name",
            "version_code",
            "release_order_id",
        )
        return_params = {k: (request.args.get(k) or "").strip() for k in return_keys}
        if not return_params.get("env_key"):
            return_params["env_key"] = env_key
        if not return_params.get("channel_id"):
            return_params["channel_id"] = (version.get("channel") or "").strip()
        if not return_params.get("platform"):
            return_params["platform"] = (version.get("platform") or "").strip()
        if not return_params.get("version_name"):
            return_params["version_name"] = (version.get("version_name") or "").strip()
        if not return_params.get("version_code"):
            return_params["version_code"] = (version.get("version_code") or "").strip()
        return_params["version_id"] = version_id
        return_qs = urlencode({k: v for k, v in return_params.items() if v})

        if entry_from == "release-order":
            release_order_id = return_params.get("release_order_id") or ""
            if release_order_id:
                return_url = (
                    f"/admin/projects/{project_id}/release-orders/{release_order_id}/edit"
                    f"{f'?{return_qs}' if return_qs else ''}"
                )
                return_label = "返回编辑发布单"
            else:
                return_url = (
                    f"/admin/projects/{project_id}/release-orders/new{f'?{return_qs}' if return_qs else ''}"
                )
                return_label = "返回新建发布单"
            active_page = "versions"
            page_title = "构建参数摘要"
        else:
            return_url = f"/admin/projects/{project_id}/versions{f'?{return_qs}' if return_qs else ''}"
            return_label = "返回版本工作台"
            active_page = "versions"
            page_title = "版本组管线模板"

        vn = (version.get("version_name") or "").strip()
        vc = (version.get("version_code") or "").strip()
        if entry_from == "version-group":
            version_label = f"{vn} / 版本组管线模板"
        else:
            version_label = f"{vn} / {vc}" if vn and vc else (vn or vc or version_id)
        can_edit = can_edit_project(project_id, current_username())
        content = render_template(
            "project_version_build_config.html",
            project_id=project_id,
            version_id=version_id,
            version_label=version_label,
            env_key=env_key,
            can_edit=can_edit,
            return_url=return_url,
            return_label=return_label,
            entry_from=entry_from,
            edit_scope_mode="version_group",
            version_name=vn,
            platform=(version.get("platform") or "").strip(),
            workflow_url=f"/admin/projects/{project_id}/versions/{version_id}/workflow",
            default_resource_server_url=DEFAULT_RESOURCE_SERVER,
        )
        return _render_ops_page(
            content,
            page_title,
            active_page=active_page,
            project_id=project_id,
            env_key=env_key,
            extra_css=(
                '<link rel="stylesheet" href="/static/project_delivery.css?v=20260625-layered1">'
                '<link rel="stylesheet" href="/static/release_focus.css?v=20260706-focus-v1">'
                '<link rel="stylesheet" href="/static/project_version_build_config.css?v=20260625-bc-layered1">'
            ),
        )

    @bp.route("/admin/projects/<project_id>/build-history")
    @admin_required_any("projects", "build")
    def project_build_history_page(project_id):
        if project_id not in projects_db:
            abort(404)
        if not can_view_project(project_id, current_username()):
            abort(403)
        scoped = request.args.get("scoped") == "1"
        scope_version_id = (request.args.get("version_id") or "").strip()
        scope_env_key = (request.args.get("env_key") or "").strip()
        if not scoped or (not scope_version_id and not scope_env_key):
            if scope_env_key:
                return redirect(f"/admin/projects/{project_id}/versions?{urlencode({'env_key': scope_env_key})}")
            return redirect(
                f"/admin/projects/{project_id}/overview?{urlencode({'tab': 'environments', 'hint': 'pick_env'})}"
            )
        proj = projects_db[project_id]
        from services.ops.helpers import _render_ops_page

        content = render_template(
            "project_build_history_content.html",
            project_id=project_id,
            project_name=proj.get("name") or project_id,
            can_edit=can_edit_project(project_id, current_username()),
            env_key=request.args.get("env_key") or "production",
            scope_version_id=scope_version_id,
            scope_env_key=scope_env_key,
            scope_platform=(request.args.get("platform") or "").strip(),
            scope_version_name=(request.args.get("version_name") or "").strip(),
            scope_version_code=(request.args.get("version_code") or "").strip(),
            scope_channel_id=(request.args.get("channel_id") or "").strip(),
        )
        return _render_ops_page(
            content,
            "构建与产物",
            active_page="builds",
            project_id=project_id,
            env_key=request.args.get("env_key") or "production",
            breadcrumb_module="交付发版",
            extra_css='<link rel="stylesheet" href="/static/project_build_history.css?v=20260708-bh9">',
        )
