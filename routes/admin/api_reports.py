"""Admin reports route adapters."""

from __future__ import annotations

from flask import jsonify, request

from services.authz import admin_required
from services.admin import report_service


def reports_create_template_response(username: str):
    payload, status = report_service.create_template(username, request.get_json(silent=True) or {})
    return jsonify(payload), status


def reports_run_response(username: str, template_id: str):
    return report_service.run_template(username, template_id)


def register_routes(bp, current_username_getter):
    @admin_required("reports")
    def _reports_create_template():
        return reports_create_template_response(current_username_getter())

    @admin_required("reports")
    def _reports_run(template_id: str):
        return reports_run_response(current_username_getter(), template_id)

    bp.add_url_rule(
        "/admin/reports/templates",
        endpoint="admin_reports_create_template",
        view_func=_reports_create_template,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/reports/run/<template_id>",
        endpoint="admin_reports_run",
        view_func=_reports_run,
    )
