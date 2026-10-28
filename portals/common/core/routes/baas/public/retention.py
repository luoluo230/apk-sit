# -*- coding: utf-8 -*-
"""BaaS public routes: retention."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

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
