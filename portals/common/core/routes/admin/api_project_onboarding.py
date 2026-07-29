# -*- coding: utf-8 -*-
"""Admin project onboarding API adapters."""

from __future__ import annotations

from flask import jsonify, request

from services.admin import channel_assignment_service, project_onboarding_service


def projects_onboard_response(actor: str, tenant_id: str):
    payload, status = project_onboarding_service.onboard_project(
        request.get_json(force=True, silent=True) or {},
        actor,
        tenant_id,
    )
    return jsonify(payload), status


def projects_channels_assign_response(project_id: str, actor: str):
    payload, status = channel_assignment_service.assign_channels(
        project_id,
        request.get_json(force=True, silent=True) or {},
        actor,
    )
    return jsonify(payload), status


def register_routes(bp, *, current_username_getter, tenant_id_getter, projects_db, can_edit_lookup):
    from services.authz import admin_required

    @admin_required("projects")
    def _projects_onboard():
        return projects_onboard_response(current_username_getter(), tenant_id_getter())

    @admin_required("projects")
    def _projects_channels_assign(project_id: str):
        if project_id not in projects_db or not can_edit_lookup(project_id):
            return jsonify({"error": "无权限"}), 403
        return projects_channels_assign_response(project_id, current_username_getter())

    bp.add_url_rule(
        "/api/admin/projects/onboard",
        endpoint="admin_projects_onboard",
        view_func=_projects_onboard,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/channels/assign",
        endpoint="admin_projects_channels_assign",
        view_func=_projects_channels_assign,
        methods=["POST"],
    )
