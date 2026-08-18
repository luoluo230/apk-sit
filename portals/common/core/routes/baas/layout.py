# -*- coding: utf-8 -*-
"""BaaS page layout — delivery shell or standalone minimal."""

from __future__ import annotations

import os

from flask import render_template, request

from models.data import projects_db


def is_baas_standalone() -> bool:
    return str(os.getenv("BAAS_STANDALONE") or "").strip().lower() in ("1", "true", "yes")


def render_baas_page(
    template_name: str,
    title: str,
    project_id: str,
    active_page: str,
    **context,
):
    if project_id not in projects_db:
        return "项目不存在", 404
    if is_baas_standalone():
        return render_template(
            template_name,
            project_id=project_id,
            project=projects_db.get(project_id) or {},
            page_title=title,
            active_page=active_page,
            env_key=str(context.get("env_key") or request.args.get("env_key") or "development"),
            **context,
        )
    from routes.delivery.helpers import render_delivery_page as _page

    return _page(template_name, title, project_id, active_page, **context)
