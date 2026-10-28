def create_topology_registry_entry(payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    _migrate_topology_storage_if_needed()
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("project_id required")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("拓扑名称不能为空")
    env_key = _normalize_env_key(payload.get("env_key") or "development")
    topology_id = _validate_topology_id(payload.get("topology_id") or "")
    if _topology_id_exists(topology_id):
        raise ValueError("拓扑 ID 已存在")
    rows = _load_topology_registry()
    row = _normalize_topology_registry_row(
        {
            "topology_id": topology_id,
            "project_id": project_id,
            "env_key": env_key,
            "name": name,
            "version_label": str(payload.get("version_label") or "v1.0.0").strip(),
            "owner": str(actor or payload.get("owner") or "admin").strip(),
            "description": str(payload.get("description") or "").strip(),
            "icon_url": str(payload.get("icon_url") or "").strip(),
            "is_default": not any(
                isinstance(item, dict)
                and str(item.get("project_id") or "") == project_id
                and _normalize_env_key(item.get("env_key") or "") == env_key
                for item in rows
            ),
            "status": "draft",
            "disabled": False,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
    )
    rows.append(row)
    _save_topology_registry(rows)
    contents = _load_topology_contents()
    contents[topology_id] = {
        "nodes": [],
        "edges": [],
        "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": _now_iso(), "layout_mode": "structured"},
    }
    _save_topology_contents(contents)
    return row


def update_topology_registry_entry(topology_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    _migrate_topology_storage_if_needed()
    tid = str(topology_id or "").strip()
    if not tid:
        raise ValueError("topology_id required")
    if payload.get("name") is not None or payload.get("topology_id") is not None:
        raise ValueError("名称与 ID 创建后不可修改")
    rows = _load_topology_registry()
    found = False
    updated: Optional[Dict[str, Any]] = None
    for idx, item in enumerate(rows):
        if not isinstance(item, dict) or str(item.get("topology_id") or "").strip() != tid:
            continue
        merged = dict(item)
        if "description" in payload:
            merged["description"] = str(payload.get("description") or "").strip()
        if "icon_url" in payload:
            merged["icon_url"] = str(payload.get("icon_url") or "").strip()
        if "disabled" in payload:
            merged["disabled"] = bool(payload.get("disabled"))
        if "status" in payload and not payload.get("disabled"):
            merged["status"] = str(payload.get("status") or merged.get("status") or "draft").strip().lower()
        merged["updated_at"] = _now_iso()
        if actor:
            merged["owner"] = str(actor).strip()
        rows[idx] = merged
        updated = _normalize_topology_registry_row(merged)
        found = True
        break
    if not found:
        raise ValueError("拓扑不存在")
    _save_topology_registry(rows)
    return updated or {}


def delete_topology_registry_entry(topology_id: str) -> bool:
    _migrate_topology_storage_if_needed()
    tid = str(topology_id or "").strip()
    if not tid:
        return False
    rows = _load_topology_registry()
    kept = [item for item in rows if not (isinstance(item, dict) and str(item.get("topology_id") or "").strip() == tid)]
    if len(kept) == len(rows):
        return False
    _save_topology_registry(kept)
    contents = _load_topology_contents()
    contents.pop(tid, None)
    _save_topology_contents(contents)
    return True


def _ensure_topology_for_scope(project_id: str, env_key: str) -> Dict[str, Any]:
    _migrate_topology_storage_if_needed()
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    rows = _load_topology_registry()
    for item in rows:
        if not isinstance(item, dict):
            continue
        row = _normalize_topology_registry_row(item)
        if row.get("project_id") == pid and row.get("env_key") == env and row.get("is_default"):
            return row
    row = _normalize_topology_registry_row(
        {
            "topology_id": "topology-" + uuid.uuid4().hex[:10],
            "project_id": pid,
            "env_key": env,
            "name": _env_label(env) + "主拓扑",
            "version_label": "v1.0.0",
            "owner": "system",
            "description": "自动创建的默认拓扑",
            "is_default": True,
            "status": "running" if env == "production" else "draft",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
    )
    rows.append(row)
    _save_topology_registry(rows)
    contents = _load_topology_contents()
    contents[row["topology_id"]] = _topology_seed_content(pid, env)
    _save_topology_contents(contents)
    return row


def _resolve_ops_topology_id(project_id: str, env_key: str, raw: str = "") -> str:
    tid = str(raw or "").strip()
    if tid:
        return tid
    ctx = _resolve_topology_context(project_id, env_key, "")
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    return str(row.get("topology_id") or "")


def _resolve_topology_context(project_id: str = "", env_key: str = "", topology_id: str = "") -> Dict[str, Any]:
    _migrate_topology_storage_if_needed()
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    rows = _list_topologies(pid, env)
    target = None
    if tid:
        for item in rows:
            if str(item.get("topology_id") or "") == tid:
                target = item
                break
    if target is None:
        preferred_tid = _runtime_default_topology_id(pid, env or "production")
        for item in rows:
            if str(item.get("topology_id") or "") == preferred_tid:
                target = item
                break
    if target is None:
        for item in rows:
            if item.get("is_default"):
                target = item
                break
    if target is None and rows:
        target = rows[0]
    if target is None:
        target = _ensure_topology_for_scope(pid, env or "production")
        rows = _list_topologies(pid, env or "production")
    tid_str = str(target.get("topology_id") or "")
    project_for_topo = str(target.get("project_id") or pid or "")
    env_for_topo = str(target.get("env_key") or env or "production")
    contents = _load_topology_contents()
    topo = contents.get(tid_str) if isinstance(contents.get(tid_str), dict) else {}
    if not topo:
        topo = _topology_seed_content(project_for_topo, env_for_topo)
        contents[tid_str] = topo
        _save_topology_contents(contents)
    elif _project_has_cluster_json(project_for_topo):
        topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        node_ids = {
            str(n.get("id") or "")
            for n in (topo.get("nodes") or [])
            if isinstance(n, dict) and str(n.get("id") or "")
        }
        needs_cluster_sync = (
            _topology_has_design_demo_nodes(topo)
            or not (topo_meta.get("runtime_topology") or topo_meta.get("cluster_source"))
            or _topology_missing_runtime_infra(topo)
            or bool({"tcp-01"} & node_ids)
        )
        if needs_cluster_sync:
            _sync_cluster_to_agents(project_for_topo)
            _apply_runtime_minimal_topology(tid_str, project_for_topo, env_for_topo)
            _purge_design_demo_project_state(project_for_topo, tid_str)
            contents = _load_topology_contents()
            topo = contents.get(tid_str) if isinstance(contents.get(tid_str), dict) else topo
    elif _needs_design_reference_upgrade(topo):
        meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        if not meta.get("cluster_source") and not meta.get("runtime_topology"):
            topo = _core_minimal_topology_content(project_for_topo, env_for_topo, runtime_ids=False)
            contents[tid_str] = topo
            _save_topology_contents(contents)
    topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    runtime_node_ids = [
        str(n.get("id") or "")
        for n in (topo.get("nodes") or [])
        if isinstance(n, dict) and str(n.get("id") or "").endswith("-cn-1")
    ]
    if runtime_node_ids and (topo_meta.get("runtime_topology") or topo_meta.get("cluster_source")):
        _ensure_runtime_topology_bindings(tid_str, runtime_node_ids)
    elif not topo_meta.get("cluster_source") and not topo_meta.get("runtime_topology"):
        _ensure_design_reference_bindings(tid_str)
        _ensure_design_reference_agents(project_for_topo or pid or "")
    return {
        "topology": topo,
        "row": target,
        "topologies": rows,
    }


def _load_topology_scoped(project_id: str = "", env_key: str = "", topology_id: str = "") -> Dict[str, Any]:
    ctx = _resolve_topology_context(project_id, env_key, topology_id)
    topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    viewport = meta.get("viewport") if isinstance(meta.get("viewport"), dict) else {}
    normalized_nodes: List[Dict[str, Any]] = []
    seen = set()
    for item in nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        role = str(item.get("role") or "business")
        kind = _infer_node_kind(role, str(item.get("kind") or ""))
        ui = item.get("ui") if isinstance(item.get("ui"), dict) else {}
        ui = _strip_default_node_ui_color(ui)
        if ui.get("list_only"):
            ui = dict(ui)
            ui.pop("list_only", None)
        ui["ports"] = _normalize_ports(kind, ui.get("ports"))
        normalized_nodes.append(
            {
                "id": nid,
                "name": str(item.get("name") or nid),
                "server_id": str(item.get("server_id") or nid),
                "project_id": str(item.get("project_id") or ctx.get("row", {}).get("project_id") or ""),
                "env": str(item.get("env") or ctx.get("row", {}).get("env_key") or "production"),
                "role": role,
                "kind": kind,
                "desc": str(item.get("desc") or ""),
                "bizStatus": str(item.get("bizStatus") or "normal"),
                "owner": str(item.get("owner") or ""),
                "group": str(item.get("group") or ""),
                "node_category": str(item.get("node_category") or ""),
                "node_type": str(item.get("node_type") or ""),
                "preset_id": str(item.get("preset_id") or ""),
                "daemon_profile": str(item.get("daemon_profile") or ""),
                "daemon_start_cmd": str(item.get("daemon_start_cmd") or ""),
                "daemon_stop_cmd": str(item.get("daemon_stop_cmd") or ""),
                "daemon_port": int(item.get("daemon_port") or 0) if item.get("daemon_port") is not None else 0,
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "ui": ui,
                "x": float(item.get("x") or ui.get("x") or 0),
                "y": float(item.get("y") or ui.get("y") or 0),
            }
        )
    valid_ids = {str(x.get("id") or "") for x in normalized_nodes if isinstance(x, dict)}
    normalized_edges: List[Dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to or frm not in valid_ids or to not in valid_ids:
            continue
        normalized_edges.append(
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
    normalized_edges = _repair_runtime_topology_edges(normalized_nodes, normalized_edges, meta)
    out_meta: Dict[str, Any] = {
            "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
            "version": int(meta.get("version") or 1),
            "updated_at": str(meta.get("updated_at") or ""),
            "layout_mode": str(meta.get("layout_mode") or "structured"),
            "layout_locked": bool(meta.get("layout_locked")),
            "design_reference": str(meta.get("design_reference") or ""),
        "runtime_topology": bool(meta.get("runtime_topology")),
        "cluster_source": bool(meta.get("cluster_source")),
        "workbench_mode": str(meta.get("workbench_mode") or "edit"),
        "workbench_locked_mode": str(meta.get("workbench_locked_mode") or ""),
        "workbench_mode_updated_at": str(meta.get("workbench_mode_updated_at") or ""),
        "description": str(meta.get("description") or ""),
    }
    if isinstance(meta.get("layout_spacing"), dict) or meta.get("layout_spacing_customized"):
        out_meta["layout_spacing"] = _normalize_layout_spacing(meta.get("layout_spacing"))
        out_meta["layout_spacing_customized"] = bool(meta.get("layout_spacing_customized"))
    return {
        "nodes": normalized_nodes,
        "edges": normalized_edges,
        "meta": out_meta,
        "registry": ctx.get("row"),
        "topologies": ctx.get("topologies") if isinstance(ctx.get("topologies"), list) else [],
    }
