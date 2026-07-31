# -*- coding: utf-8 -*-
"""Scope rollback / unpublish API routes."""

from __future__ import annotations

from flask import jsonify, request

from models.data import projects_db
from services.authz import admin_required
from services.release.release_order_service import rollback_scope_to_bundle, unpublish_scope

from routes.delivery.helpers import actor as _actor


def register_scope_lifecycle_routes(bp) -> None:
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
