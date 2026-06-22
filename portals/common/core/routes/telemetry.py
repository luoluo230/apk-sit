# -*- coding: utf-8 -*-
"""Public client telemetry ingestion routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from services.client_telemetry import ingest, list_recent

bp = Blueprint("telemetry", __name__)


def _require_admin_session():
    if not session.get("user"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.route("/api/public/client-telemetry", methods=["POST"])
def client_telemetry_ingest():
    payload = request.get_json(silent=True) or {}
    if not payload:
        return jsonify({"ok": False, "error": "empty payload"}), 400
    row = ingest(payload)
    return jsonify({"ok": True, "id": row.get("id"), "received_at": row.get("received_at")}), 200


@bp.route("/api/public/client-telemetry/recent")
def client_telemetry_recent():
    denied = _require_admin_session()
    if denied:
        return denied
    limit_text = str(request.args.get("limit") or "50").strip()
    try:
        limit = max(1, min(int(limit_text), 300))
    except Exception:
        limit = 50
    rows = list_recent(limit=limit)
    return jsonify({"ok": True, "count": len(rows), "events": rows}), 200
