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


@bp.route("/api/ops-platform/topologies")
@admin_required("gm_ops")
def ops_platform_topologies():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_arg = request.args.get("env_key")
    env_filter = ops_helpers._normalize_env_key(env_arg) if (env_arg is not None and str(env_arg).strip()) else None
    rows = ops_helpers._list_topologies(project_id, env_filter)
    env_values = []
    seen_env = set()
    for item in ops_helpers._default_env_options() + [{"env_key": str(x.get("env_key") or ""), "label": str(x.get("env_label") or ops_helpers._env_label(x.get("env_key") or ""))} for x in rows]:
        key = ops_helpers._normalize_env_key(item.get("env_key") or "")
        if not key or key in seen_env:
            continue
        seen_env.add(key)
        env_values.append({"env_key": key, "label": str(item.get("label") or ops_helpers._env_label(key))})
    return jsonify({"ok": True, "project_id": project_id, "env_key": env_filter or "", "count": len(rows), "topologies": rows, "environments": env_values})


@bp.route("/api/ops-platform/topology-bindings")
@admin_required("gm_ops")
def ops_platform_topology_bindings():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    if not project_id:
        return jsonify({"ok": False, "error": "missing_project_id"}), 400
    bindings = list_topology_bindings(project_id)
    topologies = ops_helpers._list_topologies(project_id, None)
    channels = [
        {
            "channel_id": str(item.get("id") or "").strip(),
            "channel_name": str(item.get("name") or item.get("id") or "").strip(),
            "channel_key": str(item.get("apk_subdir") or item.get("build_param") or item.get("id") or "").strip(),
        }
        for item in (get_channels_for_project(project_id) or [])
        if str(item.get("id") or "").strip()
    ]
    version_names = sorted(
        {
            str(item.get("version_name") or "").strip()
            for item in (project_versions_db.get(project_id) or [])
            if isinstance(item, dict) and str(item.get("version_name") or "").strip()
        }
    )
    return jsonify(
        {
            "ok": True,
            "project_id": project_id,
            "bindings": bindings,
            "topologies": topologies,
            "channels": channels,
            "version_names": version_names,
        }
    )


@bp.route("/api/ops-platform/topology-bindings/resolve")
@admin_required("gm_ops")
def ops_platform_topology_bindings_resolve():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = str(request.args.get("env_key") or "").strip()
    channel_id = str(request.args.get("channel_id") or "").strip()
    version_name = str(request.args.get("version_name") or "").strip()
    fallback_topology_id = str(request.args.get("fallback_topology_id") or "").strip()
    if not project_id:
        return jsonify({"ok": False, "error": "missing_project_id"}), 400
    resolved = resolve_topology_binding(
        project_id,
        env_key,
        channel_id,
        version_name=version_name,
        fallback_topology_id=fallback_topology_id,
    )
    return jsonify({"ok": True, "project_id": project_id, "resolved": resolved})


@bp.route("/api/ops-platform/topology-bindings/upsert", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_bindings_upsert():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    try:
        row = upsert_topology_binding(payload, actor=str(session.get("user") or "admin"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    log_audit(
        "ops_platform_topology_binding_upsert",
        f"project={row.get('project_id')}; env={row.get('env_key') or '-'}; channel={row.get('channel_id') or '-'}; version={row.get('version_name') or '-'}; topology={row.get('topology_id')}",
    )
    return jsonify({"ok": True, "binding": row, "bindings": list_topology_bindings(str(row.get('project_id') or ''))})


@bp.route("/api/ops-platform/topology-bindings/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_bindings_delete():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    binding_id = str(payload.get("binding_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    if not binding_id:
        return jsonify({"ok": False, "error": "missing_binding_id"}), 400
    ok = delete_topology_binding(binding_id, actor=str(session.get("user") or "admin"))
    if not ok:
        return jsonify({"ok": False, "error": "binding_not_found"}), 404
    log_audit("ops_platform_topology_binding_delete", f"binding={binding_id}; project={project_id or '-'}")
    return jsonify({"ok": True, "bindings": list_topology_bindings(project_id)})



@bp.route("/api/ops-platform/topologies/detail")
@admin_required("gm_ops")
def ops_platform_topologies_detail():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    scoped = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    return jsonify(
        {
            "ok": True,
            "project_id": str(registry.get("project_id") or project_id or ""),
            "env_key": str(registry.get("env_key") or env_key or ""),
            "topology_id": tid,
            "registry": registry,
            "topology": {
                "nodes": scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else [],
                "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
                "meta": scoped.get("meta") if isinstance(scoped.get("meta"), dict) else {},
            },
            "bindings": ops_helpers._load_scope_agent_bindings(tid),
            "service_bindings": ops_helpers._load_scope_service_bindings(tid),
        }
    )



@bp.route("/api/ops-platform/topologies/create", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topologies_create():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    name = str(payload.get("name") or "").strip()
    if not project_id:
        return jsonify({"ok": False, "error": "missing_project_id"}), 400
    if not name:
        return jsonify({"ok": False, "error": "missing_name"}), 400
    topology_id = "topology-" + uuid.uuid4().hex[:10]
    rows = ops_helpers._load_topology_registry()
    is_first_for_env = not any(
        isinstance(x, dict)
        and str(x.get("project_id") or "").strip() == project_id
        and ops_helpers._normalize_env_key(x.get("env_key") or "") == env_key
        for x in rows
    )
    row = ops_helpers._normalize_topology_registry_row(
        {
            "topology_id": topology_id,
            "project_id": project_id,
            "env_key": env_key,
            "name": name,
            "version_label": "v1.0.0",
            "owner": str(session.get("user") or "admin"),
            "description": str(payload.get("description") or "").strip(),
            "blueprint_id": str(payload.get("blueprint_id") or "").strip(),
            "is_default": is_first_for_env,
            "status": "draft",
            "created_at": ops_helpers._now_iso(),
            "updated_at": ops_helpers._now_iso(),
        }
    )
    rows.append(row)
    ops_helpers._save_topology_registry(rows)
    contents = ops_helpers._load_topology_contents()
    contents[topology_id] = {"nodes": [], "edges": [], "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": ops_helpers._now_iso(), "layout_mode": "structured"}}
    ops_helpers._save_topology_contents(contents)
    log_audit("ops_platform_topology_create", f"project={project_id}; env={env_key}; topology={topology_id}")
    return jsonify({"ok": True, "topology_id": topology_id, "registry": row, "topologies": ops_helpers._list_topologies(project_id, env_key)})



@bp.route("/api/ops-platform/topologies/copy", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topologies_copy():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    source_topology_id = str(payload.get("source_topology_id") or payload.get("topology_id") or "").strip()
    name = str(payload.get("name") or "").strip()
    if not project_id or not source_topology_id or not name:
        return jsonify({"ok": False, "error": "missing_required_fields"}), 400
    scoped = ops_helpers._load_topology_scoped(project_id, env_key, source_topology_id)
    source_row = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    if not source_row:
        return jsonify({"ok": False, "error": "topology_not_found"}), 404
    topology_id = "topology-" + uuid.uuid4().hex[:10]
    row = ops_helpers._normalize_topology_registry_row(
        {
            "topology_id": topology_id,
            "project_id": project_id,
            "env_key": str(source_row.get("env_key") or env_key or "production"),
            "name": name,
            "version_label": "v1.0.0",
            "owner": str(session.get("user") or "admin"),
            "description": str(payload.get("description") or source_row.get("description") or ""),
            "blueprint_id": str(source_row.get("blueprint_id") or ""),
            "copied_from_topology_id": source_topology_id,
            "is_default": False,
            "status": "draft",
            "created_at": ops_helpers._now_iso(),
            "updated_at": ops_helpers._now_iso(),
        }
    )
    rows = ops_helpers._load_topology_registry()
    rows.append(row)
    ops_helpers._save_topology_registry(rows)
    src_topo = {
        "nodes": scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else [],
        "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
        "meta": scoped.get("meta") if isinstance(scoped.get("meta"), dict) else {},
    }
    copied_nodes = []
    for node in src_topo.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        item = dict(node)
        item.pop("agent_id", None)
        copied_nodes.append(item)
    contents = ops_helpers._load_topology_contents()
    contents[topology_id] = {
        "nodes": copied_nodes,
        "edges": list(src_topo.get("edges") or []),
        "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": ops_helpers._now_iso(), "layout_mode": "structured"},
    }
    ops_helpers._save_topology_contents(contents)
    log_audit("ops_platform_topology_copy", f"project={project_id}; env={env_key}; source={source_topology_id}; target={topology_id}")
    return jsonify({"ok": True, "topology_id": topology_id, "registry": row, "topologies": ops_helpers._list_topologies(project_id, env_key)})



@bp.route("/api/ops-platform/topologies/set-default", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topologies_set_default():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    topology_id = str(payload.get("topology_id") or "").strip()
    if not topology_id:
        return jsonify({"ok": False, "error": "missing_topology_id"}), 400
    rows = ops_helpers._load_topology_registry()
    target = None
    for item in rows:
        if isinstance(item, dict) and str(item.get("topology_id") or "") == topology_id:
            target = ops_helpers._normalize_topology_registry_row(item)
            break
    if not target:
        return jsonify({"ok": False, "error": "topology_not_found"}), 404
    for idx, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        row = ops_helpers._normalize_topology_registry_row(item)
        if row.get("project_id") == target.get("project_id") and row.get("env_key") == target.get("env_key"):
            row["is_default"] = str(row.get("topology_id") or "") == topology_id
            row["updated_at"] = ops_helpers._now_iso()
            rows[idx] = row
    ops_helpers._save_topology_registry(rows)
    log_audit("ops_platform_topology_set_default", f"topology={topology_id}")
    return jsonify({"ok": True, "registry": target, "topologies": ops_helpers._list_topologies(str(target.get('project_id') or ''), str(target.get('env_key') or ''))})



@bp.route("/api/ops-platform/topologies/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topologies_delete():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    topology_id = str(payload.get("topology_id") or "").strip()
    if not topology_id:
        return jsonify({"ok": False, "error": "missing_topology_id"}), 400
    rows = ops_helpers._load_topology_registry()
    target = None
    for item in rows:
        if isinstance(item, dict) and str(item.get("topology_id") or "") == topology_id:
            target = ops_helpers._normalize_topology_registry_row(item)
            break
    if not target:
        return jsonify({"ok": False, "error": "topology_not_found"}), 404
    same_scope = [x for x in rows if isinstance(x, dict) and str(x.get("project_id") or "").strip() == str(target.get("project_id") or "") and ops_helpers._normalize_env_key(x.get("env_key") or "") == str(target.get("env_key") or "")]
    if len(same_scope) <= 1:
        return jsonify({"ok": False, "error": "last_topology_for_scope", "message": "当前环境至少要保留一个拓扑"}), 409
    if bool(target.get("is_default")):
        return jsonify({"ok": False, "error": "default_topology_requires_transfer", "message": "默认拓扑需先转移默认"}), 409
    active = ops_helpers._runtime_active_for_scope(str(target.get("project_id") or ""), str(target.get("env_key") or ""), topology_id)
    if active.get("active"):
        return jsonify({"ok": False, "error": "topology_run_active", "message": "当前拓扑仍有活动中的运行/测试任务"}), 409
    rows = [x for x in rows if not (isinstance(x, dict) and str(x.get("topology_id") or "") == topology_id)]
    ops_helpers._save_topology_registry(rows)
    contents = ops_helpers._load_topology_contents()
    contents.pop(topology_id, None)
    ops_helpers._save_topology_contents(contents)
    agent_bindings = ops_helpers._load_node_agent_bindings()
    if isinstance(agent_bindings, dict):
        for key in list(agent_bindings.keys()):
            if str(key or "").startswith(topology_id + "::"):
                agent_bindings.pop(key, None)
        ops_helpers._save_node_agent_bindings(agent_bindings)
    service_bindings = ops_helpers._load_node_service_bindings()
    if isinstance(service_bindings, dict):
        for key in list(service_bindings.keys()):
            if str(key or "").startswith(topology_id + "::"):
                service_bindings.pop(key, None)
        ops_helpers._save_node_service_bindings(service_bindings)
    log_audit("ops_platform_topology_delete", f"topology={topology_id}")
    return jsonify({"ok": True, "topologies": ops_helpers._list_topologies(str(target.get('project_id') or ''), str(target.get('env_key') or ''))})


