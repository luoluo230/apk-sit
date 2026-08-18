# -*- coding: utf-8 -*-
"""Casual BaaS admin API routes."""

from __future__ import annotations

from flask import jsonify, request, session

from models.data import can_edit_project, projects_db
from services.authz import admin_required
from services.baas.registry import list_catalog
from services.baas.service_crud import (
    ensure_service,
    get_service,
    list_services,
    rotate_api_secret,
    update_service,
)
from services.baas import announce_service, mail_service
from services.baas.helpers import is_casual_baas_project


def _actor() -> str:
    return str(session.get("user") or "admin")


def register_baas_admin_routes(bp) -> None:
    @bp.route("/api/projects/<project_id>/baas/services", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_services_api(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        env_key = str(
            request.args.get("env_key")
            or (request.get_json(silent=True) or {}).get("env_key")
            or "development"
        )
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_services(project_id, env_key), "catalog": list_catalog()})
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        svc, secret = ensure_service(project_id, env_key, actor=_actor())
        payload = {"service": svc}
        if secret:
            payload["api_secret"] = secret
        return jsonify({"ok": True, "data": payload}), 201

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>", methods=["GET", "PATCH"])
    @admin_required("projects")
    def baas_service_detail_api(project_id: str, service_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        if request.method == "GET":
            svc = get_service(service_id)
            if not svc or svc.get("project_id") != project_id:
                return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
            return jsonify({"ok": True, "data": svc, "catalog": list_catalog()})
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        try:
            svc = update_service(project_id, service_id, request.get_json(silent=True) or {}, actor=_actor())
            return jsonify({"ok": True, "data": svc})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>/rotate-secret", methods=["POST"])
    @admin_required("projects")
    def baas_rotate_secret_api(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        try:
            secret, svc = rotate_api_secret(project_id, service_id)
            return jsonify({"ok": True, "data": {"service": svc, "api_secret": secret}})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>/announcements", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_admin_announcements(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        if request.method == "GET":
            return jsonify({"ok": True, "data": announce_service.admin_list(service_id)})
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        row = announce_service.save_announcement(service_id, request.get_json(silent=True) or {}, actor=_actor())
        return jsonify({"ok": True, "data": row})

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>/mail", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_admin_mail(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        if request.method == "GET":
            return jsonify({"ok": True, "data": mail_service.admin_list(service_id)})
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        try:
            row = mail_service.send_mail(service_id, request.get_json(silent=True) or {}, actor=_actor())
            return jsonify({"ok": True, "data": row})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/api/projects/<project_id>/server-mode", methods=["GET", "PATCH"])
    @admin_required("projects")
    def project_server_mode_api(project_id: str):
        from models.data import projects_db as pdb
        from repositories.admin import projects_repo as projects_repo

        if project_id not in pdb:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        proj = projects_repo.get_project(project_id) or {}
        if request.method == "GET":
            return jsonify({
                "ok": True,
                "data": {
                    "server_mode": str(proj.get("server_mode") or "topology"),
                    "baas_service_id": str(proj.get("baas_service_id") or ""),
                },
            })
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("server_mode") or proj.get("server_mode") or "topology").strip().lower()
        if mode not in ("topology", "casual_baas"):
            return jsonify({"ok": False, "error": "server_mode 无效"}), 400
        proj["server_mode"] = mode
        if mode == "casual_baas":
            env_key = str(payload.get("env_key") or "development")
            svc, secret = ensure_service(project_id, env_key, actor=_actor())
            proj["baas_service_id"] = svc.get("service_id") or ""
            projects_repo.upsert_project(project_id, proj)
            return jsonify({"ok": True, "data": {"server_mode": mode, "baas_service_id": proj["baas_service_id"], "api_secret": secret}})
        projects_repo.upsert_project(project_id, proj)
        return jsonify({"ok": True, "data": {"server_mode": mode, "baas_service_id": proj.get("baas_service_id") or ""}})
