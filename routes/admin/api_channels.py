"""Admin channel route adapters."""

from __future__ import annotations

from flask import jsonify, request

from services.authz import admin_required
from services.admin import channel_service


def channels_list_response():
    payload, status = channel_service.list_channels()
    return jsonify(payload), status


def channels_create_response():
    payload, status = channel_service.create_channel(request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def channels_update_response():
    payload, status = channel_service.update_channel(request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def channels_delete_response(channel_id: str):
    payload, status = channel_service.delete_channel(channel_id)
    return jsonify(payload), status


def register_routes(bp):
    @admin_required("projects")
    def _channels_list():
        return channels_list_response()

    @admin_required("projects")
    def _channels_create():
        return channels_create_response()

    @admin_required("projects")
    def _channels_update():
        return channels_update_response()

    @admin_required("projects")
    def _channels_delete(channel_id: str):
        return channels_delete_response(channel_id)

    bp.add_url_rule("/admin/channels", endpoint="admin_channels_list", view_func=_channels_list)
    bp.add_url_rule("/admin/channels/create", endpoint="admin_channels_create", view_func=_channels_create, methods=["POST"])
    bp.add_url_rule("/admin/channels/update", endpoint="admin_channels_update", view_func=_channels_update, methods=["POST"])
    bp.add_url_rule(
        "/admin/channels/delete/<channel_id>",
        endpoint="admin_channels_delete",
        view_func=_channels_delete,
        methods=["DELETE"],
    )
