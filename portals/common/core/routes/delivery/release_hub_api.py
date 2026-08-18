# -*- coding: utf-8 -*-
"""Release Hub and artifact promotion API routes."""

from __future__ import annotations

from flask import jsonify, request

from models.data import projects_db
from services.authz import admin_required
from services.release.bundle_promotion_service import list_promotion_candidates, promote_bundle_to_env
from services.release.server_artifact_promotion_service import (
    approve_server_promotion,
    list_server_promotion_candidates,
    promote_server_artifact_to_env,
)
from services.release.release_hub_bff import build_release_hub

from routes.delivery.helpers import actor as _actor


def register_release_hub_routes(bp) -> None:
    @bp.route("/api/projects/<project_id>/release-hub", methods=["GET"])
    @admin_required("projects")
    def release_hub_api(project_id: str):
        try:
            if project_id not in projects_db:
                return jsonify({"ok": False, "error": "项目不存在"}), 404
            env_key = str(request.args.get("env_key") or "").strip()
            data = build_release_hub(project_id, env_key=env_key)
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-health", methods=["GET"])
    @admin_required("projects")
    def release_health_api(project_id: str):
        try:
            if project_id not in projects_db:
                return jsonify({"ok": False, "error": "项目不存在"}), 404
            from services.monitor.release_metrics import build_release_health_summary

            days = int(request.args.get("days") or 7)
            data = build_release_health_summary(project_id, days=days)
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/artifact-promotions", methods=["GET", "POST"])
    @admin_required("projects")
    def artifact_promotions_api(project_id: str):
        try:
            if project_id not in projects_db:
                return jsonify({"ok": False, "error": "项目不存在"}), 404
            if request.method == "GET":
                return jsonify({"ok": True, "data": list_promotion_candidates(project_id)})
            payload = request.get_json(silent=True) or {}
            result = promote_bundle_to_env(
                project_id,
                str(payload.get("source_bundle_id") or ""),
                str(payload.get("target_env_key") or ""),
                _actor(),
                note=str(payload.get("note") or ""),
            )
            return jsonify({"ok": True, "data": result}), 201
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/server-artifact-promotions", methods=["GET", "POST"])
    @admin_required("projects")
    def server_artifact_promotions_api(project_id: str):
        try:
            if project_id not in projects_db:
                return jsonify({"ok": False, "error": "项目不存在"}), 404
            if request.method == "GET":
                return jsonify({"ok": True, "data": list_server_promotion_candidates(project_id)})
            payload = request.get_json(silent=True) or {}
            result = promote_server_artifact_to_env(
                project_id,
                str(payload.get("source_server_release_id") or ""),
                str(payload.get("target_env_key") or ""),
                _actor(),
                note=str(payload.get("note") or ""),
                channel_id=str(payload.get("channel_id") or "common"),
                platform=str(payload.get("platform") or "android"),
            )
            return jsonify({"ok": True, "data": result}), 201
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route(
        "/api/projects/<project_id>/server-artifact-promotions/<server_release_id>/approve",
        methods=["POST"],
    )
    @admin_required("projects")
    def approve_server_promotion_api(project_id: str, server_release_id: str):
        try:
            if project_id not in projects_db:
                return jsonify({"ok": False, "error": "项目不存在"}), 404
            payload = request.get_json(silent=True) or {}
            result = approve_server_promotion(
                project_id,
                server_release_id,
                _actor(),
                note=str(payload.get("note") or ""),
            )
            return jsonify({"ok": True, "data": result})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
