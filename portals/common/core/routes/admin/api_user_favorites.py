# -*- coding: utf-8 -*-
"""User favorites API — page stars and project list stars."""

from __future__ import annotations

from flask import jsonify, request

from services.authz import login_required
from services.admin import user_favorites_service


def register_routes(bp, current_username_getter):
    @login_required
    def _user_favorites_get():
        try:
            data = user_favorites_service.get_user_favorites(current_username_getter())
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @login_required
    def _user_favorites_put():
        payload = request.get_json(silent=True) or {}
        try:
            data = user_favorites_service.save_user_favorites(current_username_getter(), payload)
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @login_required
    def _user_favorites_toggle_page():
        payload = request.get_json(silent=True) or {}
        key = str(payload.get("key") or "").strip()
        active_raw = payload.get("active")
        active = None if active_raw is None else bool(active_raw)
        try:
            data = user_favorites_service.toggle_page_favorite(current_username_getter(), key, active=active)
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @login_required
    def _user_favorites_toggle_project():
        payload = request.get_json(silent=True) or {}
        pid = str(payload.get("project_id") or "").strip()
        active_raw = payload.get("active")
        active = None if active_raw is None else bool(active_raw)
        try:
            data = user_favorites_service.toggle_project_favorite(current_username_getter(), pid, active=active)
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    bp.add_url_rule("/api/user/favorites", endpoint="user_favorites_get", view_func=_user_favorites_get, methods=["GET"])
    bp.add_url_rule("/api/user/favorites", endpoint="user_favorites_put", view_func=_user_favorites_put, methods=["PUT"])
    bp.add_url_rule(
        "/api/user/favorites/toggle-page",
        endpoint="user_favorites_toggle_page",
        view_func=_user_favorites_toggle_page,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/api/user/favorites/toggle-project",
        endpoint="user_favorites_toggle_project",
        view_func=_user_favorites_toggle_project,
        methods=["POST"],
    )
