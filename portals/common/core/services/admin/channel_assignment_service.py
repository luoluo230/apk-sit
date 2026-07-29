# -*- coding: utf-8 -*-
"""Atomic channel assignment for projects — shared by onboarding and channel API.

Plan: P1-02 Step 2 — project channels + env delivery scope + optional VC copy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from repositories.admin import projects_repo
from services.admin.envelope import attach_legacy_error, fail, ok
from services.admin import project_service, version_service
from services.release.env_registry import list_project_env_keys
from services.release.manifest_service import bootstrap_scopes_for_project

DOCS_CLIENT_BOOTSTRAP = "/docs/client_bootstrap_contract.md"


def _normalize_channel_ids(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(c).strip() for c in raw if str(c).strip()]


def _copy_version_rows_for_channel(
    project_id: str,
    actor: str,
    channel_id: str,
    *,
    env_keys: Optional[List[str]] = None,
) -> int:
    from repositories.admin import versions_repo
    from services.release.env_registry import normalize_release_env_key, stage_to_env_key

    rows = versions_repo.list_versions(project_id)
    if not isinstance(rows, list) or not rows:
        return 0
    allowed_envs = set(env_keys or list_project_env_keys(project_id))

    def _row_env_key(row: Dict[str, Any]) -> str:
        ek = str(row.get("env_key") or "").strip()
        if ek:
            return normalize_release_env_key(ek, project_id=project_id)
        stage = str(row.get("stage") or "").strip()
        return stage_to_env_key(stage) if stage else "development"

    templates: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        env_key = _row_env_key(row)
        if env_keys and env_key not in allowed_envs:
            continue
        key = (
            str(row.get("version_name") or "").strip(),
            env_key,
            str(row.get("platform") or "android").strip().lower(),
        )
        if key not in templates:
            templates[key] = row
    created = 0
    for (_, env_key, platform), template in templates.items():
        payload = {
            "env_key": env_key or "development",
            "platform": platform,
            "channel_id": channel_id,
            "version_name": str(template.get("version_name") or "").strip(),
            "version_code": str(template.get("version_code") or "1").strip(),
            "version_mode": str(template.get("version_mode") or "general").strip(),
        }
        if not payload["version_name"]:
            continue
        result, status = version_service.create_version(project_id, actor, payload)
        if status == 200:
            created += 1
    return created


def assign_channels(
    project_id: str,
    payload: Dict[str, Any],
    actor: str,
) -> Tuple[Dict[str, Any], int]:
    """Assign channels atomically: project whitelist, env delivery scope, optional VC rows."""
    pid = str(project_id or "").strip()
    if not pid or not projects_repo.has_project(pid):
        return attach_legacy_error(fail("项目不存在", code="not_found")), 404

    channel_ids = _normalize_channel_ids(payload.get("channel_ids") or payload.get("channels"))
    if not channel_ids:
        single = str(payload.get("channel_id") or payload.get("channel") or "").strip()
        if single:
            channel_ids = [single]
    if not channel_ids:
        return attach_legacy_error(fail("至少指定一个渠道", code="validation_error")), 400

    env_keys = payload.get("env_keys")
    env_filter = [str(k).strip().lower() for k in env_keys] if isinstance(env_keys, list) else None
    copy_vc = bool(payload.get("copy_version_rows") or payload.get("copy_vc_rows"))

    added: List[str] = []
    for cid in channel_ids:
        result, status = project_service.add_channel(pid, cid)
        if status not in (200, 409):
            return attach_legacy_error(result), status
        if status == 200:
            added.append(cid)

    proj = projects_repo.get_project(pid) or {}
    env_rows = proj.get("release_environments")
    if isinstance(env_rows, list):
        for row in env_rows:
            if not isinstance(row, dict) or not row.get("enabled", True):
                continue
            key = str(row.get("env_key") or "").strip().lower()
            if env_filter and key not in env_filter:
                continue
            channels = row.get("channels") if isinstance(row.get("channels"), list) else []
            merged = list(dict.fromkeys([*(channels or []), *channel_ids]))
            row["channels"] = merged
        proj["release_environments"] = env_rows
        projects_repo.upsert_project(pid, proj)

    copied = 0
    if copy_vc:
        for cid in channel_ids:
            copied += _copy_version_rows_for_channel(pid, actor, cid, env_keys=env_filter)

    bootstrap_scopes_for_project(pid)
    return ok(
        {
            "project_id": pid,
            "channels": proj.get("channels") or [],
            "added": added,
            "copied_version_rows": copied,
            "docs": {"client_bootstrap_contract": DOCS_CLIENT_BOOTSTRAP},
        },
        legacy={"success": True},
    ), 200
