"""Admin user CSV import/export route adapters."""

from __future__ import annotations

import io

from flask import jsonify, request, send_file

from services.authz import admin_required
from services.admin import user_transfer_service


def users_export_response():
    csv_bytes, filename = user_transfer_service.export_users_csv()
    return send_file(io.BytesIO(csv_bytes), as_attachment=True, download_name=filename, mimetype="text/csv")


def users_import_response(min_password_len: int):
    file_storage = request.files.get("file")
    payload, status = user_transfer_service.import_users_csv(file_storage, min_password_len)
    return jsonify(payload), status


def register_routes(bp, password_min_getter):
    @admin_required("user_management")
    def _users_export():
        return users_export_response()

    @admin_required("user_management")
    def _users_import():
        return users_import_response(password_min_getter())

    bp.add_url_rule("/admin/users/export", endpoint="admin_users_export", view_func=_users_export)
    bp.add_url_rule("/admin/users/import", endpoint="admin_users_import", view_func=_users_import, methods=["POST"])
