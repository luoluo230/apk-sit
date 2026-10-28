# -*- coding: utf-8 -*-
"""BaaS public routes: content."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

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
