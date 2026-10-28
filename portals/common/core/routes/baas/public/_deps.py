# -*- coding: utf-8 -*-
"""Shared imports for BaaS public route modules."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from routes.baas.http_helpers import baas_player_auth, baas_service_auth, run_baas
from services.baas import announce_service, auth_service, cloudsave_service, compliance_service, mail_service
from services.baas import activity_service, pvp_service, retention_services, social_services
from services.baas import room_service, pve_service, arena_service
from services.baas import gacha_service, hero_service, idle_service, tower_service, iap_service
from services.baas import inventory_service, guild_war_service
from services.baas.afk import afk_economy_service, afk_growth_service, afk_relic_service
from services.baas.errors import baas_fail_exc, baas_success
from services.rate_limit import rate_limit_login

baas_public_bp = Blueprint("baas_public", __name__)


def _service_auth_impl(expected_service_id: str):
    return baas_service_auth(expected_service_id)


def _player_auth_impl(service_id: str):
    return baas_player_auth(service_id, auth_service)


def _password_auth_rate_limit_impl():
    """Apply the portal-wide login throttle before expensive password work."""
    allowed, retry_after = rate_limit_login()
    if allowed:
        return None
    response = jsonify({"ok": False, "error": {"code": "BAAS_AUTH_RATE_LIMITED", "message": "请求过于频繁，请稍后再试"}})
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return response


def _patched(name: str, fallback):
    from routes.baas import public_api

    current = getattr(public_api, name, None)
    if current is not None and current is not fallback:
        return current
    return None


def _service_auth(expected_service_id: str):
    override = _patched("_service_auth", _service_auth)
    if override is not None:
        return override(expected_service_id)
    return _service_auth_impl(expected_service_id)


def _player_auth(service_id: str):
    override = _patched("_player_auth", _player_auth)
    if override is not None:
        return override(service_id)
    return _player_auth_impl(service_id)


def _password_auth_rate_limit():
    override = _patched("_password_auth_rate_limit", _password_auth_rate_limit)
    if override is not None:
        return override()
    return _password_auth_rate_limit_impl()


__all__ = [name for name in globals() if not name.startswith("__")]
