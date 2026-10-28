# -*- coding: utf-8 -*-
"""BaaS public routes: battle."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

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
                    str(body.get("slot") or ""), str(body.get("equipment_id") or body.get("item_id") or ""),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/heroes/<int:hero_id>/star-up", methods=["POST"])
    def baas_hero_star_up(service_id: str, hero_id: int):
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
                "data": afk_growth_service.star_up_hero(
                    service_id, player["player_id"], hero_id,
                    use_crystal=bool(body.get("use_crystal")),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/heroes/<int:hero_id>/talent", methods=["POST"])
    def baas_hero_talent(service_id: str, hero_id: int):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_growth_service.add_talent_point(service_id, player["player_id"], hero_id)})
        except Exception as exc:
            return baas_fail_exc(exc)

