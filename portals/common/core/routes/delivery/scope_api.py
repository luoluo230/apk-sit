# -*- coding: utf-8 -*-
"""Delivery scope, environment, channel, and overview API routes."""

from __future__ import annotations

from flask import jsonify, request

from data.platforms import list_platform_catalog
from models.data import can_edit_project, projects_db
from services.admin import project_env_service, project_service
from services.authz import admin_required
from services.ops.environment_runtime_service import build_environment_runtime_overview
from services.release.bundle_service import list_publishable_bundles
from services.release.release_order_service import (
    activate_bundle_on_scope,
    context_options,
    environment_detail,
    project_overview,
    rollback_scope_to_bundle,
    unpublish_scope,
)
from services.release.release_policy_service import release_order_form_context

from routes.delivery.helpers import actor as _actor


def register_scope_routes(bp) -> None:
    @bp.route("/api/projects/<project_id>/environments/<env_key>/runtime-overview")
    @admin_required("projects")
    def environment_runtime_overview_api(project_id: str, env_key: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        filters = {
            key: str(request.args.get(key) or "").strip()
            for key in (
                "channel_id",
                "platform",
                "service_q",
                "service_cluster",
                "service_category",
                "service_health",
                "service_status",
                "service_page",
                "service_page_size",
            )
        }
        try:
            data = build_environment_runtime_overview(project_id, env_key, filters)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        return jsonify({"ok": True, "data": data})

    @bp.route("/api/projects/<project_id>/environments/<env_key>")
    @admin_required("projects")
    def environment_detail_api(project_id: str, env_key: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        return jsonify({"ok": True, "data": environment_detail(project_id, env_key)})

    @bp.route("/api/release/platform-catalog")
    @admin_required("projects")
    def platform_catalog_api():
        catalog = []
        for row in list_platform_catalog():
            catalog.append({
                "id": str(row.get("id") or "").strip().lower(),
                "name": str(row.get("name") or row.get("id") or ""),
                "description": str(row.get("description") or ""),
                "unity_build_target": str(row.get("unity_build_target") or ""),
            })
        return jsonify({"ok": True, "data": catalog})

    @bp.route("/api/projects/context-catalog")
    @admin_required("projects")
    def project_context_catalog_api():
        return jsonify({"ok": True, "data": [
            {"project_id": pid, "project_name": str((row or {}).get("name") or pid)}
            for pid, row in projects_db.items()
        ]})

    @bp.route("/api/projects/<project_id>/release-order-form-context")
    @admin_required("projects")
    def release_order_form_context_api(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        ctx = release_order_form_context(
            project_id,
            version_id=str(request.args.get("version_id") or "").strip(),
            env_key=str(request.args.get("env_key") or "").strip(),
            channel_id=str(request.args.get("channel_id") or "").strip(),
            platform=str(request.args.get("platform") or "").strip(),
        )
        return jsonify({"ok": True, "data": ctx})

    @bp.route("/api/projects/<project_id>/context-options")
    @admin_required("projects")
    def project_context_options_api(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        return jsonify({
            "ok": True,
            "data": context_options(project_id, str(request.args.get("env_key") or "").strip()),
        })

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

    def _project_platform_mutation(project_id: str, action: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        data = request.get_json(silent=True) or {}
        pid = (data.get("platform_id") or data.get("platform") or "").strip().lower()
        handlers = {
            "add": project_service.add_platform,
            "remove": project_service.remove_platform,
            "disable": project_service.disable_platform,
            "enable": project_service.enable_platform,
        }
        payload, status = handlers[action](project_id, pid)
        return jsonify(payload), status

    @bp.route("/api/projects/<project_id>/platforms/add", methods=["POST"])
    @admin_required("projects")
    def project_platform_add_api(project_id: str):
        return _project_platform_mutation(project_id, "add")

    @bp.route("/api/projects/<project_id>/platforms/remove", methods=["POST"])
    @admin_required("projects")
    def project_platform_remove_api(project_id: str):
        return _project_platform_mutation(project_id, "remove")

    @bp.route("/api/projects/<project_id>/platforms/disable", methods=["POST"])
    @admin_required("projects")
    def project_platform_disable_api(project_id: str):
        return _project_platform_mutation(project_id, "disable")

    @bp.route("/api/projects/<project_id>/platforms/enable", methods=["POST"])
    @admin_required("projects")
    def project_platform_enable_api(project_id: str):
        return _project_platform_mutation(project_id, "enable")

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
        payload, status = project_env_service.add_environment(
            project_id, request.get_json(silent=True) or {}
        )
        return jsonify(payload), status

    @bp.route("/api/projects/<project_id>/environments/<env_key>", methods=["PATCH", "DELETE"])
    @admin_required("projects")
    def project_environment_api(project_id: str, env_key: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        if request.method == "PATCH":
            payload, status = project_env_service.update_environment(
                project_id, env_key, request.get_json(silent=True) or {}
            )
        else:
            payload, status = project_env_service.delete_environment(project_id, env_key)
        return jsonify(payload), status

    @bp.route("/api/projects/<project_id>/environments/<env_key>/delivery-scope", methods=["GET", "PATCH"])
    @admin_required("projects")
    def project_environment_delivery_scope_api(project_id: str, env_key: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        if request.method == "GET":
            payload, status = project_env_service.get_delivery_scope(project_id, env_key)
            return jsonify(payload), status
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        payload, status = project_env_service.update_delivery_scope(
            project_id, env_key, request.get_json(silent=True) or {}
        )
        return jsonify(payload), status

    @bp.route("/api/projects/<project_id>/scopes/<scope_id>/publishable-bundles")
    @admin_required("projects")
    def scope_publishable_bundles_api(project_id: str, scope_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        bundles = list_publishable_bundles(
            scope_id,
            platform=str(request.args.get("platform") or "").strip().lower(),
        )
        return jsonify({"ok": True, "data": bundles})

    @bp.route("/api/projects/<project_id>/scopes/<scope_id>/publish-bundle", methods=["POST"])
    @admin_required("projects")
    def scope_publish_bundle_api(project_id: str, scope_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        payload = request.get_json(silent=True) or {}
        try:
            data = activate_bundle_on_scope(
                project_id,
                scope_id,
                str(payload.get("bundle_id") or "").strip(),
                _actor(),
                mode=str(payload.get("mode") or "full"),
                gray_ratio=str(payload.get("gray_ratio") or ""),
                reason=str(payload.get("reason") or ""),
                release_order_id=str(payload.get("release_order_id") or payload.get("order_id") or "").strip(),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/scopes/<scope_id>/rollback", methods=["POST"])
    @admin_required("projects")
    def scope_rollback_api(project_id: str, scope_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        payload = request.get_json(silent=True) or {}
        try:
            data = rollback_scope_to_bundle(
                project_id,
                scope_id,
                str(payload.get("bundle_id") or "").strip(),
                _actor(),
                reason=str(payload.get("reason") or ""),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/scopes/<scope_id>/unpublish", methods=["POST"])
    @admin_required("projects")
    def scope_unpublish_api(project_id: str, scope_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        payload = request.get_json(silent=True) or {}
        try:
            data = unpublish_scope(
                project_id,
                scope_id,
                _actor(),
                reason=str(payload.get("reason") or ""),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
