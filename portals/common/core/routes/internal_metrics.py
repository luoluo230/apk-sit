# -*- coding: utf-8 -*-
"""Internal Prometheus metrics endpoints."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from services.security.webhook_auth import ip_allowed, webhook_auth_disabled

bp = Blueprint("internal_metrics", __name__)


@bp.route("/api/internal/metrics/release", methods=["GET"])
def release_metrics():
    if not webhook_auth_disabled() and not ip_allowed(request):
        return jsonify({"ok": False, "error": "client_ip_not_allowed"}), 401
    from services.monitor.release_metrics import render_prometheus_release_metrics

    body, content_type = render_prometheus_release_metrics()
    return Response(body, mimetype=content_type)
