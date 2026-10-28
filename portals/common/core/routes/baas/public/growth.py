# -*- coding: utf-8 -*-
"""BaaS public routes: growth."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

    @target.route(f"{prefix}/growth/equipment", methods=["GET"])
    def baas_growth_equipment(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_growth_service.get_equipment_state(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/growth/equipment/<slot>/enhance", methods=["POST"])
    def baas_growth_enhance(service_id: str, slot: str):
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
                "data": afk_growth_service.enhance_equipment(
                    service_id, player["player_id"], slot, use_luck=bool(body.get("use_luck")),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/growth/equipment/<slot>/refine", methods=["POST"])
    def baas_growth_refine(service_id: str, slot: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_growth_service.refine_equipment(service_id, player["player_id"], slot)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/growth/equipment/<slot>/awaken", methods=["POST"])
    def baas_growth_awaken(service_id: str, slot: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_growth_service.awaken_equipment(service_id, player["player_id"], slot)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/growth/equipment/<slot>/reforge", methods=["POST"])
    def baas_growth_reforge(service_id: str, slot: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_growth_service.reforge_equipment(service_id, player["player_id"], slot)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/growth/equipment/<slot>/socket", methods=["POST"])
    def baas_growth_socket(service_id: str, slot: str):
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
                "data": afk_growth_service.socket_gem(
                    service_id, player["player_id"], slot, str(body.get("gem_item_id") or "gem_ruby"),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/growth/team-power", methods=["GET"])
    def baas_growth_team_power(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        raw = str(request.args.get("heroes") or "").strip()
        team_ids = [int(x) for x in raw.split(",") if x.strip().isdigit()] if raw else None
        try:
            return jsonify({"ok": True, "data": afk_growth_service.estimate_team_power(service_id, player["player_id"], team_ids=team_ids)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/dungeons", methods=["GET"])
    def baas_dungeons_list(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_growth_service.list_dungeons_status(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/dungeons/<dungeon_id>/run", methods=["POST"])
    def baas_dungeon_run(service_id: str, dungeon_id: str):
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
                "data": afk_growth_service.run_dungeon(
                    service_id, player["player_id"], dungeon_id,
                    team=body.get("team") if isinstance(body.get("team"), dict) else None,
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

    @target.route(f"{prefix}/tower/<tower_id>/daily-claim", methods=["POST"])
    def baas_tower_daily_claim(service_id: str, tower_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": tower_service.claim_daily_rewards(service_id, player["player_id"], tower_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/tower/<tower_id>/battle/start-assist", methods=["POST"])
    def baas_tower_battle_start_assist(service_id: str, tower_id: str):
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
                "data": tower_service.start_battle_with_assist(
                    service_id, player["player_id"], tower_id, int(body.get("floor") or 1),
                    team=body.get("team") if isinstance(body.get("team"), dict) else {},
                    assist_friend_id=str(body.get("assist_friend_id") or ""),
                    assist_hero_id=int(body.get("assist_hero_id") or 0),
                ),
            })
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/arena/season", methods=["GET"])
    def baas_arena_season(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        from services.baas.afk import afk_season_service
        return jsonify({"ok": True, "data": afk_season_service.list_arena_tier_status(service_id, player["player_id"])})

    @target.route(f"{prefix}/arena/season/tier-claim", methods=["POST"])
    def baas_arena_tier_claim(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        from services.baas.afk import afk_season_service
        try:
            return jsonify({"ok": True, "data": afk_season_service.claim_arena_tier_reward(service_id, player["player_id"], str(body.get("tier") or ""))})
        except ValueError as exc:
            return baas_fail_exc(exc)

