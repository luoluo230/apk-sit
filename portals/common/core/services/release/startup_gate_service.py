# -*- coding: utf-8 -*-
"""Public startup gate: maintenance / force-update checks for client bootstrap."""

from __future__ import annotations

from typing import Any, Dict

from models.data import projects_db
from services.release.env_registry import normalize_release_env_key


def resolve_startup_gate(
    project_id: str,
    *,
    env_key: str = "",
    channel_id: str = "",
    platform: str = "",
    version_name: str = "",
    version_code: str = "",
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid or pid not in projects_db:
        return {
            "ok": True,
            "allowed": True,
            "maintenance": False,
            "force_update": False,
            "message": "",
            "force_update_url": "",
        }

    ek = normalize_release_env_key(env_key or "development", project_id=pid)
    try:
        from services.release.release_policy_service import get_env_release_policy

        policy = get_env_release_policy(pid, ek)
    except Exception:
        policy = {}

    maintenance = bool(policy.get("maintenance_mode"))
    force_update = bool(policy.get("force_client_update"))
    message = str(policy.get("maintenance_message") or "").strip()
    force_url = str(policy.get("force_update_url") or "").strip()

    if not maintenance and not force_update:
        try:
            from services.release.bundle_service import find_bootstrap_bundle

            bundle = find_bootstrap_bundle(
                pid,
                ek,
                channel_id,
                platform=platform or "android",
                version_name=version_name,
                version_code=version_code,
            )
            if isinstance(bundle, dict) and bundle.get("force_update"):
                force_update = True
                if not message:
                    message = str(bundle.get("force_update_message") or "请更新到最新版本后进入游戏。")
                if not force_url:
                    force_url = str(bundle.get("force_update_url") or "")
        except Exception:
            pass

    allowed = not maintenance and not force_update
    return {
        "ok": True,
        "allowed": allowed,
        "maintenance": maintenance,
        "force_update": force_update,
        "message": message or ("服务器维护中，请稍后再试。" if maintenance else ("需要更新客户端。" if force_update else "")),
        "force_update_url": force_url,
        "project_id": pid,
        "env_key": ek,
    }
