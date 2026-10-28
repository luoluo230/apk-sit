# -*- coding: utf-8 -*-
"""BaaS public routes: social."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

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

    @target.route(f"{prefix}/friends", methods=["GET"])
    def baas_friends_list(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        from services.baas.afk import afk_friend_service
        return jsonify({"ok": True, "data": afk_friend_service.list_friends(service_id, player["player_id"])})

    @target.route(f"{prefix}/friends/add", methods=["POST"])
    def baas_friends_add(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        from services.baas.afk import afk_friend_service
        try:
            return jsonify({"ok": True, "data": afk_friend_service.add_friend(service_id, player["player_id"], body.get("friend_player_id"))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/friends/assist", methods=["POST"])
    def baas_friends_assist(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        from services.baas.afk import afk_friend_service
        try:
            return jsonify({"ok": True, "data": afk_friend_service.assist_friend(service_id, player["player_id"], body.get("friend_player_id"))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guild/status", methods=["GET"])
    def baas_guild_status(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        from services.baas.afk import afk_guild_service
        return jsonify({"ok": True, "data": afk_guild_service.guild_status(service_id, player["player_id"])})

    @target.route(f"{prefix}/guild/donate", methods=["POST"])
    def baas_guild_donate(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        from services.baas.afk import afk_guild_service
        try:
            return jsonify({"ok": True, "data": afk_guild_service.donate(service_id, player["player_id"], amount=int(body.get("amount") or 1000))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guild/tech/upgrade", methods=["POST"])
    def baas_guild_tech_upgrade(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        from services.baas.afk import afk_guild_service
        try:
            return jsonify({"ok": True, "data": afk_guild_service.upgrade_tech(service_id, player["player_id"], str(body.get("tech_id") or ""))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guild/shop/purchase", methods=["POST"])
    def baas_guild_shop_purchase(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        from services.baas.afk import afk_guild_service
        try:
            return jsonify({"ok": True, "data": afk_guild_service.guild_shop_purchase(service_id, player["player_id"], str(body.get("goods_id") or ""))})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/guild/raid/hit", methods=["POST"])
    def baas_guild_raid_hit(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        from services.baas.afk import afk_guild_service
        try:
            return jsonify({"ok": True, "data": afk_guild_service.raid_hit(service_id, player["player_id"], int(body.get("damage") or 1000))})
        except ValueError as exc:
            return baas_fail_exc(exc)
