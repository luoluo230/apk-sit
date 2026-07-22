# -*- coding: utf-8 -*-
"""Legacy GM release API wrappers — delegate to ReleaseOrder flow."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from models.data import projects_db
from services.authz import admin_required_any

bp = Blueprint("gm_ops_release", __name__)


def _actor() -> str:
    return str(session.get("user") or session.get("username") or "admin")


def _resolve_ids(data: dict) -> tuple[str, str, str]:
    project_id = str(data.get("project_id") or data.get("_project_id") or "").strip()
    version_id = str(data.get("version_id") or data.get("_version_id") or "").strip()
    order_id = str(data.get("release_order_id") or data.get("order_id") or "").strip()
    return project_id, version_id, order_id


@bp.route("/api/gm-ops/release/precheck", methods=["POST"])
@admin_required_any("projects", "build")
def gm_release_precheck():
    data = request.get_json(silent=True) or {}
    project_id, version_id, order_id = _resolve_ids(data)
    if not project_id:
        return jsonify({"ok": False, "error": "缺少 project_id", "deprecated": True}), 400
    try:
        from services.release.release_order_service import ensure_draft_release_order, precheck_release_order

        actor = _actor()
        if not order_id and version_id:
            order = ensure_draft_release_order(project_id, version_id, actor)
            order_id = str(order.get("release_order_id") or "")
        if not order_id:
            return jsonify({"ok": False, "error": "缺少 release_order_id 或 version_id", "deprecated": True}), 400
        result = precheck_release_order(project_id, order_id, actor)
        successor = f"/api/projects/{project_id}/release-orders/{order_id}/precheck"
        return jsonify({
            "ok": True,
            "data": result,
            "release_order_id": order_id,
            "deprecated": True,
            "prefer": successor,
        }), 200, {"Deprecation": "true", "Link": f"</{successor.lstrip('/')}>; rel=\"successor-version\""}
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "deprecated": True}), 400


@bp.route("/api/gm-ops/release/publish", methods=["POST"])
@admin_required_any("projects", "build")
def gm_release_publish():
    data = request.get_json(silent=True) or {}
    project_id, version_id, order_id = _resolve_ids(data)
    if not project_id:
        return jsonify({"ok": False, "error": "缺少 project_id", "deprecated": True}), 400
    try:
        from services.release.release_order_service import (
            approve_release_order,
            ensure_draft_release_order,
            precheck_release_order,
            publish_release_order,
        )

        actor = _actor()
        if not order_id and version_id:
            order = ensure_draft_release_order(project_id, version_id, actor)
            order_id = str(order.get("release_order_id") or "")
        if not order_id:
            return jsonify({"ok": False, "error": "缺少 release_order_id 或 version_id", "deprecated": True}), 400
        if data.get("run_precheck", True):
            order = precheck_release_order(project_id, order_id, actor)
        else:
            from services.release.release_order_service import get_release_order
            order = get_release_order(project_id, order_id, include_details=False)
        status = str(order.get("status") or "")
        if status == "awaiting_approval" and data.get("auto_approve"):
            order = approve_release_order(project_id, order_id, actor, note="gm-ops legacy auto approve")
            status = str(order.get("status") or "")
        if status not in {"ready", "approved"}:
            return jsonify({
                "ok": False,
                "error": f"发布单状态 {status} 不可发布，请走 Channel 发版流程",
                "release_order_id": order_id,
                "deprecated": True,
            }), 400
        published = publish_release_order(project_id, order_id, actor)
        successor = f"/api/projects/{project_id}/release-orders/{order_id}/publish"
        return jsonify({
            "ok": True,
            "data": published,
            "release_order_id": order_id,
            "deprecated": True,
            "prefer": successor,
        }), 200, {"Deprecation": "true", "Link": f"</{successor.lstrip('/')}>; rel=\"successor-version\""}
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "deprecated": True}), 400


@bp.route("/api/gm-ops/release/rollback", methods=["POST"])
@admin_required_any("projects", "build")
def gm_release_rollback():
    data = request.get_json(silent=True) or {}
    project_id, _, order_id = _resolve_ids(data)
    if not project_id or not order_id:
        return jsonify({"ok": False, "error": "缺少 project_id 或 release_order_id", "deprecated": True}), 400
    try:
        from services.release.release_order_service import rollback_release_order

        result = rollback_release_order(project_id, order_id, _actor())
        successor = f"/api/projects/{project_id}/release-orders/{order_id}/rollback"
        return jsonify({
            "ok": True,
            "data": result,
            "deprecated": True,
            "prefer": successor,
        }), 200, {"Deprecation": "true", "Link": f"</{successor.lstrip('/')}>; rel=\"successor-version\""}
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "deprecated": True}), 400


@bp.route("/api/gm-ops/release/versions", methods=["POST"])
@admin_required_any("projects", "build")
def gm_release_versions():
    """Legacy version listing — redirect clients to project versions API."""
    data = request.get_json(silent=True) or {}
    project_id = str(data.get("project_id") or "").strip()
    if not project_id or project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目不存在", "deprecated": True}), 404
    from models.data import project_versions_db

    versions = project_versions_db.get(project_id) or []
    return jsonify({
        "ok": True,
        "versions": versions if isinstance(versions, list) else [],
        "deprecated": True,
        "prefer": f"/api/projects/{project_id}/versions",
    })
