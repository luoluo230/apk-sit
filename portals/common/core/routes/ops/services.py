# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
from routes.ops import deps as ops_helpers
from routes.ops import bp

@bp.route("/api/ops-platform/services")
@admin_required("gm_ops")
def ops_platform_services_list():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    rows = ops_helpers._services_for_project(project_id)
    return jsonify({"ok": True, "count": len(rows), "services": rows})



@bp.route("/api/ops-platform/services/upsert", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_services_upsert():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    service_id = str(payload.get("service_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    if not service_id:
        return jsonify({"ok": False, "error": "missing_service_id"}), 400

    reg = ops_helpers._load_agent_registry_v2()
    hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
    if not hit:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    if project_id:
        ag_project = str(hit.get("project_id") or "").strip()
        if ag_project and ag_project != project_id:
            return jsonify({"ok": False, "error": "OPS_AGENT_NOT_IN_PROJECT", "error_code": "OPS_AGENT_NOT_IN_PROJECT"}), 409

    services = hit.get("services") if isinstance(hit.get("services"), list) else []
    idx = -1
    for i, svc in enumerate(services):
        if isinstance(svc, dict) and str(svc.get("service_id") or "").strip() == service_id:
            idx = i
            break
    now = ops_helpers._now_iso()
    svc_obj = dict(services[idx]) if idx >= 0 and isinstance(services[idx], dict) else {}
    svc_obj["service_id"] = service_id
    svc_obj["agent_id"] = agent_id
    svc_obj["project_id"] = str(payload.get("project_id") or svc_obj.get("project_id") or hit.get("project_id") or "")
    svc_obj["node_id"] = str(payload.get("node_id") or svc_obj.get("node_id") or "")
    svc_obj["display_name"] = str(payload.get("display_name") or svc_obj.get("display_name") or service_id)
    svc_obj["service_type"] = str(payload.get("service_type") or svc_obj.get("service_type") or "standard")
    if "service_port" in payload:
        try:
            svc_obj["service_port"] = int(payload.get("service_port") or 0)
        except Exception:
            svc_obj["service_port"] = 0
    if "remote_game_server_port" in payload:
        try:
            svc_obj["remote_game_server_port"] = int(payload.get("remote_game_server_port") or 0)
        except Exception:
            svc_obj["remote_game_server_port"] = 0
    if "run_state" in payload:
        svc_obj["run_state"] = str(payload.get("run_state") or "")
    if "status" in payload:
        svc_obj["status"] = str(payload.get("status") or "")
    if "desc" in payload:
        svc_obj["desc"] = str(payload.get("desc") or "")
    if "network" in payload and isinstance(payload.get("network"), dict):
        svc_obj["network"] = payload.get("network")
    svc_obj["updated_at"] = now

    if idx >= 0:
        services[idx] = svc_obj
    else:
        services.append(svc_obj)
    hit["services"] = services
    hit["updated_at"] = now
    reg[agent_id] = ops_helpers._normalize_agent_descriptor_v2(hit)
    ops_helpers._save_agent_registry_v2(reg)
    return jsonify({"ok": True, "service": svc_obj})



@bp.route("/api/ops-platform/services/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_services_delete():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    service_id = str(payload.get("service_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    if not service_id:
        return jsonify({"ok": False, "error": "missing_service_id"}), 400

    reg = ops_helpers._load_agent_registry_v2()
    hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
    if not hit:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    if project_id:
        ag_project = str(hit.get("project_id") or "").strip()
        if ag_project and ag_project != project_id:
            return jsonify({"ok": False, "error": "OPS_AGENT_NOT_IN_PROJECT", "error_code": "OPS_AGENT_NOT_IN_PROJECT"}), 409

    services = hit.get("services") if isinstance(hit.get("services"), list) else []
    remove_index = -1
    removed_service: Dict[str, Any] = {}
    for idx, svc in enumerate(services):
        if not isinstance(svc, dict):
            continue
        if str(svc.get("service_id") or "").strip() == service_id:
            remove_index = idx
            removed_service = dict(svc)
            break

    if remove_index < 0:
        logical_service = next(
            (
                svc for svc in ops_helpers._services_for_project(project_id)
                if isinstance(svc, dict)
                and str(svc.get("service_id") or "").strip() == service_id
                and str(svc.get("agent_id") or "").strip() == agent_id
            ),
            None,
        )
        logical_source = str((logical_service or {}).get("source") or "").strip().lower()
        if logical_source in ("agent.compat", "logical.agent.compat"):
            return jsonify(
                {
                    "ok": False,
                    "error": "OPS_SERVICE_DELETE_COMPAT_BLOCKED",
                    "error_code": "OPS_SERVICE_DELETE_COMPAT_BLOCKED",
                    "message": "该服务实例来自兼容聚合，需先转为正式服务实例或从源节点移除",
                }
            ), 409
        return jsonify({"ok": False, "error": "service_not_found", "error_code": "OPS_SERVICE_NOT_FOUND"}), 404

    services.pop(remove_index)
    hit["services"] = services
    hit["updated_at"] = ops_helpers._now_iso()
    reg[agent_id] = ops_helpers._normalize_agent_descriptor_v2(hit)

    bindings = ops_helpers._load_node_service_bindings() or {}
    removed_binding_nodes = [str(node_id or "").strip() for node_id, bound_service_id in bindings.items() if str(bound_service_id or "").strip() == service_id]
    for node_id in removed_binding_nodes:
        bindings.pop(node_id, None)

    ops_helpers._save_node_service_bindings(bindings)
    ops_helpers._save_agent_registry_v2(reg)
    log_audit("ops_platform_services_delete", f"agent_id={agent_id}; service_id={service_id}; bindings={','.join(removed_binding_nodes)}")
    return jsonify(
        {
            "ok": True,
            "agent_id": agent_id,
            "service_id": service_id,
            "service": removed_service,
            "removed_binding_nodes": removed_binding_nodes,
        }
    )



@bp.route("/api/ops-platform/services/logs", methods=["GET"])
@admin_required("gm_ops")
def ops_platform_services_logs():
    project_id = str(request.args.get("project_id") or "").strip()
    service_id = str(request.args.get("service_id") or "").strip()
    level = str(request.args.get("level") or "all").strip().lower()
    query = str(request.args.get("q") or "").strip()
    try:
        tail = int(request.args.get("tail") or 400)
    except Exception:
        tail = 400
    try:
        since_offset = int(request.args.get("since_offset") or 0)
    except Exception:
        since_offset = 0
    sid_lower = service_id.lower()
    daemon_infra = sid_lower in ("mongo-db-cn-1", "redis-cache-cn-1")
    gameserver_process = sid_lower in ops_helpers._GAMESERVER_PROCESS_SERVICE_IDS
    default_session = "1" if gameserver_process else ("0" if daemon_infra else "1")
    default_lifecycle = "0" if (daemon_infra or gameserver_process) else "1"
    current_session_only = str(request.args.get("current_session") or request.args.get("session") or default_session).strip().lower() in ("1", "true", "yes", "on")
    hide_lifecycle = str(request.args.get("hide_lifecycle") or default_lifecycle).strip().lower() in ("1", "true", "yes", "on")
    tail = max(50, min(tail, 2000))
    payload = ops_helpers._read_gameserver_service_logs(
        service_id,
        level=level,
        query=query,
        tail=tail,
        since_offset=since_offset,
        current_session_only=current_session_only,
        hide_lifecycle=hide_lifecycle,
    )
    return jsonify({"ok": True, "project_id": project_id, "service_id": service_id, **payload})



@bp.route("/api/ops-platform/services/action", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_services_action():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    service_id = str(payload.get("service_id") or "").strip()
    action = str(payload.get("action") or "status").strip().lower()
    if not service_id:
        return jsonify({"ok": False, "error": "missing_service_id"}), 400

    service_hit = None
    for svc in ops_helpers._services_for_project(project_id):
        if isinstance(svc, dict) and str(svc.get("service_id") or "").strip() == service_id:
            service_hit = svc
            break
    if not service_hit:
        return jsonify({"ok": False, "error": "service_not_found", "error_code": "OPS_SERVICE_NOT_FOUND"}), 404

    topology_node_id = ops_helpers._resolve_topology_node_id_for_service(
        project_id,
        service_id,
        str(payload.get("node_id") or service_hit.get("node_id") or "").strip(),
    )
    agent_id = str(service_hit.get("agent_id") or payload.get("agent_id") or "").strip()
    reg = ops_helpers._load_agent_registry_v2()
    agent_desc = reg.get(agent_id) if agent_id and isinstance(reg.get(agent_id), dict) else {}
    dispatch_node_id = str((agent_desc or {}).get("node_id") or "").strip()
    if not dispatch_node_id:
        dispatch_node_id = topology_node_id
    if not dispatch_node_id:
        return jsonify({"ok": False, "error": "missing_dispatch_node_id", "error_code": "OPS_SERVICE_DISPATCH_NODE_MISSING"}), 400
    action_map = {
        "start": "start",
        "stop": "stop",
        "restart": "restart",
        "status": "status",
        "probe": "health_check",
        "logs": "log_tail",
    }
    action_type = action_map.get(action, "")
    if not action_type:
        return jsonify({"ok": False, "error": "unsupported_action"}), 400

    topology_node = ops_helpers._resolve_ops_dispatch_node(project_id, topology_node_id)
    if not topology_node:
        return jsonify({"ok": False, "error": "topology_node_not_found", "message": "未找到拓扑节点"}), 404

    body_payload = {
        "run_mode": "direct",
        "desired_role": str(service_hit.get("service_type") or ""),
        "desired_service_id": service_id,
        "desired_server_id": service_id,
        "topology_node_id": topology_node_id,
        "switch_required": action in ("start", "restart"),
        "launch_visible_console": bool(payload.get("launch_visible_console", action == "start")),
    }
    operator = str(session.get("user") or "admin")
    ticket_id = "OPS-SVC-" + uuid.uuid4().hex[:8]

    use_direct = (
        agent_id == CANONICAL_LOCAL_AGENT_ID
        or (ops_helpers._project_uses_runtime_topology(project_id) and ops_helpers._is_external_daemon_node(topology_node))
        or (ops_helpers._project_uses_runtime_topology(project_id) and agent_id == CANONICAL_LOCAL_AGENT_ID)
    )
    if ops_helpers._project_uses_runtime_topology(project_id):
        use_direct = True

    if use_direct:
        result = ops_helpers._execute_canonical_service_action(
            project_id,
            topology_node_id,
            service_id,
            action,
            operator,
            "服务实例标准运维动作",
            ticket_id,
            body_payload,
        )
        if not result.get("ok"):
            return jsonify({
                "ok": False,
                "error": "OPS_SERVICE_ACTION_FAILED",
                "error_code": "OPS_SERVICE_ACTION_FAILED",
                "message": str(result.get("message") or "service action failed"),
                "mode": result.get("mode") or "direct",
                "data": result.get("data") if isinstance(result.get("data"), dict) else {},
            })
        return jsonify({
            "ok": True,
            "node_id": topology_node_id,
            "dispatch_node_id": topology_node_id,
            "agent_id": agent_id,
            "service_id": service_id,
            "action": action,
            "mode": result.get("mode") or "direct",
            "message": str(result.get("message") or ""),
            "data": result.get("data") if isinstance(result.get("data"), dict) else {},
            "trace_id": "dir-" + uuid.uuid4().hex[:12],
        })

    dispatch_node_id = str((agent_desc or {}).get("node_id") or "").strip() or topology_node_id
    node = ops_helpers._resolve_ops_dispatch_node(project_id, dispatch_node_id)
    if not node:
        return jsonify({"ok": False, "error": "dispatch_node_not_found", "error_code": "OPS_SERVICE_DISPATCH_NODE_MISSING"}), 404
    req = {
        "node_id": dispatch_node_id,
        "action_type": action_type,
        "target": service_id,
        "ticket_id": ticket_id,
        "reason": "服务实例标准运维动作",
        "approver": operator,
        "run_mode": "agent",
        "via_agent": True,
        "payload": dict(body_payload, run_mode="agent"),
    }
    validation = ops_helpers._validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing") or []}), 400
    result = ops_helpers._execute_validated(req, node, validation)
    if not result.get("ok"):
        return jsonify({
            "ok": False,
            "error": "OPS_SERVICE_ACTION_FAILED",
            "error_code": "OPS_SERVICE_ACTION_FAILED",
            "message": str(result.get("message") or result.get("error") or "service action failed"),
            "data": result.get("data") if isinstance(result.get("data"), dict) else {},
        })
    return jsonify({
        "ok": True,
        "node_id": topology_node_id,
        "dispatch_node_id": dispatch_node_id,
        "agent_id": agent_id,
        "service_id": service_id,
        "action": action,
        "job_id": ((result.get("data") or {}).get("job_id") if isinstance(result.get("data"), dict) else ""),
        "trace_id": str(result.get("trace_id") or ""),
    })


