# -*- coding: utf-8 -*-
"""Public startup gate: maintenance / force-update checks for client bootstrap."""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.data import projects_db
from services.release.env_registry import normalize_release_env_key
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id


def _resolve_project_id(
    *,
    project_id: str = "",
    game_id: str = "",
    game_key: str = "",
) -> tuple[str, Optional[str]]:
    """Return (project_id, error). Prefer credential pair; accept explicit project_id."""
    pid = str(project_id or "").strip()
    gid = str(game_id or "").strip()
    gkey = str(game_key or "").strip()

    if gid and gkey:
        matched = next(
            (
                key
                for key, project in projects_db.items()
                if str(project.get("game_id") or "") == gid and str(project.get("game_key") or "") == gkey
            ),
            "",
        )
        if matched:
            return matched, None
        return "", "项目凭证无效"

    if pid and pid in projects_db:
        return pid, None

    # Legacy clients wrongly put project_id into game_id query; accept only if it is a project key.
    if gid and gid in projects_db and not gkey:
        return gid, None

    if not pid and not gid:
        return "", "project_id 或 game_id/game_key 必填"

    return "", "未知项目"


def resolve_startup_gate(
    project_id: str = "",
    *,
    game_id: str = "",
    game_key: str = "",
    env_key: str = "",
    channel_id: str = "",
    platform: str = "",
    version_name: str = "",
    version_code: str = "",
) -> Dict[str, Any]:
    pid, err = _resolve_project_id(project_id=project_id, game_id=game_id, game_key=game_key)
    if err or not pid:
        return {
            "ok": False,
            "allowed": False,
            "maintenance": False,
            "force_update": False,
            "message": err or "未知项目",
            "force_update_url": "",
            "error": err or "未知项目",
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

            plat = str(platform or "android").strip().lower() or "android"
            resolved_channel = resolve_channel_id(pid, channel_id) or str(channel_id or "").strip()
            scope_id = build_scope_id(project_slug(pid), ek, resolved_channel, plat)
            bundle = find_bootstrap_bundle(
                scope_id,
                platform=plat,
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
            # Bundle lookup failures must not invent force_update; policy flags still apply.
            pass

    allowed = not maintenance and not force_update
    return {
        "ok": True,
        "allowed": allowed,
        "maintenance": maintenance,
        "force_update": force_update,
        "message": message
        or (
            "服务器维护中，请稍后再试。"
            if maintenance
            else ("需要更新客户端。" if force_update else "")
        ),
        "force_update_url": force_url,
        "project_id": pid,
        "env_key": ek,
    }
