# -*- coding: utf-8
"""Admin page: distributed build grid."""

from __future__ import annotations

from flask import redirect, url_for

from services.authz import admin_required


def register_routes(bp):
    @bp.route("/admin/build-nodes")
    @admin_required("jenkins")
    def build_nodes_page():
        return redirect(url_for("admin_routes.infra_nodes_page"))
