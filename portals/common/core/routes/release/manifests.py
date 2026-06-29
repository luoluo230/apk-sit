# -*- coding: utf-8 -*-
"""ProjectReleaseManifest admin APIs."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.authz import admin_required
from services.release import manifest_service

bp = Blueprint("release_manifests", __name__)


@bp.route("/api/release/manifests/<path:project_id>", methods=["GET"])
@admin_required("versions")
def get_release_manifest(project_id: str):
    pid = str(project_id or "").strip()
    if not pid:
        return jsonify({"ok": False, "error": "project_id required"}), 400
    row = manifest_service.get_manifest(pid)
    if not row:
        return jsonify({"ok": False, "error": "manifest not found", "project_id": pid}), 404
    return jsonify({"ok": True, "manifest": row, "project_id": pid})


@bp.route("/api/release/manifests/upsert", methods=["POST"])
@admin_required("versions")
def upsert_release_manifest():
    payload = request.get_json(silent=True) or {}
    try:
        row = manifest_service.upsert_manifest(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "manifest": row})


@bp.route("/api/release/manifests/<path:project_id>/bootstrap-scopes", methods=["POST"])
@admin_required("versions")
def bootstrap_release_scopes(project_id: str):
    pid = str(project_id or "").strip()
    if not pid:
        return jsonify({"ok": False, "error": "project_id required"}), 400
    try:
        scopes = manifest_service.bootstrap_scopes_for_project(pid)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "project_id": pid, "scopes": scopes, "count": len(scopes)})
