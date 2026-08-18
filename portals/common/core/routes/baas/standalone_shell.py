# -*- coding: utf-8 -*-
"""Routes for standalone BaaS Portal (projects, config console, GM)."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from models.data import can_edit_project, can_view_project, projects_db
from repositories.admin import projects_repo
from services.authz import admin_required, login_required
from services.baas.service_crud import ensure_service
from routes.baas.admin_api import register_baas_admin_routes
from routes.baas.gm_api import register_baas_gm_routes
from routes.baas.pages import register_baas_pages
from server_frameworks.bootstrap import register_client_bootstrap_routes

bp = Blueprint("baas_standalone", __name__)

register_baas_admin_routes(bp)
register_baas_pages(bp)
register_baas_gm_routes(bp)
register_client_bootstrap_routes(bp)


def _actor() -> str:
    return str(session.get("user") or "admin")


def _baas_projects():
    rows = []
    for pid, item in projects_db.items():
        mode = str(item.get("server_mode") or "topology").strip().lower()
        if mode != "casual_baas":
            continue
        rows.append({
            "id": pid,
            "name": item.get("name") or pid,
            "baas_service_id": str(item.get("baas_service_id") or ""),
            "game_id": str(item.get("game_id") or ""),
            "status": item.get("status") or "active",
        })
    rows.sort(key=lambda r: r["name"])
    return rows


@bp.route("/admin/baas")
@login_required
def baas_home():
    username = _actor()
    projects = [p for p in _baas_projects() if can_view_project(p["id"], username)]
    return render_template(
        "baas_standalone_home.html",
        projects=projects,
        username=username,
    )


@bp.route("/api/baas/projects", methods=["GET", "POST"])
@admin_required("projects")
def baas_projects_api():
    if request.method == "GET":
        username = _actor()
        data = [p for p in _baas_projects() if can_view_project(p["id"], username)]
        return jsonify({"ok": True, "data": data})
    if not session.get("user"):
        return jsonify({"ok": False, "error": "未登录"}), 401
    body = request.get_json(silent=True) or {}
    project_id = str(body.get("id") or body.get("project_id") or "").strip()
    name = str(body.get("name") or "").strip()
    if not project_id or not name:
        return jsonify({"ok": False, "error": "项目 ID 与名称必填"}), 400
    if projects_repo.has_project(project_id):
        return jsonify({"ok": False, "error": "项目 ID 已存在"}), 409
    game_id = str(body.get("game_id") or f"{project_id}-{secrets.token_hex(4)}")
    game_key = str(body.get("game_key") or secrets.token_hex(32))
    payload = {
        "name": name,
        "server_mode": "casual_baas",
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "created_by": _actor(),
        "game_id": game_id,
        "game_key": game_key,
        "viewers": [],
        "editors": [_actor()],
    }
    projects_repo.upsert_project(project_id, payload)
    svc, secret = ensure_service(project_id, str(body.get("env_key") or "development"), actor=_actor())
    payload["baas_service_id"] = svc.get("service_id") or ""
    projects_repo.upsert_project(project_id, payload)
    return jsonify({
        "ok": True,
        "data": {
            "project_id": project_id,
            "baas_service_id": payload["baas_service_id"],
            "game_id": game_id,
            "game_key": game_key,
            "api_secret": secret,
        },
    }), 201
