# -*- coding: utf-8 -*-
"""BaaS public routes: auth."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

    @target.route(f"{prefix}/auth/guest", methods=["POST"])
    def baas_auth_guest(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            data = auth_service.guest_login(
                service_id,
                display_name=str(body.get("display_name") or ""),
                guest_id=str(body.get("guest_id") or ""),
            )
            realm_id = str(body.get("realm_id") or request.headers.get("X-Baas-Realm-Id") or "").strip()
            if realm_id and data.get("player_id"):
                from services.baas import realm_service

                realm_service.assign_player_realm(service_id, str(data["player_id"]), realm_id)
                data["realm_id"] = realm_id
            elif data.get("player_id"):
                from services.baas import realm_service

                data["realm_id"] = realm_service.get_player_realm(service_id, str(data["player_id"]))
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/auth/register", methods=["POST"])
    def baas_auth_register(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        limited = _password_auth_rate_limit()
        if limited:
            return limited
        body = request.get_json(silent=True) or {}
        try:
            data = auth_service.register_password(service_id, username=body.get("username"), password=body.get("password"), display_name=body.get("display_name"))
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/auth/bind-password", methods=["POST"])
    def baas_auth_bind_password(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        limited = _password_auth_rate_limit()
        if limited:
            return limited
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            data = auth_service.bind_password(
                service_id,
                player_id=str(player.get("player_id") or ""),
                username=body.get("username"),
                password=body.get("password"),
                display_name=body.get("display_name"),
            )
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/auth/login", methods=["POST"])
    def baas_auth_login(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        limited = _password_auth_rate_limit()
        if limited:
            return limited
        body = request.get_json(silent=True) or {}
        try:
            data = auth_service.password_login(service_id, username=body.get("username"), password=body.get("password"))
            return jsonify({"ok": True, "data": data})
        except ValueError as exc:
            return baas_fail_exc(exc)
