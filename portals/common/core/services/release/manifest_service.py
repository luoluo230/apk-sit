# -*- coding: utf-8 -*-
"""ProjectReleaseManifest load and scope bootstrap."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from data.channels import get_channels_for_project
from services.release.env_registry import list_project_env_keys
from services.release.scope_ids import build_scope_id, list_channel_defs, project_slug
from services.release.storage import find_manifest, load_manifests, save_manifests, upsert_scope


def list_manifests() -> List[Dict[str, Any]]:
    return load_manifests()


def get_manifest(project_id: str) -> Dict[str, Any]:
    return find_manifest(project_id)


def upsert_manifest(payload: Dict[str, Any]) -> Dict[str, Any]:
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("project_id required")
    rows = load_manifests()
    hit = -1
    for i, row in enumerate(rows):
        if isinstance(row, dict) and str(row.get("project_id") or "").strip() == project_id:
            hit = i
            break
    merged = dict(rows[hit] if hit >= 0 else {})
    merged.update(payload)
    merged["project_id"] = project_id
    if not str(merged.get("project_slug") or "").strip():
        merged["project_slug"] = project_slug(project_id)
    merged["status"] = str(merged.get("status") or "active").strip() or "active"
    merged["updated_at"] = datetime.now().isoformat()
    if hit >= 0:
        rows[hit] = merged
    else:
        rows.append(merged)
    save_manifests(rows)
    return merged


def _channel_defs(manifest: Dict[str, Any], project_id: str) -> List[Dict[str, Any]]:
    return list_channel_defs(manifest, project_id)


def bootstrap_scopes_for_project(project_id: str) -> List[Dict[str, Any]]:
    manifest = find_manifest(project_id)
    if not manifest:
        slug = project_slug(project_id)
        manifest = {
            "project_id": project_id,
            "project_slug": slug,
            "topology_pattern": "topology-{project_slug}-{env_key}-default",
            "default_scopes_per_env": True,
        }
    slug = str(manifest.get("project_slug") or project_slug(project_id)).strip()
    pattern = str(manifest.get("topology_pattern") or "topology-{project_slug}-{env_key}-default").strip()
    channels = _channel_defs(manifest, project_id)
    enabled_ids = {str(c.get("id") or "").strip() for c in get_channels_for_project(project_id)}
    if enabled_ids:
        channels = [ch for ch in channels if str(ch.get("channel_id") or "").strip() in enabled_ids]
    created: List[Dict[str, Any]] = []
    now = datetime.now().isoformat()
    for env_key in list_project_env_keys(project_id):
        for ch in channels:
            channel_platforms = ch.get("platforms") if isinstance(ch.get("platforms"), list) else []
            platforms = [str(p).strip().lower() for p in channel_platforms if str(p).strip().lower() in {"android", "ios"}]
            if not platforms:
                platforms = ["android", "ios"]
            for plat in platforms:
                scope_id = build_scope_id(slug, env_key, ch["channel_id"], plat)
                topology_id = pattern.format(project_slug=slug, env_key=env_key, project_id=project_id)
                row = {
                    "scope_id": scope_id,
                    "project_id": project_id,
                    "env_key": env_key,
                    "channel_id": ch["channel_id"],
                    "channel_key": ch.get("channel_key") or ch["channel_id"],
                    "platform": plat,
                    "default_topology_id": topology_id,
                    "override": {"topology_id": ""},
                    "status": "active",
                    "updated_at": now,
                }
                created.append(upsert_scope(row))
    return created
