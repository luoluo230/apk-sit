# -*- coding: utf-8 -*-
"""Server management hub REST API."""

from __future__ import annotations

from flask import jsonify, request, send_file, session

from models.data import can_edit_project, log_audit, projects_db
from services.authz import admin_required
from services.baas.service_crud import create_service, delete_service, get_service, update_service
from services.ops.topology_registry import (
    delete_topology_registry_entry,
    update_topology_registry_entry,
)
from services.server_management.hub_service import (
    create_topology_card,
    list_baas_cards,
    list_topology_cards,
    topology_delete_guard,
)
from services.server_management.deploy_pack_service import build_deploy_pack, deploy_pack_info


def _actor() -> str:
    return str(session.get("user") or "admin")


def _filters_from_request():
    return {
        "project_id": str(request.args.get("project_id") or "").strip(),
        "env_key": str(request.args.get("env_key") or "").strip(),
        "status": str(request.args.get("status") or "").strip(),
        "query": str(request.args.get("q") or request.args.get("query") or "").strip(),
    }


def _can_manage_project(project_id: str) -> bool:
    pid = str(project_id or "").strip()
    if not pid:
        return True
    return can_edit_project(pid, _actor())


def register_server_management_api_routes(bp) -> None:
    @bp.route("/api/server-management/topologies", methods=["GET", "POST"])
    @admin_required("gm_ops")
    def server_mgmt_topologies_api():
        if request.method == "GET":
            cards = list_topology_cards(**_filters_from_request())
            return jsonify({"ok": True, "data": {"items": cards, "count": len(cards)}})
        payload = request.get_json(silent=True) or {}
        project_id = str(payload.get("project_id") or "").strip()
        if not project_id or project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        if not _can_manage_project(project_id):
            return jsonify({"ok": False, "error": "无权限"}), 403
        try:
            card = create_topology_card(payload, actor=_actor())
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        log_audit("server_mgmt_topology_create", f"project={project_id}; topology={card.get('id')}")
        return jsonify({"ok": True, "data": card}), 201

    @bp.route("/api/server-management/topologies/<topology_id>", methods=["PATCH", "DELETE"])
    @admin_required("gm_ops")
    def server_mgmt_topology_detail_api(topology_id: str):
        cards = list_topology_cards()
        card = next((c for c in cards if c.get("id") == topology_id), None)
        if not card:
            return jsonify({"ok": False, "error": "拓扑不存在"}), 404
        project_id = str(card.get("project", {}).get("id") or "")
        if not _can_manage_project(project_id):
            return jsonify({"ok": False, "error": "无权限"}), 403
        if request.method == "DELETE":
            guard = topology_delete_guard(topology_id)
            if guard:
                return jsonify({"ok": False, "error": guard}), 409
            if not delete_topology_registry_entry(topology_id):
                return jsonify({"ok": False, "error": "删除失败"}), 404
            log_audit("server_mgmt_topology_delete", f"topology={topology_id}")
            return jsonify({"ok": True})
        payload = request.get_json(silent=True) or {}
        try:
            update_topology_registry_entry(topology_id, payload, actor=_actor())
            refreshed = next((c for c in list_topology_cards() if c.get("id") == topology_id), card)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        log_audit("server_mgmt_topology_update", f"topology={topology_id}")
        return jsonify({"ok": True, "data": refreshed})

    @bp.route("/api/server-management/baas-services", methods=["GET", "POST"])
    @admin_required("projects")
    def server_mgmt_baas_api():
        if request.method == "GET":
            cards = list_baas_cards(**_filters_from_request())
            return jsonify({"ok": True, "data": {"items": cards, "count": len(cards)}})
        payload = request.get_json(silent=True) or {}
        project_id = str(payload.get("project_id") or "").strip()
        if not project_id or project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        if not _can_manage_project(project_id):
            return jsonify({"ok": False, "error": "无权限"}), 403
        try:
            svc, secret = create_service(payload, actor=_actor())
            from services.server_management.hub_service import build_baas_card

            card = build_baas_card(svc)
            if secret:
                card["api_secret"] = secret
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        log_audit("server_mgmt_baas_create", f"project={project_id}; service={card.get('id')}")
        return jsonify({"ok": True, "data": card}), 201

    @bp.route("/api/server-management/baas-services/<service_id>", methods=["PATCH", "DELETE"])
    @admin_required("projects")
    def server_mgmt_baas_detail_api(service_id: str):
        svc = get_service(service_id)
        if not svc:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        project_id = str(svc.get("project_id") or "")
        if not _can_manage_project(project_id):
            return jsonify({"ok": False, "error": "无权限"}), 403
        if request.method == "DELETE":
            try:
                if not delete_service(project_id, service_id):
                    return jsonify({"ok": False, "error": "删除失败"}), 404
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 409
            log_audit("server_mgmt_baas_delete", f"service={service_id}")
            return jsonify({"ok": True})
        payload = request.get_json(silent=True) or {}
        try:
            update_service(project_id, service_id, payload, actor=_actor())
            from services.server_management.hub_service import build_baas_card

            refreshed = build_baas_card(get_service(service_id) or svc)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        log_audit("server_mgmt_baas_update", f"service={service_id}")
        return jsonify({"ok": True, "data": refreshed})

    @bp.route("/api/server-management/projects", methods=["GET"])
    @admin_required("projects")
    def server_mgmt_projects_api():
        items = [
            {"id": pid, "name": str(row.get("name") or pid), "icon_url": str(row.get("icon") or "")}
            for pid, row in sorted((projects_db or {}).items(), key=lambda x: str((x[1] or {}).get("name") or x[0]))
        ]
        return jsonify({"ok": True, "data": items})

    @bp.route("/api/server-management/deploy-pack/<kind>", methods=["GET"])
    @admin_required("projects")
    def server_mgmt_deploy_pack_api(kind: str):
        kind_norm = str(kind or "").strip().lower()
        if kind_norm not in ("topology", "baas"):
            return jsonify({"ok": False, "error": "无效的架构类型"}), 400
        try:
            data, filename = build_deploy_pack(kind_norm)
        except (ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        import io

        return send_file(
            io.BytesIO(data),
            mimetype="application/zip",
            as_attachment=True,
            download_name=filename,
        )

    @bp.route("/api/server-management/deploy-pack/<kind>/info", methods=["GET"])
    @admin_required("projects")
    def server_mgmt_deploy_pack_info_api(kind: str):
        kind_norm = str(kind or "").strip().lower()
        if kind_norm not in ("topology", "baas"):
            return jsonify({"ok": False, "error": "无效的架构类型"}), 400
        return jsonify({"ok": True, "data": deploy_pack_info(kind_norm)})
