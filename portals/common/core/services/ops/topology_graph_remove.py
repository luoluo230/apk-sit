# -*- coding: utf-8 -*-
"""Remove topology nodes and edges."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from models.data import log_audit
from services.ops import topology_registry as topo
from services.ops.topology_graph import _topology_view


def delete_edge(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    project_id = str(payload.get("project_id") or "").strip()
    env_key = topo._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    edge_id = str(payload.get("edge_id") or "").strip()
    if not edge_id:
        return {"ok": False, "error": "missing edge_id"}, 400

    graph = topo._load_topology_scoped(project_id, env_key, topology_id)
    registry = graph.get("registry") if isinstance(graph.get("registry"), dict) else {}
    if topo._is_critical_topology_edge(graph, edge_id):
        return {
            "ok": False,
            "error": "edge_delete_blocked",
            "error_code": "OPS_EDGE_DELETE_BLOCKED",
            "message": "关键链路连线不可删除（会导致架构断裂）",
        }, 409
    before = len(graph.get("edges") or [])
    graph["edges"] = [
        x for x in (graph.get("edges") or [])
        if not (isinstance(x, dict) and str(x.get("id") or "") == edge_id)
    ]
    after = len(graph.get("edges") or [])
    if after == before:
        return {"ok": False, "error": "edge not found"}, 404
    saved = topo._save_topology_scoped(
        str(registry.get("project_id") or project_id or ""),
        str(registry.get("env_key") or env_key or ""),
        str(registry.get("topology_id") or topology_id or ""),
        graph,
    )
    log_audit("ops_platform_topology_edge_delete", f"edge={edge_id}")
    body = {"ok": True, "message": "Edge deleted"}
    body.update(_topology_view(saved, registry))
    return body, 200


def delete_node(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    project_id = str(payload.get("project_id") or "").strip()
    env_key = topo._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return {"ok": False, "error": "missing node_id"}, 400

    graph = topo._load_topology_scoped(project_id, env_key, topology_id)
    registry = graph.get("registry") if isinstance(graph.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node_ids = {str(x.get("id") or "") for x in (graph.get("nodes") or []) if isinstance(x, dict)}
    if node_id not in node_ids:
        return {"ok": False, "error": "node not found"}, 404
    if topo._is_critical_topology_node(graph, node_id):
        return {
            "ok": False,
            "error": "node_delete_blocked",
            "error_code": "OPS_NODE_DELETE_BLOCKED",
            "message": "Critical node cannot be deleted",
        }, 409

    before_edges = len(graph.get("edges") or [])
    graph["nodes"] = [
        x for x in (graph.get("nodes") or [])
        if not (isinstance(x, dict) and str(x.get("id") or "") == node_id)
    ]
    graph["edges"] = [
        x for x in (graph.get("edges") or [])
        if not (
            isinstance(x, dict)
            and (str(x.get("from") or "") == node_id or str(x.get("to") or "") == node_id)
        )
    ]
    meta = dict(graph.get("meta") or {})
    meta["replace_all"] = True
    graph["meta"] = meta
    saved = topo._save_topology_scoped(
        str(registry.get("project_id") or project_id or ""),
        str(registry.get("env_key") or env_key or ""),
        tid,
        graph,
    )

    bindings = topo._load_scope_agent_bindings(tid)
    if node_id in bindings:
        bindings.pop(node_id, None)
        topo._save_scope_agent_binding(tid, node_id, "")
    service_bindings = topo._load_scope_service_bindings(tid)
    if node_id in service_bindings:
        service_bindings.pop(node_id, None)
        topo._save_scope_service_binding(tid, node_id, "")

    log_audit(
        "ops_platform_topology_node_delete",
        f"node={node_id}; removed_edges={before_edges - len(saved.get('edges') or [])}",
    )
    body = {
        "ok": True,
        "message": "Node deleted",
        "bindings": bindings,
        "service_bindings": service_bindings,
    }
    body.update(_topology_view(saved, registry))
    return body, 200
