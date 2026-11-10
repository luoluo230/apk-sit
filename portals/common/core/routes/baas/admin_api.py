# -*- coding: utf-8 -*-
"""Casual BaaS admin API routes."""

from __future__ import annotations

from services.baas.errors import baas_fail, baas_fail_exc, baas_success
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
            return baas_fail_exc(Exception("项目不存在"))
        env_key = str(
            request.args.get("env_key")
            or (request.get_json(silent=True) or {}).get("env_key")
            or "development"
        )
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_services(project_id, env_key), "catalog": list_catalog()})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        svc, secret = ensure_service(project_id, env_key, actor=_actor())
        payload = {"service": svc}
        if secret:
            payload["api_secret"] = secret
        return jsonify({"ok": True, "data": payload}), 201

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>", methods=["GET", "PATCH"])
    @admin_required("projects")
    def baas_service_detail_api(project_id: str, service_id: str):
        if project_id not in projects_db:
            return baas_fail_exc(Exception("项目不存在"))
        if request.method == "GET":
            svc = get_service(service_id)
            if not svc or svc.get("project_id") != project_id:
                return baas_fail_exc(Exception("休闲服务不存在"))
            return jsonify({"ok": True, "data": svc, "catalog": list_catalog()})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        try:
            svc = update_service(project_id, service_id, request.get_json(silent=True) or {}, actor=_actor())
            return jsonify({"ok": True, "data": svc})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>/rotate-secret", methods=["POST"])
    @admin_required("projects")
    def baas_rotate_secret_api(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        try:
            secret, svc = rotate_api_secret(project_id, service_id)
            return jsonify({"ok": True, "data": {"service": svc, "api_secret": secret}})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>/announcements", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_admin_announcements(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": announce_service.admin_list(service_id)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        row = announce_service.save_announcement(service_id, request.get_json(silent=True) or {}, actor=_actor())
        return jsonify({"ok": True, "data": row})

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>/mail", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_admin_mail(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": mail_service.admin_list(service_id)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        try:
            row = mail_service.send_mail(service_id, request.get_json(silent=True) or {}, actor=_actor())
            return jsonify({"ok": True, "data": row})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route("/api/projects/<project_id>/server-mode", methods=["GET", "PATCH"])
    @admin_required("projects")
    def project_server_mode_api(project_id: str):
        from models.data import projects_db as pdb
        from repositories.admin import projects_repo as projects_repo

        if project_id not in pdb:
            return baas_fail_exc(Exception("项目不存在"))
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
            return baas_fail_exc(Exception("无权限"))
        payload = request.get_json(silent=True) or {}
        current = str(proj.get("server_mode") or "topology").strip().lower()
        mode = str(payload.get("server_mode") or current).strip().lower()
        if mode not in ("topology", "casual_baas"):
            return baas_fail_exc(Exception("server_mode 无效"))
        # P4-01：创建后锁定，禁止在设置里切换架构
        if current in ("topology", "casual_baas") and mode != current:
            return jsonify({
                "ok": False,
                "error": "服务器类型在创建项目时已选定，不可更改。如需另一架构请新建项目。",
            }), 400
        proj["server_mode"] = mode
        if mode == "casual_baas" and not str(proj.get("baas_service_id") or "").strip():
            env_key = str(payload.get("env_key") or "development")
            svc, secret = ensure_service(project_id, env_key, actor=_actor())
            proj["baas_service_id"] = svc.get("service_id") or ""
            projects_repo.upsert_project(project_id, proj)
            return jsonify({"ok": True, "data": {"server_mode": mode, "baas_service_id": proj["baas_service_id"], "api_secret": secret, "locked": True}})
        projects_repo.upsert_project(project_id, proj)
        return jsonify({"ok": True, "data": {"server_mode": mode, "baas_service_id": proj.get("baas_service_id") or "", "locked": True}})

    @bp.route("/api/projects/<project_id>/baas/runtime-status", methods=["GET"])
    @admin_required("projects")
    def baas_runtime_status_api(project_id: str):
        if project_id not in projects_db:
            return baas_fail_exc(Exception("项目不存在"))
        if not is_casual_baas_project(project_id):
            return jsonify({"ok": False, "error": "仅轻度 BaaS 项目可用"}), 400
        from services.baas.runtime_monitor import project_runtime_status
        from services.baas.capacity import postgres_pool_settings, redis_ping

        data = project_runtime_status(project_id)
        data["capacity"] = postgres_pool_settings()
        data["redis_ping"] = redis_ping()
        return jsonify({"ok": True, "data": data})

    @bp.route("/api/projects/<project_id>/baas/services/<service_id>/realms", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_realms_api(project_id: str, service_id: str):
        if project_id not in projects_db or not is_casual_baas_project(project_id):
            return baas_fail_exc(Exception("项目不存在或非 BaaS"))
        svc = get_service(service_id)
        if not svc or str(svc.get("project_id")) != project_id:
            return baas_fail_exc(Exception("服务不存在"))
        from services.baas import realm_service

        if request.method == "GET":
            realm_service.ensure_default_realm(service_id, actor=_actor())
            return jsonify({"ok": True, "data": {"items": realm_service.list_realms(service_id, include_closed=True)}})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        payload = request.get_json(silent=True) or {}
        try:
            row = realm_service.open_realm(
                service_id,
                name=str(payload.get("name") or "新区"),
                actor=_actor(),
                status=str(payload.get("status") or "new"),
            )
            return jsonify({"ok": True, "data": row}), 201
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(
        "/api/projects/<project_id>/baas/services/<service_id>/realms/merge",
        methods=["POST"],
    )
    @admin_required("projects")
    def baas_realms_merge_api(project_id: str, service_id: str):
        if project_id not in projects_db or not is_casual_baas_project(project_id):
            return baas_fail_exc(Exception("项目不存在或非 BaaS"))
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        svc = get_service(service_id)
        if not svc or str(svc.get("project_id")) != project_id:
            return baas_fail_exc(Exception("服务不存在"))
        payload = request.get_json(silent=True) or {}
        from services.baas import realm_service

        try:
            result = realm_service.start_merge(
                service_id,
                str(payload.get("source_realm_id") or ""),
                str(payload.get("target_realm_id") or ""),
                actor=_actor(),
            )
            return jsonify({"ok": True, "data": result})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route("/api/projects/<project_id>/baas/nodes", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_nodes_api(project_id: str):
        if project_id not in projects_db or not is_casual_baas_project(project_id):
            return baas_fail_exc(Exception("项目不存在或非 BaaS"))
        from services.baas import node_registry

        proj = projects_db.get(project_id) or {}
        sid = str(proj.get("baas_service_id") or "")
        if request.method == "GET":
            return jsonify({"ok": True, "data": {"items": node_registry.list_nodes(sid)}})
        payload = request.get_json(silent=True) or {}
        row = node_registry.heartbeat(
            service_id=sid,
            node_id=str(payload.get("node_id") or ""),
            host=str(payload.get("host") or ""),
            port=int(payload.get("port") or 0),
            meta=payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
        )
        return jsonify({"ok": True, "data": row})
