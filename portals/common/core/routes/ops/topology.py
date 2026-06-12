# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import get_channels_for_project, log_audit, project_versions_db
from services.authz import admin_required
from services.release.topology_binding_service import (
    delete_topology_binding,
    list_topology_bindings,
    resolve_topology_binding,
    upsert_topology_binding,
)
import services.ops.helpers as ops_helpers
from routes.ops import bp

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



@bp.route("/api/ops-platform/topology/node/bindings")
@admin_required("gm_ops")
def ops_platform_node_bindings():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    scoped = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    valid_nodes = set(str(x.get("id") or "") for x in (scoped.get("nodes") or []) if isinstance(x, dict))
    bindings = ops_helpers._resolve_scope_agent_bindings_for_scope(tid, project_id, env_key, valid_nodes)
    service_bindings = ops_helpers._resolve_scope_service_bindings_for_scope(tid, project_id, env_key, valid_nodes)
    out: Dict[str, str] = {str(nid): str(aid) for nid, aid in bindings.items() if str(nid or "").strip() in valid_nodes and str(aid or "").strip()}
    out_services: Dict[str, str] = {}
    valid_services = set(
        str(x.get("service_id") or "").strip()
        for x in ops_helpers._services_for_project(project_id)
        if isinstance(x, dict)
    )
    for nid, sid in service_bindings.items():
        n = str(nid or "").strip()
        s = str(sid or "").strip()
        if not n or not s or n not in valid_nodes:
            continue
        if valid_services and s not in valid_services:
            continue
        out_services[n] = s
    return jsonify({"ok": True, "project_id": project_id, "env_key": str(registry.get("env_key") or env_key or ""), "topology_id": tid, "bindings": out, "service_bindings": out_services})



@bp.route("/api/ops-platform/topology/node/bind-agent", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_bind_node_agent():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    scoped = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node = next((x for x in (scoped.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    reg = ops_helpers._load_agent_registry_v2()
    if agent_id:
        ag = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
        if not ag:
            return jsonify({"ok": False, "error": "agent_not_found"}), 404
        ag_project = str(ag.get("project_id") or "")
        if project_id and ag_project and ag_project != project_id:
            return jsonify({"ok": False, "error": "OPS_AGENT_NOT_IN_PROJECT", "error_code": "OPS_AGENT_NOT_IN_PROJECT"}), 409
        if str(ag.get("probe_status") or "").upper() != "PASS":
            return jsonify({"ok": False, "error": "OPS_AGENT_PROBE_REQUIRED", "error_code": "OPS_AGENT_PROBE_REQUIRED", "message": "Agent 尚未通过联通测试，禁止绑定"}), 412
    bindings = ops_helpers._load_scope_agent_bindings(tid)
    service_bindings = ops_helpers._load_scope_service_bindings(tid)
    if agent_id:
        bindings[node_id] = agent_id
        # Backward-compat: if service primary missing, map by node->service candidate under this agent.
        if not str(service_bindings.get(node_id) or "").strip():
            for svc in ops_helpers._services_for_project(project_id):
                if not isinstance(svc, dict):
                    continue
                if str(svc.get("agent_id") or "").strip() != agent_id:
                    continue
                if str(svc.get("node_id") or "").strip() == node_id:
                    sid = str(svc.get("service_id") or "").strip()
                    if sid:
                        service_bindings[node_id] = sid
                        break
    else:
        bindings.pop(node_id, None)
        service_bindings.pop(node_id, None)
    ops_helpers._save_scope_agent_binding(tid, node_id, agent_id)
    ops_helpers._save_scope_service_binding(tid, node_id, str(service_bindings.get(node_id) or ""))
    if not agent_id:
        ops_helpers._save_scope_service_binding(tid, node_id, "")
    log_audit("ops_platform_bind_node_agent", f"node={node_id}; agent={agent_id}")
    return jsonify({"ok": True, "node_id": node_id, "agent_id": agent_id, "topology_id": tid, "bindings": bindings, "service_bindings": service_bindings})



@bp.route("/api/ops-platform/topology/node/bind-service", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_bind_node_service():
    payload = request.get_json(silent=True) or {}
    service_id = str(payload.get("service_id") or "").strip()
    if not service_id:
        return jsonify({"ok": False, "error": "missing_service_id"}), 400
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400

    scoped = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node = next((x for x in (scoped.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404

    agent_id = str(payload.get("agent_id") or "").strip()
    service_hit = None
    for svc in ops_helpers._services_for_project(project_id):
        if not isinstance(svc, dict):
            continue
        if str(svc.get("service_id") or "").strip() == service_id:
            service_hit = svc
            break
    if not service_hit:
        return jsonify({"ok": False, "error": "service_not_found", "error_code": "OPS_SERVICE_NOT_FOUND"}), 404
    if not agent_id:
        agent_id = str(service_hit.get("agent_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    reg = ops_helpers._load_agent_registry_v2()
    ag = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
    if not ag:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    ag_project = str(ag.get("project_id") or "")
    if project_id and ag_project and ag_project != project_id:
        return jsonify({"ok": False, "error": "OPS_AGENT_NOT_IN_PROJECT", "error_code": "OPS_AGENT_NOT_IN_PROJECT"}), 409
    if str(ag.get("probe_status") or "").upper() != "PASS":
        return jsonify({"ok": False, "error": "OPS_AGENT_PROBE_REQUIRED", "error_code": "OPS_AGENT_PROBE_REQUIRED", "message": "Agent 尚未通过联通测试，禁止绑定"}), 412

    bindings = ops_helpers._load_scope_agent_bindings(tid)
    service_bindings = ops_helpers._load_scope_service_bindings(tid)
    bindings[node_id] = agent_id
    service_bindings[node_id] = service_id
    ops_helpers._save_scope_agent_binding(tid, node_id, agent_id)
    ops_helpers._save_scope_service_binding(tid, node_id, service_id)
    log_audit("ops_platform_bind_node_service", f"node={node_id}; service={service_id}; agent={agent_id}")
    return jsonify({
        "ok": True,
        "node_id": node_id,
        "agent_id": agent_id,
        "service_id": service_id,
        "topology_id": tid,
        "binding_mode": "service_primary",
        "bindings": bindings,
        "service_bindings": service_bindings,
    })



@bp.route("/api/ops-platform/topology/node/start-remote", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_start_remote():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    scoped = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    topo_node = next((x for x in (scoped.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    node = ops_helpers._build_runtime_node_from_topology_node(project_id, str(registry.get("env_key") or env_key or ""), topo_node or {}, tid) if topo_node else None
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    if project_id and str(node.get("project_id") or "") and str(node.get("project_id") or "") != project_id:
        return jsonify({"ok": False, "error": "project_mismatch"}), 409

    bindings = ops_helpers._load_scope_agent_bindings(tid)
    service_bindings = ops_helpers._load_scope_service_bindings(tid)
    bound_service_id = str(payload.get("service_id") or service_bindings.get(node_id) or "").strip()
    agent_id = str(bindings.get(node_id) or "")
    if bound_service_id and not agent_id:
        for svc in ops_helpers._services_for_project(project_id):
            if not isinstance(svc, dict):
                continue
            if str(svc.get("service_id") or "").strip() == bound_service_id:
                agent_id = str(svc.get("agent_id") or "").strip()
                if agent_id:
                    break
    if not agent_id:
        return jsonify({"ok": False, "error": "agent_not_bound", "error_code": "OPS_REMOTE_START_FAILED", "message": "节点未绑定 Agent"}), 412
    reg = ops_helpers._load_agent_registry_v2()
    ag = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
    if not ag:
        return jsonify({"ok": False, "error": "agent_not_registered", "error_code": "OPS_REMOTE_START_FAILED", "message": "绑定 Agent 不存在"}), 404
    if str(ag.get("probe_status") or "").upper() != "PASS":
        return jsonify({"ok": False, "error": "OPS_AGENT_PROBE_FAILED", "error_code": "OPS_AGENT_PROBE_FAILED", "message": "Agent 联通测试未通过"}), 412

    req = {
        "node_id": node_id,
        "action_type": "start",
        "target": node_id,
        "ticket_id": "OPS-REMOTE-" + uuid.uuid4().hex[:8],
        "reason": "节点编辑器远端启动",
        "approver": str(session.get("user") or "admin"),
        "run_mode": "agent",
        "via_agent": True,
        "payload": {
            "run_mode": "agent",
            "desired_role": str(node.get("role") or ""),
            "desired_server_id": str(node.get("server_id") or ""),
            "desired_service_id": bound_service_id,
            "switch_required": True,
            "launch_visible_console": bool(payload.get("launch_visible_console", True)),
        },
    }
    validation = ops_helpers._validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing") or []}), 400
    if validation.get("require_approval") and not validation.get("approved"):
        aid = create_approval(
            "gm_ops_action",
            str(session.get("user") or "admin"),
            "ops_action",
            str(validation.get("approval_target_id") or ""),
            reason=str(validation.get("reason") or "remote start"),
            project_id=str(node.get("project_id") or project_id),
        )
        ok, err = approve_or_reject(aid, str(session.get("user") or "admin"), "approve", "remote start auto approve")
        if not ok:
            return jsonify({"ok": False, "error": "approval_failed", "message": str(err or "approval failed")}), 502
        req["approval_id"] = aid
        validation = ops_helpers._validate_ops_request(req, node)

    result = ops_helpers._execute_validated(req, node, validation)
    if not result.get("ok"):
        return jsonify({"ok": False, "error": "OPS_REMOTE_START_FAILED", "error_code": "OPS_REMOTE_START_FAILED", "message": str(result.get("message") or result.get("error") or "remote start failed")}), 502
    return jsonify({
        "ok": True,
        "node_id": node_id,
        "agent_id": agent_id,
        "service_id": bound_service_id,
        "job_id": ((result.get("data") or {}).get("job_id") if isinstance(result.get("data"), dict) else ""),
        "trace_id": str(result.get("trace_id") or ""),
    })



@bp.route("/api/ops-platform/topology/auto-bind-agents", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_auto_bind_agents():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node_ids = [str(n.get("id") or "") for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "")]
    reg = ops_helpers._load_agent_registry_v2()
    bindings = ops_helpers._load_scope_agent_bindings(tid)
    bound = 0
    skipped = 0
    failed = 0
    detail: List[Dict[str, Any]] = []
    canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else {}
    canonical_services = {
        str(s.get("node_id") or s.get("service_id") or "").strip()
        for s in (canonical.get("services") if isinstance(canonical.get("services"), list) else [])
        if isinstance(s, dict)
    }
    use_canonical = bool(ops_helpers._project_uses_runtime_topology(project_id) and canonical and not canonical.get("stale"))
    for nid in node_ids:
        matched = None
        fail_reason = ""
        if use_canonical:
            matched = CANONICAL_LOCAL_AGENT_ID
        elif not use_canonical:
            for aid, row in reg.items():
                if not isinstance(row, dict) or row.get("stale"):
                    continue
                if project_id and str(row.get("project_id") or "") not in ("", project_id):
                    continue
                if str(row.get("node_id") or "") != nid:
                    continue
                if str(row.get("probe_status") or "").upper() != "PASS":
                    fail_reason = "probe_not_pass"
                    continue
                if str(row.get("effective_status") or row.get("status") or "").upper() not in ("ONLINE", "READY", "RUNNING"):
                    fail_reason = "agent_not_online"
                    continue
                matched = str(aid or "")
                break
        if matched:
            bindings[nid] = matched
            ops_helpers._save_scope_agent_binding(tid, nid, matched)
            bound += 1
            detail.append({"node_id": nid, "agent_id": matched, "ok": True, "result": "bound"})
        else:
            candidates = [row for row in reg.values() if isinstance(row, dict) and str(row.get("node_id") or "") == nid]
            if candidates:
                failed += 1
                detail.append({"node_id": nid, "agent_id": "", "ok": False, "result": "failed", "reason": fail_reason or "agent_not_usable"})
            else:
                skipped += 1
                detail.append({"node_id": nid, "agent_id": "", "ok": False, "result": "skipped", "reason": "no_candidate"})
    return jsonify({"ok": True, "project_id": project_id, "env_key": str(registry.get("env_key") or env_key or ""), "topology_id": tid, "bound_count": bound, "skipped_count": skipped, "failed_count": failed, "bindings": bindings, "detail": detail})



@bp.route("/api/ops-platform/topology")
@admin_required("gm_ops")
def ops_platform_topology():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    return jsonify({
        "ok": True,
        "project_id": str(registry.get("project_id") or project_id or ""),
        "env_key": str(registry.get("env_key") or env_key or ""),
        "topology_id": str(registry.get("topology_id") or topology_id or ""),
        "registry": registry,
        "topologies": topo.get("topologies") if isinstance(topo.get("topologies"), list) else [],
        "topology": {"nodes": topo.get("nodes") or [], "edges": topo.get("edges") or [], "meta": topo.get("meta") or {}},
        "node_count": len(topo.get("nodes") or []),
    })



@bp.route("/api/ops-platform/topology/workbench-mode", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_workbench_mode():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    workbench_mode = str(payload.get("workbench_mode") or "").strip().lower()
    locked_mode = str(payload.get("workbench_locked_mode") if payload.get("workbench_locked_mode") is not None else "").strip().lower()
    if workbench_mode and workbench_mode not in ("edit", "run", "test"):
        return jsonify({"ok": False, "error": "invalid_mode", "message": "无效的工作台模式"}), 400
    if locked_mode and locked_mode not in ("edit", "run", "test"):
        return jsonify({"ok": False, "error": "invalid_locked_mode", "message": "无效的锁定模式"}), 400
    scoped = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "").strip()
    pid = str(registry.get("project_id") or project_id or "").strip()
    env = ops_helpers._normalize_env_key(registry.get("env_key") or env_key or "production")
    nodes = scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else []
    if not tid or not nodes:
        return jsonify({"ok": False, "error": "topology_not_found", "message": "未找到拓扑或拓扑为空"}), 404
    meta = scoped.get("meta") if isinstance(scoped.get("meta"), dict) else {}
    if workbench_mode in ("edit", "run", "test"):
        meta["workbench_mode"] = workbench_mode
    if "workbench_locked_mode" in payload:
        meta["workbench_locked_mode"] = locked_mode if locked_mode in ("edit", "run", "test") else ""
        if locked_mode in ("edit", "run", "test"):
            meta["workbench_mode"] = locked_mode
    meta["workbench_mode_updated_at"] = ops_helpers._now_iso()
    saved = ops_helpers._save_topology_scoped(
        pid,
        env,
        tid,
        {
            "nodes": nodes,
            "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
            "meta": meta,
        },
    )
    saved_meta = saved.get("meta") if isinstance(saved.get("meta"), dict) else meta
    log_audit(
        "ops_platform_topology_workbench_mode",
        f"topology={tid}; mode={saved_meta.get('workbench_mode')}; locked={saved_meta.get('workbench_locked_mode') or ''}",
    )
    return jsonify({
        "ok": True,
        "workbench_mode": str(saved_meta.get("workbench_mode") or "edit"),
        "workbench_locked_mode": str(saved_meta.get("workbench_locked_mode") or ""),
        "workbench_mode_updated_at": str(saved_meta.get("workbench_mode_updated_at") or ""),
    })



@bp.route("/api/ops-platform/topology/save", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_save():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    topo = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
    valid, errors = ops_helpers._validate_topology_contract(topo)
    if not valid:
        return jsonify({"ok": False, "error": "topology_contract_invalid", "message": "；".join(errors), "errors": errors}), 400
    ctx = ops_helpers._resolve_topology_context(project_id, env_key, topology_id)
    registry = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    pid = str(registry.get("project_id") or project_id or "")
    tid = str(registry.get("topology_id") or topology_id or "")
    agent_stat = ops_helpers._upsert_agents_from_topology(pid, saved.get("nodes") if isinstance(saved.get("nodes"), list) else [])
    purge_stat = {}
    saved_meta = saved.get("meta") if isinstance(saved.get("meta"), dict) else {}
    if saved_meta.get("runtime_topology") or ops_helpers._project_uses_runtime_topology(pid):
        purge_stat = ops_helpers._purge_design_demo_project_state(pid, tid)
    sync_result = ops_helpers._sync_topology_to_game_server(pid, str(registry.get("env_key") or env_key or ""), tid, str(session.get("user") or "admin"))
    canonical_stat = ops_helpers._consolidate_runtime_agents_to_canonical(pid)
    log_audit("ops_platform_topology_save", f"project={registry.get('project_id') or project_id}; env={registry.get('env_key') or env_key}; topology={registry.get('topology_id') or topology_id}; nodes={len((saved.get('nodes') or []))}; edges={len((saved.get('edges') or []))}")
    return jsonify({
        "ok": True,
        "message": "Topology saved",
        "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}},
        "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry,
        "agents": agent_stat,
        "purge": purge_stat,
        "sync": sync_result,
        "canonical": canonical_stat,
    })



@bp.route("/api/ops-platform/topology/node/update", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_update():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
    if not node_id:
        return jsonify({"ok": False, "error": "missing node_id"}), 400

    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    target = None
    for item in topo.get("nodes") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == node_id:
            target = item
            break
    if not target:
        return jsonify({"ok": False, "error": "node not found"}), 404

    if "role" in patch:
        target["role"] = str(patch.get("role") or "business")
    if "name" in patch:
        target["name"] = str(patch.get("name") or target.get("id") or "")
    if "kind" in patch:
        target["kind"] = ops_helpers._infer_node_kind(str(target.get("role") or "business"), str(patch.get("kind") or ""))
    if "desc" in patch:
        target["desc"] = str(patch.get("desc") or "")
    if "bizStatus" in patch:
        target["bizStatus"] = str(patch.get("bizStatus") or "normal")
    if "owner" in patch:
        target["owner"] = str(patch.get("owner") or "")
    if "x" in patch:
        try:
            target["x"] = float(patch.get("x"))
        except Exception:
            pass
    if "y" in patch:
        try:
            target["y"] = float(patch.get("y"))
        except Exception:
            pass
    if "tags" in patch and isinstance(patch.get("tags"), list):
        target["tags"] = patch.get("tags")
    if "preset_id" in patch:
        target["preset_id"] = str(patch.get("preset_id") or "").strip()
    if "daemon_start_cmd" in patch:
        target["daemon_start_cmd"] = str(patch.get("daemon_start_cmd") or "").strip()
    if "daemon_stop_cmd" in patch:
        target["daemon_stop_cmd"] = str(patch.get("daemon_stop_cmd") or "").strip()
    if "daemon_port" in patch:
        try:
            target["daemon_port"] = int(patch.get("daemon_port") or 0)
        except Exception:
            pass
    if "ui" in patch and isinstance(patch.get("ui"), dict):
        target["ui"] = patch.get("ui")
    if not isinstance(target.get("ui"), dict):
        target["ui"] = {}
    target["kind"] = ops_helpers._infer_node_kind(str(target.get("role") or "business"), str(target.get("kind") or ""))
    target["ui"]["ports"] = ops_helpers._normalize_ports(str(target.get("kind") or "standard"), target["ui"].get("ports"))
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)

    log_audit("ops_platform_topology_node_update", f"node={node_id}")
    return jsonify({"ok": True, "message": "节点属性已更新", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology/node/clone", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_clone():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    src = next((x for x in nodes if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not src:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    clone = copy.deepcopy(src)
    new_id = f"{node_id}-copy-{uuid.uuid4().hex[:4]}"
    clone["id"] = new_id
    clone["name"] = f"{str(src.get('name') or node_id)} 副本"
    clone["server_id"] = str(src.get("server_id") or new_id)
    ui = clone.get("ui") if isinstance(clone.get("ui"), dict) else {}
    try:
        clone["x"] = float(src.get("x") or ui.get("x") or 120) + 48.0
    except Exception:
        clone["x"] = 168.0
    try:
        clone["y"] = float(src.get("y") or ui.get("y") or 120) + 48.0
    except Exception:
        clone["y"] = 168.0
    ui["x"] = clone["x"]
    ui["y"] = clone["y"]
    clone["ui"] = ui
    nodes.append(clone)
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_node_clone", f"node={node_id}; clone={new_id}")
    return jsonify({"ok": True, "message": "节点已复制", "node_id": new_id, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology/node/disable", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_disable():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    disabled = bool(payload.get("disabled", True))
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    target = next((x for x in (topo.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not target:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    ui = target.get("ui") if isinstance(target.get("ui"), dict) else {}
    ui["disabled"] = disabled
    target["ui"] = ui
    target["bizStatus"] = "offline" if disabled else "normal"
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_node_disable", f"node={node_id}; disabled={disabled}")
    return jsonify({"ok": True, "message": "节点状态已更新", "disabled": disabled, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology/node/logs")
@admin_required("gm_ops")
def ops_platform_topology_node_logs():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    node_id = str(request.args.get("node_id") or "").strip()
    limit = max(1, min(200, int(request.args.get("limit") or 40)))
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    node = next((x for x in (topo.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    jobs = [x for x in reversed(ops_helpers._load_agent_jobs()) if isinstance(x, dict) and str(x.get("node_id") or "") == node_id][:limit]
    events = [x for x in ops_helpers._load_json_config(OPS_EVENT_LOG_KEY, []) if isinstance(x, dict) and str(x.get("node_id") or "") == node_id]
    events = list(reversed(events[-limit:]))
    bindings = ops_helpers._load_scope_agent_bindings(str(registry.get("topology_id") or topology_id or ""))
    return jsonify({
        "ok": True,
        "node": node,
        "agent_id": str(bindings.get(node_id) or ""),
        "jobs": jobs,
        "events": events,
    })












@bp.route("/api/ops-platform/topology/structured/add-existing-target", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_add_existing_target():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    frm = str(payload.get("from_node_id") or payload.get("from") or "").strip()
    to = str(payload.get("to_node_id") or payload.get("to") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    ok, result, status = ops_helpers._ops_structured_append_edge(topo, frm, to)
    if not ok:
        return jsonify(result), status
    ops_helpers._ops_topology_meta_structured(topo)
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_structured_add_existing_target", f"{frm}->{to}")
    return jsonify({"ok": True, "message": "已添加下游连线", "edge": result, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology/structured/add-new-target", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_add_new_target():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    frm = str(payload.get("from_node_id") or payload.get("from") or "").strip()
    preset_id = str(payload.get("preset_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    if not frm or not preset_id:
        return jsonify({"ok": False, "error": "missing_required_fields", "message": "缺少源节点或模板"}), 400
    preset = None
    for item in ops_helpers._load_node_presets():
        if isinstance(item, dict) and str(item.get("preset_id") or "") == preset_id:
            preset = item
            break
    if not preset:
        return jsonify({"ok": False, "error": "preset_not_found", "message": "节点模板不存在"}), 404

    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    src_node = next((x for x in (topo.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == frm), None)
    if not src_node:
        return jsonify({"ok": False, "error": "node not found", "message": "源节点不存在"}), 404
    role = str(preset.get("role") or "business")
    node_kind = ops_helpers._infer_node_kind(role, str(preset.get("kind") or ""))
    candidate = {
        "id": str(payload.get("id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}",
        "name": str(payload.get("name") or preset.get("name") or preset_id),
        "server_id": str(payload.get("server_id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}",
        "project_id": project_id,
        "env": str(registry.get("env_key") or env_key or "production"),
        "owner": str(payload.get("owner") or "ops-admin"),
        "role": role,
        "node_category": str(preset.get("category") or ""),
        "node_type": str(preset.get("node_type") or ""),
        "desc": str(payload.get("description") or preset.get("default_desc") or ""),
        "bizStatus": "normal",
        "tags": [str(preset.get("category") or ""), role],
        "x": 160.0,
        "y": 160.0,
        "ui": {"x": 160.0, "y": 160.0, "w": 220, "h": 90, "color": "#0f172a", "locked": False, "ports": ops_helpers._normalize_ports(node_kind, preset.get("default_ports"))},
    }
    if not ops_helpers._can_link_nodes(src_node, candidate):
        return jsonify({"ok": False, "error": "invalid_edge_by_role", "error_code": "OPS_EDGE_ROLE_FORBIDDEN", "message": "该模板不能作为当前节点的下游"}), 409
    new_id = str(candidate.get("id") or "").strip()
    if any(isinstance(x, dict) and str(x.get("id") or "") == new_id for x in (topo.get("nodes") or [])):
        return jsonify({"ok": False, "error": "node_id_exists", "message": f"节点ID已存在: {new_id}"}), 409
    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    topo["nodes"] = topo_nodes
    if not any(isinstance(n, dict) and str(n.get("id") or "") == new_id for n in topo_nodes):
        topo_nodes.append(candidate)
    ok, result, status = ops_helpers._ops_structured_append_edge(topo, frm, new_id)
    if not ok:
        return jsonify(result), status
    ops_helpers._ops_topology_meta_structured(topo)
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_structured_add_new_target", f"{frm}->{new_id}; preset={preset_id}")
    return jsonify({"ok": True, "message": "已添加下游节点", "node": candidate, "edge": result, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology/structured/delete-node", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_delete_node():
    return ops_platform_topology_node_delete()



@bp.route("/api/ops-platform/topology/structured/delete-edge", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_delete_edge():
    return ops_platform_topology_edge_delete()



@bp.route("/api/ops-platform/topology/edge/upsert", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_edge_upsert():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    frm = str(payload.get("from") or "").strip()
    to = str(payload.get("to") or "").strip()
    from_port = str(payload.get("from_port") or "out-1").strip()
    to_port = str(payload.get("to_port") or "in-1").strip()
    etype = str(payload.get("type") or "depends_on").strip()
    note = str(payload.get("note") or "").strip()
    if not frm or not to or frm == to:
        return jsonify({"ok": False, "error": "invalid edge endpoints"}), 400

    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = edges
    valid = set([str(x.get("id") or "") for x in topo.get("nodes") or [] if isinstance(x, dict)])
    if frm not in valid or to not in valid:
        return jsonify({"ok": False, "error": "node not found"}), 404
    topo_nodes = {str(x.get("id") or ""): x for x in (topo.get("nodes") or []) if isinstance(x, dict)}
    fn = topo_nodes.get(frm) or {}
    tn = topo_nodes.get(to) or {}
    if not ops_helpers._can_link_nodes(fn, tn):
        return jsonify({
            "ok": False,
            "error": "invalid_edge_by_role",
            "error_code": "OPS_EDGE_ROLE_FORBIDDEN",
            "message": "当前节点角色规则不允许该连线",
        }), 409
    fkind = str(fn.get("kind") or ops_helpers._infer_node_kind(str(fn.get("role") or ""), ""))
    tkind = str(tn.get("kind") or ops_helpers._infer_node_kind(str(tn.get("role") or ""), ""))
    if fkind == "terminal" or tkind == "entry":
        return jsonify({"ok": False, "error": "node_kind_violation", "error_code": "OPS_NODE_KIND_VIOLATION", "message": "Node kind direction is not allowed"}), 400
    fports = ops_helpers._normalize_ports(fkind, ((fn.get("ui") or {}).get("ports") if isinstance(fn.get("ui"), dict) else None))
    tports = ops_helpers._normalize_ports(tkind, ((tn.get("ui") or {}).get("ports") if isinstance(tn.get("ui"), dict) else None))
    if from_port not in [str(p.get("id") or "") for p in fports.get("out", [])] or to_port not in [str(p.get("id") or "") for p in tports.get("in", [])]:
        return jsonify({"ok": False, "error": "port_not_found", "error_code": "OPS_PORT_NOT_FOUND", "message": "Port not found"}), 400
    for ex in edges:
        if not isinstance(ex, dict):
            continue
        if str(ex.get("from") or "") == frm and str(ex.get("to") or "") == to and str(ex.get("from_port") or "out-1") == from_port and str(ex.get("to_port") or "in-1") == to_port:
            return jsonify({"ok": False, "error": "edge_duplicate", "error_code": "OPS_EDGE_DUPLICATE", "message": "Duplicate edge"}), 409
    incoming_count = 0
    for ex in edges:
        if isinstance(ex, dict) and str(ex.get("to") or "") == to and str(ex.get("to_port") or "in-1") == to_port:
            incoming_count += 1
    in_max = 1
    for p in tports.get("in", []):
        if str(p.get("id") or "") == to_port:
            in_max = int(p.get("max_links") or 1)
            break
    if incoming_count >= in_max:
        return jsonify({"ok": False, "error": "port_capacity_exceeded", "error_code": "OPS_PORT_CAPACITY_EXCEEDED", "message": "Input port capacity exceeded"}), 409
    outgoing_count = 0
    for ex in edges:
        if isinstance(ex, dict) and str(ex.get("from") or "") == frm and str(ex.get("from_port") or "out-1") == from_port:
            outgoing_count += 1
    out_max = 1
    for p in fports.get("out", []):
        if str(p.get("id") or "") == from_port:
            out_max = int(p.get("max_links") or 1)
            break
    if outgoing_count >= out_max:
        return jsonify({"ok": False, "error": "port_capacity_exceeded", "error_code": "OPS_PORT_CAPACITY_EXCEEDED", "message": "Output port capacity exceeded"}), 409

    updated = False
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("from") or "") == frm and str(edge.get("to") or "") == to and str(edge.get("from_port") or "out-1") == from_port and str(edge.get("to_port") or "in-1") == to_port:
            edge["type"] = etype
            edge["note"] = note
            updated = True
            break
    if not updated:
        edges.append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": frm, "to": to, "from_port": from_port, "to_port": to_port, "type": etype, "note": note})

    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_edge_upsert", f"{frm}->{to}; type={etype}")
    resp = {"ok": True, "message": "连线已保存", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry}
    return jsonify(resp)



@bp.route("/api/ops-platform/topology/edge/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_edge_delete():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    edge_id = str(payload.get("edge_id") or "").strip()
    if not edge_id:
        return jsonify({"ok": False, "error": "missing edge_id"}), 400

    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    if ops_helpers._is_critical_topology_edge(topo, edge_id):
        return jsonify({
            "ok": False,
            "error": "edge_delete_blocked",
            "error_code": "OPS_EDGE_DELETE_BLOCKED",
            "message": "关键链路连线不可删除（会导致架构断裂）",
        }), 409
    before = len(topo.get("edges") or [])
    topo["edges"] = [x for x in (topo.get("edges") or []) if not (isinstance(x, dict) and str(x.get("id") or "") == edge_id)]
    after = len(topo.get("edges") or [])
    if after == before:
        return jsonify({"ok": False, "error": "edge not found"}), 404
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_edge_delete", f"edge={edge_id}")
    return jsonify({"ok": True, "message": "Edge deleted", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})






@bp.route("/api/ops-platform/topology/node/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_delete():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "Missing ops execute permission"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing node_id"}), 400

    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node_ids = {str(x.get("id") or "") for x in (topo.get("nodes") or []) if isinstance(x, dict)}
    if node_id not in node_ids:
        return jsonify({"ok": False, "error": "node not found"}), 404
    if ops_helpers._is_critical_topology_node(topo, node_id):
        return jsonify({"ok": False, "error": "node_delete_blocked", "error_code": "OPS_NODE_DELETE_BLOCKED", "message": "Critical node cannot be deleted"}), 409

    before_edges = len(topo.get("edges") or [])
    topo["nodes"] = [x for x in (topo.get("nodes") or []) if not (isinstance(x, dict) and str(x.get("id") or "") == node_id)]
    topo["edges"] = [x for x in (topo.get("edges") or []) if not (isinstance(x, dict) and (str(x.get("from") or "") == node_id or str(x.get("to") or "") == node_id))]
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), tid, topo)

    bindings = ops_helpers._load_scope_agent_bindings(tid)
    if node_id in bindings:
        bindings.pop(node_id, None)
        ops_helpers._save_scope_agent_binding(tid, node_id, "")
    service_bindings = ops_helpers._load_scope_service_bindings(tid)
    if node_id in service_bindings:
        service_bindings.pop(node_id, None)
        ops_helpers._save_scope_service_binding(tid, node_id, "")

    log_audit("ops_platform_topology_node_delete", f"node={node_id}; removed_edges={before_edges - len(saved.get('edges') or [])}")
    return jsonify({"ok": True, "message": "Node deleted", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "bindings": bindings, "service_bindings": service_bindings, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology-blueprints")
@admin_required("gm_ops")
def ops_platform_topology_blueprints():
    rows = ops_helpers._load_topology_blueprints()
    out: List[Dict[str, Any]] = []
    for x in rows:
        if not isinstance(x, dict):
            continue
        out.append(
            {
                "blueprint_id": str(x.get("blueprint_id") or ""),
                "name": str(x.get("name") or ""),
                "desc": str(x.get("desc") or ""),
                "framework_profile": str(x.get("framework_profile") or ""),
                "blueprint_version": int(x.get("blueprint_version") or 0),
                "nodes": x.get("nodes") if isinstance(x.get("nodes"), list) else [],
                "edges": x.get("edges") if isinstance(x.get("edges"), list) else [],
            }
        )
    return jsonify({"ok": True, "count": len(out), "blueprints": out})



@bp.route("/api/ops-platform/topology/apply-blueprint", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_apply_blueprint():
    payload = request.get_json(silent=True) or {}
    bid = str(payload.get("blueprint_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    replace_existing = bool(payload.get("replace_existing", True))
    if not bid:
        return jsonify({"ok": False, "error": "missing_blueprint_id"}), 400

    bp_item = None
    for item in ops_helpers._load_topology_blueprints():
        if isinstance(item, dict) and str(item.get("blueprint_id") or "") == bid:
            bp_item = item
            break
    if not bp_item:
        return jsonify({"ok": False, "error": "blueprint_not_found"}), 404

    presets = ops_helpers._load_node_presets()
    preset_map = {str(p.get("preset_id") or ""): p for p in presets if isinstance(p, dict)}
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    if replace_existing:
        topo = {"nodes": [], "edges": [], "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": ops_helpers._now_iso()}}
    existing_ids = set(str(n.get("id") or "") for n in (topo.get("nodes") or []) if isinstance(n, dict))
    created_node_ids: List[str] = []
    created_by_preset: Dict[str, List[str]] = {}

    plan_nodes = bp_item.get("nodes") if isinstance(bp_item.get("nodes"), list) else []
    for entry in plan_nodes:
        if not isinstance(entry, dict):
            continue
        preset_id = str(entry.get("preset_id") or "").strip()
        count = max(1, min(20, int(entry.get("count") or 1)))
        preset = preset_map.get(preset_id)
        if not preset:
            continue
        for idx in range(count):
            new_id = f"{preset_id}-{uuid.uuid4().hex[:6]}"
            while new_id in existing_ids:
                new_id = f"{preset_id}-{uuid.uuid4().hex[:6]}"
            existing_ids.add(new_id)
            role = str(preset.get("role") or "business")
            node_kind = ops_helpers._infer_node_kind(role, str(preset.get("kind") or ""))
            contract = ops_helpers._load_node_contract(preset_id) or {}
            default_port = int(preset.get("default_port") or contract.get("default_port") or 0)
            daemon_defaults = ops_helpers._contract_daemon_defaults(preset_id, default_port) if preset_id else {}
            created_node_ids.append(new_id)
            created_by_preset.setdefault(preset_id, []).append(new_id)
            remote_ui = {"port": default_port} if default_port > 0 else {}
            network_ui = {"endpoints": [f"127.0.0.1:{default_port}"]} if default_port > 0 else {}
            node_ports = ops_helpers._gateway_blueprint_ports() if preset_id == "gateway_http" else ops_helpers._normalize_ports(node_kind, None)
            topo["nodes"].append(
                {
                    "id": new_id,
                    "name": f"{str(preset.get('name') or preset_id)}-{idx + 1}",
                    "server_id": new_id,
                    "preset_id": preset_id,
                    "project_id": project_id,
                    "env": str(registry.get("env_key") or env_key or "production"),
                    "role": role,
                    "kind": node_kind,
                    "desc": str(preset.get("default_desc") or ""),
                    "bizStatus": "normal",
                    "owner": "ops-admin",
                    "daemon_profile": str(preset.get("daemon_profile") or ""),
                    "daemon_start_cmd": str(daemon_defaults.get("StartCommand") or ""),
                    "daemon_stop_cmd": str(daemon_defaults.get("StopCommand") or ""),
                    "daemon_port": default_port,
                    "x": 160.0,
                    "y": 160.0,
                    "tags": [str(preset.get("category") or ""), role],
                    "ui": {
                        "x": 160.0,
                        "y": 160.0,
                        "w": 220,
                        "h": 90,
                        "color": "#0f172a",
                        "locked": False,
                        "ports": node_ports,
                        "remote": remote_ui,
                        "network": network_ui,
                    },
                }
            )

    ops_helpers._layout_blueprint_nodes_by_layer(topo, created_node_ids)

    plan_edges = bp_item.get("edges") if isinstance(bp_item.get("edges"), list) else []
    ops_helpers._apply_topology_blueprint_edges(topo, created_by_preset, plan_edges)

    saved_topo = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_apply_blueprint", f"blueprint={bid}; created={len(created_node_ids)}; project={project_id}")
    return jsonify({"ok": True, "blueprint_id": bid, "created_count": len(created_node_ids), "created_node_ids": created_node_ids, "topology": {"nodes": saved_topo.get("nodes") or [], "edges": saved_topo.get("edges") or [], "meta": saved_topo.get("meta") or {}}, "registry": saved_topo.get("registry") if isinstance(saved_topo.get("registry"), dict) else registry})


