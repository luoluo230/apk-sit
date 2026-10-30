# -*- coding: utf-8 -*-
"""Topology graph edits: preset nodes, edges, and deletes.

Routes keep permission checks. The graph change itself lives here.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

from models.data import log_audit
from services.ops import runtime_orchestrator as runtime
from services.ops import topology_registry as topo


def _topology_view(saved: Dict[str, Any], registry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "topology": {
            "nodes": saved.get("nodes") or [],
            "edges": saved.get("edges") or [],
            "meta": saved.get("meta") or {},
        },
        "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry,
    }


def add_node_from_preset(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    preset_id = str(payload.get("preset_id") or "").strip()
    name = str(payload.get("name") or "").strip()
    server_id = str(payload.get("server_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = topo._normalize_env_key(payload.get("env_key") or payload.get("env") or "production")
    topology_id = str(payload.get("topology_id") or "").strip()
    channel = str(payload.get("channel") or "").strip()
    owner = str(payload.get("owner") or "").strip()
    node_note = str(payload.get("description") or "").strip()
    daemon_start_cmd = str(payload.get("daemon_start_cmd") or "").strip()
    daemon_stop_cmd = str(payload.get("daemon_stop_cmd") or "").strip()

    presets = topo._load_node_presets()
    preset = None
    for item in presets:
        if str(item.get("preset_id") or "") == preset_id:
            preset = item
            break
    if not preset:
        return {"ok": False, "error": "preset_not_found"}, 404

    contract = topo._load_node_contract(preset_id) or {}
    default_port = int(preset.get("default_port") or contract.get("default_port") or 0)
    if not daemon_start_cmd and preset_id:
        daemon_start_cmd = str(topo._contract_daemon_defaults(preset_id, default_port).get("StartCommand") or "").strip()
    if not daemon_stop_cmd and preset_id:
        daemon_stop_cmd = str(topo._contract_daemon_defaults(preset_id, default_port).get("StopCommand") or "").strip()

    rows = topo._load_nodes()
    new_id = str(payload.get("id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}"
    if any(str(x.get("id") or "") == new_id for x in rows):
        return {"ok": False, "error": "node_id_exists", "message": f"节点ID已存在: {new_id}"}, 409

    node = topo._normalize_node(
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
    topo._save_nodes(rows)
    runtime._set_daemon_state(new_id, {"status": "ADDED", "last_action": "create", "last_error": "", "pid": 0})

    ctx = topo._resolve_topology_context(project_id, env_key, topology_id)
    registry = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    graph = topo._load_topology_scoped(project_id, env_key, topology_id)
    topo_nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    topo_edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    node_kind = topo._infer_node_kind(str(node.get("role") or "business"), str(preset.get("kind") or ""))
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
                    "ports": topo._normalize_ports(node_kind, (preset.get("default_ports") if isinstance(preset, dict) else None)),
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
        src = topo._resolve_node(node_id=eid) or {}
        if not src:
            continue
        if topo._can_link_nodes(src, node):
            exists = any(
                isinstance(e, dict) and str(e.get("from") or "") == eid and str(e.get("to") or "") == new_id
                for e in topo_edges
            )
            if not exists:
                topo_edges.append({
                    "id": f"edge-{uuid.uuid4().hex[:10]}",
                    "from": eid,
                    "to": new_id,
                    "from_port": "out-1",
                    "to_port": "in-1",
                    "type": "depends_on",
                    "note": "preset-auto",
                })
        if topo._can_link_nodes(node, src):
            exists = any(
                isinstance(e, dict) and str(e.get("from") or "") == new_id and str(e.get("to") or "") == eid
                for e in topo_edges
            )
            if not exists:
                topo_edges.append({
                    "id": f"edge-{uuid.uuid4().hex[:10]}",
                    "from": new_id,
                    "to": eid,
                    "from_port": "out-1",
                    "to_port": "in-1",
                    "type": "depends_on",
                    "note": "preset-auto",
                })
    graph["nodes"] = topo_nodes
    graph["edges"] = topo_edges
    saved = topo._save_topology_scoped(
        str(registry.get("project_id") or project_id or ""),
        str(registry.get("env_key") or env_key or ""),
        str(registry.get("topology_id") or topology_id or ""),
        graph,
    )
    log_audit("ops_platform_node_add_from_preset", f"node={new_id}; preset={preset_id}")
    body = {"ok": True, "message": "Node added", "node": node}
    body.update(_topology_view(saved, registry))
    return body, 200


def upsert_edge(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    project_id = str(payload.get("project_id") or "").strip()
    env_key = topo._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    frm = str(payload.get("from") or "").strip()
    to = str(payload.get("to") or "").strip()
    from_port = str(payload.get("from_port") or "out-1").strip()
    to_port = str(payload.get("to_port") or "in-1").strip()
    etype = str(payload.get("type") or "depends_on").strip()
    note = str(payload.get("note") or "").strip()
    if not frm or not to or frm == to:
        return {"ok": False, "error": "invalid edge endpoints"}, 400

    graph = topo._load_topology_scoped(project_id, env_key, topology_id)
    registry = graph.get("registry") if isinstance(graph.get("registry"), dict) else {}
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    graph["edges"] = edges
    valid = {str(x.get("id") or "") for x in graph.get("nodes") or [] if isinstance(x, dict)}
    if frm not in valid or to not in valid:
        return {"ok": False, "error": "node not found"}, 404
    topo_nodes = {str(x.get("id") or ""): x for x in (graph.get("nodes") or []) if isinstance(x, dict)}
    fn = topo_nodes.get(frm) or {}
    tn = topo_nodes.get(to) or {}
    if not topo._can_link_nodes(fn, tn):
        return {
            "ok": False,
            "error": "invalid_edge_by_role",
            "error_code": "OPS_EDGE_ROLE_FORBIDDEN",
            "message": "当前节点角色规则不允许该连线",
        }, 409
    fkind = str(fn.get("kind") or topo._infer_node_kind(str(fn.get("role") or ""), ""))
    tkind = str(tn.get("kind") or topo._infer_node_kind(str(tn.get("role") or ""), ""))
    if fkind == "terminal" or tkind == "entry":
        return {
            "ok": False,
            "error": "node_kind_violation",
            "error_code": "OPS_NODE_KIND_VIOLATION",
            "message": "Node kind direction is not allowed",
        }, 400
    fports = topo._normalize_ports(fkind, ((fn.get("ui") or {}).get("ports") if isinstance(fn.get("ui"), dict) else None))
    tports = topo._normalize_ports(tkind, ((tn.get("ui") or {}).get("ports") if isinstance(tn.get("ui"), dict) else None))
    if from_port not in [str(p.get("id") or "") for p in fports.get("out", [])] or to_port not in [str(p.get("id") or "") for p in tports.get("in", [])]:
        return {"ok": False, "error": "port_not_found", "error_code": "OPS_PORT_NOT_FOUND", "message": "Port not found"}, 400
    for ex in edges:
        if not isinstance(ex, dict):
            continue
        if (
            str(ex.get("from") or "") == frm
            and str(ex.get("to") or "") == to
            and str(ex.get("from_port") or "out-1") == from_port
            and str(ex.get("to_port") or "in-1") == to_port
        ):
            return {"ok": False, "error": "edge_duplicate", "error_code": "OPS_EDGE_DUPLICATE", "message": "Duplicate edge"}, 409
    incoming_count = 0
    for ex in edges:
        if isinstance(ex, dict) and str(ex.get("to") or "") == to and str(ex.get("to_port") or "in-1") == to_port:
            incoming_count += 1
    in_max = 1
    for port in tports.get("in", []):
        if str(port.get("id") or "") == to_port:
            in_max = int(port.get("max_links") or 1)
            break
    if incoming_count >= in_max:
        return {
            "ok": False,
            "error": "port_capacity_exceeded",
            "error_code": "OPS_PORT_CAPACITY_EXCEEDED",
            "message": "Input port capacity exceeded",
        }, 409
    outgoing_count = 0
    for ex in edges:
        if isinstance(ex, dict) and str(ex.get("from") or "") == frm and str(ex.get("from_port") or "out-1") == from_port:
            outgoing_count += 1
    out_max = 1
    for port in fports.get("out", []):
        if str(port.get("id") or "") == from_port:
            out_max = int(port.get("max_links") or 1)
            break
    if outgoing_count >= out_max:
        return {
            "ok": False,
            "error": "port_capacity_exceeded",
            "error_code": "OPS_PORT_CAPACITY_EXCEEDED",
            "message": "Output port capacity exceeded",
        }, 409

    updated = False
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if (
            str(edge.get("from") or "") == frm
            and str(edge.get("to") or "") == to
            and str(edge.get("from_port") or "out-1") == from_port
            and str(edge.get("to_port") or "in-1") == to_port
        ):
            edge["type"] = etype
            edge["note"] = note
            updated = True
            break
    if not updated:
        edges.append({
            "id": f"edge-{uuid.uuid4().hex[:10]}",
            "from": frm,
            "to": to,
            "from_port": from_port,
            "to_port": to_port,
            "type": etype,
            "note": note,
        })

    saved = topo._save_topology_scoped(
        str(registry.get("project_id") or project_id or ""),
        str(registry.get("env_key") or env_key or ""),
        str(registry.get("topology_id") or topology_id or ""),
        graph,
    )
    log_audit("ops_platform_topology_edge_upsert", f"{frm}->{to}; type={etype}")
    body = {"ok": True, "message": "连线已保存"}
    body.update(_topology_view(saved, registry))
    return body, 200
