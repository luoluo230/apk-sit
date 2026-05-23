"""Admin user route adapters."""

from __future__ import annotations

from flask import jsonify, request

from services.authz import admin_required
from services.admin import user_service


def users_list_response():
    payload, status = user_service.list_users()
    return jsonify(payload), status


def users_get_response(username: str):
    payload, status = user_service.get_user(username)
    return jsonify(payload), status


def users_create_response(min_password_len: int):
    payload, status = user_service.create_user(request.get_json(silent=True) or {}, min_password_len)
    return jsonify(payload), status


def users_update_response():
    payload, status = user_service.update_user(request.get_json(silent=True) or {})
    return jsonify(payload), status


def users_reset_password_response(min_password_len: int):
    payload, status = user_service.reset_password(request.get_json(silent=True) or {}, min_password_len)
    return jsonify(payload), status


def users_delete_response(username: str):
    payload, status = user_service.delete_user(username)
    return jsonify(payload), status


def register_routes(bp, password_min_getter):
    @admin_required("user_management")
    def _users_list():
        return users_list_response()

    @admin_required("user_management")
    def _users_get(username: str):
        return users_get_response(username)

    @admin_required("user_management")
    def _users_create():
        return users_create_response(password_min_getter())

    @admin_required("user_management")
    def _users_update():
        return users_update_response()

    @admin_required("user_management")
    def _users_reset_password():
        return users_reset_password_response(password_min_getter())

    @admin_required("user_management")
    def _users_delete(username: str):
        return users_delete_response(username)

    bp.add_url_rule("/admin/users/list", endpoint="admin_users_list", view_func=_users_list)
    bp.add_url_rule("/admin/users/get/<username>", endpoint="admin_users_get", view_func=_users_get)
    bp.add_url_rule("/admin/users/create", endpoint="admin_users_create", view_func=_users_create, methods=["POST"])
    bp.add_url_rule("/admin/users/update", endpoint="admin_users_update", view_func=_users_update, methods=["POST"])
    bp.add_url_rule(
        "/admin/users/reset-password",
        endpoint="admin_users_reset_password",
        view_func=_users_reset_password,
        methods=["POST"],
    )
    bp.add_url_rule("/admin/users/delete/<username>", endpoint="admin_users_delete", view_func=_users_delete, methods=["DELETE"])
