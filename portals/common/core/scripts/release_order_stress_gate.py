#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""10-thread release_order stress gate (P0-02 Step 3)."""

from __future__ import annotations

import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

PROJECT_ID = "GomeKu"
SCOPE_ID = "gomeku:development:1001:android"


def _ensure_fixture() -> None:
    from models.db import init_db, reset_db_connection
    from repositories.registry import accessors
    from data.projects import projects_db

    reset_db_connection(close_all=True)
    init_db()
    if PROJECT_ID not in projects_db:
        accessors.save_project(
            PROJECT_ID,
            {
                "project_id": PROJECT_ID,
                "slug": "gomeku",
                "name": "GomeKu",
                "platforms": ["android", "wechat_minigame"],
                "channels": ["1001"],
            },
        )
    versions = accessors.list_project_versions(PROJECT_ID) or []
    if not any(str(v.get("version_code")) == "12" for v in versions):
        accessors.save_project_versions(
            PROJECT_ID,
            versions
            + [
                {
                    "id": uuid.uuid4().hex[:12],
                    "channel_id": "1001",
                    "channel": "1001",
                    "version_name": "1.0.0",
                    "version_code": "12",
                    "platform": "android",
                    "env_key": "development",
                }
            ],
        )


def _worker(idx: int) -> str:
    from models.db import reset_db_connection
    from services.release import order_crud

    reset_db_connection(close_all=True)
    _ensure_fixture()
    row = order_crud.create_release_order(
        PROJECT_ID,
        {
            "scope_id": SCOPE_ID,
            "env_key": "development",
            "channel_id": "1001",
            "platform": "android",
            "status": "draft",
            "version_name": "1.0.0",
            "version_code": "12",
            "version_id": "",
        },
        actor="stress-gate",
    )
    if not row or not row.get("release_order_id"):
        raise RuntimeError("order not readable after create")
    return str(row["release_order_id"])


def main() -> int:
    os.environ.setdefault("USE_SQLITE", "true")
    errors = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_worker, i) for i in range(10)]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                errors.append(str(exc))
    if errors:
        print("release_order_stress_gate FAILED:")
        for e in errors[:10]:
            print(" ", e)
        return 1
    print("release_order_stress_gate PASS (10 threads)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
