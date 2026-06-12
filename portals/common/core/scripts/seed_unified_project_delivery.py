# -*- coding: utf-8 -*-
"""Rebuild local demo delivery data using the unified SQLite model."""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.data import project_versions_db, projects_db  # noqa: E402
from models.db import _get_conn, get_cursor, init_db  # noqa: E402
from services.release.env_registry import normalize_release_env_key  # noqa: E402
from services.release.manifest_service import bootstrap_scopes_for_project  # noqa: E402
from services.release.release_order_service import create_release_order  # noqa: E402
from services.release.topology_binding_service import upsert_topology_binding  # noqa: E402


def main() -> None:
    init_db()
    with get_cursor() as cur:
        for table in (
            "release_order_events",
            "release_order_artifacts",
            "release_order_prechecks",
            "release_approvals",
            "release_orders",
            "release_bundles",
            "release_scopes",
            "topology_bindings",
        ):
            cur.execute(f"DELETE FROM {table}")

    for project_id in projects_db:
        bootstrap_scopes_for_project(project_id)
        topologies = _get_conn().execute(
            "SELECT topology_id, env_key FROM ops_topologies WHERE project_id=? ORDER BY is_default DESC, updated_at DESC",
            (project_id,),
        ).fetchall()
        topology_by_env = {}
        for row in topologies:
            topology_by_env.setdefault(str(row["env_key"]), str(row["topology_id"]))
        channels = [str(value) for value in (projects_db.get(project_id) or {}).get("channels") or []]
        for env_key, topology_id in topology_by_env.items():
            for channel_id in channels:
                upsert_topology_binding(
                    {
                        "project_id": project_id,
                        "env_key": env_key,
                        "channel_id": channel_id,
                        "topology_id": topology_id,
                        "note": "统一项目交付演示绑定",
                    },
                    actor="seed",
                )

        seen = set()
        for version in project_versions_db.get(project_id) or []:
            if not isinstance(version, dict):
                continue
            env_key = normalize_release_env_key(version.get("env_key") or version.get("stage"), default="development")
            key = (env_key, str(version.get("channel") or ""), str(version.get("platform") or "android"))
            if key in seen or not key[1]:
                continue
            seen.add(key)
            create_release_order(
                project_id,
                {
                    "env_key": env_key,
                    "channel_id": key[1],
                    "platform": key[2],
                    "version_id": str(version.get("id") or ""),
                    "reason": "统一项目交付演示发布单",
                },
                "seed",
            )
    print("Unified project delivery demo data rebuilt.")


if __name__ == "__main__":
    main()
