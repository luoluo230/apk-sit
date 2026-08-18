# -*- coding: utf-8 -*-
"""BaaS bootstrap payload for clients."""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.data import projects_db
from services.baas.helpers import is_casual_baas_project, resolve_project_by_game_credentials
from services.baas.registry import list_catalog, public_endpoints_for_features
from services.baas.service_crud import ensure_service, get_service, list_services


def build_baas_bootstrap(
    *,
    game_id: str = "",
    game_key: str = "",
    project_id: str = "",
    env_key: str = "development",
    service_id: str = "",
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid:
        pid = resolve_project_by_game_credentials(game_id=game_id, game_key=game_key) or ""
    if not pid or pid not in projects_db:
        raise ValueError("项目凭证无效")
    if not is_casual_baas_project(pid):
        raise ValueError("项目未启用轻度 BaaS 模式")
    ek = str(env_key or "development").strip() or "development"
    sid = str(service_id or "").strip()
    if sid:
        svc = get_service(sid)
        if not svc or svc.get("project_id") != pid:
            raise ValueError("休闲服务不存在")
    else:
        services = list_services(pid, ek)
        if services:
            svc = get_service(services[0]["service_id"]) or {}
        else:
            svc, _secret = ensure_service(pid, ek)
    flags = dict(svc.get("feature_flags") or {})
    endpoints = public_endpoints_for_features(flags)
    base = f"/api/baas/v1/{svc['service_id']}"
    from services.release.baas_bootstrap_contract import CONTRACT_VERSION

    return {
        "ok": True,
        "contract_version": CONTRACT_VERSION,
        "project_id": pid,
        "service_id": svc["service_id"],
        "env_key": svc.get("env_key") or ek,
        "config_version": svc.get("config_version") or 1,
        "feature_flags": flags,
        "features": list_catalog(),
        "endpoints": {k: v.replace("{service_id}", svc["service_id"]) for k, v in endpoints.items()},
        "public_api_base": base,
        "auth_header_service": "X-Baas-Service-Id",
        "auth_header_key": "X-Baas-Api-Key",
    }
