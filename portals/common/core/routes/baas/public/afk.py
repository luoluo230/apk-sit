# -*- coding: utf-8 -*-
"""BaaS public routes: afk."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

    @target.route(f"{prefix}/afk/home", methods=["GET"])
    def baas_afk_home(service_id: str):
        sid, err = _service_auth(service_id)
        if err: return err
        player, perr = _player_auth(service_id)
        if perr: return perr
        from services.baas.afk.afk_home_service import get_home
        return run_baas(lambda: get_home(service_id, player["player_id"]))

    @target.route(f"{prefix}/progression/unlocks", methods=["GET"])
    def baas_progression_unlocks(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_relic_service.list_systems(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/artifacts", methods=["GET"])
    def baas_artifacts_list(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_relic_service.list_artifacts(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/artifacts/<artifact_id>/upgrade", methods=["POST"])
    def baas_artifact_upgrade(service_id: str, artifact_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_relic_service.upgrade_artifact(service_id, player["player_id"], artifact_id)})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/runes", methods=["GET"])
    def baas_runes_list(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": afk_relic_service.list_runes(service_id, player["player_id"])})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/runes/inscribe", methods=["POST"])
    def baas_rune_inscribe(service_id: str):
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
                "data": afk_relic_service.inscribe_rune(
                    service_id, player["player_id"],
                    str(body.get("slot") or ""),
                    int(body.get("socket_index") or 0),
                    str(body.get("rune_id") or ""),
                    int(body.get("rune_quality") or 3),
                ),
            })
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/economy/items", methods=["GET"])
    def baas_economy_items(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        try:
            return jsonify({"ok": True, "data": {"items": afk_economy_service.list_items(service_id)}})
        except Exception as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/vip/state", methods=["GET"])
    def baas_vip_state(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        from services.baas.afk import afk_vip_service
        return jsonify({"ok": True, "data": afk_vip_service.get_state(service_id, player["player_id"])})

    @target.route(f"{prefix}/vip/daily-claim", methods=["POST"])
    def baas_vip_daily_claim(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        from services.baas.afk import afk_vip_service
        try:
            return jsonify({"ok": True, "data": afk_vip_service.claim_daily(service_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/config-group", methods=["GET"])
    def baas_config_group(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        from services.baas.afk.afk_config_group import group_factors, list_groups

        return jsonify({
            "ok": True,
            "data": {**group_factors(service_id, player["player_id"]), **list_groups()},
        })

    @target.route(f"{prefix}/config-group/assign", methods=["POST"])
    def baas_config_group_assign(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        body = request.get_json(silent=True) or {}
        player_id = str(body.get("player_id") or "").strip()
        group_id = str(body.get("group_id") or "").strip()
        if not player_id or not group_id:
            return baas_fail_exc(ValueError("player_id 和 group_id 必填"))
        from services.baas.afk.afk_config_group import set_player_group

        try:
            return jsonify({"ok": True, "data": set_player_group(service_id, player_id, group_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)
