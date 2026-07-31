# -*- coding: utf-8 -*-
"""Legacy commercial release endpoints — redirect / thin wrappers only."""

from __future__ import annotations

from flask import Blueprint, jsonify, redirect, request, session

from models.data import projects_db
from services.authz import admin_required_any, has_scope

bp = Blueprint("commercial_release_routes", __name__, url_prefix="")


@bp.route("/admin/build/commercial-release")
@admin_required_any("projects", "build")
def commercial_release_page():
    """Legacy commercial release UI — redirect to project delivery hub."""
    project_id = (request.args.get("project_id") or "").strip()
    if project_id and project_id in projects_db:
        return redirect(f"/admin/projects/{project_id}/overview?legacy=commercial-release")
    return redirect("/admin/projects?legacy=commercial-release")


@bp.route("/admin/build/commercial-release/trigger", methods=["POST"])
@bp.route("/api/admin/build/commercial-release/trigger", methods=["POST"])
@admin_required_any("projects", "build")
def trigger_commercial_release():
    """Legacy trigger — delegates to release-order quick-build when version context is present."""
    if not has_scope("build.trigger"):
        return jsonify({"success": False, "error": "无权限触发构建"}), 403

    data = request.get_json(silent=True) or {}
    if not data and request.get_data():
        return jsonify({"success": False, "error": "请求体不是合法 JSON"}), 400

    project_id = (data.get("_project_id") or "").strip()
    version_id = (data.get("_version_id") or "").strip()
    if not project_id or not version_id:
        return jsonify({
            "success": False,
            "error": "legacy trigger 需 _project_id 与 _version_id；请改用 POST /api/projects/{id}/versions/{vid}/quick-build",
            "deprecated": True,
        }), 400

    try:
        from services.release.release_order_service import ensure_draft_release_order, request_build as ro_request_build

        actor = session.get("user") or ""
        draft = ensure_draft_release_order(project_id, version_id, actor)
        updated = ro_request_build(project_id, draft.get("release_order_id") or "", actor)
        build_number = ((updated.get("payload") or {}).get("build_job_id")) or ""
        successor = f"/api/projects/{project_id}/versions/{version_id}/quick-build"
        return jsonify({
            "success": True,
            "build_number": build_number,
            "release_order_id": draft.get("release_order_id"),
            "pipeline_source": "version_group",
            "deprecated": True,
            "prefer": successor,
        }), 200, {"Deprecation": "true", "Link": f"</{successor.lstrip('/')}>; rel=\"successor-version\""}
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc), "deprecated": True}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"通过发布单触发构建失败：{exc}", "deprecated": True}), 500


from routes.commercial_release_legacy import register_commercial_release_legacy_routes

register_commercial_release_legacy_routes(bp)

