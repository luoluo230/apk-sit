# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import approvals_db, log_audit
from services.authz import admin_required
import services.ops.helpers as ops_helpers
from routes.ops import bp

@bp.route("/api/ops-platform/overview")
@admin_required("gm_ops")
def ops_platform_overview():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    env_key = ops_helpers._resolve_ops_env_key(request.args.get("env_key") or "")
    from services.ops.cluster_health_bridge import enrich_overview
    payload = ops_helpers._build_overview(project_id=project_id, env_key=env_key)
    operator = str(session.get("user") or "intranet-ops")
    return jsonify(enrich_overview(payload, operator=operator))



@bp.route("/api/ops-platform/events")
@admin_required("gm_ops")
def ops_platform_events():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    limit_text = str(request.args.get("limit") or "80").strip()
    try:
        limit = max(1, min(int(limit_text), 300))
    except Exception:
        limit = 80

    rows = ops_helpers._load_json_config(OPS_EVENT_LOG_KEY, [])
    if not isinstance(rows, list):
        rows = []

    snapshot = ops_helpers._load_json_config(OPS_ALERT_SNAPSHOT_KEY, {})
    alerts = snapshot.get("alerts") if isinstance(snapshot, dict) and isinstance(snapshot.get("alerts"), list) else []

    merged: List[Dict[str, Any]] = []
    merged.extend([x for x in alerts if isinstance(x, dict)])
    merged.extend([x for x in rows if isinstance(x, dict)])
    merged.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    return jsonify({"ok": True, "count": len(merged[:limit]), "events": merged[:limit]})



@bp.route("/api/ops-platform/client-log", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_client_log():
    payload = request.get_json(silent=True) or {}
    event = str(payload.get("event") or "unknown_event").strip()
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    try:
        compact = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        compact = "{}"
    if len(compact) > 1800:
        compact = compact[:1800] + "...(truncated)"
    log_audit("ops_platform_client_log", f"{event}: {compact}")
    return jsonify({"ok": True})



@bp.route("/api/ops-platform/module-map")
@admin_required("gm_ops")
def ops_platform_module_map():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    pid = ops_helpers._resolve_ops_project_id(request.args.get("project_id", ""))
    modules = [
        {"id": "overview", "name": "项目运维总览", "href": f"/admin/projects/{pid}/ops", "children": ["kpi", "risk", "todo"]},
        {"id": "topology", "name": "拓扑与配置编排", "href": f"/admin/projects/{pid}/topologies", "children": ["node_library", "canvas", "inspector"]},
        {"id": "action_center", "name": "动作执行中心", "href": f"/admin/projects/{pid}/actions", "children": ["catalog", "approval", "execute", "history"]},
        {"id": "diagnostics", "name": "诊断与体检", "href": f"/admin/projects/{pid}/diagnostics", "children": ["rules", "filter", "export"]},
        {"id": "events_trace", "name": "事件与追踪", "href": f"/admin/projects/{pid}/ops", "children": ["timeline", "trace", "audit"]},
        {"id": "agent_control", "name": "Agent 管控", "href": f"/admin/projects/{pid}/agents", "children": ["registry", "policy", "queue"]},
        {"id": "change_governance", "name": "发布与变更治理", "href": f"/admin/projects/{pid}/change-governance", "children": ["change_window", "freeze"]},
        {"id": "governance", "name": "权限与合规", "href": "/admin/approval", "children": ["rbac", "approval", "audit"]},
    ]
    return jsonify({"ok": True, "modules": modules})












@bp.route("/api/ops-platform/control-plane/summary")
@admin_required("gm_ops")
def ops_platform_control_plane_summary():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    from services.ops.modules import agent_control
    return jsonify(agent_control.build_control_plane_summary())



@bp.route("/api/ops-platform/change-governance/summary")
@admin_required("gm_ops")
def ops_platform_change_governance_summary():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    from services.ops.modules import change_governance
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._resolve_ops_env_key(request.args.get("env_key") or "")
    return jsonify(change_governance.build_summary(project_id=project_id, env_key=env_key))



@bp.route("/api/ops-platform/change-governance/freeze", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_change_governance_freeze():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    from services.ops.modules import change_governance
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    active = bool(payload.get("active"))
    reason = str(payload.get("reason") or ("变更冻结" if active else "解除冻结"))
    actor = str(session.get("user") or "admin")
    result = change_governance.set_freeze(project_id, active, reason, actor)
    if not result.get("ok"):
        return jsonify(result), 400
    log_audit("ops_platform_change_freeze", f"project={project_id}; active={active}")
    return jsonify(result)



@bp.route("/api/ops-platform/action-targets")
@admin_required("gm_ops")
def ops_platform_action_targets():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    env_key = ops_helpers._resolve_ops_env_key(request.args.get("env_key") or "")
    targets = ops_helpers._list_action_targets(project_id, env_key)
    return jsonify({"ok": True, "project_id": project_id, "env_key": env_key, "count": len(targets), "targets": targets})



@bp.route("/api/ops-platform/diagnostics/summary")
@admin_required("gm_ops")
def ops_platform_diagnostics_summary():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    from services.ops.modules import diagnostics
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    env_key = ops_helpers._resolve_ops_env_key(request.args.get("env_key") or "")
    return jsonify(diagnostics.build_summary(project_id=project_id, env_key=env_key))



@bp.route("/api/ops-platform/action-catalog")
@admin_required("gm_ops")
def ops_platform_action_catalog():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    from services.ops.modules import action_center
    rows = action_center.list_catalog()
    return jsonify({"ok": True, "actions": rows, "data": rows, "catalog": rows})



@bp.route("/api/ops-platform/node-presets")
@admin_required("gm_ops")
def ops_platform_node_presets():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    presets = ops_helpers._load_node_presets()
    out = []
    for p in presets:
        if not isinstance(p, dict):
            continue
        role = str(p.get("role") or "business")
        kind = ops_helpers._infer_node_kind(role, str(p.get("kind") or ""))
        item = dict(p)
        item["kind"] = kind
        item["default_ports"] = ops_helpers._normalize_ports(kind, p.get("default_ports"))
        out.append(item)
    return jsonify({"ok": True, "count": len(out), "presets": out})



@bp.route("/api/ops-platform/node/add-from-preset", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_add_node_from_preset():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    preset_id = str(payload.get("preset_id") or "").strip()
    name = str(payload.get("name") or "").strip()
    server_id = str(payload.get("server_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or payload.get("env") or "production")
    topology_id = str(payload.get("topology_id") or "").strip()
    channel = str(payload.get("channel") or "").strip()
    owner = str(payload.get("owner") or "").strip()
    node_note = str(payload.get("description") or "").strip()
    daemon_start_cmd = str(payload.get("daemon_start_cmd") or "").strip()
    daemon_stop_cmd = str(payload.get("daemon_stop_cmd") or "").strip()

    presets = ops_helpers._load_node_presets()
    preset = None
    for item in presets:
        if str(item.get("preset_id") or "") == preset_id:
            preset = item
            break
    if not preset:
        return jsonify({"ok": False, "error": "preset_not_found"}), 404

    contract = ops_helpers._load_node_contract(preset_id) or {}
    default_port = int(preset.get("default_port") or contract.get("default_port") or 0)
    if not daemon_start_cmd and preset_id:
        daemon_start_cmd = str(ops_helpers._contract_daemon_defaults(preset_id, default_port).get("StartCommand") or "").strip()
    if not daemon_stop_cmd and preset_id:
        daemon_stop_cmd = str(ops_helpers._contract_daemon_defaults(preset_id, default_port).get("StopCommand") or "").strip()

    rows = ops_helpers._load_nodes()
    new_id = str(payload.get("id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}"
    if any(str(x.get("id") or "") == new_id for x in rows):
        return jsonify({"ok": False, "error": "node_id_exists", "message": f"节点ID已存在: {new_id}"}), 409

    node = ops_helpers._normalize_node(
        {
            "id": new_id,
            "name": name or f"{preset.get('name')}-{new_id[-4:]}",
            "base_url": str(payload.get("base_url") or "").strip(),
            "ops_base_url": str(payload.get("ops_base_url") or "").strip(),
            "ops_read_key": str(payload.get("ops_read_key") or "").strip(),
            "ops_write_key": str(payload.get("ops_write_key") or "").strip(),
            "ops_actor": str(payload.get("ops_actor") or "").strip(),
            "ops_role": str(payload.get("ops_role") or "SuperAdmin").strip(),
            "server_id": server_id or new_id,
            "project_id": project_id,
            "owner": owner,
            "role": str(preset.get("role") or "business"),
            "node_category": str(preset.get("category") or ""),
            "node_type": str(preset.get("node_type") or ""),
            "description": node_note or str(preset.get("default_desc") or ""),
            "biz_status": "normal",
            "allowed_upstream_roles": list(preset.get("fixed_upstream_roles") or []),
            "allowed_downstream_roles": list(preset.get("fixed_downstream_roles") or []),
            "daemon_profile": str(preset.get("daemon_profile") or ""),
            "daemon_start_cmd": daemon_start_cmd,
            "daemon_stop_cmd": daemon_stop_cmd,
            "env": env_key,
            "channel": channel,
            "enabled": True,
            "tags": [str(preset.get("category") or ""), str(preset.get("role") or "")],
        }
    )
    rows.append(node)
    ops_helpers._save_nodes(rows)
    ops_helpers._set_daemon_state(new_id, {"status": "ADDED", "last_action": "create", "last_error": "", "pid": 0})

    ctx = ops_helpers._resolve_topology_context(project_id, env_key, topology_id)
    registry = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    topo_edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    node_kind = ops_helpers._infer_node_kind(str(node.get("role") or "business"), str(preset.get("kind") or ""))
    if not any(isinstance(n, dict) and str(n.get("id") or "") == new_id for n in topo_nodes):
        x = float(payload.get("x") or 20)
        y = float(payload.get("y") or 20)
        remote_ui = {"port": default_port} if default_port > 0 else {}
        network_ui = {"endpoints": [f"127.0.0.1:{default_port}"]} if default_port > 0 else {}
        topo_nodes.append(
            {
                "id": new_id,
                "name": node.get("name") or new_id,
                "server_id": node.get("server_id") or new_id,
                "preset_id": preset_id,
                "role": node.get("role") or "business",
                "kind": node_kind,
                "desc": node.get("description") or "",
                "bizStatus": node.get("biz_status") or "normal",
                "owner": node.get("owner") or "",
                "daemon_profile": str(preset.get("daemon_profile") or ""),
                "daemon_start_cmd": daemon_start_cmd,
                "daemon_stop_cmd": daemon_stop_cmd,
                "daemon_port": default_port,
                "x": x,
                "y": y,
                "ui": {
                    "x": x,
                    "y": y,
                    "w": 220,
                    "h": 90,
                    "color": "#0f172a",
                    "ports": ops_helpers._normalize_ports(node_kind, (preset.get("default_ports") if isinstance(preset, dict) else None)),
                    "remote": remote_ui,
                    "network": network_ui,
                },
            }
        )
    for exist in topo_nodes:
        if not isinstance(exist, dict):
            continue
        eid = str(exist.get("id") or "")
        if not eid or eid == new_id:
            continue
        src = ops_helpers._resolve_node(node_id=eid) or {}
        if not src:
            continue
        if ops_helpers._can_link_nodes(src, node):
            exists = any(isinstance(e, dict) and str(e.get("from") or "") == eid and str(e.get("to") or "") == new_id for e in topo_edges)
            if not exists:
                topo_edges.append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": eid, "to": new_id, "from_port": "out-1", "to_port": "in-1", "type": "depends_on", "note": "preset-auto"})
        if ops_helpers._can_link_nodes(node, src):
            exists = any(isinstance(e, dict) and str(e.get("from") or "") == new_id and str(e.get("to") or "") == eid for e in topo_edges)
            if not exists:
                topo_edges.append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": new_id, "to": eid, "from_port": "out-1", "to_port": "in-1", "type": "depends_on", "note": "preset-auto"})
    topo["nodes"] = topo_nodes
    topo["edges"] = topo_edges
    saved_topo = ops_helpers._save_topology_scoped(
        str(registry.get("project_id") or project_id or ""),
        str(registry.get("env_key") or env_key or ""),
        str(registry.get("topology_id") or topology_id or ""),
        topo,
    )
    log_audit("ops_platform_node_add_from_preset", f"node={new_id}; preset={preset_id}")
    return jsonify({
        "ok": True,
        "message": "Node added",
        "node": node,
        "topology": {"nodes": saved_topo.get("nodes") or [], "edges": saved_topo.get("edges") or [], "meta": saved_topo.get("meta") or {}},
        "registry": saved_topo.get("registry") if isinstance(saved_topo.get("registry"), dict) else registry,
    })
















































































@bp.route("/api/ops-platform/node/daemon-action", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_node_daemon_action():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = ops_helpers._node_or_400(payload)
    if err:
        return err
    action = str(payload.get("action") or "status").strip().lower()
    ticket_id = str(payload.get("ticket_id") or "OPS-DAEMON").strip()
    reason = str(payload.get("reason") or "daemon action").strip()
    operator = str(session.get("user") or "intranet-ops")
    result = ops_helpers._ops_platform_daemon_action(node, action, reason, ticket_id, operator)
    ok = bool(result.get("success"))
    if ok:
        ops_helpers._append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": ops_helpers._now_iso(), "severity": "info", "status": "resolved", "title": f"守护进程动作: {action}", "message": f"node={node.get('id')}; {result.get('message')}", "node_id": node.get("id")})
    else:
        ops_helpers._append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": ops_helpers._now_iso(), "severity": "critical", "status": "open", "title": f"守护进程动作失败: {action}", "message": f"node={node.get('id')}; {result.get('message')}", "node_id": node.get("id")})
    log_audit("ops_platform_daemon_action", f"node={node.get('id')}; action={action}; ok={ok}")
    return jsonify({"ok": ok, "node": node.get("id"), "action": action, "message": str(result.get("message") or ""), "result": result}), (200 if ok else 502)




@bp.route("/api/ops-platform/node-onboarding")
@admin_required("gm_ops")
def ops_platform_node_onboarding():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    return jsonify(ops_helpers._build_node_onboarding(project_id=project_id))




@bp.route("/api/ops-platform/summary")
@admin_required("gm_ops")
def ops_platform_summary():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._resolve_ops_env_key(request.args.get("env_key") or "")
    from services.ops.cluster_health_bridge import enrich_overview

    overview = ops_helpers._build_overview(project_id=project_id, env_key=env_key)
    operator = str(session.get("user") or "intranet-ops")
    overview = enrich_overview(overview, operator=operator)
    nodes = overview.get("nodes") if isinstance(overview.get("nodes"), list) else []
    legacy_rows: List[Dict[str, Any]] = []
    for n in nodes:
        status_value = str(n.get("status") or "UNKNOWN")
        legacy_rows.append(
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "base_url": n.get("base_url"),
                "ops_base_url": n.get("ops_base_url"),
                "server_id": n.get("server_id"),
                "status": {
                    "success": status_value in ("ONLINE", "MAINTENANCE", "DEGRADED"),
                    "data": {
                        "status": status_value,
                        "cpu": n.get("cpu"),
                        "memoryMb": n.get("memory_mb"),
                        "diskUsagePercent": n.get("disk_percent"),
                    },
                    "message": status_value,
                },
                "ops_health": {
                    "success": bool(n.get("health_ok")),
                    "data": {"ready": n.get("ready_ok")},
                    "message": "OK" if n.get("health_ok") else "FAIL",
                },
            }
        )
    return jsonify({
        "ok": True,
        "count": len(legacy_rows),
        "nodes": legacy_rows,
        "summary": overview.get("summary"),
        "cluster_health": overview.get("cluster_health"),
    })



@bp.route("/api/ops-platform/action", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_action():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    form_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}

    mapped = {
        "agent_status": "health_check",
        "online": "start",
        "offline": "stop",
        "start_all": "start_all",
        "stop_all": "stop_all",
    }.get(action)

    if not mapped:
        return jsonify({"ok": False, "error": "unsupported action"}), 400

    req = {
        "node_id": payload.get("node_id") or "",
        "project_id": payload.get("project_id") or "",
        "env": payload.get("env") or "",
        "channel": payload.get("channel") or "",
        "action_type": mapped,
        "target": str(form_payload.get("serverId") or "").strip(),
        "ticket_id": str(form_payload.get("ticketId") or form_payload.get("ticket_id") or "OPS-COMPAT").strip(),
        "reason": str(form_payload.get("reason") or "compat action").strip(),
        "approver": str(form_payload.get("approver") or session.get("user") or "").strip(),
        "dry_run": bool(form_payload.get("dryRun") or form_payload.get("dry_run") or False),
        "payload": form_payload,
        "approval_id": str(form_payload.get("approval_id") or "").strip(),
    }

    node, err = ops_helpers._node_or_400(req)
    if err:
        return err

    validation = ops_helpers._validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing"), "message": "缺少必填字段"}), 400
    if validation.get("require_approval") and (not validation.get("dry_run")) and (not validation.get("approved")):
        return jsonify({"ok": False, "error": "approval required", "message": "High risk action requires approval"}), 412

    executed = ops_helpers._execute_validated(req, node, validation)
    result = executed.get("result") if isinstance(executed.get("result"), dict) else {}
    return jsonify({
        "ok": bool(executed.get("ok")),
        "node": node.get("id"),
        "action": action,
        "trace_id": executed.get("trace_id"),
        "message": executed.get("message"),
        "result": result,
    }), (200 if executed.get("ok") else 502)


@bp.route("/api/ops-platform/permissions")
@admin_required("gm_ops")
def ops_platform_permissions():
    """Return current user's ops scope for client-side permission gating."""
    can_view = ops_helpers._allow_ops_view()
    can_execute = ops_helpers._allow_ops_execute()
    return jsonify({
        "ok": True,
        "view": can_view,
        "execute": can_execute,
    })

