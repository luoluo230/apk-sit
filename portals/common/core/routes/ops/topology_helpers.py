# -*- coding: utf-8 -*-
"""Shared topology route helpers."""
from __future__ import annotations

from models.data import get_channels_for_project, project_versions_db
from services.release.topology_binding_service import list_topology_bindings
from routes.ops import deps as ops_helpers


def project_topology_catalog(project_id: str):
    rows = ops_helpers._list_topologies(project_id, None)
    env_values = []
    seen_env = set()
    for item in ops_helpers._default_env_options() + [
        {"env_key": str(x.get("env_key") or ""), "label": str(x.get("env_label") or ops_helpers._env_label(x.get("env_key") or ""))}
        for x in rows
    ]:
        key = ops_helpers._normalize_env_key(item.get("env_key") or "")
        if key and key not in seen_env:
            seen_env.add(key)
            env_values.append({"env_key": key, "label": str(item.get("label") or ops_helpers._env_label(key))})
    return {"project_id": project_id, "count": len(rows), "topologies": rows, "environments": env_values}


def project_binding_catalog(project_id: str):
    return {
        "project_id": project_id,
        "bindings": list_topology_bindings(project_id),
        "topologies": ops_helpers._list_topologies(project_id, None),
        "channels": [
            {
                "channel_id": str(item.get("id") or "").strip(),
                "channel_name": str(item.get("name") or item.get("id") or "").strip(),
            }
            for item in (get_channels_for_project(project_id) or [])
            if str(item.get("id") or "").strip()
        ],
        "version_names": sorted(
            {
                str(item.get("version_name") or "").strip()
                for item in (project_versions_db.get(project_id) or [])
                if isinstance(item, dict) and str(item.get("version_name") or "").strip()
            }
        ),
    }
