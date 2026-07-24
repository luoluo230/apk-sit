# -*- coding: utf-8
"""Internal build-node heartbeat/register API. Plan: P0-01."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from services.build.build_node_service import register_or_heartbeat
from services.security.webhook_auth import assert_internal_webhook_request

bp = Blueprint("internal_build_nodes", __name__)


def _signature_header() -> str:
    return (
        request.headers.get("X-Signature-SHA256")
        or request.headers.get("X-Build-Node-Signature")
        or request.headers.get("X-Webhook-Signature")
        or ""
    )


@bp.route("/api/internal/build-nodes/heartbeat", methods=["POST"])
def build_node_heartbeat():
    raw = request.get_data(cache=True) or b""
    auth_error = assert_internal_webhook_request(
        request,
        raw,
        _signature_header(),
        "BUILD_NODE_WEBHOOK_SECRET",
        "BUILD_NODE_SHARED_SECRET",
        "JENKINS_BUILD_WEBHOOK_SECRET",
    )
    if auth_error:
        return jsonify({"ok": False, "error": auth_error}), 401
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "invalid payload"}), 400
    try:
        node = register_or_heartbeat(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "node": node})
