"""Admin audit route adapters."""

from __future__ import annotations

import io

from flask import request, send_file

from services.authz import admin_required
from services.admin import audit_service


def audit_export_response():
    user_filter = (request.args.get("user") or "").strip()
    action_filter = (request.args.get("action") or "").strip()
    date_from = (request.args.get("date_from") or "").strip()[:10]
    date_to = (request.args.get("date_to") or "").strip()[:10]
    keyword = (request.args.get("keyword") or "").strip()
    data, filename = audit_service.export_csv(user_filter, action_filter, date_from, date_to, keyword)
    return send_file(io.BytesIO(data), as_attachment=True, download_name=filename, mimetype="text/csv")


def register_routes(bp):
    @admin_required("audit_log")
    def _audit_export():
        return audit_export_response()

    bp.add_url_rule("/admin/audit-log/export", endpoint="admin_audit_log_export", view_func=_audit_export)
