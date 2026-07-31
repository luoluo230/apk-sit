# -*- coding: utf-8
"""Admin global search page."""

from __future__ import annotations

import html
import json
import os
from urllib.parse import quote

from flask import request

from config import DATA_DIR
from models.data import (
    can_edit_project,
    can_view_project,
    project_tasks_db,
    project_versions_db,
    projects_db,
)
from services.authz import login_required


def register_routes(bp, *, admin_layout, current_username):
    @bp.route("/admin/search")
    @login_required
    def admin_search():
        """全局搜索：项目、任务、用户、发布单、版本、文档。"""
        q = (request.args.get("q") or "").strip()[:80]
        username = current_username()
        results = {
            "projects": [],
            "tasks": [],
            "users": [],
            "release_orders": [],
            "versions": [],
            "docs": [],
        }
        if q:
            ql = q.lower()
            for pid, p in projects_db.items():
                if not can_view_project(pid, username):
                    continue
                if (
                    ql in (pid or "").lower()
                    or ql in (p.get("name") or "").lower()
                    or ql in (p.get("name_en") or "").lower()
                    or ql in (p.get("intro") or "").lower()
                ):
                    results["projects"].append(
                        {
                            "id": pid,
                            "name": p.get("name", pid),
                            "link": "/admin/projects/%s/tasks" % pid,
                        }
                    )
            for pid, tasks in project_tasks_db.items():
                if not can_view_project(pid, username):
                    continue
                for t in tasks or []:
                    if ql in (t.get("title") or "").lower() or ql in (t.get("content") or "").lower():
                        results["tasks"].append(
                            {
                                "id": t.get("id"),
                                "project_id": pid,
                                "title": (t.get("title") or "")[:60],
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
                        results["users"].append({"id": uname, "link": "/admin/users"})
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
                            "title": "%s / %s"
                            % (ver.get("version_name") or vid, ver.get("version_code") or "-"),
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
                    doc_rows = (
                        docs_payload if isinstance(docs_payload, list) else (docs_payload.get("documents") or [])
                    )
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
                                "link": "/docs/%s" % quote(did) if did else "/docs",
                            }
                        )
                        if len(results["docs"]) >= 20:
                            break
            except Exception:
                pass

        def _rows(items, cols):
            if not items:
                return '<tr><td class="px-4 py-2 text-gray-500">无结果</td></tr>'
            out = []
            for item in items[:20]:
                if cols == 1:
                    out.append(
                        '<tr><td class="px-4 py-2"><a href="%s" class="text-indigo-600 hover:underline">%s</a></td></tr>'
                        % (
                            html.escape(item["link"]),
                            html.escape(str(item.get("title") or item.get("id") or "")),
                        )
                    )
                else:
                    out.append(
                        '<tr><td class="px-4 py-2"><a href="%s" class="text-indigo-600 hover:underline">%s</a></td>'
                        '<td class="px-4 py-1.5 text-sm text-gray-500">%s</td></tr>'
                        % (
                            html.escape(item["link"]),
                            html.escape(str(item.get("title") or item.get("name") or item.get("id") or "")),
                            html.escape(str(item.get("project_id") or item.get("id") or "")),
                        )
                    )
            return "".join(out)

        escaped_q = html.escape(q)
        content = (
            f"""
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <form method="get" action="/admin/search" class="p-4 border-b flex gap-2">
            <input type="text" name="q" value="{escaped_q}" placeholder="搜索项目、文档、任务、版本、发布单、用户…" class="flex-1 px-4 py-1.5 border border-gray-200 rounded-lg text-sm">
            <button type="submit" class="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium">搜索</button>
        </form>
        <div class="p-3 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <div><h3 class="font-semibold text-gray-800 mb-2">项目</h3><table class="min-w-full text-sm">{_rows(results["projects"], 2)}</table></div>
            <div><h3 class="font-semibold text-gray-800 mb-2">发布单</h3><table class="min-w-full text-sm">{_rows(results["release_orders"], 2)}</table></div>
            <div><h3 class="font-semibold text-gray-800 mb-2">版本</h3><table class="min-w-full text-sm">{_rows(results["versions"], 2)}</table></div>
            <div><h3 class="font-semibold text-gray-800 mb-2">文档</h3><table class="min-w-full text-sm">{_rows(results["docs"], 1)}</table></div>
            <div><h3 class="font-semibold text-gray-800 mb-2">任务</h3><table class="min-w-full text-sm">{_rows(results["tasks"], 2)}</table></div>
            <div><h3 class="font-semibold text-gray-800 mb-2">用户</h3><table class="min-w-full text-sm">{_rows([{"link": u["link"], "title": u["id"], "id": u["id"]} for u in results["users"]], 1)}</table></div>
        </div>
    </div>"""
        )
        return admin_layout(content, "全局搜索", back_href="/admin")
