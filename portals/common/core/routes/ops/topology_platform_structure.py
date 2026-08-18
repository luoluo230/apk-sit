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


