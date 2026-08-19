# -*- coding: utf-8 -*-
"""Admin global search aggregation."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List
from urllib.parse import quote

from config import DATA_DIR
from models.data import (
    can_edit_project,
    can_view_project,
    project_tasks_db,
    project_versions_db,
    projects_db,
)


def search_admin_content(query: str, username: str) -> Dict[str, List[Dict[str, Any]]]:
    """Search projects, tasks, users, release orders, versions, and docs."""
    q = str(query or "").strip()[:80]
    results: Dict[str, List[Dict[str, Any]]] = {
        "projects": [],
        "tasks": [],
        "users": [],
        "release_orders": [],
        "versions": [],
        "docs": [],
    }
    if not q:
        return results

    ql = q.lower()
    for pid, project in projects_db.items():
        if not can_view_project(pid, username):
            continue
        if (
            ql in (pid or "").lower()
            or ql in (project.get("name") or "").lower()
            or ql in (project.get("name_en") or "").lower()
            or ql in (project.get("intro") or "").lower()
        ):
            results["projects"].append(
                {
                    "id": pid,
                    "name": project.get("name", pid),
                    "title": project.get("name", pid),
                    "category": "project",
                    "link": "/admin/projects/%s/tasks" % pid,
                }
            )

    for pid, tasks in project_tasks_db.items():
        if not can_view_project(pid, username):
            continue
        for task in tasks or []:
            if ql in (task.get("title") or "").lower() or ql in (task.get("content") or "").lower():
                results["tasks"].append(
                    {
                        "id": task.get("id"),
                        "project_id": pid,
                        "title": (task.get("title") or "")[:60],
                        "category": "task",
                        "link": "/admin/projects/%s/tasks" % pid,
                    }
                )

    from repositories.admin import users_repo

    user_index = users_repo.list_users()
    if can_edit_project(next(iter(projects_db.keys()), ""), username) or (
        user_index.get(username) or {}
    ).get("role") in ("admin", "super_admin"):
        for uname in user_index:
            if ql in (uname or "").lower():
                results["users"].append(
                    {
                        "id": uname,
                        "title": uname,
                        "category": "user",
                        "link": "/admin/users",
                    }
                )

    try:
        from models.db import _db_lock, _get_conn, init_db
        from services.release.storage import _decode

        init_db()
        with _db_lock:
            order_rows = _get_conn().execute(
                "SELECT project_id, release_order_id, version_name, version_code, status, payload "
                "FROM release_orders ORDER BY updated_at DESC LIMIT 400"
            ).fetchall()
        for row in order_rows or []:
            pid = str(row["project_id"] or "")
            if pid not in projects_db or not can_view_project(pid, username):
                continue
            payload = _decode(row["payload"], {}) or {}
            hay = " ".join(
                [
                    str(row["release_order_id"] or ""),
                    str(row["version_name"] or ""),
                    str(row["version_code"] or ""),
                    str(row["status"] or ""),
                    str(payload.get("release_reason_type") or ""),
                ]
            ).lower()
            if ql not in hay:
                continue
            oid = str(row["release_order_id"] or "")
            results["release_orders"].append(
                {
                    "id": oid,
                    "project_id": pid,
                    "title": "%s (%s)" % (row["version_name"] or oid, row["version_code"] or "-"),
                    "category": "release_order",
                    "link": "/admin/projects/%s/release-orders/%s" % (pid, oid),
                }
            )
            if len(results["release_orders"]) >= 20:
                break
    except Exception:
        pass

    for pid, versions in (project_versions_db or {}).items():
        if pid not in projects_db or not can_view_project(pid, username):
            continue
        for ver in versions or []:
            if not isinstance(ver, dict):
                continue
            hay = " ".join(
                [
                    str(ver.get("id") or ""),
                    str(ver.get("version_name") or ""),
                    str(ver.get("version_code") or ""),
                    str(ver.get("channel_id") or ver.get("channel") or ""),
                    str(ver.get("platform") or ""),
                ]
            ).lower()
            if ql not in hay:
                continue
            vid = str(ver.get("id") or "")
            results["versions"].append(
                {
                    "id": vid,
                    "project_id": pid,
                    "title": "%s / %s" % (ver.get("version_name") or vid, ver.get("version_code") or "-"),
                    "category": "version",
                    "link": "/admin/projects/%s/versions?version_id=%s" % (pid, quote(vid)),
                }
            )
            if len(results["versions"]) >= 20:
                break
        if len(results["versions"]) >= 20:
            break

    try:
        docs_path = os.path.join(DATA_DIR, "documents.json")
        if os.path.isfile(docs_path):
            with open(docs_path, "r", encoding="utf-8") as fh:
                docs_payload = json.load(fh)
            doc_rows = docs_payload if isinstance(docs_payload, list) else (docs_payload.get("documents") or [])
            for doc in doc_rows or []:
                if not isinstance(doc, dict):
                    continue
                hay = " ".join(
                    [
                        str(doc.get("id") or ""),
                        str(doc.get("title") or ""),
                        str(doc.get("summary") or doc.get("description") or ""),
                        str(doc.get("module") or ""),
                        str(doc.get("category") or ""),
                    ]
                ).lower()
                if ql not in hay:
                    continue
                did = str(doc.get("id") or doc.get("slug") or "")
                results["docs"].append(
                    {
                        "id": did,
                        "title": str(doc.get("title") or did)[:60],
                        "category": "doc",
                        "link": "/docs/%s" % quote(did) if did else "/docs",
                    }
                )
                if len(results["docs"]) >= 20:
                    break
    except Exception:
        pass

    return results


def flatten_search_hits(results: Dict[str, List[Dict[str, Any]]], *, limit: int = 12) -> List[Dict[str, Any]]:
    """Merge category buckets into a single ranked list for typeahead."""
    order = ("projects", "release_orders", "versions", "docs", "tasks", "users")
    hits: List[Dict[str, Any]] = []
    for bucket in order:
        for item in results.get(bucket) or []:
            if len(hits) >= limit:
                return hits
            hits.append(dict(item))
    return hits
