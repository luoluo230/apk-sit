# -*- coding: utf-8 -*-
"""Migrate legacy project_versions rows to include scope_id / env_key."""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.data import project_versions_db, save_project_versions, projects_db  # noqa: E402
from services.release.manifest_service import bootstrap_scopes_for_project  # noqa: E402
from services.release.release_context import apply_scope_fields_to_version_row  # noqa: E402


def main() -> int:
    changed_projects = 0
    changed_rows = 0
    for project_id in list((projects_db or {}).keys()):
        pid = str(project_id).strip()
        if not pid:
            continue
        bootstrap_scopes_for_project(pid)
        versions = project_versions_db.get(pid) or []
        if not isinstance(versions, list):
            continue
        project_changed = False
        for i, row in enumerate(versions):
            if not isinstance(row, dict):
                continue
            updated = apply_scope_fields_to_version_row(row, pid)
            if updated != row:
                versions[i] = updated
                changed_rows += 1
                project_changed = True
        if project_changed:
            project_versions_db[pid] = versions
            changed_projects += 1
    save_project_versions()
    print(f"migrated projects={changed_projects} rows={changed_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
