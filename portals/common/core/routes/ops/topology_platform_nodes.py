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


