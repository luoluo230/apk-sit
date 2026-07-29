# -*- coding: utf-8
"""Admin pages for unified infra nodes."""

from __future__ import annotations

from flask import redirect, render_template, url_for

from services.authz import admin_required


def register_routes(bp):
    @bp.route("/admin/infra-nodes")
    @admin_required("jenkins")
    def infra_nodes_page():
        return render_template(
            "build_nodes_page.html",
            page_title="基础设施节点",
        )

    @bp.route("/admin/build-nodes")
    @admin_required("jenkins")
    def build_nodes_page_redirect():
        return redirect(url_for("admin_routes.infra_nodes_page"))
