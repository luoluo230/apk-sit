# -*- coding: utf-8 -*-
"""Admin global search page."""

from __future__ import annotations

import html

from flask import jsonify, request

from services.admin.global_search_service import flatten_search_hits, search_admin_content
from services.authz import login_required


def register_routes(bp, *, admin_layout, current_username):
    @bp.route("/admin/search")
    @login_required
    def admin_search():
        """全局搜索：项目、任务、用户、发布单、版本、文档。"""
        q = (request.args.get("q") or "").strip()[:80]
        username = current_username()
        results = search_admin_content(q, username)

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

    @bp.route("/api/admin/search")
    @login_required
    def admin_search_api():
        q = (request.args.get("q") or "").strip()[:80]
        username = current_username()
        results = search_admin_content(q, username)
        hits = flatten_search_hits(results, limit=12)
        total = sum(len(results.get(key) or []) for key in results)
        return jsonify({"ok": True, "query": q, "total": total, "results": results, "hits": hits})
