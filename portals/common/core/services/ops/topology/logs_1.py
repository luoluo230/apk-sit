def _is_design_demo_topology_row(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("design_demo_node_count") is not None:
        return True
    tid = str(row.get("topology_id") or "").strip()
    if tid.startswith("topology-design-"):
        return True
    desc = str(row.get("description") or "").strip()
    if "设计稿 demo" in desc or desc == "设计稿 demo 拓扑":
        return True
    return False


def _purge_design_demo_topology_registry(project_id: str = "") -> Dict[str, int]:
    """Remove seeded design-demo topology registry rows and contents."""
    pid = str(project_id or "").strip()
    rows = _load_topology_registry()
    if not isinstance(rows, list):
        return {"removed_registry": 0, "removed_contents": 0}
    kept: List[Dict[str, Any]] = []
    removed_ids: List[str] = []
    for item in rows:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        row = _normalize_topology_registry_row(item)
        if pid and str(row.get("project_id") or "") != pid:
            kept.append(row)
            continue
        if _is_design_demo_topology_row(row):
            removed_ids.append(str(row.get("topology_id") or ""))
            continue
        kept.append(row)
    removed_registry = len(rows) - len(kept)
    if removed_registry:
        _save_topology_registry(kept)
    contents = _load_topology_contents()
    removed_contents = 0
    for tid in removed_ids:
        if tid and tid in contents:
            contents.pop(tid, None)
            removed_contents += 1
    if removed_contents:
        _save_topology_contents(contents)
    if pid and removed_registry:
        for tid in removed_ids:
            _purge_design_demo_project_state(pid, tid)
    return {"removed_registry": removed_registry, "removed_contents": removed_contents}


def _normalize_topology_registry_row(row: Dict[str, Any]) -> Dict[str, Any]:
    item = row if isinstance(row, dict) else {}
    env_key = _normalize_env_key(item.get("env_key"))
    topology_id = str(item.get("topology_id") or "").strip() or ("topology-" + uuid.uuid4().hex[:10])
    disabled = bool(item.get("disabled", False))
    raw_status = str(item.get("status") or "draft").strip().lower()
    if disabled and raw_status not in ("archived",):
        effective_status = "disabled"
    else:
        effective_status = raw_status
    out = {
        "topology_id": topology_id,
        "project_id": str(item.get("project_id") or "").strip(),
        "env_key": env_key,
        "env_label": _env_label(env_key),
        "name": str(item.get("name") or topology_id).strip(),
        "version_label": str(item.get("version_label") or "").strip(),
        "owner": str(item.get("owner") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "icon_url": str(item.get("icon_url") or "").strip() or "/static/project_ui/svg/nav_topology.svg",
        "disabled": disabled,
        "blueprint_id": str(item.get("blueprint_id") or "").strip(),
        "copied_from_topology_id": str(item.get("copied_from_topology_id") or "").strip(),
        "is_default": bool(item.get("is_default", False)),
        "status": effective_status,
        "registry_status": raw_status,
        "created_at": str(item.get("created_at") or _now_iso()),
        "updated_at": str(item.get("updated_at") or item.get("created_at") or _now_iso()),
    }
    nc, ec = _topology_content_counts(topology_id)
    if item.get("design_demo_node_count") is not None:
        out["design_demo_node_count"] = int(item.get("design_demo_node_count") or 0)
        out["design_demo_edge_count"] = int(item.get("design_demo_edge_count") or 0)
        out["node_count"] = out["design_demo_node_count"]
        out["edge_count"] = out["design_demo_edge_count"]
    elif nc or ec:
        out["node_count"] = nc
        out["edge_count"] = ec
    elif item.get("node_count") is not None:
        out["node_count"] = int(item.get("node_count") or 0)
        out["edge_count"] = int(item.get("edge_count") or 0)
    else:
        out["node_count"] = 5
        out["edge_count"] = 6
    return out


def _design_reference_topology_content(project_id: str = "", env_key: str = "production") -> Dict[str, Any]:
    """设计稿标准 6 节点 demo 拓扑：Gateway / Auth / Ops / Game / TCP Transport / Database。"""
    gateway_ports = {
        "in": [],
        "out": [
            {"id": "out-1", "label": "http:80", "kind": "out", "max_links": 1},
            {"id": "out-2", "label": "http:443", "kind": "out", "max_links": 1},
        ],
    }

    def _node(
        node_id: str,
        name: str,
        role: str,
        desc: str,
        x: int,
        y: int,
        color: str,
        kind: str = "",
        tags: Optional[List[str]] = None,
        ports: Optional[Dict[str, Any]] = None,
        owner: str = "",
        group: str = "",
        list_only: bool = False,
        remote_port: int = 0,
        endpoints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        k = kind or _infer_node_kind(role, "")
        ui_ports = ports if isinstance(ports, dict) else _normalize_ports(k, None)
        ui: Dict[str, Any] = {
            "x": x,
            "y": y,
            "w": 220,
            "h": 108,
            "color": color,
            "locked": False,
            "ports": ui_ports,
            "list_only": bool(list_only),
        }
        if remote_port:
            ui["remote"] = {"port": int(remote_port)}
        if endpoints:
            ui["network"] = {"endpoints": list(endpoints)}
        return {
            "id": node_id,
            "name": name,
            "server_id": node_id,
            "project_id": str(project_id or ""),
            "env": _normalize_env_key(env_key) or "production",
            "role": role,
            "kind": k,
            "desc": desc,
            "bizStatus": "normal",
            "owner": str(owner or ""),
            "group": str(group or ""),
            "x": float(x),
            "y": float(y),
            "tags": tags if isinstance(tags, list) else [],
            "ui": ui,
        }

    nodes = [
        _node("gateway-01", "Gateway", "gateway", "网关服务", 72, 48, "#1890ff", "entry", ports=gateway_ports),
        _node("auth-01", "Auth", "auth", "认证服务", 72, 248, "#52c41a"),
        _node("ops-01", "Ops", "admin", "运维服务", 320, 248, "#faad14"),
        _node(
            "game-01", "Game", "business",
            "核心游戏逻辑服务节点。处理玩家会话与游戏逻辑。",
            560, 128, "#722ed1", "game",
            tags=["business", "core"], owner="运维团队", group="游戏服务",
            remote_port=9501, endpoints=["10.0.1.15:9501"],
        ),
        _node("tcp-01", "TCP Transport", "transport", "传输服务", 820, 328, "#f5222d", "terminal"),
        _node("db-01", "Database", "database", "Mongo 主存储", 560, 280, "#13c2c2", tags=["storage"]),
    ]
    edges = [
        {"id": "edge-gw-auth", "from": "gateway-01", "to": "auth-01", "from_port": "out-1", "to_port": "in-1", "type": "http", "note": "http:80"},
        {"id": "edge-gw-ops", "from": "gateway-01", "to": "ops-01", "from_port": "out-2", "to_port": "in-1", "type": "http", "note": "http:443"},
        {"id": "edge-auth-game", "from": "auth-01", "to": "game-01", "from_port": "out-1", "to_port": "in-1", "type": "tcp", "note": "tcp:5501"},
        {"id": "edge-ops-game", "from": "ops-01", "to": "game-01", "from_port": "out-1", "to_port": "in-1", "type": "tcp", "note": "tcp:5512"},
        {"id": "edge-game-tcp", "from": "game-01", "to": "tcp-01", "from_port": "out-1", "to_port": "in-1", "type": "tcp", "note": "tcp:9512"},
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "layout_mode": "structured",
            "layout_locked": False,
            "design_reference": "v4",
            "layout_spacing": {"rank_gap": 268, "row_gap": 128},
            "updated_at": _now_iso(),
        },
    }


def _topology_has_design_demo_nodes(topo: Any) -> bool:
    if not isinstance(topo, dict):
        return False
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
    return bool(ids & _DESIGN_DEMO_NODE_IDS)


def _ensure_runtime_topology_bindings(topology_id: str, node_ids: List[str]) -> None:
    tid = str(topology_id or "").strip()
    if not tid:
        return
    agent_store = _load_node_agent_bindings()
    service_store = _load_node_service_bindings()
    agent_changed = False
    service_changed = False
    for raw_nid in node_ids or []:
        node_id = str(raw_nid or "").strip()
        if not node_id:
            continue
        agent_key = _scope_binding_key(tid, node_id)
        if str(agent_store.get(agent_key) or "").strip() != CANONICAL_LOCAL_AGENT_ID:
            agent_store[agent_key] = CANONICAL_LOCAL_AGENT_ID
            agent_changed = True
        service_key = _scope_binding_key(tid, node_id)
        if str(service_store.get(service_key) or "").strip() != node_id:
            service_store[service_key] = node_id
            service_changed = True
    if agent_changed:
        _save_node_agent_bindings(agent_store)
    if service_changed:
        _save_node_service_bindings(service_store)


def _topology_missing_runtime_infra(topo: Any) -> bool:
    if not isinstance(topo, dict):
        return False
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict) and str(n.get("id") or "")}
    if "game-cn-1" in ids:
        return not _RUNTIME_INFRA_NODE_IDS.issubset(ids)
    if "game-01" in ids:
        return not {"redis-01", "db-01"}.issubset(ids)
    return False


def _build_runtime_infra_topology_node(
    node_id: str,
    preset_id: str,
    name: str,
    role: str,
    desc: str,
    project_id: str,
    env_key: str,
    x: int,
    y: int,
    color: str,
    port: int,
) -> Dict[str, Any]:
    kind = _infer_node_kind(role, "")
    contract = _load_node_contract(preset_id) or {}
    daemon_defaults = _contract_daemon_defaults(preset_id, port)
    ui_ports = _normalize_ports(kind, None)
    return {
        "id": node_id,
        "name": name,
        "server_id": node_id,
        "preset_id": preset_id,
        "node_type": str(contract.get("node_type") or preset_id),
        "project_id": str(project_id or ""),
        "env": _normalize_env_key(env_key) or "production",
        "role": role,
        "kind": kind,
        "desc": desc,
        "bizStatus": "normal",
        "owner": "ops-admin",
        "group": str(contract.get("category") or "infrastructure"),
        "daemon_profile": "external_daemon",
        "daemon_start_cmd": str(daemon_defaults.get("StartCommand") or ""),
        "daemon_stop_cmd": str(daemon_defaults.get("StopCommand") or ""),
        "daemon_port": int(port or 0),
        "x": float(x),
        "y": float(y),
        "tags": [role, preset_id],
        "ui": {
            "x": float(x),
            "y": float(y),
            "w": 220,
            "h": 90,
            "color": color,
            "locked": False,
            "ports": ui_ports,
            "remote": {"port": int(port or 0)} if port > 0 else {},
            "network": {"endpoints": [f"127.0.0.1:{port}"]} if port > 0 else {},
        },
    }


def _apply_runtime_minimal_topology(topology_id: str, project_id: str, env_key: str = "production") -> Dict[str, Any]:
    """将指定拓扑重写为 cluster.json 最小完整栈（应用层 + Redis/Mongo 数据层）。"""
    tid = str(topology_id or "").strip()
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key) or "production"
    if not tid or not pid:
        return {"updated": False, "reason": "missing_scope"}
    cluster_rows = _load_cluster_json() if _project_has_cluster_json(pid) else []
    if cluster_rows:
        topo = _build_cluster_topology_content(cluster_rows, pid)
    else:
        topo = _core_minimal_topology_content(pid, env, runtime_ids=False)
    topo = _append_runtime_infra_stack(topo, pid, env)
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    meta["runtime_topology"] = True
    meta["cluster_source"] = bool(cluster_rows)
    meta["updated_at"] = _now_iso()
    meta.pop("design_reference", None)
    topo["meta"] = meta
    for node in topo.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node["env"] = env
        node["project_id"] = pid
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = _repair_runtime_topology_edges(nodes, edges, meta)
    contents = _load_topology_contents()
    contents[tid] = topo
    _save_topology_contents(contents)
    runtime_node_ids = [
        str(n.get("id") or "")
        for n in nodes
        if isinstance(n, dict) and str(n.get("id") or "").endswith("-cn-1")
    ]
    if runtime_node_ids:
        _ensure_runtime_topology_bindings(tid, runtime_node_ids)
    return {"updated": True, "topology_id": tid, "node_count": len(nodes), "edge_count": len(topo.get("edges") or [])}


def _migrate_gomeku_design_topology_contents(project_id: str = "GomeKu") -> None:
    """一次性升级 GomeKu 各环境仍残留的设计稿 demo 拓扑内容。"""
    pid = str(project_id or "").strip()
    if not _project_has_cluster_json(pid):
        return
    env_by_tid: Dict[str, str] = {}
    for row in _load_topology_registry():
        if not isinstance(row, dict) or str(row.get("project_id") or "") != pid:
            continue
        tid = str(row.get("topology_id") or "").strip()
        if tid:
            env_by_tid[tid] = _normalize_env_key(row.get("env_key"))
    for tid, topo in list(_load_topology_contents().items()):
        if "gomeku" not in str(tid).lower() or not isinstance(topo, dict):
            continue
        meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        node_ids = {
            str(n.get("id") or "")
            for n in (topo.get("nodes") or [])
            if isinstance(n, dict) and str(n.get("id") or "")
        }
        needs_upgrade = (
            _topology_has_design_demo_nodes(topo)
            or str(meta.get("design_reference") or "").startswith("v")
            or bool({"tcp-01"} & node_ids)
            or _topology_missing_runtime_infra(topo)
        )
        if not needs_upgrade:
            continue
        env = env_by_tid.get(tid) or "production"
        _apply_runtime_minimal_topology(tid, pid, env)
