# -*- coding: utf-8
"""Admin API for server release plane (P2-01)."""

from __future__ import annotations

import os
import tempfile

from flask import jsonify, request, session

from services.authz import admin_required
from services.release import server_artifact_service as sas
from services.release import server_release_service as srs


def register_routes(bp):
    @bp.route("/api/admin/projects/<project_id>/server-artifacts", methods=["GET", "POST"])
    @admin_required("projects")
    def api_server_artifacts(project_id: str):
        if request.method == "GET":
            rows = sas.list_artifacts(project_id)
            return jsonify({"ok": True, "data": rows})
        body = request.get_json(silent=True) or {}
        upload = request.files.get("bundle") if request.files else None
        source_path = ""
        if upload and upload.filename:
            suffix = os.path.splitext(upload.filename)[1] or ".zip"
            fd, source_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            upload.save(source_path)
        try:
            row = sas.register_artifact(project_id, body, source_path=source_path)
        finally:
            if source_path and os.path.isfile(source_path):
                try:
                    os.remove(source_path)
                except OSError:
                    pass
        return jsonify({"ok": True, "data": row}), 201

    @bp.route("/api/admin/projects/<project_id>/server-artifacts/<artifact_id>", methods=["GET"])
    @admin_required("projects")
    def api_server_artifact_detail(project_id: str, artifact_id: str):
        row = sas.get_artifact(artifact_id)
        if not row or str(row.get("project_id") or "") != str(project_id):
            return jsonify({"ok": False, "error": "制品不存在"}), 404
        return jsonify({"ok": True, "data": row})

    @bp.route("/api/admin/projects/<project_id>/server-releases", methods=["GET", "POST"])
    @admin_required("projects")
    def api_server_releases(project_id: str):
        actor = str(session.get("user") or "admin")
        if request.method == "GET":
            env_key = str(request.args.get("env_key") or "").strip()
            return jsonify({"ok": True, "data": srs.list_server_releases(project_id, env_key=env_key)})
        body = request.get_json(silent=True) or {}
        row = srs.create_server_release(project_id, body, actor)
        return jsonify({"ok": True, "data": row}), 201

    @bp.route("/api/admin/projects/<project_id>/server-releases/<server_release_id>", methods=["GET", "PATCH"])
    @admin_required("projects")
    def api_server_release_detail(project_id: str, server_release_id: str):
        actor = str(session.get("user") or "admin")
        if request.method == "GET":
            row = srs.get_server_release(project_id, server_release_id)
            if not row:
                return jsonify({"ok": False, "error": "服务端发布单不存在"}), 404
            return jsonify({"ok": True, "data": row})
        body = request.get_json(silent=True) or {}
        row = srs.update_server_release(project_id, server_release_id, body, actor)
        return jsonify({"ok": True, "data": row})

    @bp.route("/api/admin/projects/<project_id>/server-releases/<server_release_id>/deploy", methods=["POST"])
    @admin_required("projects")
    def api_server_release_deploy(project_id: str, server_release_id: str):
        actor = str(session.get("user") or "admin")
        try:
            row = srs.deploy_server_release(project_id, server_release_id, actor)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "data": row})

    @bp.route("/api/admin/projects/<project_id>/server-releases/<server_release_id>/rollback", methods=["POST"])
    @admin_required("projects")
    def api_server_release_rollback(project_id: str, server_release_id: str):
        actor = str(session.get("user") or "admin")
        body = request.get_json(silent=True) or {}
        try:
            row = srs.rollback_server_release(
                project_id,
                server_release_id,
                actor,
                previous_artifact_id=str(body.get("previous_artifact_id") or ""),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "data": row})

    @bp.route("/api/admin/projects/<project_id>/server-releases/<server_release_id>/complete-deploy", methods=["POST"])
    @admin_required("projects")
    def api_server_release_complete_deploy(project_id: str, server_release_id: str):
        body = request.get_json(silent=True) or {}
        actor = str(session.get("user") or "admin")
        row = srs.complete_deploy_server_release(
            project_id,
            server_release_id,
            ok=bool(body.get("ok", True)),
            actor=actor,
            detail=body.get("detail") if isinstance(body.get("detail"), dict) else {},
        )
        return jsonify({"ok": True, "data": row})
