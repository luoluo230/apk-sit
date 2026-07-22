# -*- coding: utf-8 -*-
"""Build/release journey and quick delivery action APIs."""

from __future__ import annotations

from flask import jsonify, request

from models.data import projects_db
from services.authz import admin_required
from services.release.release_order_service import (
    ensure_draft_release_order,
    quick_build_version,
    quick_publish_delivery,
    resolve_channel_build_journey,
    resolve_channel_release_journey,
    resolve_delivery_actions,
    sync_building_release_orders,
)

from routes.delivery.helpers import actor as _actor, normalize_channel_route_id as _normalize_channel_route_id


def register_journey_routes(bp) -> None:
    @bp.route("/api/projects/<project_id>/environments/<env_key>/channels/<channel_id>/build-journey")
    @admin_required("projects")
    def channel_build_journey_api(project_id: str, env_key: str, channel_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        try:
            data = resolve_channel_build_journey(
                project_id,
                env_key,
                _normalize_channel_route_id(project_id, channel_id),
                platform=str(request.args.get("platform") or "").strip().lower(),
                version_id=str(request.args.get("version_id") or "").strip(),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/environments/<env_key>/channels/<channel_id>/release-journey")
    @admin_required("projects")
    def channel_release_journey_api(project_id: str, env_key: str, channel_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        try:
            data = resolve_channel_release_journey(
                project_id,
                env_key,
                _normalize_channel_route_id(project_id, channel_id),
                platform=str(request.args.get("platform") or "").strip().lower(),
                version_id=str(request.args.get("version_id") or "").strip(),
                bundle_id=str(request.args.get("bundle_id") or "").strip(),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/versions/<version_id>/delivery-actions", methods=["GET"])
    @admin_required("projects")
    def version_delivery_actions_api(project_id: str, version_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        try:
            data = resolve_delivery_actions(project_id, version_id)
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/versions/<version_id>/quick-build", methods=["POST"])
    @admin_required("projects")
    def version_quick_build_api(project_id: str, version_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        try:
            data = quick_build_version(project_id, version_id, _actor())
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/versions/<version_id>/ensure-release-order", methods=["POST"])
    @admin_required("projects")
    def version_ensure_release_order_api(project_id: str, version_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        try:
            data = ensure_draft_release_order(
                project_id, version_id, _actor(), reason="发版流程创建发布单"
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/delivery-attempts/quick-publish", methods=["POST"])
    @admin_required("projects")
    def delivery_quick_publish_api(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        payload = request.get_json(silent=True) or {}
        try:
            data = quick_publish_delivery(
                project_id,
                str(payload.get("env_key") or "").strip(),
                str(payload.get("channel_id") or "").strip(),
                str(payload.get("platform") or "").strip(),
                str(payload.get("version_id") or "").strip(),
                _actor(),
                skip_build=bool(payload.get("skip_build")),
                force_build=bool(payload.get("force_build")),
                auto_verify=payload.get("auto_verify", True) is not False,
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-orders/sync-building", methods=["POST"])
    @admin_required("projects")
    def release_orders_sync_building_api(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        rows = sync_building_release_orders(project_id, actor=_actor())
        return jsonify({"ok": True, "data": {"updated": rows, "count": len(rows)}})
