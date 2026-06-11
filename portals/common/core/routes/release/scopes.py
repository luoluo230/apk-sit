# -*- coding: utf-8 -*-
"""ReleaseScope / ReleaseBundle / Manifest API."""

from __future__ import annotations

import os

from flask import jsonify, request

from routes.auth import admin_required
from routes.release import release_bp
from services.ops.helpers import _render_ops_page
from services.release.bundle_service import get_bundle, list_bundles, run_scope_precheck
from services.release.manifest_service import bootstrap_scopes_for_project, get_manifest, list_manifests, upsert_manifest
from services.release.release_context import resolve_release_context
from services.release.scope_resolver import list_scopes, resolve_scope


@release_bp.route("/admin/release/onboarding")
@admin_required("gm_ops")
def release_onboarding_page():
    tpl_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "ops_release_onboarding.html")
    with open(tpl_path, encoding="utf-8") as fh:
        content = fh.read()
    return _render_ops_page(content, "发版平台 Onboarding", active_page="release_onboarding", project_id="GomeKu", env_key="production")


@release_bp.route("/api/release/scopes")
def release_scopes_list():
    project_id = (request.args.get("project_id") or "").strip()
    rows = list_scopes(project_id)
    return jsonify({"ok": True, "count": len(rows), "scopes": rows})


@release_bp.route("/api/release/scopes/<path:scope_id>")
def release_scope_detail(scope_id: str):
    from services.release.storage import find_scope as _find_scope

    scope_row = _find_scope(scope_id)
    if not scope_row:
        return jsonify({"ok": False, "error": "RELEASE_SCOPE_NOT_FOUND", "scope_id": scope_id}), 404
    ctx = resolve_release_context(
        str(scope_row.get("project_id") or ""),
        str(scope_row.get("env_key") or ""),
        str(scope_row.get("channel_id") or ""),
    )
    active_bundle_id = ctx.get("active_bundle_id") or ""
    return jsonify(
        {
            "ok": True,
            "scope": scope_row,
            "resolved": {
                "topology_id": ctx.get("server_snapshot", {}).get("topology_id"),
                "runtime_run_id": ctx.get("server_snapshot", {}).get("runtime_run_id"),
                "topology_version_label": ctx.get("server_snapshot", {}).get("topology_version_label"),
                "profile_source": ctx.get("profile_source"),
                "network_profile_preview": ctx.get("network_profile"),
                "active_bundle_id": active_bundle_id,
            },
        }
    )


@release_bp.route("/api/release/scopes/upsert", methods=["POST"])
@admin_required("gm_ops")
def release_scope_upsert():
    payload = request.get_json(silent=True) or {}
    scope_id = str(payload.get("scope_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = str(payload.get("env_key") or "").strip()
    channel_id = str(payload.get("channel_id") or "").strip()
    if not project_id or not channel_id:
        return jsonify({"ok": False, "error": "project_id and channel_id required"}), 400
    scope = resolve_scope(project_id, env_key, channel_id, auto_create=False) or {}
    merged = dict(scope)
    merged.update(payload)
    if scope_id:
        merged["scope_id"] = scope_id
    from services.release.storage import upsert_scope

    saved = upsert_scope(merged)
    return jsonify({"ok": True, "scope": saved})


@release_bp.route("/api/release/scopes/<path:scope_id>/precheck")
@admin_required("gm_ops")
def release_scope_precheck(scope_id: str):
    from services.release.storage import find_scope as _find_scope
    from routes.gm_ops import _find_best_release

    scope_row = _find_scope(scope_id)
    if not scope_row:
        return jsonify({"ok": False, "error": "RELEASE_SCOPE_NOT_FOUND"}), 404
    project_id = str(scope_row.get("project_id") or "")
    env = str(scope_row.get("env_key") or "")
    channel = str(scope_row.get("channel_id") or "")
    platform = (request.args.get("platform") or "android").strip().lower()
    version_name = (request.args.get("version_name") or "").strip()
    release = _find_best_release(project_id, env, channel, platform, version_name, published_only=False)
    if not release:
        return jsonify({"ok": False, "error": "release not found for scope"}), 404
    result = run_scope_precheck(scope_row, release)
    status = 200 if result.get("ok") else 412
    if not result.get("topology_runtime_aligned"):
        status = 409
    return jsonify({"ok": bool(result.get("ok")), "precheck": result}), status


@release_bp.route("/api/release/bundles")
def release_bundles_list():
    project_id = (request.args.get("project_id") or "").strip()
    scope_id = (request.args.get("scope_id") or "").strip()
    status = (request.args.get("status") or "").strip()
    rows = list_bundles(project_id=project_id, scope_id=scope_id, status=status)
    return jsonify({"ok": True, "count": len(rows), "bundles": rows})


@release_bp.route("/api/release/bundles/<bundle_id>")
def release_bundle_detail(bundle_id: str):
    row = get_bundle(bundle_id)
    if not row:
        return jsonify({"ok": False, "error": "RELEASE_BUNDLE_NOT_FOUND"}), 404
    return jsonify({"ok": True, "bundle": row})


@release_bp.route("/api/release/manifests")
def release_manifests_list():
    rows = list_manifests()
    return jsonify({"ok": True, "count": len(rows), "manifests": rows})


@release_bp.route("/api/release/manifests/<project_id>")
def release_manifest_detail(project_id: str):
    row = get_manifest(project_id)
    if not row:
        return jsonify({"ok": False, "error": "manifest not found"}), 404
    return jsonify({"ok": True, "manifest": row})


@release_bp.route("/api/release/manifests/upsert", methods=["POST"])
@admin_required("gm_ops")
def release_manifest_upsert():
    payload = request.get_json(silent=True) or {}
    try:
        saved = upsert_manifest(payload)
    except ValueError as ex:
        return jsonify({"ok": False, "error": str(ex)}), 400

    project_bootstrapped = False
    pid = str(saved.get("project_id") or "").strip()
    if pid and payload.get("bootstrap_project", False):
        project_bootstrapped = _ensure_project_db_entry(pid, saved)

    return jsonify({"ok": True, "manifest": saved, "project_bootstrapped": project_bootstrapped})


def _ensure_project_db_entry(project_id: str, manifest: dict) -> bool:
    from datetime import datetime
    from models.data import projects_db, save_projects

    if project_id in projects_db:
        return False
    channels = []
    for mc in (manifest.get("channels") or []):
        if isinstance(mc, dict) and str(mc.get("channel_id") or "").strip():
            channels.append(str(mc["channel_id"]).strip())
    projects_db[project_id] = {
        "name": str(manifest.get("project_slug") or project_id),
        "name_en": project_id,
        "description": "",
        "created_at": datetime.now().isoformat(),
        "created_by": "release-onboarding",
        "order": len(projects_db) + 1,
        "status": "active",
        "channels": channels,
        "game_id": str(manifest.get("game_id") or "").strip(),
        "game_key": str(manifest.get("game_key") or "").strip(),
    }
    save_projects()
    return True


@release_bp.route("/api/release/manifests/<project_id>/bootstrap-scopes", methods=["POST"])
@admin_required("gm_ops")
def release_manifest_bootstrap_scopes(project_id: str):
    rows = bootstrap_scopes_for_project(project_id)
    return jsonify({"ok": True, "count": len(rows), "scopes": rows})
