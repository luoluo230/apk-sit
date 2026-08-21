# -*- coding: utf-8 -*-
"""Casual BaaS public REST API."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from routes.baas.http_helpers import baas_player_auth, baas_service_auth, run_baas
from services.baas import announce_service, auth_service, cloudsave_service, compliance_service, mail_service
from services.baas import activity_service, pvp_service, retention_services, social_services
from services.baas import room_service, pve_service, arena_service
from services.baas import gacha_service, hero_service, idle_service, tower_service, iap_service
from services.baas import inventory_service, guild_war_service
from services.baas.errors import baas_fail_exc, baas_success

baas_public_bp = Blueprint("baas_public", __name__)


def _service_auth(expected_service_id: str):
    return baas_service_auth(expected_service_id)


def _player_auth(service_id: str):
    return baas_player_auth(service_id, auth_service)


def register_baas_public_routes(bp=None) -> None:
    target = bp or baas_public_bp
    prefix = "/api/baas/v1/<service_id>"

    @target.route(f"{prefix}/auth/guest", methods=["POST"])
    def baas_auth_guest(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        try:
            data = auth_service.guest_login(service_id, display_name=str((request.get_json(silent=True) or {}).get("display_name") or ""))
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/auth/register", methods=["POST"])
    def baas_auth_register(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            data = auth_service.register_password(service_id, username=body.get("username"), password=body.get("password"), display_name=body.get("display_name"))
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/auth/login", methods=["POST"])
    def baas_auth_login(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            data = auth_service.password_login(service_id, username=body.get("username"), password=body.get("password"))
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/announcements/active", methods=["GET"])
    def baas_announcements(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        display_type = str(request.args.get("display_type") or request.args.get("type") or "").strip()
        return jsonify({"ok": True, "data": announce_service.list_active(service_id, display_type=display_type)})

    @target.route(f"{prefix}/activities/active", methods=["GET"])
    def baas_activities_active(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        profile = (player or {}).get("profile") if player else {}
        return jsonify({"ok": True, "data": activity_service.list_active_for_player(service_id, profile or {})})

    @target.route(f"{prefix}/mail/inbox", methods=["GET"])
    def baas_mail_inbox(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        return jsonify({"ok": True, "data": mail_service.inbox(service_id, player["player_id"])})

    @target.route(f"{prefix}/mail/<mail_id>/claim", methods=["POST"])
    def baas_mail_claim(service_id: str, mail_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": mail_service.claim_mail(service_id, player["player_id"], mail_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/cloudsave/<key>", methods=["GET", "PUT"])
    def baas_cloudsave(service_id: str, key: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            if request.method == "GET":
                return jsonify({"ok": True, "data": cloudsave_service.get_key(service_id, player["player_id"], key)})
            body = request.get_json(silent=True) or {}
            return jsonify({
                "ok": True,
                "data": cloudsave_service.put_key(
                    service_id,
                    player["player_id"],
                    key,
                    body.get("value"),
                    expected_version=int(body.get("expected_version", -1)),
                ),
            })
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/cloudsave", methods=["GET"])
    def baas_cloudsave_list(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        return jsonify({"ok": True, "data": cloudsave_service.list_keys(service_id, player["player_id"])})

    @target.route(f"{prefix}/leaderboards/<board_id>/submit", methods=["POST"])
    def baas_lb_submit(service_id: str, board_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": retention_services.submit_score(service_id, player["player_id"], board_id, body.get("score", 0), display_name=player.get("display_name") or "")})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/leaderboards/<board_id>/top", methods=["GET"])
    def baas_lb_top(service_id: str, board_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        limit = int(request.args.get("limit") or 50)
        scope = str(request.args.get("scope") or "").strip()
        if scope == "cross_server" or board_id.startswith("guild_war:"):
            data = guild_war_service.cross_server_top(service_id, board_id, limit=limit)
        else:
            data = retention_services.top_scores(service_id, board_id, limit)
        return jsonify({"ok": True, "data": data})

    @target.route(f"{prefix}/shop/catalog", methods=["GET"])
    def baas_shop_catalog(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        return jsonify({"ok": True, "data": retention_services.shop_catalog(service_id)})

    @target.route(f"{prefix}/shop/purchase", methods=["POST"])
    def baas_shop_purchase(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": retention_services.purchase(service_id, player["player_id"], body.get("product_id"))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/shop/wallet", methods=["GET"])
    def baas_wallet(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        return jsonify({"ok": True, "data": retention_services.get_wallet(service_id, player["player_id"])})

    @target.route(f"{prefix}/achievements", methods=["GET"])
    def baas_achievements(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        return jsonify({"ok": True, "data": retention_services.list_achievements(service_id, player["player_id"])})

    @target.route(f"{prefix}/achievements/<achievement_id>/progress", methods=["POST"])
    def baas_achievement_progress(service_id: str, achievement_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": retention_services.report_achievement_progress(service_id, player["player_id"], achievement_id, int(body.get("progress") or 0))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/achievements/<achievement_id>/claim", methods=["POST"])
    def baas_achievement_claim(service_id: str, achievement_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": retention_services.claim_achievement(service_id, player["player_id"], achievement_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/gifts/redeem", methods=["POST"])
    def baas_gift_redeem(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": retention_services.redeem_gift(service_id, player["player_id"], body.get("code"))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guilds/war/season", methods=["GET"])
    def baas_guild_war_season(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        try:
            return jsonify({"ok": True, "data": guild_war_service.get_active_season(service_id)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guilds/<guild_id>/war/register", methods=["POST"])
    def baas_guild_war_register(service_id: str, guild_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": guild_war_service.register_guild(service_id, player["player_id"], guild_id)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guilds/<guild_id>/war/submit", methods=["POST"])
    def baas_guild_war_submit(service_id: str, guild_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": guild_war_service.submit_battle_result(
                    service_id, player["player_id"], guild_id,
                    win=bool(body.get("win")),
                    score_delta=int(body.get("score_delta") or 0),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guilds", methods=["POST"])
    def baas_guild_create(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": social_services.create_guild(service_id, player["player_id"], body.get("name"))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guilds/<guild_id>", methods=["GET"])
    def baas_guild_get(service_id: str, guild_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        try:
            return jsonify({"ok": True, "data": social_services.get_guild(service_id, guild_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guilds/<guild_id>/join", methods=["POST"])
    def baas_guild_join(service_id: str, guild_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": social_services.join_guild(service_id, player["player_id"], guild_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/battlepass/state", methods=["GET"])
    def baas_bp_state(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": social_services.battlepass_state(service_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/battlepass/xp", methods=["POST"])
    def baas_bp_xp(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": social_services.battlepass_add_xp(service_id, player["player_id"], int(body.get("xp") or 0))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/battlepass/claim", methods=["POST"])
    def baas_bp_claim(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": social_services.battlepass_claim(service_id, player["player_id"], int(body.get("level") or 0))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/tasks/periodic", methods=["GET"])
    def baas_tasks_list(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        return jsonify({"ok": True, "data": social_services.list_periodic_tasks(service_id, player["player_id"])})

    @target.route(f"{prefix}/tasks/<task_id>/progress", methods=["POST"])
    def baas_task_progress(service_id: str, task_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": social_services.update_periodic_task(service_id, player["player_id"], task_id, int(body.get("progress") or 0))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/tasks/<task_id>/claim", methods=["POST"])
    def baas_task_claim(service_id: str, task_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": social_services.claim_periodic_task(service_id, player["player_id"], task_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/compliance/session-start", methods=["POST"])
    def baas_compliance_start(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "data": compliance_service.session_start(service_id, player["player_id"], real_name_verified=bool(body.get("real_name_verified")))})

    @target.route(f"{prefix}/compliance/heartbeat", methods=["POST"])
    def baas_compliance_heartbeat(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "data": compliance_service.heartbeat(service_id, player["player_id"], minutes_played=int(body.get("minutes") or 1))})

    @target.route(f"{prefix}/compliance/verify-real-name", methods=["POST"])
    def baas_compliance_verify(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": compliance_service.verify_real_name(service_id, player["player_id"], name=body.get("name"), id_number=body.get("id_number"))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pve/stamina", methods=["GET"])
    def baas_pve_stamina(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": pve_service.get_stamina(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pve/progress", methods=["GET"])
    def baas_pve_progress(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": pve_service.get_progress(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pve/battle/start", methods=["POST"])
    def baas_pve_battle_start(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": pve_service.start_battle(
                    service_id,
                    player["player_id"],
                    str(body.get("stage_id") or ""),
                    team=body.get("team") if isinstance(body.get("team"), dict) else {},
                    display_name=player.get("display_name") or "",
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pve/battle/settle", methods=["POST"])
    def baas_pve_battle_settle(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": pve_service.settle_battle(
                    service_id,
                    player["player_id"],
                    str(body.get("battle_id") or ""),
                    win=bool(body.get("win")),
                    stars=int(body.get("stars") or 0),
                    duration_ms=int(body.get("duration_ms") or 0),
                    checksum=str(body.get("checksum") or ""),
                    replay_hash=str(body.get("replay_hash") or ""),
                    replay_ticks=int(body.get("replay_ticks") or 0),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/arena/state", methods=["GET"])
    def baas_arena_state(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": arena_service.get_state(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/arena/defense", methods=["GET", "POST"])
    def baas_arena_defense(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            if request.method == "GET":
                target = str(request.args.get("player_id") or player["player_id"])
                return jsonify({"ok": True, "data": arena_service.get_defense(service_id, target)})
            body = request.get_json(silent=True) or {}
            return jsonify({
                "ok": True,
                "data": arena_service.update_defense(
                    service_id,
                    player["player_id"],
                    defense=body.get("defense") if isinstance(body.get("defense"), dict) else {},
                    power=int(body.get("power") or 0),
                    display_name=player.get("display_name") or "",
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/arena/opponents", methods=["GET"])
    def baas_arena_opponents(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            count = int(request.args.get("count") or 3)
            return jsonify({"ok": True, "data": arena_service.list_opponents(service_id, player["player_id"], count=count)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/arena/battle/start", methods=["POST"])
    def baas_arena_battle_start(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": arena_service.start_battle(
                    service_id,
                    player["player_id"],
                    str(body.get("defender_id") or ""),
                    team=body.get("team") if isinstance(body.get("team"), dict) else {},
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/arena/battle/settle", methods=["POST"])
    def baas_arena_battle_settle(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": arena_service.settle_battle(
                    service_id,
                    player["player_id"],
                    str(body.get("battle_id") or ""),
                    win=bool(body.get("win")),
                    duration_ms=int(body.get("duration_ms") or 0),
                    checksum=str(body.get("checksum") or ""),
                    replay_hash=str(body.get("replay_hash") or ""),
                    replay_ticks=int(body.get("replay_ticks") or 0),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/heroes/roster", methods=["GET"])
    def baas_hero_roster(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": hero_service.get_roster(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/heroes/<int:hero_id>/level-up", methods=["POST"])
    def baas_hero_level_up(service_id: str, hero_id: int):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": hero_service.level_up(service_id, player["player_id"], hero_id)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/heroes/<int:hero_id>/equip", methods=["POST"])
    def baas_hero_equip(service_id: str, hero_id: int):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": hero_service.equip(
                    service_id, player["player_id"], hero_id,
                    str(body.get("slot") or ""), str(body.get("equipment_id") or ""),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/inventory", methods=["GET"])
    def baas_inventory_list(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        item_type = str(request.args.get("type") or "")
        try:
            return jsonify({"ok": True, "data": inventory_service.list_inventory(service_id, player["player_id"], item_type=item_type)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/inventory/<item_uid>/use", methods=["POST"])
    def baas_inventory_use(service_id: str, item_uid: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": inventory_service.consume_item(
                    service_id, player["player_id"], item_uid, quantity=int(body.get("quantity") or 1),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/gacha/pools", methods=["GET"])
    def baas_gacha_pools(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        return jsonify({"ok": True, "data": gacha_service.list_pools(service_id)})

    @target.route(f"{prefix}/gacha/<pool_id>/pity", methods=["GET"])
    def baas_gacha_pity(service_id: str, pool_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": gacha_service.get_pity_state(service_id, player["player_id"], pool_id)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/gacha/<pool_id>/pull", methods=["POST"])
    def baas_gacha_pull(service_id: str, pool_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": gacha_service.pull(service_id, player["player_id"], pool_id, count=int(body.get("count") or 1)),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/idle/status", methods=["GET"])
    def baas_idle_status(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": idle_service.get_status(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/idle/claim", methods=["POST"])
    def baas_idle_claim(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": idle_service.claim(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/tower/<tower_id>/progress", methods=["GET"])
    def baas_tower_progress(service_id: str, tower_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": tower_service.get_progress(service_id, player["player_id"], tower_id)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/tower/<tower_id>/battle/start", methods=["POST"])
    def baas_tower_battle_start(service_id: str, tower_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": tower_service.start_battle(
                    service_id, player["player_id"], tower_id, int(body.get("floor") or 1),
                    team=body.get("team") if isinstance(body.get("team"), dict) else {},
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/tower/battle/settle", methods=["POST"])
    def baas_tower_battle_settle(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": tower_service.settle_battle(
                    service_id, player["player_id"], str(body.get("battle_id") or ""),
                    win=bool(body.get("win")), stars=int(body.get("stars") or 0),
                    duration_ms=int(body.get("duration_ms") or 0),
                    checksum=str(body.get("checksum") or ""),
                    replay_hash=str(body.get("replay_hash") or ""),
                    replay_ticks=int(body.get("replay_ticks") or 0),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/iap/products", methods=["GET"])
    def baas_iap_products(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        return jsonify({"ok": True, "data": iap_service.list_products(service_id)})

    @target.route(f"{prefix}/iap/orders", methods=["POST"])
    def baas_iap_create_order(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": iap_service.create_order(
                    service_id, player["player_id"], str(body.get("product_id") or ""),
                    platform=str(body.get("platform") or "dev"),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/iap/orders/<order_id>/verify", methods=["POST"])
    def baas_iap_verify(service_id: str, order_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({
                "ok": True,
                "data": iap_service.verify_and_deliver(
                    service_id, player["player_id"], order_id,
                    receipt=str(body.get("receipt") or ""),
                    platform=str(body.get("platform") or ""),
                    transaction_id=str(body.get("transaction_id") or ""),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms", methods=["GET", "POST"])
    def baas_rooms(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        if request.method == "GET":
            env_key = str(request.args.get("env_key") or "")
            try:
                return jsonify({"ok": True, "data": room_service.list_public_rooms(service_id, env_key=env_key)})
            except ValueError as exc:
                return baas_fail_exc(exc)
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                {
                    "ok": True,
                    "data": room_service.create_room(
                        service_id,
                        player["player_id"],
                        visibility=str(body.get("visibility") or "public"),
                        max_players=body.get("max_players"),
                        env_key=str(body.get("env_key") or ""),
                        battle_mode=str(body.get("battle_mode") or "pvp_1v1"),
                        password=str(body.get("password") or ""),
                    ),
                }
            )
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/join", methods=["POST"])
    def baas_room_join(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                {
                    "ok": True,
                    "data": room_service.join_room(
                        service_id,
                        player["player_id"],
                        room_id=str(body.get("room_id") or ""),
                        invite_code=str(body.get("invite_code") or ""),
                        password=str(body.get("password") or ""),
                        as_spectator=bool(body.get("as_spectator")),
                    ),
                }
            )
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/rejoin", methods=["POST"])
    def baas_room_rejoin(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": room_service.rejoin_room(service_id, room_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/disconnect", methods=["POST"])
    def baas_room_disconnect(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": room_service.mark_disconnected(service_id, room_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/kick", methods=["POST"])
    def baas_room_kick(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        target_id = str(body.get("target_id") or "").strip()
        try:
            return jsonify({"ok": True, "data": room_service.kick_player(service_id, room_id, player["player_id"], target_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/start-battle", methods=["POST"])
    def baas_room_start_battle(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": room_service.start_battle(service_id, room_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/frames", methods=["GET", "POST"])
    def baas_room_frames(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        if request.method == "GET":
            since_seq = int(request.args.get("since_seq") or 0)
            wait_ms = int(request.args.get("wait_ms") or 0)
            exclude_player = str(request.headers.get("X-Baas-Player-Id") or request.args.get("exclude_player_id") or "").strip()
            try:
                if wait_ms > 0:
                    data = room_service.poll_frames(
                        service_id,
                        room_id,
                        since_seq=since_seq,
                        wait_ms=wait_ms,
                        exclude_player_id=exclude_player,
                    )
                else:
                    data = room_service.get_frames(service_id, room_id, since_seq=since_seq)
                return jsonify({"ok": True, "data": data})
            except ValueError as exc:
                return baas_fail_exc(exc)
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": room_service.push_frame(service_id, room_id, player["player_id"], body.get("frame") or {})})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/finish-battle", methods=["POST"])
    def baas_room_finish_battle(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": room_service.finish_battle(service_id, room_id, player["player_id"], body.get("result") or {})})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/replays/<replay_id>", methods=["GET"])
    def baas_replay_get(service_id: str, replay_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        try:
            return jsonify({"ok": True, "data": room_service.get_replay(service_id, replay_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pvp/matchmake", methods=["POST"])
    def baas_pvp_match(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                {
                    "ok": True,
                    "data": pvp_service.matchmake(
                        service_id,
                        player["player_id"],
                        env_key=str(body.get("env_key") or ""),
                        battle_mode=str(body.get("battle_mode") or ""),
                    ),
                }
            )
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pvp/rooms/<room_id>", methods=["GET"])
    def baas_pvp_room(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        try:
            viewer = str(request.headers.get("X-Baas-Player-Id") or request.args.get("player_id") or "").strip()
            return jsonify({"ok": True, "data": pvp_service.get_room(service_id, room_id, viewer_id=viewer)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pvp/rooms/<room_id>/state", methods=["POST"])
    def baas_pvp_sync(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": pvp_service.sync_state(service_id, room_id, player["player_id"], body.get("state") or {})})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pvp/rooms/<room_id>/leave", methods=["POST"])
    def baas_pvp_leave(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": pvp_service.leave_room(service_id, room_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)


register_baas_public_routes()
