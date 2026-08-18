# -*- coding: utf-8 -*-
"""Casual BaaS admin console pages."""

from __future__ import annotations

from flask import abort, render_template, request, session

from models.data import can_edit_project, can_view_project, projects_db
from routes.baas.layout import render_baas_page as _page
from services.authz import admin_required
from services.baas.registry import list_catalog
from services.baas.service_crud import ensure_service, get_service


def register_baas_pages(bp) -> None:
    @bp.route("/admin/projects/<project_id>/casual-services")
    @bp.route("/admin/projects/<project_id>/casual-services/<service_id>")
    @admin_required("projects")
    def casual_services_console_page(project_id: str, service_id: str = ""):
        if project_id not in projects_db:
            abort(404)
        username = str(session.get("user") or "")
        if not can_view_project(project_id, username):
            abort(403)
        env_key = str(request.args.get("env_key") or "development").strip() or "development"
        sid = str(
            service_id
            or request.args.get("service_id")
            or projects_db.get(project_id, {}).get("baas_service_id")
            or ""
        ).strip()
        if not sid:
            svc, _ = ensure_service(project_id, env_key)
            sid = svc.get("service_id") or ""
        svc = get_service(sid) if sid else None
        if not svc or svc.get("project_id") != project_id:
            abort(404)
        return _page(
            "casual_services_console.html",
            "休闲服务",
            project_id,
            "casual-services",
            service_id=sid,
            env_key=svc.get("env_key") or env_key,
            can_edit=can_edit_project(project_id, username),
            catalog=list_catalog(),
        )
