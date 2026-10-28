# -*- coding: utf-8
"""Admin pages for unified infra nodes."""

from __future__ import annotations

from flask import redirect, render_template, url_for

from services.authz import admin_required
from services.ops.helpers import _render_ops_page

_NODES_CSS = '<link rel="stylesheet" href="/static/tailwind.css">'


def _nodes_page(title: str):
    content = render_template("build_nodes_page.html")
    return _render_ops_page(content, title, active_page="infra-nodes", extra_css=_NODES_CSS)


def register_routes(bp):
    @bp.route("/admin/infra-nodes")
    @admin_required("jenkins")
    def infra_nodes_page():
        return _nodes_page("基础设施节点")

    @bp.route("/admin/build-nodes")
    @admin_required("jenkins")
    def build_nodes_page_redirect():
        return redirect(url_for("admin_routes.infra_nodes_page"))
