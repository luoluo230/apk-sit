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


@bp.route("/admin/build/commercial-release/activate", methods=["POST"])
@admin_required_any("projects", "build")
def activate_commercial_release():
    """Legacy activate — prefer release order publish."""
    data = request.get_json(silent=True) or {}
    project_id = (data.get("_project_id") or data.get("project_id") or "").strip()
    version_id = (data.get("_version_id") or data.get("version_id") or "").strip()
    if not project_id or not version_id:
        return jsonify({
            "success": False,
            "error": "legacy activate 需 project_id 与 version_id；请改用发版流程 publish",
            "deprecated": True,
        }), 400

    try:
        from services.release.release_order_service import (
            ensure_draft_release_order,
            precheck_release_order,
            publish_release_order,
        )

        actor = session.get("user") or ""
        order = ensure_draft_release_order(project_id, version_id, actor, reason="legacy commercial activate")
        order_id = str(order.get("release_order_id") or "")
        status = str(order.get("status") or "")
        if status in {"draft", "artifacts_ready", "precheck_failed"}:
            order = precheck_release_order(project_id, order_id, actor)
            status = str(order.get("status") or "")
        if status == "awaiting_approval":
            return jsonify({
                "success": False,
                "error": "生产环境需审批，请从发版流程完成发布",
                "release_order_id": order_id,
                "deprecated": True,
            }), 400
        if status in {"ready", "approved"}:
            published = publish_release_order(project_id, order_id, actor)
            return jsonify({
                "success": True,
                "release_order_id": order_id,
                "bundle_id": published.get("bundle_id"),
                "deprecated": True,
                "prefer": f"/admin/projects/{project_id}/release-orders/{order_id}",
            }), 200, {"Deprecation": "true"}
        return jsonify({
            "success": False,
            "error": f"发布单状态 {status} 无法直接激活，请走 Channel 发版流程",
            "release_order_id": order_id,
            "deprecated": True,
        }), 400
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc), "deprecated": True}), 400


@bp.route("/admin/build/commercial-release/plan-preview", methods=["POST"])
@admin_required_any("projects", "build")
def preview_commercial_plan():
    """Legacy plan preview — diff against pipeline defaults or redirect hint."""
    data = request.get_json(silent=True) or {}
    plan = data.get("plan") or {}
    project_id = str(data.get("project_id") or data.get("_project_id") or "").strip()
    version_id = str(data.get("version_id") or data.get("_version_id") or "").strip()
    if not plan and project_id and version_id:
        return jsonify({
            "deprecated": True,
            "redirect": f"/admin/projects/{project_id}/release-orders/new?version_id={version_id}",
            "message": "请使用发版单表单预览计划",
        }), 200
    baseline: dict = {}
    if project_id and version_id:
        from models.data import project_versions_db
        from services.commercial_release_plan import plan_defaults_from_pipeline

        version = next((row for row in (project_versions_db.get(project_id) or []) if str(row.get("id") or "") == version_id), None)
        if isinstance(version, dict):
            baseline = plan_defaults_from_pipeline(version, project_id)
    diff = []
    keys = sorted(set(list(plan.keys()) + list(baseline.keys())))
    for key in keys:
        old = baseline.get(key)
        new = plan.get(key)
        if old != new:
            diff.append({"key": key, "from": old, "to": new})
    return jsonify({
        "plan": plan,
        "baseline": baseline,
        "diff": diff,
        "changed_count": len(diff),
        "deprecated": True,
        "prefer": f"/admin/projects/{project_id}/release-orders/new" if project_id else "",
    })
