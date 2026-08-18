# -*- coding: utf-8 -*-
"""Topology route submodule."""
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import create_approval, get_channels_for_project, log_audit, project_versions_db
from services.authz import admin_required
from services.release.topology_binding_service import (
    build_topology_binding_picker,
    delete_topology_binding,
    delete_topology_binding_for_scope,
    list_topology_bindings,
    resolve_topology_binding,
    upsert_topology_binding,
)
from routes.ops import deps as ops_helpers
from routes.ops import bp

from routes.ops.topology_helpers import project_binding_catalog, project_topology_catalog


@bp.route("/api/projects/<project_id>/topologies", methods=["GET", "POST"])
@admin_required("gm_ops")
def project_topologies(project_id: str):
    if request.method == "GET":
        return jsonify({"ok": True, "data": project_topology_catalog(project_id)})
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "拓扑名称不能为空"}), 400
    topology_id = "topology-" + uuid.uuid4().hex[:10]
    rows = ops_helpers._load_topology_registry()
    row = ops_helpers._normalize_topology_registry_row(
        {
            "topology_id": topology_id,
            "project_id": project_id,
            "env_key": env_key,
            "name": name,
            "version_label": "v1.0.0",
            "owner": str(session.get("user") or "admin"),
            "description": str(payload.get("description") or "").strip(),
            "is_default": not any(
                isinstance(item, dict)
                and str(item.get("project_id") or "") == project_id
                and ops_helpers._normalize_env_key(item.get("env_key") or "") == env_key
                for item in rows
            ),
            "status": "draft",
            "created_at": ops_helpers._now_iso(),
            "updated_at": ops_helpers._now_iso(),
        }
    )
    rows.append(row)
    ops_helpers._save_topology_registry(rows)
    contents = ops_helpers._load_topology_contents()
    contents[topology_id] = {
        "nodes": [],
        "edges": [],
        "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": ops_helpers._now_iso(), "layout_mode": "structured"},
    }
    ops_helpers._save_topology_contents(contents)
    log_audit("project_topology_create", f"project={project_id}; env={env_key}; topology={topology_id}")
    return jsonify({"ok": True, "data": {"topology_id": topology_id, "registry": row}})


@bp.route("/api/projects/<project_id>/topology-bindings", methods=["GET", "POST"])
@admin_required("gm_ops")
def project_topology_bindings(project_id: str):
    if request.method == "GET":
        return jsonify({"ok": True, "data": project_binding_catalog(project_id)})
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = dict(request.get_json(silent=True) or {})
    payload["project_id"] = project_id
    try:
        row = upsert_topology_binding(payload, actor=str(session.get("user") or "admin"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    log_audit("project_topology_binding_upsert", f"project={project_id}; binding={row.get('binding_id')}")
    return jsonify({"ok": True, "data": {"binding": row, **project_binding_catalog(project_id)}})


@bp.route("/api/projects/<project_id>/topology-bindings/<binding_id>", methods=["DELETE"])
@admin_required("gm_ops")
def project_topology_binding_delete(project_id: str, binding_id: str):
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    if not delete_topology_binding(binding_id, actor=str(session.get("user") or "admin")):
        return jsonify({"ok": False, "error": "绑定规则不存在"}), 404
    log_audit("project_topology_binding_delete", f"project={project_id}; binding={binding_id}")
    return jsonify({"ok": True, "data": project_binding_catalog(project_id)})


@bp.route("/api/projects/<project_id>/topology-binding-picker", methods=["GET"])
@admin_required("gm_ops")
def project_topology_binding_picker(project_id: str):
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    channel_id = str(request.args.get("channel_id") or "").strip()
    platform = str(request.args.get("platform") or "").strip().lower()
    version_name = str(request.args.get("version_name") or "").strip()
    if not channel_id:
        return jsonify({"ok": False, "error": "channel_id required"}), 400
    data = build_topology_binding_picker(
        project_id,
        env_key,
        channel_id,
        platform=platform,
        version_name=version_name,
    )
    return jsonify({"ok": True, "data": data})


@bp.route("/api/projects/<project_id>/topology-bindings/scope", methods=["DELETE"])
@admin_required("gm_ops")
def project_topology_binding_delete_scope(project_id: str):
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or request.args.get("env_key") or "")
    channel_id = str(payload.get("channel_id") or request.args.get("channel_id") or "").strip()
    platform = str(payload.get("platform") or request.args.get("platform") or "").strip().lower()
    version_name = str(payload.get("version_name") or request.args.get("version_name") or "").strip()
    if not channel_id:
        return jsonify({"ok": False, "error": "channel_id required"}), 400
    deleted = delete_topology_binding_for_scope(
        project_id,
        env_key,
        channel_id,
        platform=platform,
        version_name=version_name,
    )
    if not deleted:
        return jsonify({"ok": False, "error": "当前 scope 无覆盖绑定"}), 404
    log_audit(
        "project_topology_binding_delete_scope",
        f"project={project_id}; env={env_key}; channel={channel_id}; platform={platform}",
    )
    return jsonify({"ok": True, "data": project_binding_catalog(project_id)})
