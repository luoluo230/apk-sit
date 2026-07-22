# -*- coding: utf-8 -*-
"""Release scope and bundle public APIs for CI gates and clients."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.release.bundle_service import find_active_bundle, list_bundles, run_scope_precheck
from services.release.scope_resolver import resolve_network_profile
from services.release.storage import find_scope

bp = Blueprint("release_scopes", __name__)


@bp.route("/api/release/scopes/<path:scope_id>")
def get_release_scope(scope_id: str):
    sid = str(scope_id or "").strip()
    scope = find_scope(sid)
    if not scope:
        return jsonify({"ok": False, "error": "scope not found", "scope_id": sid}), 404

    version_name = str(request.args.get("version_name") or "1.0.0").strip()
    platform = str(request.args.get("platform") or scope.get("platform") or "android").strip().lower()
    profile, profile_source = resolve_network_profile(scope, version_name=version_name)
    active_bundle = find_active_bundle(sid, platform=platform)
    precheck = {}
    if request.args.get("precheck") in ("1", "true", "yes"):
        from models.data import project_versions_db

        project_id = str(scope.get("project_id") or "")
        version_row = None
        for row in project_versions_db.get(project_id) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("version_name") or "") == version_name:
                version_row = row
                break
        if version_row:
            precheck = run_scope_precheck(scope, version_row)

    return jsonify({
        "ok": True,
        "scope_id": sid,
        "scope": scope,
        "resolved": {
            "scope_id": sid,
            "project_id": scope.get("project_id"),
            "env_key": scope.get("env_key"),
            "channel_id": scope.get("channel_id"),
            "active_bundle_id": scope.get("active_bundle_id") or (active_bundle or {}).get("bundle_id"),
            "platform": platform,
            "network_profile_preview": profile,
            "profile_source": profile_source,
            "precheck": precheck,
        },
    })


@bp.route("/api/release/bundles")
def get_release_bundles():
    scope_id = str(request.args.get("scope_id") or "").strip()
    project_id = str(request.args.get("project_id") or "").strip()
    status = str(request.args.get("status") or request.args.get("publish_status") or "").strip()
    rows = list_bundles(project_id=project_id, scope_id=scope_id, status=status)
    return jsonify({
        "ok": True,
        "scope_id": scope_id or None,
        "bundles": rows,
        "count": len(rows),
    })
