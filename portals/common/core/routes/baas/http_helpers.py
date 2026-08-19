# -*- coding: utf-8 -*-
"""Shared HTTP helpers for BaaS routes."""

from __future__ import annotations

from typing import Any, Callable, Optional, Tuple

from flask import jsonify, request

from services.baas.errors import baas_error, baas_fail, baas_fail_exc, baas_success
from services.baas.helpers import parse_bearer_token, verify_api_secret
from services.baas.service_crud import get_service_auth_row


def baas_service_auth(expected_service_id: str):
    service_id = str(expected_service_id or "").strip()
    api_key = str(request.headers.get("X-Baas-Api-Key") or request.args.get("api_key") or "").strip()
    header_sid = str(request.headers.get("X-Baas-Service-Id") or "").strip()
    if header_sid and header_sid != service_id:
        return None, baas_fail("BAAS_AUTH_SERVICE_MISMATCH")
    if not service_id or not api_key:
        return None, baas_fail("BAAS_AUTH_MISSING_KEY")
    row = get_service_auth_row(service_id)
    if not row or not verify_api_secret(api_key, str(row["api_secret_hash"] or "")):
        return None, baas_fail("BAAS_AUTH_INVALID_CREDENTIALS")
    return service_id, None


def baas_player_auth(service_id: str, auth_service):
    auth = str(request.headers.get("Authorization") or "")
    token = parse_bearer_token(auth)
    player_id = str(request.headers.get("X-Baas-Player-Id") or request.args.get("player_id") or "").strip()
    if not player_id or not token:
        return None, baas_fail("BAAS_AUTH_PLAYER_REQUIRED")
    try:
        return auth_service.resolve_player(service_id, player_id, token), None
    except Exception as exc:
        return None, baas_fail_exc(exc)


def run_baas(fn: Callable[[], Any]) -> Tuple[Any, int]:
    try:
        return baas_success(fn())
    except Exception as exc:
        return baas_fail_exc(exc)
