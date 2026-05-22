"""Admin settings route adapters."""

from __future__ import annotations

from flask import jsonify, request

from services.authz import admin_required, has_scope
from services.admin import settings_service


def settings_save_response(setting_keys, username: str):
    payload, status = settings_service.save_settings(request.get_json(silent=True) or {}, setting_keys, username)
    return jsonify(payload), status


def register_routes(bp, setting_keys, current_username_getter):
    @admin_required("system_settings")
    def _settings_save():
        if not has_scope("system_settings.manage"):
            return jsonify({"error": "无权限修改系统设置"}), 403
        return settings_save_response(setting_keys, current_username_getter())

    bp.add_url_rule("/admin/settings/save", endpoint="admin_settings_save", view_func=_settings_save, methods=["POST"])
