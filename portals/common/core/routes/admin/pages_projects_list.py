# -*- coding: utf-8 -*-
"""Project list + onboarding wizard page routes (split from admin_routes)."""

from __future__ import annotations

from flask import render_template
from services.authz import admin_required
from services.ops.helpers import _render_ops_page
from routes.admin.views.projects import projects_page_context, onboarding_wizard_page_context

PROJECT_LIST_ASSET_VER = "20261030-edit-creds-ro"
ONBOARDING_WIZARD_ASSET_VER = "20260728-p102"


def register_routes(bp):
    @bp.route("/admin/projects/new/wizard")
    @admin_required("projects")
    def admin_project_onboarding_wizard_page():
        content = render_template("project_onboarding_wizard.html", **onboarding_wizard_page_context())
        js = f'<script src="/static/project_onboarding.js?v={ONBOARDING_WIZARD_ASSET_VER}"></script>'
        return _render_ops_page(
            content,
            "新建项目向导",
            active_page="projects",
            breadcrumb_module="项目",
            extra_js=js,
        )

    @bp.route("/admin/projects")
    @admin_required("projects")
    def admin_projects_page():
        content = render_template("project_list.html", **projects_page_context())
        css = (
            f'<link rel="stylesheet" href="/static/project_ui/pm-modal.css?v={PROJECT_LIST_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-project-card.css?v={PROJECT_LIST_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_ui/pm-right-rail.css?v={PROJECT_LIST_ASSET_VER}">'
            f'<link rel="stylesheet" href="/static/project_list.css?v={PROJECT_LIST_ASSET_VER}">'
        )
        js = (
            f'<script src="/static/user_favorites_sync.js?v={PROJECT_LIST_ASSET_VER}"></script>'
            f'<script src="/static/project_ui/pm-display-labels.js?v={PROJECT_LIST_ASSET_VER}"></script>'
            f'<script src="/static/project_list.js?v={PROJECT_LIST_ASSET_VER}"></script>'
        )
        return _render_ops_page(
            content,
            "项目列表",
            active_page="projects",
            breadcrumb_module="总览",
            extra_css=css,
            extra_js=js,
        )
