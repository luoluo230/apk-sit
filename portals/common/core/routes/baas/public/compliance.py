# -*- coding: utf-8 -*-
"""BaaS public routes: compliance."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

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
