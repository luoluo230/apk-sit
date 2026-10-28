# -*- coding: utf-8 -*-
"""BaaS page layout — delivery shell or standalone Dev Portal shell."""

from __future__ import annotations

import os

from flask import render_template, request, session

from models.data import projects_db

BAAS_SHELL_ASSET_VER = "20260827-baas-shell1"
BAAS_CONSOLE_ASSET_VER = "20260827-json1"


def is_baas_standalone() -> bool:
    return str(os.getenv("BAAS_STANDALONE") or "").strip().lower() in ("1", "true", "yes")


def _baas_csrf_token() -> str:
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except Exception:
        return ""


def _baas_json_assets() -> tuple[str, str]:
    css = f'<link rel="stylesheet" href="/static/baas_json_field.css?v={BAAS_CONSOLE_ASSET_VER}">'
    js = f'<script src="/static/baas_json_field.js?v={BAAS_CONSOLE_ASSET_VER}"></script>'
    return css, js


def _baas_console_css(*extra_files: str) -> str:
    json_css, _ = _baas_json_assets()
    parts = [
        json_css,
        f'<link rel="stylesheet" href="/static/casual_services_console.css?v={BAAS_CONSOLE_ASSET_VER}">',
    ]
    for name in extra_files:
        parts.append(f'<link rel="stylesheet" href="/static/{name}?v={BAAS_CONSOLE_ASSET_VER}">')
    return "".join(parts)


def _baas_console_js(template_name: str) -> str:
    _, json_js = _baas_json_assets()
    if template_name == "baas_gm_console.html":
        return json_js + f'<script src="/static/baas_gm_console.js?v={BAAS_CONSOLE_ASSET_VER}"></script>'
    return json_js + f'<script src="/static/casual_services_console.js?v={BAAS_CONSOLE_ASSET_VER}"></script>'


def render_baas_shell_page(
    content: str,
    title: str,
    *,
    active_page: str = "",
    project_id: str = "",
    service_id: str = "",
    extra_css: str = "",
    extra_js: str = "",
):
    project_name = project_id
    if project_id:
        row = projects_db.get(project_id) or {}
        project_name = str(row.get("name") or project_id).strip() or project_id
    if not is_baas_standalone():
        from services.ops.helpers import _render_ops_page

        return _render_ops_page(
            content,
            title,
            active_page=active_page or "baas",
            project_id=project_id,
            breadcrumb_module="BaaS",
            extra_css=extra_css,
            extra_js=extra_js,
        )
    user_name = str(session.get("user") or session.get("username") or "管理员").strip() or "管理员"
    return render_template(
        "baas_shell.html",
        content=content,
        title=title,
        active_page=active_page,
        project_id=project_id,
        project_name=project_name,
        service_id=service_id,
        user_name=user_name,
        csrf_token=_baas_csrf_token(),
        baas_shell_asset_ver=BAAS_SHELL_ASSET_VER,
        extra_css=extra_css,
        extra_js=extra_js,
    )


def render_baas_page(
    template_name: str,
    title: str,
    project_id: str,
    active_page: str,
    **context,
):
    if project_id not in projects_db:
        return "项目不存在", 404
    env_key = str(context.pop("env_key", None) or request.args.get("env_key") or "development")
    service_id = str(context.get("service_id") or "").strip()
    ctx = dict(context)
    ctx.setdefault("env_key", env_key)
    content = render_template(
        template_name,
        project_id=project_id,
        project=projects_db.get(project_id) or {},
        page_title=title,
        active_page=active_page,
        **ctx,
    )
    extra_css = _baas_console_css("baas_gm_console.css") if template_name == "baas_gm_console.html" else _baas_console_css()
    return render_baas_shell_page(
        content,
        title,
        active_page=active_page,
        project_id=project_id,
        service_id=service_id,
        extra_css=extra_css,
        extra_js=_baas_console_js(template_name),
    )


def render_baas_home_page(content: str, *, active_page: str = "baas-home", extra_js: str = ""):
    return render_baas_shell_page(
        content,
        "BaaS 项目",
        active_page=active_page,
        extra_js=extra_js,
    )
