# -*- coding: utf-8 -*-
"""BaaS GM admin API."""

from __future__ import annotations

from services.baas.errors import baas_fail, baas_fail_exc, baas_success
from flask import jsonify, request, session

from models.data import can_edit_project, projects_db
from services.authz import admin_required
from services.baas.gm_service import (
    admin_leaderboard,
    adjust_wallet,
    ban_ip,
    ban_player,
    broadcast_mail,
    delete_mail_template,
    get_player_detail,
    gm_dashboard,
    grant_items,
    inspect_cloudsave,
    list_activities,
    list_announcements,
    list_bans,
    list_gift_codes,
    list_gm_audit,
    list_mail_templates,
    list_players,
    list_room_replays_admin,
    list_rooms_admin,
    mute_player,
    reset_leaderboard,
    resolve_player_session_token,
    save_activity,
    save_announcement,
    save_mail_template,
    set_cloudsave,
    unban_ip,
    unban_player,
    unmute_player,
    upsert_gift_code,
    close_room_admin,
    get_room_admin,
    kick_room_player_admin,
    finish_room_battle_admin,
)
from services.baas import gameserver_bridge_service
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
            return baas_fail_exc(Exception("休闲服务不存在"))
        return jsonify({"ok": True, "data": gm_dashboard(service_id)})

    @bp.route(f"{prefix}/players", methods=["GET"])
    @admin_required("projects")
    def baas_gm_players(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        q = str(request.args.get("q") or request.args.get("query") or "")
        limit = int(request.args.get("limit") or 50)
        return jsonify({"ok": True, "data": list_players(service_id, query=q, limit=limit)})

    @bp.route(f"{prefix}/players/<player_id>", methods=["GET"])
    @admin_required("projects")
    def baas_gm_player_detail(project_id: str, service_id: str, player_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        try:
            return jsonify({"ok": True, "data": get_player_detail(service_id, player_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/wallet", methods=["POST"])
    @admin_required("projects")
    def baas_gm_wallet(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
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
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/mail/broadcast", methods=["POST"])
    @admin_required("projects")
    def baas_gm_mail_broadcast(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        try:
            data = broadcast_mail(service_id, request.get_json(silent=True) or {}, actor=_actor())
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/gift-codes", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_gm_gift_codes(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_gift_codes(service_id)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        try:
            row = upsert_gift_code(service_id, request.get_json(silent=True) or {}, actor=_actor())
            return jsonify({"ok": True, "data": row})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/bans", methods=["GET", "POST", "DELETE"])
    @admin_required("projects")
    def baas_gm_bans(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_bans(service_id)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        try:
            if request.method == "DELETE":
                if body.get("ip_pattern"):
                    return jsonify({"ok": True, "data": unban_ip(service_id, str(body.get("ip_pattern")), actor=_actor())})
                return jsonify({"ok": True, "data": unban_player(service_id, str(body.get("player_id") or ""), actor=_actor())})
            if body.get("ip_pattern"):
                data = ban_ip(
                    service_id,
                    str(body.get("ip_pattern")),
                    reason=str(body.get("reason") or ""),
                    expires_at=str(body.get("expires_at") or ""),
                    actor=_actor(),
                )
            else:
                data = ban_player(
                    service_id,
                    str(body.get("player_id") or ""),
                    reason=str(body.get("reason") or ""),
                    expires_at=str(body.get("expires_at") or ""),
                    actor=_actor(),
                )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/mutes", methods=["POST", "DELETE"])
    @admin_required("projects")
    def baas_gm_mutes(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        try:
            if request.method == "DELETE":
                return jsonify({"ok": True, "data": unmute_player(service_id, str(body.get("player_id") or ""), actor=_actor())})
            return jsonify({
                "ok": True,
                "data": mute_player(
                    service_id,
                    str(body.get("player_id") or ""),
                    hours=int(body.get("hours") or 0),
                    reason=str(body.get("reason") or ""),
                    actor=_actor(),
                ),
            })
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/announcements", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_gm_announcements(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_announcements(service_id)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        try:
            return jsonify({"ok": True, "data": save_announcement(service_id, request.get_json(silent=True) or {}, actor=_actor())})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/activities", methods=["GET", "POST"])
    @admin_required("projects")
    def baas_gm_activities(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_activities(service_id)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        try:
            return jsonify({"ok": True, "data": save_activity(service_id, request.get_json(silent=True) or {}, actor=_actor())})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/leaderboards/<board_id>", methods=["GET", "DELETE"])
    @admin_required("projects")
    def baas_gm_leaderboard(project_id: str, service_id: str, board_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": admin_leaderboard(service_id, board_id)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        return jsonify({"ok": True, "data": reset_leaderboard(service_id, board_id, actor=_actor())})

    @bp.route(f"{prefix}/cloudsave/<player_id>", methods=["GET"])
    @bp.route(f"{prefix}/cloudsave/<player_id>/<key>", methods=["GET", "PUT"])
    @admin_required("projects")
    def baas_gm_cloudsave(project_id: str, service_id: str, player_id: str, key: str = ""):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": inspect_cloudsave(service_id, player_id, key)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
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
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/audit", methods=["GET"])
    @admin_required("projects")
    def baas_gm_audit(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        limit = int(request.args.get("limit") or 80)
        return jsonify({"ok": True, "data": list_gm_audit(service_id, limit=limit)})

    @bp.route(f"{prefix}/mail-templates", methods=["GET", "POST", "DELETE"])
    @admin_required("projects")
    def baas_gm_mail_templates(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        if request.method == "GET":
            return jsonify({"ok": True, "data": list_mail_templates(service_id)})
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        try:
            if request.method == "DELETE":
                return jsonify({"ok": True, "data": delete_mail_template(service_id, str(body.get("template_id") or ""), actor=_actor())})
            return jsonify({"ok": True, "data": save_mail_template(service_id, body, actor=_actor())})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/grant-items", methods=["POST"])
    @admin_required("projects")
    def baas_gm_grant_items(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        try:
            data = grant_items(
                service_id,
                str(body.get("player_id") or ""),
                body.get("items") if isinstance(body.get("items"), list) else [],
                title=str(body.get("title") or ""),
                body=str(body.get("body") or ""),
                actor=_actor(),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/gameserver/health", methods=["GET"])
    @admin_required("projects")
    def baas_gm_gameserver_health(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        data = gameserver_bridge_service.ops_health(actor=_actor())
        ok = data.get("success") is True or data.get("reachable") is not False
        return jsonify({"ok": ok, "data": data})

    @bp.route(f"{prefix}/gameserver/kick", methods=["POST"])
    @admin_required("projects")
    def baas_gm_gameserver_kick(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        try:
            token = str(body.get("session_token") or body.get("token") or "").strip()
            if not token and body.get("player_id"):
                token = resolve_player_session_token(service_id, str(body.get("player_id")))
            if not token:
                raise ValueError("player_id 或 session_token 必填")
            data = gameserver_bridge_service.kick_session(token, actor=_actor())
            from models.db import log_audit_db

            log_audit_db("default", _actor(), "baas_gm_kick_online", f"{service_id}/{body.get('player_id') or token[:8]}", "")
            ok = data.get("success") is True
            return jsonify({"ok": ok, "data": data}), (200 if ok else 502)
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/gameserver/maintenance", methods=["POST"])
    @admin_required("projects")
    def baas_gm_gameserver_maintenance(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        message = str(body.get("message") or "服务器维护中，请稍后再试")
        data = gameserver_bridge_service.trigger_maintenance(message, actor=_actor())
        from models.db import log_audit_db

        log_audit_db("default", _actor(), "baas_gm_maintenance", f"{service_id} {message[:80]}", "")
        ok = data.get("success") is True
        return jsonify({"ok": ok, "data": data}), (200 if ok else 502)

    @bp.route(f"{prefix}/rooms/replays", methods=["GET"])
    @admin_required("projects")
    def baas_gm_room_replays(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        limit = int(request.args.get("limit") or 20)
        return jsonify({"ok": True, "data": list_room_replays_admin(service_id, limit=limit)})

    @bp.route(f"{prefix}/rooms", methods=["GET"])
    @admin_required("projects")
    def baas_gm_rooms(project_id: str, service_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        status = str(request.args.get("status") or "")
        limit = int(request.args.get("limit") or 50)
        return jsonify({"ok": True, "data": list_rooms_admin(service_id, status=status, limit=limit)})

    @bp.route(f"{prefix}/rooms/<room_id>", methods=["GET"])
    @admin_required("projects")
    def baas_gm_room_detail(project_id: str, service_id: str, room_id: str):
        svc = get_service(service_id)
        if not svc or svc.get("project_id") != project_id:
            return baas_fail_exc(Exception("休闲服务不存在"))
        try:
            return jsonify({"ok": True, "data": get_room_admin(service_id, room_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/rooms/<room_id>/close", methods=["POST"])
    @admin_required("projects")
    def baas_gm_room_close(project_id: str, service_id: str, room_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        try:
            data = close_room_admin(service_id, room_id, reason=str(body.get("reason") or "gm"), actor=_actor())
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/rooms/<room_id>/kick", methods=["POST"])
    @admin_required("projects")
    def baas_gm_room_kick(project_id: str, service_id: str, room_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        target = str(body.get("player_id") or body.get("target_id") or "").strip()
        if not target:
            return baas_fail_exc(Exception("player_id 必填"))
        try:
            data = kick_room_player_admin(service_id, room_id, target, actor=_actor())
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/rooms/<room_id>/finish", methods=["POST"])
    @admin_required("projects")
    def baas_gm_room_finish(project_id: str, service_id: str, room_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        try:
            data = finish_room_battle_admin(service_id, room_id, result=body.get("result") if isinstance(body.get("result"), dict) else None, actor=_actor())
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @bp.route(f"{prefix}/gameserver/stop", methods=["POST"])
    @admin_required("projects")
    def baas_gm_gameserver_stop(project_id: str, service_id: str):
        if not can_edit_project(project_id, _actor()):
            return baas_fail_exc(Exception("无权限"))
        body = request.get_json(silent=True) or {}
        message = str(body.get("message") or "服务器维护中，请稍后再试")
        data = gameserver_bridge_service.stop_gateway(message, actor=_actor())
        from models.db import log_audit_db

        log_audit_db("default", _actor(), "baas_gm_stop_gateway", f"{service_id} {message[:80]}", "")
        ok = data.get("success") is True
        return jsonify({"ok": ok, "data": data}), (200 if ok else 502)

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
