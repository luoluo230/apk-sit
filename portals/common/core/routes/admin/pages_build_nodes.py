# -*- coding: utf-8
"""Admin page: distributed build grid."""

from __future__ import annotations

from flask import render_template

from services.authz import admin_required


def register_routes(bp):
    @bp.route("/admin/build-nodes")
    @admin_required("jenkins")
    def build_nodes_page():
        return render_template(
            "build_nodes_page.html",
            page_title="构建节点",
        )
