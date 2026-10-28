# -*- coding: utf-8 -*-
"""Casual BaaS public REST API. Route bodies live in routes.baas.public."""

from routes.baas.public._deps import (
    _password_auth_rate_limit,
    _player_auth,
    _service_auth,
    baas_public_bp,
)
from routes.baas.public.afk import register as register_afk
from routes.baas.public.auth import register as register_auth
from routes.baas.public.battle import register as register_battle
from routes.baas.public.compliance import register as register_compliance
from routes.baas.public.content import register as register_content
from routes.baas.public.growth import register as register_growth
from routes.baas.public.realtime import register as register_realtime
from routes.baas.public.retention import register as register_retention
from routes.baas.public.social import register as register_social


def register_baas_public_routes(bp=None) -> None:
    target = bp or baas_public_bp
    register_auth(target)
    register_content(target)
    register_retention(target)
    register_social(target)
    register_battle(target)
    register_growth(target)
    register_realtime(target)
    register_afk(target)
    register_compliance(target)


register_baas_public_routes()
