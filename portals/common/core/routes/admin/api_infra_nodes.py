# -*- coding: utf-8
"""Admin API for unified infra node registry."""

from __future__ import annotations

from flask import jsonify, request

from services.authz import admin_required
from services.infra.infra_node_registry import (
    build_grid_summary,
    delete_node,
    list_nodes,
    recommended_build_node_for_platform,
)
from services.build.build_grid import list_build_roles, normalize_build_platform


def register_routes(bp):
    @bp.route("/api/admin/infra-nodes", methods=["GET"])
    @admin_required("jenkins")
    def api_infra_nodes_list():
        plane = str(request.args.get("plane") or "all").strip().lower()
        role = str(request.args.get("role") or "").strip()
        project_id = str(request.args.get("project_id") or "").strip()
        nodes = list_nodes(role=role, project_id=project_id, plane=plane if plane in ("build", "runtime") else "")
        return jsonify({"ok": True, "plane": plane, "nodes": nodes})

    @bp.route("/api/admin/infra-nodes/summary", methods=["GET"])
    @admin_required("jenkins")
    def api_infra_nodes_summary():
        return jsonify({"ok": True, **build_grid_summary()})

    @bp.route("/api/admin/infra-nodes/recommended-build-node", methods=["GET"])
    @admin_required("projects")
    def api_recommended_build_node():
        platform = normalize_build_platform(str(request.args.get("platform") or "android"))
        return jsonify({"ok": True, "data": recommended_build_node_for_platform(platform)})

    @bp.route("/api/admin/infra-nodes/<node_id>", methods=["DELETE"])
    @admin_required("jenkins")
    def api_infra_nodes_delete(node_id):
        ok = delete_node(node_id)
        if not ok:
            return jsonify({"ok": False, "error": "节点不存在"}), 404
        return jsonify({"ok": True})

    @bp.route("/api/admin/build-nodes", methods=["GET"])
    @admin_required("jenkins")
    def api_build_nodes_list_compat():
        role = str(request.args.get("role") or "").strip()
        return jsonify({
            "ok": True,
            "roles": list_build_roles(),
            "nodes": list_nodes(role=role, plane="build") if role else list_nodes(plane="build"),
            "summary": build_grid_summary(),
        })

    @bp.route("/api/admin/build-nodes/summary", methods=["GET"])
    @admin_required("jenkins")
    def api_build_nodes_summary_compat():
        return jsonify({"ok": True, **build_grid_summary()})

    @bp.route("/api/admin/build-nodes/<node_id>", methods=["DELETE"])
    @admin_required("jenkins")
    def api_build_nodes_delete_compat(node_id):
        ok = delete_node(node_id)
        if not ok:
            return jsonify({"ok": False, "error": "节点不存在"}), 404
        return jsonify({"ok": True})
