def _save_topology_scoped(project_id: str, env_key: str, topology_id: str, topology: Dict[str, Any]) -> Dict[str, Any]:
    ctx = _resolve_topology_context(project_id, env_key, topology_id)
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    tid = str(row.get("topology_id") or topology_id or "").strip()
    normalized = _load_topology_scoped(str(row.get("project_id") or project_id or ""), str(row.get("env_key") or env_key or ""), tid)
    incoming_nodes = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
    incoming_edges = topology.get("edges") if isinstance(topology.get("edges"), list) else []
    incoming_meta = topology.get("meta") if isinstance(topology.get("meta"), dict) else {}
    replace_all = bool(incoming_meta.get("runtime_topology") or incoming_meta.get("replace_all"))

    node_index: Dict[str, Any] = {}
    if not replace_all:
        node_index = {str(x.get("id") or ""): x for x in (normalized.get("nodes") or []) if isinstance(x, dict)}
    for item in incoming_nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid:
            continue
        src = node_index.get(nid) or {
            "id": nid,
            "name": str(item.get("name") or nid),
            "server_id": str(item.get("server_id") or nid),
            "project_id": str(row.get("project_id") or project_id or ""),
            "env": str(row.get("env_key") or env_key or "production"),
            "role": "business",
            "kind": "standard",
            "desc": "",
            "bizStatus": "normal",
            "owner": "",
            "tags": [],
            "ui": {},
            "x": 0.0,
            "y": 0.0,
        }
        src["name"] = str(item.get("name") or src.get("name") or nid)
        src["server_id"] = str(item.get("server_id") or src.get("server_id") or nid)
        src["role"] = str(item.get("role") or src.get("role") or "business")
        src["kind"] = _infer_node_kind(str(src.get("role") or "business"), str(item.get("kind") or src.get("kind") or ""))
        src["desc"] = str(item.get("desc") or src.get("desc") or "")
        src["bizStatus"] = str(item.get("bizStatus") or src.get("bizStatus") or "normal")
        src["owner"] = str(item.get("owner") or src.get("owner") or "")
        src["node_category"] = str(item.get("node_category") or src.get("node_category") or "")
        src["node_type"] = str(item.get("node_type") or src.get("node_type") or "")
        src["tags"] = item.get("tags") if isinstance(item.get("tags"), list) else (src.get("tags") if isinstance(src.get("tags"), list) else [])
        for field in (
            "preset_id", "daemon_profile", "daemon_start_cmd", "daemon_stop_cmd", "group", "notes",
        ):
            if field in item:
                src[field] = item.get(field)
        if "daemon_port" in item:
            try:
                src["daemon_port"] = int(item.get("daemon_port") or 0)
            except Exception:
                pass
        src["ui"] = item.get("ui") if isinstance(item.get("ui"), dict) else (src.get("ui") if isinstance(src.get("ui"), dict) else {})
        src["ui"]["ports"] = _normalize_ports(str(src.get("kind") or "standard"), src["ui"].get("ports"))
        try:
            src["x"] = float(item.get("x"))
        except Exception:
            pass
        try:
            src["y"] = float(item.get("y"))
        except Exception:
            pass
        src["project_id"] = str(row.get("project_id") or project_id or "")
        src["env"] = str(row.get("env_key") or env_key or "production")
        node_index[nid] = src

    valid_ids = set(node_index.keys())
    merged_edges: List[Dict[str, Any]] = []
    for edge in incoming_edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to or frm == to or frm not in valid_ids or to not in valid_ids:
            continue
        merged_edges.append(
            {
                "id": str(edge.get("id") or f"edge-{uuid.uuid4().hex[:10]}"),
                "from": frm,
                "to": to,
                "from_port": str(edge.get("from_port") or "out-1"),
                "to_port": str(edge.get("to_port") or "in-1"),
                "type": str(edge.get("type") or "depends_on"),
                "note": str(edge.get("note") or ""),
                "ui": edge.get("ui") if isinstance(edge.get("ui"), dict) else {},
            }
        )
    viewport = incoming_meta.get("viewport") if isinstance(incoming_meta.get("viewport"), dict) else {}
    prev_meta = normalized.get("meta") if isinstance(normalized.get("meta"), dict) else {}
    spacing = incoming_meta.get("layout_spacing") if isinstance(incoming_meta.get("layout_spacing"), dict) else prev_meta.get("layout_spacing")
    spacing_customized = bool(
        incoming_meta.get("layout_spacing_customized")
        if "layout_spacing_customized" in incoming_meta
        else prev_meta.get("layout_spacing_customized")
    )
    if isinstance(incoming_meta.get("layout_spacing"), dict):
        spacing_customized = True
    meta_out: Dict[str, Any] = {
        "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
        "version": int(incoming_meta.get("version") or prev_meta.get("version") or 1),
        "updated_at": _now_iso(),
        "layout_mode": str(incoming_meta.get("layout_mode") or prev_meta.get("layout_mode") or "structured"),
        "layout_locked": bool(incoming_meta.get("layout_locked") if "layout_locked" in incoming_meta else prev_meta.get("layout_locked")),
        "design_reference": str(incoming_meta.get("design_reference") or prev_meta.get("design_reference") or ""),
        "runtime_topology": bool(incoming_meta.get("runtime_topology") or prev_meta.get("runtime_topology")),
        "cluster_source": bool(incoming_meta.get("cluster_source") or prev_meta.get("cluster_source")),
        "description": str(incoming_meta.get("description") or prev_meta.get("description") or ""),
    }
    if spacing_customized:
        meta_out["layout_spacing"] = _normalize_layout_spacing(spacing)
        meta_out["layout_spacing_customized"] = True
    payload = {
        "nodes": list(node_index.values()),
        "edges": merged_edges,
        "meta": meta_out,
        "updated_at": _now_iso(),
    }
    contents = _load_topology_contents()
    contents[tid] = payload
    _save_topology_contents(contents)

    rows = _load_topology_registry()
    for idx, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        if str(item.get("topology_id") or "") != tid:
            continue
        merged = _normalize_topology_registry_row(item)
        merged["updated_at"] = _now_iso()
        rows[idx] = merged
        break
    _save_topology_registry(rows)
    saved = dict(payload)
    saved["registry"] = _resolve_topology_context(str(row.get("project_id") or ""), str(row.get("env_key") or ""), tid).get("row")
    return saved


def _topology_gateway_node(project_id: str = "", env_key: str = "") -> Dict[str, Any]:
    return (
        _resolve_node(project_id=str(project_id or "").strip(), env=_normalize_env_key(env_key))
        or _resolve_node(project_id=str(project_id or "").strip())
        or _resolve_node()
        or {}
    )


def _build_runtime_node_from_topology_node(project_id: str, env_key: str, topo_node: Dict[str, Any], topology_id: str = "") -> Dict[str, Any]:
    base = dict(_topology_gateway_node(project_id, env_key))
    node = topo_node if isinstance(topo_node, dict) else {}
    node_id = str(node.get("id") or "").strip()
    base["id"] = node_id
    base["name"] = str(node.get("name") or node_id or base.get("name") or "")
    base["project_id"] = str(project_id or base.get("project_id") or "")
    base["env"] = _normalize_env_key(env_key or node.get("env") or base.get("env") or "")
    base["server_id"] = str(node.get("server_id") or node_id or base.get("server_id") or "")
    base["owner"] = str(node.get("owner") or base.get("owner") or "")
    base["role"] = str(node.get("role") or base.get("role") or "business")
    base["description"] = str(node.get("desc") or node.get("description") or base.get("description") or "")
    base["topology_id"] = str(topology_id or "")
    base["preset_id"] = str(node.get("preset_id") or "").strip()
    base["daemon_profile"] = str(node.get("daemon_profile") or "").strip()
    base["daemon_start_cmd"] = str(node.get("daemon_start_cmd") or "").strip()
    base["daemon_stop_cmd"] = str(node.get("daemon_stop_cmd") or "").strip()
    if node.get("daemon_port") is not None:
        base["daemon_port"] = int(node.get("daemon_port") or 0)
    contract = _resolve_node_contract_for_topology_node(node)
    port = _resolve_topology_node_port(node, contract, None, None)
    if port > 0:
        base["port"] = port
    preset_id = str(node.get("preset_id") or contract.get("preset_id") or "").strip()
    if preset_id and (not base.get("daemon_start_cmd") or not base.get("daemon_stop_cmd")):
        daemon_defaults = _contract_daemon_defaults(preset_id, port)
        if not base.get("daemon_start_cmd"):
            base["daemon_start_cmd"] = _format_contract_command(str(daemon_defaults.get("StartCommand") or ""), port)
        if not base.get("daemon_stop_cmd"):
            base["daemon_stop_cmd"] = _format_contract_command(str(daemon_defaults.get("StopCommand") or ""), port)
    if preset_id == "mongo_db" and base.get("daemon_start_cmd"):
        mongo_dbpath = _gomeku_mongo_dbpath()
        os.makedirs(mongo_dbpath, exist_ok=True)
    return base


def _sync_topology_to_game_server(project_id: str, env_key: str, topology_id: str, actor: str) -> Dict[str, Any]:
    gateway_node = _topology_gateway_node(project_id, env_key)
    if not gateway_node:
        return {"ok": False, "error": "missingops_gateway_node", "message": "未找到可用的 Ops 网关节点"}
    payload = _topology_to_cluster_payload(project_id, env_key, topology_id)
    result = ops_gateway.apply_topology(
        gateway_node,
        payload=payload,
        actor=actor,
        reason="topology save sync",
        ticket_id="OPS-TOPO-" + uuid.uuid4().hex[:8],
    )
    return {
        "ok": bool(result.get("success")),
        "message": str(result.get("message") or ""),
        "status": int(result.get("status") or 0),
        "data": result.get("data") if isinstance(result.get("data"), dict) else {},
        "payload": payload,
    }


def _binding_fallback_topology_ids(project_id: str = "", env_key: str = "", topology_id: str = "") -> List[str]:
    tid = str(topology_id or "").strip()
    out: List[str] = []
    for candidate in (
        tid,
        _runtime_default_topology_id(project_id, env_key),
        "topology-gomeku-production-default",
        "topology-design-gomeku-production",
    ):
        c = str(candidate or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def _repair_runtime_topology_edges(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    meta: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    meta = meta if isinstance(meta, dict) else {}
    if not meta.get("runtime_topology"):
        return edges
    valid_ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict) and str(n.get("id") or "")}
    if not {"gateway-cn-1", "ops-cn-1", "game-cn-1"}.issubset(valid_ids):
        return edges
    existing = {(str(e.get("from") or ""), str(e.get("to") or "")) for e in edges if isinstance(e, dict)}
    out = list(edges)
    for frm, to, note in _RUNTIME_TOPOLOGY_EDGE_SPECS:
        if frm not in valid_ids or to not in valid_ids or (frm, to) in existing:
            continue
        out.append({
            "id": f"edge-{frm}-{to}",
            "from": frm,
            "to": to,
            "from_port": "out-1",
            "to_port": "in-1",
            "type": "depends_on",
            "note": note,
        })
        existing.add((frm, to))
    for frm, to, note in _RUNTIME_INFRA_EDGE_SPECS:
        if frm not in valid_ids or to not in valid_ids or (frm, to) in existing:
            continue
        out.append({
            "id": f"edge-{frm}-{to}",
            "from": frm,
            "to": to,
            "from_port": "out-1",
            "to_port": "in-1",
            "type": "depends_on",
            "note": note,
        })
        existing.add((frm, to))
    return out


def _resolve_topology_probe_port(
    node: Dict[str, Any],
    contract: Dict[str, Any],
    service: Optional[Dict[str, Any]] = None,
    agent: Optional[Dict[str, Any]] = None,
) -> int:
    if _is_embedded_topology_node(node, contract):
        return 0
    return _resolve_topology_node_port(node, contract, service, agent)


def _default_topology_for_nodes(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    out_nodes: List[Dict[str, Any]] = []
    out_edges: List[Dict[str, Any]] = []
    total = max(1, len(nodes))
    cols = max(3, min(5, int((total ** 0.5) + 0.8)))
    for idx, n in enumerate(nodes):
        row = idx // cols
        col = idx % cols
        kind = _infer_node_kind(str(n.get("role") or ""), str(n.get("kind") or ""))
        out_nodes.append(
            {
                "id": str(n.get("id") or ""),
                "role": str(n.get("role") or "business"),
                "kind": kind,
                "desc": str(n.get("description") or ""),
                "bizStatus": str(n.get("biz_status") or "normal"),
                "owner": str(n.get("owner") or ""),
                "x": int(26 + col * 185),
                "y": int(26 + row * 132),
                "tags": n.get("tags") if isinstance(n.get("tags"), list) else [],
                "ui": {
                    "x": int(26 + col * 185),
                    "y": int(26 + row * 132),
                    "w": 220,
                    "h": 90,
                    "color": "#0f172a",
                    "locked": False,
                    "ports": _normalize_ports(kind, None),
                },
            }
        )
    for i in range(max(0, len(out_nodes) - 1)):
        frm = out_nodes[i].get("id")
        to = out_nodes[i + 1].get("id")
        if frm and to:
            out_edges.append(
                {
                    "id": f"edge-{uuid.uuid4().hex[:10]}",
                    "from": frm,
                    "to": to,
                    "from_port": "out-1",
                    "to_port": "in-1",
                    "type": "depends_on",
                    "note": "",
                }
            )
    return {"nodes": out_nodes, "edges": out_edges, "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}}}
