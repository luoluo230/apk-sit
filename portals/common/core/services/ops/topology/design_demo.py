def _ensure_design_demo_registry(project_id: str) -> None:
    """Deprecated — design demo seeds removed; purge any legacy rows instead."""
    _purge_design_demo_topology_registry(project_id)


def _purge_design_demo_project_state(project_id: str, topology_id: str = "") -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid:
        return {"removed_agents": 0, "removed_bindings": 0}
    reg = _load_agent_registry_v2()
    removed_agents = 0
    for aid in list(reg.keys()):
        item = reg.get(aid) if isinstance(reg.get(aid), dict) else {}
        if str(item.get("project_id") or pid).strip() != pid:
            continue
        if _is_design_demo_agent_row(item):
            reg.pop(aid, None)
            removed_agents += 1
    _save_agent_registry_v2(reg)

    bindings = _load_node_agent_bindings()
    removed_bindings = 0
    tid = str(topology_id or "").strip()
    for key in list(bindings.keys()):
        node_part = key.split("::", 1)[-1] if "::" in key else key
        if node_part not in _DESIGN_DEMO_NODE_IDS:
            continue
        if tid and not str(key).startswith(tid + "::"):
            continue
        bindings.pop(key, None)
        removed_bindings += 1
    _save_node_agent_bindings(bindings)
    return {"removed_agents": removed_agents, "removed_bindings": removed_bindings}


def _needs_design_reference_upgrade(topo: Any) -> bool:
    if not isinstance(topo, dict):
        return True
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    if meta.get("runtime_topology") or meta.get("cluster_source"):
        if any(isinstance(n, dict) and str(n.get("id") or "").endswith("-cn-1") for n in nodes):
            return False
    if str(meta.get("design_reference") or "") == "v4":
        for item in nodes:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "")
            if nid == "game-01" and "核心游戏逻辑" not in str(item.get("desc") or ""):
                return True
            if nid == "game-01" and str(item.get("owner") or "") != "运维团队":
                return True
            if nid == "db-01":
                ui = item.get("ui") if isinstance(item.get("ui"), dict) else {}
                if ui.get("list_only"):
                    return True
        edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
        notes = {str(e.get("note") or "") for e in edges if isinstance(e, dict)}
        if "http:80" not in notes or "tcp:9512" not in notes:
            return True
        if "db-01" not in {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}:
            return True
        return False
    if str(meta.get("design_reference") or "") in ("v1", "v2", "v3", ""):
        return True
    if len(nodes) >= 5:
        ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
        if {"gateway-01", "auth-01", "game-01", "tcp-01", "db-01"}.issubset(ids):
            return False
    if len(nodes) <= 1:
        return True
    ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
    if ids <= {"local-gm", ""}:
        return True
    for item in nodes:
        if not isinstance(item, dict):
            continue
        if _text_has_mojibake(str(item.get("desc") or "")):
            return True
    return False


def _ensure_design_reference_bindings(topology_id: str) -> None:
    tid = str(topology_id or "").strip()
    if not tid:
        return
    store = _load_node_agent_bindings()
    if not isinstance(store, dict):
        store = {}
    key = _scope_binding_key(tid, "game-01")
    if not str(store.get(key) or "").strip():
        store[key] = "agent-01"
        _save_node_agent_bindings(store)


def _ensure_design_reference_agents(project_id: str) -> None:
    """Sync real cluster agents and bind topology nodes — never seed synthetic ONLINE agents."""
    pid = str(project_id or "").strip()
    if not pid:
        return
    try:
        _sync_cluster_to_agents(pid)
    except Exception:
        pass
    registry = _load_agent_registry_v2()
    if not isinstance(registry, dict) or not registry:
        return
    store = _load_node_agent_bindings()
    if not isinstance(store, dict):
        store = {}
    changed = False
    for aid, row in registry.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("project_id") or "").strip() != pid:
            continue
        node_id = str(row.get("node_id") or "").strip()
        if not node_id:
            continue
        key = _scope_binding_key("", node_id)
        if str(store.get(key) or "").strip() == str(aid).strip():
            continue
        store[key] = str(aid).strip()
        changed = True
    if changed:
        _save_node_agent_bindings(store)


def _gateway_blueprint_ports() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "in": [],
        "out": [
            {"id": "out-1", "label": "http:80", "kind": "out", "max_links": 8, "required": False},
            {"id": "out-2", "label": "http:443", "kind": "out", "max_links": 8, "required": False},
        ],
    }


def _normalize_blueprint_edge_rel(rel: Any) -> Optional[Dict[str, Any]]:
    if isinstance(rel, list) and len(rel) >= 2:
        mode = "round_robin"
        if len(rel) > 2 and isinstance(rel[2], str):
            mode = str(rel[2] or "round_robin").strip().lower()
        return {
            "from": str(rel[0] or "").strip(),
            "to": str(rel[1] or "").strip(),
            "mode": mode,
            "from_port": "out-1",
            "to_port": "in-1",
            "note": "blueprint-auto",
            "type": "depends_on",
        }
    if isinstance(rel, dict):
        frm = str(rel.get("from") or rel.get("from_preset") or "").strip()
        to = str(rel.get("to") or rel.get("to_preset") or "").strip()
        if not frm or not to:
            return None
        return {
            "from": frm,
            "to": to,
            "mode": str(rel.get("mode") or "round_robin").strip().lower(),
            "from_port": str(rel.get("from_port") or "out-1").strip(),
            "to_port": str(rel.get("to_port") or "in-1").strip(),
            "note": str(rel.get("note") or "blueprint-auto").strip(),
            "type": str(rel.get("type") or "depends_on").strip(),
        }
    return None


def _layout_blueprint_nodes_by_layer(topo: Dict[str, Any], created_node_ids: List[str]) -> None:
    created_set = set(created_node_ids)
    created_nodes = [n for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "") in created_set]
    if not created_nodes:
        return
    layer_buckets: Dict[int, List[Dict[str, Any]]] = {}
    for node in created_nodes:
        preset_id = str(node.get("preset_id") or "").strip()
        layer = int(_BLUEPRINT_LAYER_BY_PRESET.get(preset_id, 2))
        layer_buckets.setdefault(layer, []).append(node)
    rank_gap = 268.0
    row_gap = 128.0
    base_x = 72.0
    base_y = 48.0
    for layer in sorted(layer_buckets.keys()):
        rows = layer_buckets[layer]
        x = base_x + float(layer) * rank_gap
        for idx, node in enumerate(rows):
            y = base_y + float(idx) * row_gap
            node["x"] = x
            node["y"] = y
            ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
            ui["x"] = x
            ui["y"] = y
            if "w" not in ui:
                ui["w"] = 220
            if "h" not in ui:
                ui["h"] = 90
            node["ui"] = ui
