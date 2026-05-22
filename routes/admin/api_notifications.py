"""Admin notifications route adapters."""

from __future__ import annotations

from flask import jsonify

from services.authz import admin_required
from services.admin import notification_service


def notifications_mark_read_response(username: str, nid: str):
    payload, status = notification_service.mark_read(username, nid)
    return jsonify(payload), status


def notifications_mark_all_read_response(username: str):
    payload, status = notification_service.mark_all_read(username)
    return jsonify(payload), status


def register_routes(bp, current_username_getter):
    @admin_required("notifications")
    def _mark_read(nid: str):
        return notifications_mark_read_response(current_username_getter(), nid)

    @admin_required("notifications")
    def _mark_all_read():
        return notifications_mark_all_read_response(current_username_getter())

    bp.add_url_rule("/admin/notifications/<nid>/read", endpoint="admin_notification_mark_read", view_func=_mark_read, methods=["POST"])
    bp.add_url_rule(
        "/admin/notifications/read-all",
        endpoint="admin_notifications_read_all",
        view_func=_mark_all_read,
        methods=["POST"],
    )
