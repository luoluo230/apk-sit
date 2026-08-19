# -*- coding: utf-8
"""Channel publish E2E dry-run for iOS and minigame scopes."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _check_scope(project_id: str, platform: str) -> dict:
    from models.data import projects_db, project_versions_db

    ok = project_id in projects_db
    versions = project_versions_db.get(project_id) or []
    scoped = [
        row
        for row in versions
        if isinstance(row, dict) and str(row.get("platform") or "").lower() == platform
    ]
    return {
        "project_exists": ok,
        "platform": platform,
        "version_rows": len(scoped),
        "ready": ok and len(scoped) > 0,
    }


def main() -> int:
    project_id = str(os.getenv("E2E_PROJECT_ID") or "GomeKu")
    results = {
        "ios": _check_scope(project_id, "ios"),
        "minigame_wechat": _check_scope(project_id, "wechat"),
    }
    results["ok"] = all(row.get("ready") for row in results.values())
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
