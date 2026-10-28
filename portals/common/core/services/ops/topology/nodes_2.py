def _normalize_ports(kind: str, ports: Any) -> Dict[str, List[Dict[str, Any]]]:
    defaults = _default_ports_for_kind(kind)
    if not isinstance(ports, dict):
        return defaults

    out: Dict[str, List[Dict[str, Any]]] = {"in": [], "out": []}
    for side in ("in", "out"):
        rows = ports.get(side) if isinstance(ports.get(side), list) else []
        for idx, p in enumerate(rows):
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or f"{side}-{idx+1}").strip()
            if not pid:
                pid = f"{side}-{idx+1}"
            out[side].append(
                {
                    "id": pid,
                    "label": str(p.get("label") or pid),
                    "kind": side,
                    "max_links": 1,
                    "required": bool(p.get("required", False)),
                }
            )
    if kind == "entry":
        out["in"] = []
        if not out["out"]:
            out["out"] = defaults["out"]
    elif kind == "terminal":
        out["out"] = []
        if not out["in"]:
            out["in"] = defaults["in"]
    else:
        if not out["in"]:
            out["in"] = defaults["in"]
        if not out["out"]:
            out["out"] = defaults["out"]
    return out


def _commercial_framework_core_edges() -> List[Dict[str, Any]]:
    """各规模模板共享的控制面与数据层连线（preset 级，应用时按实例展开）。"""
    return [
        {"from": "gateway_http", "to": "auth_service", "from_port": "out-1", "note": "http:80", "mode": "each_to_all"},
        {"from": "gateway_http", "to": "ops_service", "from_port": "out-2", "note": "http:443", "mode": "each_to_all"},
        {"from": "auth_service", "to": "business_main", "note": "tcp:session", "mode": "each_to_all"},
        {"from": "ops_service", "to": "business_main", "note": "tcp:control", "mode": "each_to_all"},
        {"from": "business_main", "to": "redis_cache", "note": "structured-auto", "mode": "each_to_all"},
        {"from": "business_main", "to": "mongo_db", "note": "structured-auto", "mode": "each_to_all"},
    ]


def _effective_node_kind(node: Dict[str, Any]) -> str:
    role = str((node or {}).get("role") or "business")
    explicit = str((node or {}).get("kind") or "").strip().lower()
    if explicit in ("entry", "standard", "terminal"):
        return explicit
    return _infer_node_kind(role, "")


def _ops_port_max(port: Dict[str, Any]) -> int:
    try:
        return max(1, int(port.get("max_links") or 1))
    except Exception:
        return 1


def _ops_port_link_count(edges: List[Dict[str, Any]], node_id: str, side: str, port_id: str) -> int:
    if side == "out":
        return len([e for e in edges if isinstance(e, dict) and str(e.get("from") or "") == node_id and str(e.get("from_port") or "out-1") == port_id])
    return len([e for e in edges if isinstance(e, dict) and str(e.get("to") or "") == node_id and str(e.get("to_port") or "in-1") == port_id])


def _ops_next_port_id(ports: List[Dict[str, Any]], side: str) -> str:
    prefix = "out" if side == "out" else "in"
    used = {str(p.get("id") or "") for p in ports if isinstance(p, dict)}
    idx = 1
    while f"{prefix}-{idx}" in used:
        idx += 1
    return f"{prefix}-{idx}"


def _ops_ensure_free_port(topo_node: Dict[str, Any], side: str, edges: List[Dict[str, Any]]) -> str:
    node_id = str(topo_node.get("id") or "")
    kind = _effective_node_kind(topo_node)
    ui = topo_node.get("ui") if isinstance(topo_node.get("ui"), dict) else {}
    ports_obj = _normalize_ports(kind, ui.get("ports"))
    rows = ports_obj.get(side) if isinstance(ports_obj.get(side), list) else []
    for port in rows:
        pid = str(port.get("id") or "")
        if pid and _ops_port_link_count(edges, node_id, side, pid) < _ops_port_max(port):
            ui["ports"] = ports_obj
            topo_node["ui"] = ui
            return pid
    max_ports = 8 if kind in ("entry", "terminal") else 6
    if len(rows) >= max_ports:
        return ""
    pid = _ops_next_port_id(rows, side)
    rows.append({"id": pid, "label": pid, "kind": side, "max_links": 1, "required": False})
    ports_obj[side] = rows
    ui["ports"] = ports_obj
    topo_node["ui"] = ui
    return pid


def _ops_structured_append_edge(topo: Dict[str, Any], frm: str, to: str) -> Tuple[bool, Dict[str, Any], int]:
    if not frm or not to or frm == to:
        return False, {"ok": False, "error": "invalid edge endpoints", "message": "连线起点或终点无效"}, 400
    node_map = _ops_topology_node_map(topo)
    edges = _ops_topology_edge_list(topo)
    fn = node_map.get(frm)
    tn = node_map.get(to)
    if not fn or not tn:
        return False, {"ok": False, "error": "node not found", "message": "节点不存在"}, 404
    if not _can_link_nodes(fn, tn):
        reason = _link_role_block_reason(fn, tn) or "当前节点角色规则不允许该连线"
        return False, {"ok": False, "error": "invalid_edge_by_role", "error_code": "OPS_EDGE_ROLE_FORBIDDEN", "message": reason}, 409
    fkind = _effective_node_kind(fn)
    tkind = _effective_node_kind(tn)
    if fkind == "terminal" or tkind == "entry":
        return False, {"ok": False, "error": "node_kind_violation", "error_code": "OPS_NODE_KIND_VIOLATION", "message": "节点语义方向不允许该连线"}, 409
    if any(isinstance(e, dict) and str(e.get("from") or "") == frm and str(e.get("to") or "") == to for e in edges):
        return False, {"ok": False, "error": "edge_duplicate", "error_code": "OPS_EDGE_DUPLICATE", "message": "两个节点之间已存在连线"}, 409
    from_port = _ops_ensure_free_port(fn, "out", edges)
    to_port = _ops_ensure_free_port(tn, "in", edges)
    if not from_port or not to_port:
        return False, {"ok": False, "error": "port_capacity_exceeded", "error_code": "OPS_PORT_CAPACITY_EXCEEDED", "message": "节点端口数量已达上限"}, 409
    tn_ui = tn.get("ui") if isinstance(tn.get("ui"), dict) else {}
    if tn_ui.get("list_only"):
        tn_ui = dict(tn_ui)
        tn_ui["list_only"] = False
        tn["ui"] = tn_ui
    edge = {"id": f"edge-{uuid.uuid4().hex[:10]}", "from": frm, "to": to, "from_port": from_port, "to_port": to_port, "type": "depends_on", "note": "structured-auto", "ui": {}}
    edges.append(edge)
    return True, edge, 200


def _can_reach_without_node(edges: List[Dict[str, Any]], src: str, dst: str, blocked: str) -> bool:
    if src == dst:
        return True
    graph: Dict[str, List[str]] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        a = str(e.get("from") or "")
        b = str(e.get("to") or "")
        if not a or not b or a == blocked or b == blocked:
            continue
        graph.setdefault(a, []).append(b)
    seen = set([src])
    queue = [src]
    while queue:
        cur = queue.pop(0)
        for nxt in graph.get(cur, []):
            if nxt in seen:
                continue
            if nxt == dst:
                return True
            seen.add(nxt)
            queue.append(nxt)
    return False
