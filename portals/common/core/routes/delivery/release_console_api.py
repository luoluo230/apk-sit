# -*- coding: utf-8 -*-
"""Release console and batch API routes."""

from __future__ import annotations

from flask import jsonify, request

from models.data import projects_db
from services.authz import admin_required
from services.release.release_batch_service import (
    batch_build,
    batch_cancel,
    batch_precheck,
    batch_publish,
    batch_readiness,
    batch_rollback,
    batch_verify,
    create_release_batch,
    get_release_batch,
    list_release_batches,
    resolve_batch_next_action,
    update_release_batch,
)
from services.release.release_console_bff import build_release_console

from routes.delivery.helpers import actor as _actor


def register_release_console_routes(bp) -> None:
    @bp.route("/api/projects/<project_id>/release-console", methods=["GET"])
    @admin_required("projects")
    def release_console_api(project_id: str):
        try:
            if project_id not in projects_db:
                return jsonify({"ok": False, "error": "项目不存在"}), 404
            env_key = str(request.args.get("env_key") or "").strip()
            batch_id = str(request.args.get("batch_id") or "").strip()
            data = build_release_console(project_id, env_key=env_key, batch_id=batch_id)
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches", methods=["GET", "POST"])
    @admin_required("projects")
    def release_batches_api(project_id: str):
        try:
            if project_id not in projects_db:
                return jsonify({"ok": False, "error": "项目不存在"}), 404
            if request.method == "GET":
                limit = int(request.args.get("limit") or 20)
                return jsonify({"ok": True, "data": list_release_batches(project_id, limit=limit)})
            row = create_release_batch(project_id, request.get_json(silent=True) or {}, _actor())
            return jsonify({"ok": True, "data": row}), 201
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>", methods=["GET", "PATCH"])
    @admin_required("projects")
    def release_batch_api(project_id: str, batch_id: str):
        try:
            if request.method == "PATCH":
                return jsonify({
                    "ok": True,
                    "data": update_release_batch(
                        project_id, batch_id, request.get_json(silent=True) or {}, _actor()
                    ),
                })
            row = get_release_batch(project_id, batch_id, include_events=True)
            if not row:
                return jsonify({"ok": False, "error": "发版批次不存在"}), 404
            return jsonify({"ok": True, "data": row})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/readiness")
    @admin_required("projects")
    def release_batch_readiness_api(project_id: str, batch_id: str):
        try:
            return jsonify({"ok": True, "data": batch_readiness(project_id, batch_id)})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/next-action")
    @admin_required("projects")
    def release_batch_next_action_api(project_id: str, batch_id: str):
        try:
            return jsonify({"ok": True, "data": resolve_batch_next_action(project_id, batch_id)})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    def _batch_action(project_id: str, batch_id: str, action: str):
        payload = request.get_json(silent=True) or {}
        handlers = {
            "build": lambda: batch_build(
                project_id,
                batch_id,
                _actor(),
                retry_failed_only=bool(payload.get("retry_failed_only")),
            ),
            "precheck": lambda: batch_precheck(
                project_id,
                batch_id,
                _actor(),
                auto_ensure_runtime=bool(payload.get("auto_ensure_runtime")),
            ),
            "publish": lambda: batch_publish(
                project_id,
                batch_id,
                _actor(),
                skip_failed_lines=bool(payload.get("skip_failed_lines")),
                confirm_production=bool(payload.get("confirm_production")),
            ),
            "verify": lambda: batch_verify(
                project_id,
                batch_id,
                _actor(),
                ok=bool(payload.get("ok", True)),
            ),
            "cancel": lambda: batch_cancel(project_id, batch_id, _actor()),
            "rollback": lambda: batch_rollback(
                project_id,
                batch_id,
                _actor(),
                skip_failed_lines=bool(payload.get("skip_failed_lines")),
            ),
        }
        handler = handlers.get(action)
        if not handler:
            return jsonify({"ok": False, "error": f"未知动作: {action}"}), 400
        return jsonify({"ok": True, "data": handler()})

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/build", methods=["POST"])
    @admin_required("projects")
    def release_batch_build_api(project_id: str, batch_id: str):
        try:
            return _batch_action(project_id, batch_id, "build")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/precheck", methods=["POST"])
    @admin_required("projects")
    def release_batch_precheck_api(project_id: str, batch_id: str):
        try:
            return _batch_action(project_id, batch_id, "precheck")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/publish", methods=["POST"])
    @admin_required("projects")
    def release_batch_publish_api(project_id: str, batch_id: str):
        try:
            return _batch_action(project_id, batch_id, "publish")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/verify", methods=["POST"])
    @admin_required("projects")
    def release_batch_verify_api(project_id: str, batch_id: str):
        try:
            return _batch_action(project_id, batch_id, "verify")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/cancel", methods=["POST"])
    @admin_required("projects")
    def release_batch_cancel_api(project_id: str, batch_id: str):
        try:
            return _batch_action(project_id, batch_id, "cancel")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/rollback", methods=["POST"])
    @admin_required("projects")
    def release_batch_rollback_api(project_id: str, batch_id: str):
        try:
            return _batch_action(project_id, batch_id, "rollback")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/release-batches/<batch_id>/events")
    @admin_required("projects")
    def release_batch_events_api(project_id: str, batch_id: str):
        row = get_release_batch(project_id, batch_id, include_events=True)
        if not row:
            return jsonify({"ok": False, "error": "发版批次不存在"}), 404
        return jsonify({"ok": True, "data": row.get("events") or []})
