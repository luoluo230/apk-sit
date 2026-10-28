def _append_runtime_infra_stack(topo: Dict[str, Any], project_id: str = "", env_key: str = "production") -> Dict[str, Any]:
    """补齐最小完整栈的数据层：Game → Redis + Mongo。"""
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key) or "production"
    nodes = list(topo.get("nodes") or []) if isinstance(topo.get("nodes"), list) else []
    edges = list(topo.get("edges") or []) if isinstance(topo.get("edges"), list) else []
    node_by_id = {str(n.get("id") or ""): n for n in nodes if isinstance(n, dict) and str(n.get("id") or "")}
    if "game-cn-1" in node_by_id:
        infra_specs = [
            ("redis-cache-cn-1", "redis_cache", "Redis", "cache", "Redis 缓存与会话存储", 820, 48, "#eb2f96", 6379),
            ("mongo-db-cn-1", "mongo_db", "MongoDB", "database", "Mongo 业务主存储", 820, 248, "#13c2c2", 27017),
        ]
        edge_specs = list(_RUNTIME_INFRA_EDGE_SPECS)
    elif "game-01" in node_by_id:
        infra_specs = [
            ("redis-01", "redis_cache", "Redis", "cache", "Redis 缓存与会话存储", 820, 48, "#eb2f96", 6379),
            ("db-01", "mongo_db", "MongoDB", "database", "Mongo 业务主存储", 820, 248, "#13c2c2", 27017),
        ]
        edge_specs = list(_CORE_MINIMAL_DEMO_INFRA_EDGE_SPECS)
    else:
        return topo

    for node_id, preset_id, name, role, desc, x, y, color, port in infra_specs:
        if node_id in node_by_id:
            continue
        node = _build_runtime_infra_topology_node(
            node_id, preset_id, name, role, desc, pid, env, x, y, color, port
        )
        nodes.append(node)
        node_by_id[node_id] = node

    valid_ids = set(node_by_id.keys())
    existing = {(str(e.get("from") or ""), str(e.get("to") or "")) for e in edges if isinstance(e, dict)}
    for frm, to, note in edge_specs:
        if frm not in valid_ids or to not in valid_ids or (frm, to) in existing:
            continue
        edges.append(
            {
                "id": f"edge-{frm}-{to}",
                "from": str(frm),
                "to": str(to),
                "from_port": "out-1",
                "to_port": "in-1",
                "type": "depends_on",
                "note": str(note),
            }
        )
        existing.add((frm, to))

    topo["nodes"] = nodes
    topo["edges"] = edges
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    meta["blueprint_id"] = str(meta.get("blueprint_id") or "minimal_framework")
    meta["framework_profile"] = str(meta.get("framework_profile") or "commercial_game_server")
    topo["meta"] = meta
    return topo


def _ops_platform_redirect_to_runtime_project():
    """Redirect to default project/env if scope params are missing."""
    raw_pid = str(request.args.get("project_id") or "").strip()
    raw_env = str(request.args.get("env_key") or "").strip()
    if raw_pid and raw_env:
        return None
    args = request.args.to_dict(flat=True)
    if not raw_pid:
        args["project_id"] = _resolve_ops_project_id("")
    if not raw_env:
        args["env_key"] = _resolve_ops_env_key("")
    if request.path.rstrip("/").endswith("/topology"):
        if not str(args.get("topology_id") or "").strip():
            args["topology_id"] = _runtime_default_topology_id(
                args.get("project_id", ""),
                args.get("env_key", "production"),
            )
    return redirect(request.path + "?" + urlencode(args))


def _load_scope_agent_bindings(topology_id: str) -> Dict[str, str]:
    data = _load_node_agent_bindings()
    out: Dict[str, str] = {}
    tid = str(topology_id or "").strip()
    for key, value in (data.items() if isinstance(data, dict) else []):
        text = str(key or "").strip()
        if not text or not str(value or "").strip():
            continue
        if "::" in text:
            scope_id, node_id = text.split("::", 1)
            if scope_id != tid:
                continue
            out[node_id] = str(value or "").strip()
        elif not tid:
            out[text] = str(value or "").strip()
    return out


def _resolve_scope_agent_bindings_for_scope(
    topology_id: str,
    project_id: str = "",
    env_key: str = "",
    valid_nodes: Optional[set] = None,
) -> Dict[str, str]:
    best: Dict[str, str] = {}
    nodes = valid_nodes if isinstance(valid_nodes, set) else None
    for tid in _binding_fallback_topology_ids(project_id, env_key, topology_id):
        cur = _load_scope_agent_bindings(tid)
        if not cur:
            continue
        if nodes:
            filtered = {k: v for k, v in cur.items() if k in nodes}
            if len(filtered) > len(best):
                best = filtered
        elif len(cur) > len(best):
            best = cur
    return best


def _resolve_scope_service_bindings_for_scope(
    topology_id: str,
    project_id: str = "",
    env_key: str = "",
    valid_nodes: Optional[set] = None,
) -> Dict[str, str]:
    best: Dict[str, str] = {}
    nodes = valid_nodes if isinstance(valid_nodes, set) else None
    for tid in _binding_fallback_topology_ids(project_id, env_key, topology_id):
        cur = _load_scope_service_bindings(tid)
        if not cur:
            continue
        if nodes:
            filtered = {k: v for k, v in cur.items() if k in nodes}
            if len(filtered) > len(best):
                best = filtered
        elif len(cur) > len(best):
            best = cur
    return best


def _save_scope_agent_binding(topology_id: str, node_id: str, agent_id: str) -> Dict[str, Any]:
    data = _load_node_agent_bindings()
    if not isinstance(data, dict):
        data = {}
    key = _scope_binding_key(topology_id, node_id)
    if agent_id:
        data[key] = agent_id
    else:
        data.pop(key, None)
    _save_node_agent_bindings(data)
    return data


def _load_scope_service_bindings(topology_id: str) -> Dict[str, str]:
    data = _load_node_service_bindings()
    out: Dict[str, str] = {}
    tid = str(topology_id or "").strip()
    for key, value in (data.items() if isinstance(data, dict) else []):
        text = str(key or "").strip()
        if not text or not str(value or "").strip():
            continue
        if "::" in text:
            scope_id, node_id = text.split("::", 1)
            if scope_id != tid:
                continue
            out[node_id] = str(value or "").strip()
        elif not tid:
            out[text] = str(value or "").strip()
    return out


def _save_scope_service_binding(topology_id: str, node_id: str, service_id: str) -> Dict[str, Any]:
    data = _load_node_service_bindings()
    if not isinstance(data, dict):
        data = {}
    key = _scope_binding_key(topology_id, node_id)
    if service_id:
        data[key] = service_id
    else:
        data.pop(key, None)
    _save_node_service_bindings(data)
    return data


def _apply_service_runtime_after_action(
    service_id: str,
    *,
    status: str,
    live: bool,
    metrics: Optional[Dict[str, Any]] = None,
) -> None:
    st = str(status or "STOPPED").strip().upper()
    probe = "PASS" if live and st == "RUNNING" else ("FAIL" if st == "STOPPED" else "")
    fields: Dict[str, Any] = {"status": st, "run_state": st, "probe_status": probe}
    if metrics is not None:
        fields["metrics"] = metrics
    _update_canonical_service_runtime(service_id, **fields)


def _update_canonical_service_runtime(service_id: str, **fields: Any) -> None:
    sid = str(service_id or "").strip()
    if not sid:
        return
    reg = _load_agent_registry_v2()
    canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else None
    if not canonical:
        return
    services = canonical.get("services") if isinstance(canonical.get("services"), list) else []
    now = _now_iso()
    changed = False
    for svc in services:
        if not isinstance(svc, dict):
            continue
        if str(svc.get("service_id") or svc.get("node_id") or "").strip() != sid:
            continue
        for key, value in fields.items():
            if value is not None:
                svc[key] = value
        svc["updated_at"] = now
        changed = True
        break
    if changed:
        canonical["services"] = services
        canonical["updated_at"] = now
        reg[CANONICAL_LOCAL_AGENT_ID] = canonical
        _save_agent_registry_v2(reg)
