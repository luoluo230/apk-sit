# -*- coding: utf-8 -*-
"""Public realm list / enter (Wave C 选服)."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

    @target.route(f"{prefix}/realms", methods=["GET"])
    def baas_public_realms(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        from services.baas import realm_service

        realm_service.ensure_default_realm(service_id)
        items = realm_service.list_realms(service_id, include_closed=False)
        return jsonify({
            "ok": True,
            "data": {
                "items": [
                    {
                        "realm_id": r.get("realm_id"),
                        "name": r.get("name"),
                        "status": r.get("status"),
                        "open_at": r.get("open_at"),
                    }
                    for r in items
                ],
                "realm_header": "X-Baas-Realm-Id",
            },
        })

    @target.route(f"{prefix}/realms/enter", methods=["POST"])
    def baas_public_realm_enter(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        realm_id = str(body.get("realm_id") or request.headers.get("X-Baas-Realm-Id") or "").strip()
        if not realm_id:
            return baas_fail_exc(ValueError("realm_id 必填"))
        from services.baas import realm_service

        try:
            data = realm_service.assign_player_realm(
                service_id,
                str(player.get("player_id") or ""),
                realm_id,
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)
