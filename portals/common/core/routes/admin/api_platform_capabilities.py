# -*- coding: utf-8 -*-
"""Platform capability registry API adapters. Plan P1-03."""

from __future__ import annotations

from flask import jsonify

from models.data import projects_db
from services.authz import admin_required
from services.build.platform_capability import list_platform_capabilities, list_project_enabled_platforms


def platform_capabilities_response():
    rows = list_platform_capabilities()
    return jsonify({"ok": True, "data": {"platforms": rows, "total": len(rows)}}), 200


def project_enabled_platforms_response(project_id: str):
    rows = list_project_enabled_platforms(project_id)
    return jsonify({"ok": True, "data": {"project_id": project_id, "platforms": rows, "total": len(rows)}}), 200


def register_routes(bp):
    @admin_required("projects")
    def _platform_capabilities():
        return platform_capabilities_response()

    @admin_required("projects")
    def _project_enabled_platforms(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        return project_enabled_platforms_response(project_id)

    bp.add_url_rule(
        "/api/admin/platforms/capabilities",
        endpoint="admin_platform_capabilities",
        view_func=_platform_capabilities,
    )
    bp.add_url_rule(
        "/api/admin/projects/<project_id>/platforms/enabled",
        endpoint="admin_project_platforms_enabled",
        view_func=_project_enabled_platforms,
    )
