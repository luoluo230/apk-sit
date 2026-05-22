"""Admin site-config route adapters."""

from __future__ import annotations

from flask import jsonify, request

from services.authz import admin_required
from services.admin import site_config_service


def site_config_save_company_response():
    payload, status = site_config_service.save_company(request.get_json(silent=True) or {})
    return jsonify(payload), status


def site_config_save_portal_response(portal_kind: str):
    payload, status = site_config_service.save_portal(portal_kind, request.get_json(silent=True) or {})
    return jsonify(payload), status


def site_config_visual_editor_save_response(portal_kind: str, normalize_modules_fn):
    payload, status = site_config_service.save_visual_editor(portal_kind, request.get_json(silent=True) or {}, normalize_modules_fn)
    return jsonify(payload), status


def register_routes(bp, normalize_modules_fn):
    @admin_required("system_settings")
    def _save_company():
        return site_config_save_company_response()

    @admin_required("system_settings")
    def _save_player():
        return site_config_save_portal_response("player")

    @admin_required("system_settings")
    def _save_dev():
        return site_config_save_portal_response("dev")

    @admin_required("system_settings")
    def _visual_editor_save(portal_kind: str):
        return site_config_visual_editor_save_response(portal_kind, normalize_modules_fn)

    bp.add_url_rule("/admin/site-config/company", endpoint="admin_site_config_save_company", view_func=_save_company, methods=["POST"])
    bp.add_url_rule(
        "/admin/site-config/portal/player",
        endpoint="admin_site_config_save_player_portal",
        view_func=_save_player,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/site-config/portal/dev",
        endpoint="admin_site_config_save_dev_portal",
        view_func=_save_dev,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/site-config/editor/<portal_kind>/save",
        endpoint="admin_site_config_visual_editor_save",
        view_func=_visual_editor_save,
        methods=["POST"],
    )
