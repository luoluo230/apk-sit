# -*- coding: utf-8 -*-
"""Server management hub pages."""

from __future__ import annotations

from flask import render_template, request

from models.data import projects_db
from services.authz import admin_required
from services.ops.helpers import _render_local_template, _render_ops_page
from server_frameworks.registry import is_module_enabled


def _hub_page_context(locked_project_id: str = ""):
    locked = str(locked_project_id or "").strip()
    show_topology = is_module_enabled("topology_server")
    show_baas = is_module_enabled("casual_baas_server")
    tab = str(request.args.get("tab") or ("topology" if show_topology else "baas")).strip().lower()
    if tab not in ("topology", "baas"):
        tab = "topology" if show_topology else "baas"
    if tab == "topology" and not show_topology:
        tab = "baas"
    if tab == "baas" and not show_baas:
        tab = "topology"
    return {
        "locked_project_id": locked,
        "default_tab": tab,
        "show_topology_tab": show_topology,
        "show_baas_tab": show_baas,
        "filter_project_id": locked or str(request.args.get("project_id") or "").strip(),
        "filter_env_key": str(request.args.get("env_key") or "").strip(),
        "filter_status": str(request.args.get("status") or "").strip(),
        "filter_query": str(request.args.get("q") or "").strip(),
        "projects_json": [
            {"id": pid, "name": str(row.get("name") or pid)}
            for pid, row in sorted((projects_db or {}).items(), key=lambda x: str((x[1] or {}).get("name") or x[0]))
        ],
    }


def register_server_management_page_routes(bp) -> None:
    @bp.route("/admin/server-management")
    @admin_required("gm_ops")
    def server_management_global_page():
        ctx = _hub_page_context("")
        content = _render_local_template("server_management_hub.html", **ctx)
        css = '<link rel="stylesheet" href="/static/project_environment_detail.css?v=20260724-sm2">'
        css += '<link rel="stylesheet" href="/static/server_management_hub.css?v=20260724-sm2">'
        js = '<script src="/static/server_management_hub.js?v=20260724-sm2"></script>'
        return _render_ops_page(
            content,
            "服务器管理",
            active_page="server-management",
            breadcrumb_module="运行管理",
            extra_css=css,
            extra_js=js,
        )

    @bp.route("/admin/projects/<project_id>/server-management")
    @admin_required("gm_ops")
    def server_management_project_page(project_id: str):
        pid = str(project_id or "").strip()
        if pid not in projects_db:
            from flask import abort

            abort(404)
        ctx = _hub_page_context(pid)
        content = _render_local_template("server_management_hub.html", **ctx)
        css = '<link rel="stylesheet" href="/static/project_environment_detail.css?v=20260724-sm2">'
        css += '<link rel="stylesheet" href="/static/server_management_hub.css?v=20260724-sm2">'
        js = '<script src="/static/server_management_hub.js?v=20260724-sm2"></script>'
        return _render_ops_page(
            content,
            "服务器管理",
            active_page="server-management",
            project_id=pid,
            breadcrumb_module="运行管理",
            extra_css=css,
            extra_js=js,
        )
