# -*- coding: utf-8 -*-
"""BaaS GM admin API."""

from __future__ import annotations

from flask import jsonify, request, session

from models.data import can_edit_project, projects_db
from services.authz import admin_required
from services.baas.gm_service import (
    admin_leaderboard,
    adjust_wallet,
    broadcast_mail,
    get_player_detail,
    gm_dashboard,
    inspect_cloudsave,
    list_gift_codes,
    list_players,
    reset_leaderboard,
    set_cloudsave,
    upsert_gift_code,
)
from services.baas.service_crud import get_service


def _actor() -> str:
    return str(session.get("user") or "admin")


def register_baas_gm_routes(bp) -> None:
    prefix = "/api/projects/<project_id>/baas/services/<service_id>/gm"

    @bp.route(f"{prefix}/dashboard", methods=["GET"])
    @admin_required("projects")
    def baas_gm_dashboard(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        return jsonify({"ok": True, "data": gm_dashboard(service_id)})

    @bp.route(f"{prefix}/players", methods=["GET"])
    @admin_required("projects")
    def baas_gm_players(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        q = str(request.args.get("q") or request.args.get("query") or "")
        limit = int(request.args.get("limit") or 50)
        return jsonify({"ok": True, "data": list_players(service_id, query=q, limit=limit)})

    @bp.route(f"{prefix}/players/<player_id>", methods=["GET"])
    @admin_required("projects")
    def baas_gm_player_detail(project_id: str, service_id: str, player_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        try:
            return jsonify({"ok": True, "data": get_player_detail(service_id, player_id)})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404

    @bp.route(f"{prefix}/wallet", methods=["POST"])
    @admin_required("projects")
    def baas_gm_wallet(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        body = request.get_json(silent=True) or {}
        try:
            data = adjust_wallet(
                service_id,
                str(body.get("player_id") or ""),
                str(body.get("currency_id") or "gold"),
                int(body.get("delta") or 0),
                actor=_actor(),
                reason=str(body.get("reason") or ""),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route(f"{prefix}/mail/broadcast", methods=["POST"])
    @admin_required("projects")
    def baas_gm_mail_broadcast(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        try:
            data = broadcast_mail(service_id, request.get_json(silent=True) or {}, actor=_actor())
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route(f"{prefix}/gift-codes", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_gm_gift_codes(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_gift_codes(service_id)})
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        try:
            row = upsert_gift_code(service_id, request.get_json(silent=True) or {}, actor=_actor())
            return jsonify({"ok": True, "data": row})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route(f"{prefix}/leaderboards/<board_id>", methods=["GET", "DELETE"])
    @admin_required("projects")
    def baas_gm_leaderboard(project_id: str, service_id: str, board_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        if request.method == "GET":
            return jsonify({"ok": True, "data": admin_leaderboard(service_id, board_id)})
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        return jsonify({"ok": True, "data": reset_leaderboard(service_id, board_id, actor=_actor())})

    @bp.route(f"{prefix}/cloudsave/<player_id>", methods=["GET"])
    @bp.route(f"{prefix}/cloudsave/<player_id>/<key>", methods=["GET", "PUT"])
    @admin_required("projects")
    def baas_gm_cloudsave(project_id: str, service_id: str, player_id: str, key: str = ""):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return jsonify({"ok": False, "error": "休闲服务不存在"}), 404
        if request.method == "GET":
            return jsonify({"ok": True, "data": inspect_cloudsave(service_id, player_id, key)})
        if not can_edit_project(project_id, _actor()):
            return jsonify({"ok": False, "error": "无权限"}), 403
        body = request.get_json(silent=True) or {}
        try:
            data = set_cloudsave(
                service_id,
                player_id,
                key or str(body.get("key") or ""),
                body.get("value"),
                actor=_actor(),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @bp.route("/admin/projects/<project_id>/baas-gm")
    @bp.route("/admin/projects/<project_id>/baas-gm/<service_id>")
    @admin_required("projects")
    def baas_gm_console_page(project_id: str, service_id: str = ""):
        from flask import abort, render_template

        from routes.baas.layout import render_baas_page as _page
        from services.baas.service_crud import ensure_service

        if project_id not in projects_db:
            abort(404)
        username = _actor()
        from models.data import can_view_project

        if not can_view_project(project_id, username):
            abort(403)
        env_key = str(request.args.get("env_key") or "development").strip() or "development"
        sid = str(
            service_id
            or request.args.get("service_id")
            or projects_db.get(project_id, {}).get("baas_service_id")
            or ""
        ).strip()
        if not sid:
            svc, _ = ensure_service(project_id, env_key)
            sid = svc.get("service_id") or ""
        svc = get_service(sid) if sid else None
        if not svc or svc.get("project_id") != project_id:
            abort(404)
        return _page(
            "baas_gm_console.html",
            "BaaS GM 运维",
            project_id,
            "baas-gm",
            service_id=sid,
            env_key=svc.get("env_key") or env_key,
            can_edit=can_edit_project(project_id, username),
        )
