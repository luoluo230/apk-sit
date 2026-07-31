#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registry integration smoke: onboard path → repo → infra_nodes (P0-02 DoD)."""

from __future__ import annotations

import os
import sys
import uuid

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


def main() -> int:
    os.environ.setdefault("USE_SQLITE", "true")
    from models.db import init_db

    init_db()
    from repositories.registry import accessors
    from repositories.infra_nodes_repo import list_nodes

    slug = f"regsmoke{uuid.uuid4().hex[:6]}"
    project_id = slug.title()
    accessors.save_project(
        project_id,
        {
            "project_id": project_id,
            "slug": slug,
            "name": f"Registry Smoke {slug}",
            "platforms": ["android"],
            "channels": ["1001"],
        },
    )
    loaded = accessors.get_project(project_id)
    if not loaded or loaded.get("slug") != slug:
        print("registry_integration_smoke FAILED: project round-trip")
        return 1
    nodes = list_nodes(role=None)
    if not isinstance(nodes, list):
        print("registry_integration_smoke FAILED: infra_nodes list")
        return 1
    print("registry_integration_smoke PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
