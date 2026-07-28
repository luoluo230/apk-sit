# -*- coding: utf-8 -*-
"""Topology CRUD, scoped load/save, bindings."""

from __future__ import annotations

from services.ops import shared_bootstrap as _boot

globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})

from services.ops.topology_service import (
    _default_env_options,
    _env_label,
    _load_topology_contents,
    _load_topology_registry,
    _normalize_env_key,
    _runtime_default_topology_id,
    _save_topology_contents,
    _save_topology_registry,
    _scope_binding_key,
    _topology_content_counts,
)

def _normalize_node(payload: Dict[str, Any]) -> Dict[str, Any]:
    node_id = str(payload.get("id") or uuid.uuid4().hex[:12]).strip()
    fallback_ops_base = str(
        payload.get("ops_base_url")
        or os.getenv("GM_LEGACY_OPS_BASE_URL", "")
        or payload.get("base_url")
        or os.getenv("GM_LEGACY_BASE_URL", "")
        or "http://127.0.0.1:5054"
        or ""
    ).strip()
    return {
        "id": node_id,
        "name": str(payload.get("name") or node_id).strip(),
        "base_url": str(payload.get("base_url") or "").strip(),
        "ops_base_url": fallback_ops_base,
        "ops_read_key": str(payload.get("ops_read_key") or "").strip(),
        "ops_write_key": str(payload.get("ops_write_key") or "").strip(),
        "ops_actor": str(payload.get("ops_actor") or "").strip(),
        "ops_role": str(payload.get("ops_role") or "").strip(),
        "username": str(payload.get("username") or "").strip(),
        "password": str(payload.get("password") or "").strip(),
        "server_id": str(payload.get("server_id") or "").strip(),
        "project_id": str(payload.get("project_id") or "").strip(),
        "owner": str(payload.get("owner") or "").strip(),
        "role": str(payload.get("role") or "business").strip(),
        "node_category": str(payload.get("node_category") or "").strip(),
        "node_type": str(payload.get("node_type") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "biz_status": str(payload.get("biz_status") or "normal").strip(),
        "allowed_upstream_roles": payload.get("allowed_upstream_roles") if isinstance(payload.get("allowed_upstream_roles"), list) else [],
        "allowed_downstream_roles": payload.get("allowed_downstream_roles") if isinstance(payload.get("allowed_downstream_roles"), list) else [],
        "daemon_profile": str(payload.get("daemon_profile") or "").strip(),
        "daemon_start_cmd": str(payload.get("daemon_start_cmd") or "").strip(),
        "daemon_stop_cmd": str(payload.get("daemon_stop_cmd") or "").strip(),
        "env": str(payload.get("env") or "").strip(),
        "channel": str(payload.get("channel") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
        "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else [],
    }

def _default_nodes() -> List[Dict[str, Any]]:
    base_url = str(os.getenv("GM_LEGACY_BASE_URL", "http://127.0.0.1:8080")).strip()
    ops_base_url = str(os.getenv("GM_LEGACY_OPS_BASE_URL", "http://127.0.0.1:5054")).strip()
    ops_read_key = str(os.getenv("GM_LEGACY_OPS_READ_KEY", "2062f00689b2abee75b9bab1bd49f435c57e580d14db436942374d09a5d5468a")).strip()
    ops_write_key = str(os.getenv("GM_LEGACY_OPS_WRITE_KEY", "2062f00689b2abee75b9bab1bd49f435c57e580d14db436942374d09a5d5468a")).strip()
    ops_actor = str(os.getenv("GM_LEGACY_OPS_ACTOR", "intranet-ops")).strip()
    ops_role = str(os.getenv("GM_LEGACY_OPS_ROLE", "SuperAdmin")).strip()
    username = str(os.getenv("GM_LEGACY_USERNAME", "gm")).strip()
    password = str(os.getenv("GM_LEGACY_PASSWORD", "")).strip()
    return [
        _normalize_node(
            {
                "id": "local-gm",
                "name": "本地GM节点",
                "base_url": base_url,
                "ops_base_url": ops_base_url,
                "ops_read_key": ops_read_key,
                "ops_write_key": ops_write_key,
                "ops_actor": ops_actor,
                "ops_role": ops_role,
                "username": username,
                "password": password,
                "server_id": "",
                "role": "business",
                "node_category": "application",
                "node_type": "business_server",
                "description": "默认节点",
                "biz_status": "normal",
                "allowed_upstream_roles": ["gateway", "scheduler", "admin"],
                "allowed_downstream_roles": ["database", "cache", "mq", "search"],
                "daemon_profile": "ops_native",
                "enabled": True,
            }
        )
    ]

def _repair_legacy_node_text(item: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(item or {})
    name = str(row.get("name") or "")
    desc = str(row.get("description") or "")
    if _text_has_mojibake(name):
        if str(row.get("id") or "") == "local-gm":
            row["name"] = "本地GM节点"
        else:
            row["name"] = str(row.get("id") or "节点")
    if _text_has_mojibake(desc):
        row["description"] = "默认节点"
    return row

def _load_nodes() -> List[Dict[str, Any]]:
    raw = get_system_config(NODE_CONFIG_KEY, [])
    if isinstance(raw, list) and raw:
        rows: List[Dict[str, Any]] = []
        changed = False
        for item in raw:
            if isinstance(item, dict):
                repaired = _repair_legacy_node_text(item)
                if repaired != item:
                    changed = True
                rows.append(_normalize_node(repaired))
        if rows:
            if changed:
                _save_nodes(rows)
            return rows
    return _default_nodes()

def _save_nodes(rows: List[Dict[str, Any]]) -> None:
    normalized = [_normalize_node(item if isinstance(item, dict) else {}) for item in (rows or [])]
    set_system_config(
        NODE_CONFIG_KEY,
        normalized,
        value_type="json",
        description="Legacy GM + Ops 节点配置",
        username="system",
    )

def _resolve_node(node_id: str = "", project_id: str = "", env: str = "", channel: str = "") -> Optional[Dict[str, Any]]:
    rows = _load_nodes()
    enabled = [x for x in rows if x.get("enabled")]
    if node_id:
        for item in rows:
            if str(item.get("id") or "") == node_id:
                return item
    if project_id:
        for item in enabled:
            if str(item.get("project_id") or "") == project_id:
                if env and str(item.get("env") or "") not in ("", env):
                    continue
                if channel and str(item.get("channel") or "") not in ("", channel):
                    continue
                return item
    return enabled[0] if enabled else (rows[0] if rows else None)

def _node_or_400(payload: Dict[str, Any]):
    node = _resolve_flow_test_node(payload)
    if not node:
        return None, (jsonify({"ok": False, "error": "no node configured"}), 400)
    return node, None

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

def _ensure_design_demo_registry(project_id: str) -> None:
    """Deprecated — design demo seeds removed; purge any legacy rows instead."""
    _purge_design_demo_topology_registry(project_id)

def _normalize_topology_registry_row(row: Dict[str, Any]) -> Dict[str, Any]:
    item = row if isinstance(row, dict) else {}
    env_key = _normalize_env_key(item.get("env_key"))
    topology_id = str(item.get("topology_id") or "").strip() or ("topology-" + uuid.uuid4().hex[:10])
    out = {
        "topology_id": topology_id,
        "project_id": str(item.get("project_id") or "").strip(),
        "env_key": env_key,
        "env_label": _env_label(env_key),
        "name": str(item.get("name") or topology_id).strip(),
        "version_label": str(item.get("version_label") or "").strip(),
        "owner": str(item.get("owner") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "blueprint_id": str(item.get("blueprint_id") or "").strip(),
        "copied_from_topology_id": str(item.get("copied_from_topology_id") or "").strip(),
        "is_default": bool(item.get("is_default", False)),
        "status": str(item.get("status") or "draft").strip().lower(),
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

def _project_has_cluster_json(project_id: str = "") -> bool:
    pid = str(project_id or "").strip()
    if pid and pid != "GomeKu":
        return False
    return bool(_load_cluster_json())

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

def _core_minimal_topology_content(
    project_id: str = "",
    env_key: str = "production",
    *,
    runtime_ids: bool = False,
) -> Dict[str, Any]:
    """最小完整栈：Gateway / Auth / Ops / Game + Redis / Mongo。"""
    env = _normalize_env_key(env_key) or "production"
    pid = str(project_id or "").strip()
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
        ports: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        k = kind or _infer_node_kind(role, "")
        ui_ports = ports if isinstance(ports, dict) else _normalize_ports(k, None)
        return {
            "id": node_id,
            "name": name,
            "server_id": node_id,
            "project_id": pid,
            "env": env,
            "role": role,
            "kind": k,
            "desc": desc,
            "bizStatus": "normal",
            "owner": "",
            "group": "",
            "x": float(x),
            "y": float(y),
            "tags": [],
            "ui": {
                "x": float(x),
                "y": float(y),
                "w": 220,
                "h": 108,
                "color": color,
                "locked": False,
                "ports": ui_ports,
            },
        }

    if runtime_ids:
        node_specs: List[Tuple[Any, ...]] = [
            ("gateway-cn-1", "Gateway", "gateway", "网关服务", 72, 48, "#1890ff", "entry", gateway_ports),
            ("auth-cn-1", "Auth", "auth", "认证服务", 72, 248, "#52c41a"),
            ("ops-cn-1", "Ops", "ops", "运维服务", 320, 248, "#faad14", "admin"),
            ("game-cn-1", "Game", "business", "游戏服务", 560, 128, "#722ed1", "game"),
        ]
        edge_specs = [
            ("gateway-cn-1", "auth-cn-1", "http:80"),
            ("gateway-cn-1", "ops-cn-1", "http:443"),
            ("auth-cn-1", "game-cn-1", "tcp:5512"),
            ("ops-cn-1", "game-cn-1", "tcp:5512"),
        ]
        meta_extra = {"runtime_topology": True, "cluster_source": True}
    else:
        node_specs = [
            ("gateway-01", "Gateway", "gateway", "网关服务", 72, 48, "#1890ff", "entry", gateway_ports),
            ("auth-01", "Auth", "auth", "认证服务", 72, 248, "#52c41a"),
            ("ops-01", "Ops", "admin", "运维服务", 320, 248, "#faad14"),
            ("game-01", "Game", "business", "游戏服务", 560, 128, "#722ed1", "game"),
        ]
        edge_specs = [
            ("gateway-01", "auth-01", "http:80"),
            ("gateway-01", "ops-01", "http:443"),
            ("auth-01", "game-01", "tcp:5501"),
            ("ops-01", "game-01", "tcp:5512"),
        ]
        meta_extra = {"design_reference": "minimal-v1"}

    nodes: List[Dict[str, Any]] = []
    for spec in node_specs:
        nid, name, role, desc, x, y, color = spec[:7]
        kind = str(spec[7] or "") if len(spec) > 7 else ""
        ports = spec[8] if len(spec) > 8 else None
        nodes.append(_node(str(nid), str(name), str(role), str(desc), int(x), int(y), str(color), kind, ports))

    edges: List[Dict[str, Any]] = []
    for frm, to, note in edge_specs:
        edges.append(
            {
                "id": f"edge-{frm}-{to}",
                "from": str(frm),
                "to": str(to),
                "from_port": "out-1",
                "to_port": "in-1",
                "type": "http" if str(note).startswith("http") else "tcp",
                "note": str(note),
            }
        )

    meta: Dict[str, Any] = {
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "layout_mode": "structured",
        "layout_locked": False,
        "layout_spacing": {"rank_gap": 268, "row_gap": 128},
        "updated_at": _now_iso(),
    }
    meta.update(meta_extra)
    topo = {"nodes": nodes, "edges": edges, "meta": meta}
    return _append_runtime_infra_stack(topo, pid, env)

def _project_uses_runtime_topology(project_id: str) -> bool:
    pid = str(project_id or "").strip()
    if not pid:
        return False
    if _project_has_cluster_json(pid):
        return True
    _migrate_topology_storage_if_needed()
    tid = _runtime_default_topology_id(pid, "production")
    contents = _load_topology_contents()
    topo = contents.get(tid) if isinstance(contents.get(tid), dict) else {}
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    has_runtime_nodes = any(isinstance(n, dict) and str(n.get("id") or "").endswith("-cn-1") for n in nodes)
    return has_runtime_nodes and bool(meta.get("runtime_topology") or meta.get("cluster_source"))

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

def _topology_ops_dispatch_base(project_id: str, env_key: str, topo: Dict[str, Any]) -> str:
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    ops_node = next(
        (
            n for n in nodes
            if isinstance(n, dict) and str(n.get("id") or "") in ("ops-cn-1", "ops-01")
        ),
        None,
    )
    port = 5504
    if isinstance(ops_node, dict):
        ui = ops_node.get("ui") if isinstance(ops_node.get("ui"), dict) else {}
        remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
        try:
            port = int(remote.get("port") or ops_node.get("daemon_port") or 5504)
        except Exception:
            port = 5504
    return f"http://127.0.0.1:{port}"

def _resolve_topology_node_id_for_service(project_id: str, service_id: str, hint_node_id: str = "") -> str:
    """将 service_id / 绑定键 / demo 映射解析为可 dispatch 的拓扑 node_id。"""
    sid = str(service_id or "").strip()
    hint = str(hint_node_id or "").strip()
    candidates: List[str] = []
    if hint:
        candidates.append(hint)
    if sid:
        candidates.append(sid)
        mapped = str(_DEMO_TO_RUNTIME_NODE.get(sid) or "").strip()
        if mapped:
            candidates.append(mapped)
    for key, value in (_load_node_service_bindings() or {}).items():
        if str(value or "").strip() != sid:
            continue
        text = str(key or "").strip()
        node_id = text.split("::", 1)[-1].strip() if "::" in text else text
        if node_id:
            candidates.append(node_id)
    seen: set = set()
    for nid in candidates:
        if not nid or nid in seen:
            continue
        seen.add(nid)
        if _resolve_ops_dispatch_node(project_id, nid):
            return nid
    return hint or sid

def _resolve_ops_dispatch_node(project_id: str, node_id: str, env_key: str = "production") -> Optional[Dict[str, Any]]:
    nid = str(node_id or "").strip()
    if not nid:
        return None
    for item in _load_nodes():
        if isinstance(item, dict) and str(item.get("id") or "").strip() == nid:
            return item

    pid = str(project_id or "").strip()
    ctx = _resolve_topology_context(pid, _normalize_env_key(env_key) or "production", "")
    topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    tid = str(row.get("topology_id") or "")
    lookup_id = _DEMO_TO_RUNTIME_NODE.get(nid, nid)
    topo_node = next(
        (
            n for n in (topo.get("nodes") or [])
            if isinstance(n, dict) and str(n.get("id") or "").strip() == lookup_id
        ),
        None,
    )
    if not isinstance(topo_node, dict):
        return None
    built = _build_runtime_node_from_topology_node(pid, env_key, topo_node, tid)
    built["ops_base_url"] = _topology_ops_dispatch_base(pid, env_key, topo)
    built["enabled"] = True
    return _normalize_node(built)

def _resolve_flow_test_node(payload: Dict[str, Any], node_id: str = "") -> Optional[Dict[str, Any]]:
    project_id = str((payload or {}).get("project_id") or "").strip()
    env_key = _normalize_env_key((payload or {}).get("env_key") or "production")
    nid = str(node_id or (payload or {}).get("node_id") or "").strip()
    if not nid:
        return None
    if project_id:
        hit = _resolve_ops_dispatch_node(project_id, nid, env_key)
        if hit:
            return hit
    return _resolve_node(
        node_id=nid,
        project_id=project_id,
        env=str((payload or {}).get("env") or "").strip(),
        channel=str((payload or {}).get("channel") or "").strip(),
    )

def _smoke_probe_topology_node(project_id: str, env_key: str, topology_id: str, node: Dict[str, Any]) -> Dict[str, Any]:
    contract = _resolve_node_contract_for_topology_node(node)
    port = _resolve_topology_node_port(node, contract, None, None)
    host = "127.0.0.1"
    role = str(node.get("role") or "").strip().lower()
    nid = str(node.get("id") or "")

    if _is_external_daemon_node(node):
        ok = _probe_tcp_open(host, port) if port > 0 else False
        return {"ok": ok, "message": f"daemon tcp {'PASS' if ok else 'FAIL'} ({host}:{port})", "mode": "tcp-probe"}

    if port > 0 and _probe_tcp_open(host, port):
        return {"ok": True, "message": f"tcp PASS ({host}:{port})", "mode": "tcp-probe"}

    if role in ("auth", "game", "business", "admin", "ops"):
        for svc in _services_for_project(project_id):
            if not isinstance(svc, dict):
                continue
            st = str(svc.get("status") or svc.get("run_state") or "").upper()
            p = int(svc.get("remote_game_server_port") or svc.get("service_port") or 0)
            if st in ("RUNNING", "ONLINE", "READY", "STARTING") and p > 0 and _probe_tcp_open(host, p):
                return {
                    "ok": True,
                    "message": f"cluster service live via {svc.get('service_id')}:{p}",
                    "mode": "cluster-probe",
                }
        return {
            "ok": False,
            "message": f"节点 {nid} 未检测到可用端口（请先一键启动全流程）",
            "mode": "cluster-probe",
        }

    ok = _probe_tcp_open(host, port) if port > 0 else False
    return {"ok": ok, "message": f"tcp {'PASS' if ok else 'FAIL'} ({host}:{port or '-'})", "mode": "tcp-probe"}

def _auto_approve_ops_request(req: Dict[str, Any], node: Dict[str, Any], validation: Dict[str, Any], actor: str, note: str) -> Dict[str, Any]:
    if not validation.get("require_approval") or validation.get("approved"):
        return validation
    aid = create_approval(
        "gm_ops_action",
        actor,
        "ops_action",
        str(validation.get("approval_target_id") or ""),
        reason=str(validation.get("reason") or note),
        project_id=str(node.get("project_id") or ""),
    )
    ok, err = approve_or_reject(aid, actor, "approve", note)
    if not ok:
        validation = dict(validation)
        validation["ok"] = False
        validation["missing"] = list(validation.get("missing") or []) + ["approval_failed"]
        validation["approval_error"] = str(err or "approval failed")
        return validation
    req["approval_id"] = aid
    return _validate_ops_request(req, node)

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

def _default_topology_content_from_nodes(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = _load_topology(rows)
    if not isinstance(base.get("meta"), dict):
        base["meta"] = {}
    base["meta"]["layout_mode"] = "structured"
    return base

def _topology_seed_content(project_id: str, env_key: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key) or "production"
    cluster_rows = _load_cluster_json() if _project_has_cluster_json(pid) else []
    if cluster_rows:
        return _build_cluster_topology_content(cluster_rows, pid)
    return _core_minimal_topology_content(pid, env, runtime_ids=False)

def _migrate_topology_storage_if_needed() -> None:
    rows = _load_topology_registry()
    contents = _load_topology_contents()
    if rows and contents:
        return

    all_nodes = _load_nodes()
    project_ids = sorted({str(x.get("project_id") or "").strip() for x in all_nodes if isinstance(x, dict) and str(x.get("project_id") or "").strip()})
    if not project_ids:
        project_ids = [""]

    registry_rows: List[Dict[str, Any]] = rows if isinstance(rows, list) else []
    content_map: Dict[str, Any] = contents if isinstance(contents, dict) else {}
    topology_by_scope: Dict[str, str] = {}
    now = _now_iso()
    for project_id in project_ids:
        scoped_nodes = [x for x in all_nodes if isinstance(x, dict) and str(x.get("project_id") or "").strip() == project_id] if project_id else list(all_nodes)
        scoped_envs = sorted({_normalize_env_key(x.get("env") or "") for x in scoped_nodes if isinstance(x, dict)}) or ["production"]
        for env_key in scoped_envs:
            env_nodes = []
            for item in scoped_nodes:
                if not isinstance(item, dict):
                    continue
                item_env = _normalize_env_key(item.get("env") or "")
                if item_env and item_env != env_key:
                    continue
                env_nodes.append(item)
            topology_id = f"topology-{(project_id or 'default').replace('/', '-').replace(' ', '-').lower() or 'default'}-{env_key}-default"
            topology_by_scope[f"{project_id}::{env_key}"] = topology_id
            if not any(str((x or {}).get("topology_id") or "") == topology_id for x in registry_rows if isinstance(x, dict)):
                registry_rows.append(
                    _normalize_topology_registry_row(
                        {
                            "topology_id": topology_id,
                            "project_id": project_id,
                            "env_key": env_key,
                            "name": _env_label(env_key) + "主拓扑",
                            "version_label": "v1.0.0",
                            "owner": "system",
                            "description": "从历史单拓扑配置迁移",
                            "is_default": True,
                            "status": "running" if env_key == "production" else "draft",
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
                )
            content_map[topology_id] = _default_topology_content_from_nodes(env_nodes)

    if registry_rows:
        _save_topology_registry(registry_rows)
    if content_map:
        _save_topology_contents(content_map)

    binding_store = _load_node_agent_bindings()
    if isinstance(binding_store, dict) and binding_store and not any("::" in str(k or "") for k in binding_store.keys()):
        converted: Dict[str, Any] = {}
        for node_id, agent_id in binding_store.items():
            node_text = str(node_id or "").strip()
            if not node_text:
                continue
            raw_node = next((x for x in all_nodes if isinstance(x, dict) and str(x.get("id") or "").strip() == node_text), None)
            project_id = str((raw_node or {}).get("project_id") or "").strip()
            env_key = _normalize_env_key((raw_node or {}).get("env") or "")
            topology_id = topology_by_scope.get(f"{project_id}::{env_key}") or topology_by_scope.get(f"{project_id}::production") or next(iter(content_map.keys()), "")
            converted[_scope_binding_key(topology_id, node_text)] = agent_id
        if converted:
            _save_node_agent_bindings(converted)

    service_binding_store = _load_node_service_bindings()
    if isinstance(service_binding_store, dict) and service_binding_store and not any("::" in str(k or "") for k in service_binding_store.keys()):
        converted_services: Dict[str, Any] = {}
        for node_id, service_id in service_binding_store.items():
            node_text = str(node_id or "").strip()
            if not node_text:
                continue
            raw_node = next((x for x in all_nodes if isinstance(x, dict) and str(x.get("id") or "").strip() == node_text), None)
            project_id = str((raw_node or {}).get("project_id") or "").strip()
            env_key = _normalize_env_key((raw_node or {}).get("env") or "")
            topology_id = topology_by_scope.get(f"{project_id}::{env_key}") or topology_by_scope.get(f"{project_id}::production") or next(iter(content_map.keys()), "")
            converted_services[_scope_binding_key(topology_id, node_text)] = service_id
        if converted_services:
            _save_node_service_bindings(converted_services)

    runtime_rows = _load_runtime_runs()
    runtime_changed = False
    for row in runtime_rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("topology_id") or "").strip():
            continue
        project_id = str(row.get("project_id") or "").strip()
        env_key = _normalize_env_key(row.get("env_key") or "")
        topology_id = topology_by_scope.get(f"{project_id}::{env_key}") or topology_by_scope.get(f"{project_id}::production") or next(iter(content_map.keys()), "")
        row["env_key"] = env_key or "production"
        row["topology_id"] = topology_id
        runtime_changed = True
    if runtime_changed:
        _save_runtime_runs(runtime_rows)

def _list_topologies(project_id: str = "", env_key: Optional[str] = None) -> List[Dict[str, Any]]:
    _migrate_topology_storage_if_needed()
    pid = str(project_id or "").strip()
    if pid == "GomeKu" and _project_has_cluster_json(pid):
        _migrate_gomeku_design_topology_contents(pid)
    env_filter = _normalize_env_key(env_key) if (env_key is not None and str(env_key).strip()) else None
    if pid:
        _purge_design_demo_topology_registry(pid)
    out: List[Dict[str, Any]] = []
    for item in _load_topology_registry():
        if not isinstance(item, dict):
            continue
        row = _normalize_topology_registry_row(item)
        if _is_design_demo_topology_row(row):
            continue
        if pid and row.get("project_id") != pid:
            continue
        if env_filter and row.get("env_key") != env_filter:
            continue
        out.append(row)
    out.sort(key=lambda x: (x.get("project_id") or "", x.get("env_key") or "", 0 if x.get("is_default") else 1, x.get("updated_at") or ""), reverse=False)
    return out

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
            "owner": _session_username("system"),
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

def _resolve_ops_project_id(raw: str = "") -> str:
    pid = str(raw or "").strip()
    if pid:
        return pid
    pid = str(session.get("ops_last_project") or "").strip()
    if pid:
        return pid
    return "GomeKu"

def _resolve_ops_env_key(raw: str = "") -> str:
    env = str(raw or "").strip()
    if env:
        return _normalize_env_key(env)
    env = str(session.get("ops_last_env") or "").strip()
    if env:
        return _normalize_env_key(env)
    return "production"

def _agent_matches_env(item: Dict[str, Any], env_key: str = "") -> bool:
    if not env_key:
        return True
    env = _normalize_env_key(env_key)
    if isinstance(item, dict):
        aid = str(item.get("agent_id") or "").strip()
        pid = str(item.get("project_id") or "").strip()
        if aid == CANONICAL_LOCAL_AGENT_ID and pid and _project_uses_runtime_topology(pid):
            return True
    agent_env = _normalize_env_key(str((item or {}).get("env_key") or (item or {}).get("env") or "production"))
    return agent_env == env

def _resolve_ops_topology_id(project_id: str, env_key: str, raw: str = "") -> str:
    tid = str(raw or "").strip()
    if tid:
        return tid
    ctx = _resolve_topology_context(project_id, env_key, "")
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    return str(row.get("topology_id") or "")

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

def _normalize_layout_spacing(raw: Any) -> Dict[str, int]:
    row = raw if isinstance(raw, dict) else {}
    try:
        rank_gap = int(row.get("rank_gap") or 268)
    except Exception:
        rank_gap = 268
    try:
        row_gap = int(row.get("row_gap") or 128)
    except Exception:
        row_gap = 128
    return {
        "rank_gap": max(160, min(480, rank_gap)),
        "row_gap": max(80, min(240, row_gap)),
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

def _strip_default_node_ui_color(ui: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ui or {})
    if str(out.get("color") or "").strip().lower() == "#0f172a":
        out.pop("color", None)
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

def _enrich_preset_from_contract(preset: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(preset, dict):
        return preset
    pid = str(preset.get("preset_id") or "").strip()
    contract = _load_node_contract(pid) if pid else None
    out = dict(preset)
    if isinstance(contract, dict):
        if not out.get("default_port") and contract.get("default_port"):
            out["default_port"] = int(contract.get("default_port") or 0)
        if not out.get("probe_strategy") and contract.get("probe_strategy"):
            out["probe_strategy"] = str(contract.get("probe_strategy") or "")
        if contract.get("role") and str(out.get("role") or "") == "admin":
            out["role"] = str(contract.get("role") or out.get("role") or "")
        if contract.get("execution_model") in ("daemon", "worker"):
            out["daemon_profile"] = "external_daemon"
    return out

def _default_node_presets() -> List[Dict[str, Any]]:
    raw = [
        {
            "preset_id": "gateway_http",
            "name": "网关服务",
            "category": "application",
            "role": "gateway",
            "node_type": "gateway_server",
            "default_desc": "入口网关，承接流量并转发业务服务",
            "fixed_upstream_roles": ["edge", "lb", "admin", "ops"],
            "fixed_downstream_roles": ["business", "pressure", "auth"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "auth_service",
            "name": "认证服务",
            "category": "application",
            "role": "auth",
            "node_type": "auth_server",
            "default_desc": "用户认证与会话校验服务",
            "fixed_upstream_roles": ["gateway", "edge"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "business_main",
            "name": "游戏服务",
            "category": "application",
            "role": "business",
            "node_type": "business_server",
            "default_desc": "核心业务处理节点",
            "fixed_upstream_roles": ["gateway", "scheduler", "admin", "ops", "auth"],
            "fixed_downstream_roles": ["database", "cache", "mq", "search", "transport"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "ops_service",
            "name": "运维服务",
            "category": "application",
            "role": "ops",
            "node_type": "ops_server",
            "default_desc": "运维控制与诊断服务",
            "fixed_upstream_roles": ["gateway", "edge"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "tcp_transport",
            "name": "传输服务",
            "category": "network",
            "role": "transport",
            "node_type": "tcp_transport",
            "default_desc": "TCP 长连接传输节点",
            "fixed_upstream_roles": ["business", "gateway"],
            "fixed_downstream_roles": [],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "pressure_worker",
            "name": "压测服务",
            "category": "test",
            "role": "pressure",
            "node_type": "pressure_server",
            "default_desc": "压测流量与性能回归节点",
            "fixed_upstream_roles": ["gateway", "admin", "ops"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "redis_cache",
            "name": "Redis 缓存",
            "category": "infrastructure",
            "role": "cache",
            "node_type": "redis_cache",
            "default_desc": "缓存与会话存储节点",
            "fixed_upstream_roles": ["business", "gateway", "scheduler"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mongo_db",
            "name": "Mongo Database",
            "category": "database",
            "role": "database",
            "node_type": "mongo_database",
            "default_desc": "业务主存储数据库",
            "fixed_upstream_roles": ["business", "scheduler", "admin", "ops"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mq_kafka",
            "name": "消息队列",
            "category": "infrastructure",
            "role": "mq",
            "node_type": "mq_kafka",
            "default_desc": "异步事件队列",
            "fixed_upstream_roles": ["business", "gateway", "scheduler"],
            "fixed_downstream_roles": ["business", "analytics"],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "scheduler_job",
            "name": "调度服务",
            "category": "application",
            "role": "scheduler",
            "node_type": "scheduler_server",
            "default_desc": "定时任务与批处理节点",
            "fixed_upstream_roles": ["admin", "ops"],
            "fixed_downstream_roles": ["business", "database", "cache", "mq"],
            "daemon_profile": "external_daemon",
        },
    ]
    return [_enrich_preset_from_contract(x) for x in raw]

def _load_node_presets() -> List[Dict[str, Any]]:
    defaults = _default_node_presets()
    default_by_id = {str(p.get("preset_id") or "").strip(): p for p in defaults if str(p.get("preset_id") or "").strip()}
    raw = get_system_config(OPS_NODE_PRESETS_KEY, [])
    if isinstance(raw, list) and raw:
        out: List[Dict[str, Any]] = []
        seen: set = set()
        for item in raw:
            if isinstance(item, dict) and str(item.get("preset_id") or "").strip():
                pid = str(item.get("preset_id") or "").strip()
                if pid == "mysql_db":
                    continue
                seen.add(pid)
                out.append(_enrich_preset_from_contract(item))
        if out:
            if any(_text_has_mojibake(str(x.get("name") or "") + str(x.get("default_desc") or "")) for x in out):
                _save_json_config(OPS_NODE_PRESETS_KEY, defaults, description="Ops node preset catalog")
                return defaults
            missing_core = [pid for pid in _CORE_PRESET_IDS if pid not in seen]
            if missing_core:
                merged = list(out)
                for pid in missing_core:
                    preset = default_by_id.get(pid)
                    if preset:
                        merged.append(preset)
                _save_json_config(OPS_NODE_PRESETS_KEY, merged, description="Ops node preset catalog")
                return merged
            return out
    presets = _default_node_presets()
    _save_json_config(OPS_NODE_PRESETS_KEY, presets, description="Ops node preset catalog")
    return presets

def _preset_role_rules(role: str) -> Dict[str, List[str]]:
    r = str(role or "").strip().lower()
    up: set = set()
    down: set = set()
    for preset in _load_node_presets():
        if str(preset.get("role") or "").strip().lower() != r:
            continue
        for item in (preset.get("fixed_upstream_roles") or []):
            up.add(str(item))
        for item in (preset.get("fixed_downstream_roles") or []):
            down.add(str(item))
    return {"allowed_upstream_roles": sorted(up), "allowed_downstream_roles": sorted(down)}

def _connect_rule_meta(node: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(node or {})
    role = str(row.get("role") or "business").strip().lower()
    preset_rules = _preset_role_rules(role)
    row["role"] = role
    row["allowed_upstream_roles"] = list(preset_rules["allowed_upstream_roles"])
    row["allowed_downstream_roles"] = list(preset_rules["allowed_downstream_roles"])
    return row

def _link_role_block_reason(from_node: Dict[str, Any], to_node: Dict[str, Any]) -> str:
    frm = _connect_rule_meta(from_node or {})
    to = _connect_rule_meta(to_node or {})
    from_role = str(frm.get("role") or "").strip().lower()
    to_role = str(to.get("role") or "").strip().lower()
    allow_down = [str(x).strip().lower() for x in (frm.get("allowed_downstream_roles") or []) if str(x).strip()]
    allow_up = [str(x).strip().lower() for x in (to.get("allowed_upstream_roles") or []) if str(x).strip()]
    if allow_down and to_role and to_role not in allow_down:
        return f"「{from_role}」不允许连接「{to_role}」（可连下游：{', '.join(allow_down)}）"
    if allow_up and from_role and from_role not in allow_up:
        return f"「{to_role}」不接受来自「{from_role}」（可接受上游：{', '.join(allow_up)}）"
    return ""

def _can_link_nodes(from_node: Dict[str, Any], to_node: Dict[str, Any]) -> bool:
    return not _link_role_block_reason(from_node, to_node)

def _infer_node_kind(role: str, explicit_kind: str = "") -> str:
    ek = str(explicit_kind or "").strip().lower()
    if ek in ("entry", "standard", "terminal"):
        return ek
    r = str(role or "").strip().lower()
    if r in ("gateway", "edge"):
        return "entry"
    if r in ("database", "cache", "mq", "search", "transport", "tcp"):
        return "terminal"
    return "standard"

def _default_ports_for_kind(kind: str) -> Dict[str, List[Dict[str, Any]]]:
    k = _infer_node_kind("", kind)
    if k == "entry":
        return {"in": [], "out": [{"id": "out-1", "label": "out-1", "kind": "out", "max_links": 1}]}
    if k == "terminal":
        return {"in": [{"id": "in-1", "label": "in-1", "kind": "in", "max_links": 1}], "out": []}
    return {
        "in": [{"id": "in-1", "label": "in-1", "kind": "in", "max_links": 1}],
        "out": [{"id": "out-1", "label": "out-1", "kind": "out", "max_links": 1}],
    }

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

def _load_topology(current_nodes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = current_nodes if isinstance(current_nodes, list) else _load_nodes()
    raw = get_system_config(OPS_TOPOLOGY_KEY, {})
    if isinstance(raw, dict):
        nodes = raw.get("nodes") if isinstance(raw.get("nodes"), list) else []
        edges = raw.get("edges") if isinstance(raw.get("edges"), list) else []
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    else:
        nodes, edges, meta = [], [], {}

    valid_ids = set([str(x.get("id") or "") for x in rows if isinstance(x, dict)])
    merged_nodes: List[Dict[str, Any]] = []
    seen = set()
    for item in nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid or nid not in valid_ids or nid in seen:
            continue
        seen.add(nid)
        merged_nodes.append(
            {
                "id": nid,
                "role": str(item.get("role") or "business"),
                "kind": _infer_node_kind(str(item.get("role") or "business"), str(item.get("kind") or "")),
                "desc": str(item.get("desc") or ""),
                "bizStatus": str(item.get("bizStatus") or "normal"),
                "owner": str(item.get("owner") or ""),
                "x": float(item.get("x") or 0),
                "y": float(item.get("y") or 0),
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "ui": item.get("ui") if isinstance(item.get("ui"), dict) else {},
            }
        )
    if len(merged_nodes) < len(valid_ids):
        default_topo = _default_topology_for_nodes(rows)
        for item in default_topo.get("nodes") or []:
            nid = str(item.get("id") or "")
            if nid and nid not in seen:
                merged_nodes.append(item)
                seen.add(nid)

    merged_edges: List[Dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to or frm not in valid_ids or to not in valid_ids:
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
    for n in merged_nodes:
        if not isinstance(n, dict):
            continue
        kind = _infer_node_kind(str(n.get("role") or ""), str(n.get("kind") or ""))
        n["kind"] = kind
        ui = n.get("ui") if isinstance(n.get("ui"), dict) else {}
        ui["ports"] = _normalize_ports(kind, ui.get("ports"))
        if "w" not in ui:
            ui["w"] = 220
        if "h" not in ui:
            ui["h"] = 90
        n["ui"] = ui
    viewport = meta.get("viewport") if isinstance(meta.get("viewport"), dict) else {}
    out_meta = {
        "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
        "version": int(meta.get("version") or 1),
        "updated_at": str(meta.get("updated_at") or ""),
    }
    return {"nodes": merged_nodes, "edges": merged_edges, "meta": out_meta}

def _save_topology(topology: Dict[str, Any]) -> Dict[str, Any]:
    nodes = topology.get("nodes") if isinstance(topology, dict) and isinstance(topology.get("nodes"), list) else []
    edges = topology.get("edges") if isinstance(topology, dict) and isinstance(topology.get("edges"), list) else []
    meta = topology.get("meta") if isinstance(topology, dict) and isinstance(topology.get("meta"), dict) else {}
    viewport = meta.get("viewport") if isinstance(meta.get("viewport"), dict) else {}
    payload = {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
            "version": int(meta.get("version") or 1),
            "updated_at": _now_iso(),
        },
        "updated_at": _now_iso(),
    }
    _save_json_config(OPS_TOPOLOGY_KEY, payload, description="Ops 平台拓扑配置")
    return payload

def _gateway_blueprint_ports() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "in": [],
        "out": [
            {"id": "out-1", "label": "http:80", "kind": "out", "max_links": 8, "required": False},
            {"id": "out-2", "label": "http:443", "kind": "out", "max_links": 8, "required": False},
        ],
    }

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

def _blueprint_edge_instance_pairs(source_ids: List[str], target_ids: List[str], mode: str) -> List[Tuple[str, str]]:
    if not source_ids or not target_ids:
        return []
    m = str(mode or "round_robin").strip().lower()
    pairs: List[Tuple[str, str]] = []
    if m == "each_to_all":
        for sid in source_ids:
            for tid in target_ids:
                pairs.append((sid, tid))
    elif m == "each_to_first":
        tid = target_ids[0]
        for sid in source_ids:
            pairs.append((sid, tid))
    elif m == "indexed":
        for idx, sid in enumerate(source_ids):
            if idx < len(target_ids):
                pairs.append((sid, target_ids[idx]))
    else:
        for idx, sid in enumerate(source_ids):
            pairs.append((sid, target_ids[idx % len(target_ids)]))
    return pairs

def _apply_topology_blueprint_edges(
    topo: Dict[str, Any],
    created_by_preset: Dict[str, List[str]],
    plan_edges: List[Any],
) -> None:
    if not isinstance(topo.get("edges"), list):
        topo["edges"] = []
    existing = topo["edges"]
    for rel in plan_edges or []:
        spec = _normalize_blueprint_edge_rel(rel)
        if not spec:
            continue
        s_nodes = created_by_preset.get(str(spec.get("from") or "")) or []
        t_nodes = created_by_preset.get(str(spec.get("to") or "")) or []
        if not s_nodes or not t_nodes:
            continue
        for sid, tid in _blueprint_edge_instance_pairs(s_nodes, t_nodes, str(spec.get("mode") or "round_robin")):
            dup = False
            for edge in existing:
                if not isinstance(edge, dict):
                    continue
                if (
                    str(edge.get("from") or "") == sid
                    and str(edge.get("to") or "") == tid
                    and str(edge.get("from_port") or "out-1") == str(spec.get("from_port") or "out-1")
                ):
                    dup = True
                    break
            if dup:
                continue
            existing.append(
                {
                    "id": f"edge-{uuid.uuid4().hex[:10]}",
                    "from": sid,
                    "to": tid,
                    "from_port": str(spec.get("from_port") or "out-1"),
                    "to_port": str(spec.get("to_port") or "in-1"),
                    "type": str(spec.get("type") or "depends_on"),
                    "note": str(spec.get("note") or "blueprint-auto"),
                }
            )

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

def _default_topology_blueprints() -> List[Dict[str, Any]]:
    core_edges = _commercial_framework_core_edges()
    return [
        {
            "blueprint_id": "minimal_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "最小框架",
            "desc": "通用游戏服最小栈：入口网关、认证、运维控制、业务逻辑、缓存与主库；适合单机/开发/小规模上线",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
            ],
            "edges": list(core_edges),
        },
        {
            "blueprint_id": "medium_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "中型框架",
            "desc": "通用中型架构：最小栈 + 业务水平扩展、异步消息与定时调度；适合常规商业服与多实例部署",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 2},
                {"preset_id": "scheduler_job", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": list(core_edges)
            + [
                {"from": "business_main", "to": "mq_kafka", "note": "async-events", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "business_main", "note": "batch-jobs", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "mongo_db", "note": "batch-read", "mode": "each_to_first"},
            ],
        },
        {
            "blueprint_id": "full_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "全量框架",
            "desc": "通用大型架构：多入口、控制面、多业务实例、实时传输、消息与调度；适合完整运维链路与生产扩展",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 2},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 3},
                {"preset_id": "tcp_transport", "count": 1},
                {"preset_id": "scheduler_job", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": list(core_edges)
            + [
                {"from": "business_main", "to": "tcp_transport", "note": "tcp:realtime", "mode": "each_to_all"},
                {"from": "business_main", "to": "mq_kafka", "note": "async-events", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "business_main", "note": "batch-jobs", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "mongo_db", "note": "batch-read", "mode": "each_to_first"},
            ],
        },
        {
            "blueprint_id": "pressure_test_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "压测框架",
            "desc": "压测专用（非生产）：入口网关 + 业务节点 + 压测 Worker；不含 Auth/Ops/缓存/数据库，与商业生产模板隔离",
            "framework_profile": "pressure_test",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "business_main", "count": 1},
                {"preset_id": "pressure_worker", "count": 1},
            ],
            "edges": [
                {"from": "gateway_http", "to": "business_main", "from_port": "out-1", "note": "http:load-entry", "mode": "each_to_all"},
                {"from": "pressure_worker", "to": "business_main", "note": "stress:qps", "mode": "each_to_all"},
            ],
        },
    ]

def _merge_topology_blueprints_with_defaults(stored: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    defaults = _default_topology_blueprints()
    default_by_id = {str(d.get("blueprint_id") or ""): d for d in defaults}
    stored_by_id = {
        str(x.get("blueprint_id") or ""): x
        for x in stored
        if isinstance(x, dict) and str(x.get("blueprint_id") or "").strip()
    }
    merged: List[Dict[str, Any]] = []
    changed = False
    for default_row in defaults:
        bid = str(default_row.get("blueprint_id") or "")
        old = stored_by_id.get(bid)
        old_ver = int(old.get("blueprint_version") or 0) if isinstance(old, dict) else 0
        new_ver = int(default_row.get("blueprint_version") or 0)
        if isinstance(old, dict) and old_ver >= new_ver:
            merged.append(old)
        else:
            merged.append(default_row)
            changed = True
    for bid, row in stored_by_id.items():
        if bid not in default_by_id:
            merged.append(row)
    if not stored:
        changed = True
    return merged, changed

def _load_topology_blueprints() -> List[Dict[str, Any]]:
    raw = get_system_config(OPS_TOPOLOGY_BLUEPRINTS_KEY, [])
    stored: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and str(item.get("blueprint_id") or "").strip():
                stored.append(item)
    merged, changed = _merge_topology_blueprints_with_defaults(stored)
    if changed or not stored:
        _save_json_config(OPS_TOPOLOGY_BLUEPRINTS_KEY, merged, description="Ops topology blueprints")
    return merged

def _is_external_daemon_node(node: Dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        return False
    profile = str(node.get("daemon_profile") or "").strip().lower()
    role = str(node.get("role") or "").strip().lower()
    return profile == "external_daemon" or role in ("database", "cache", "mongo", "redis")

def _gameserver_tcp_probe_port(service_id: str, node: Optional[Dict[str, Any]] = None) -> int:
    sid = str(service_id or "").strip().lower()
    if sid in _GAMESERVER_TCP_PROBE_PORTS:
        return int(_GAMESERVER_TCP_PROBE_PORTS.get(sid) or 0)
    return 0

def _reconcile_gameserver_daemon_state(service_id: str) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {}
    live = _gameserver_service_live(sid)
    state = _get_daemon_state(sid)
    cur_status = str(state.get("status") or "").strip().upper()
    pid = _find_gameserver_pid_by_service(sid) if live else 0
    if live:
        patch = {"status": "RUNNING", "pid": int(pid or state.get("pid") or 0), "last_error": ""}
    elif cur_status in ("STARTING", "STOPPING"):
        patch = {"status": "STOPPED", "pid": 0, "last_error": ""}
    else:
        patch = {"status": "STOPPED", "pid": 0}
    merged = _set_daemon_state(sid, patch)
    return merged

def _reconcile_all_gameserver_daemon_states() -> None:
    for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
        try:
            _reconcile_gameserver_daemon_state(sid)
        except Exception:
            pass

def _gameserver_session_marker_path(repo: str = "", service_id: str = "") -> str:
    root = str(repo or _resolve_game_server_repo() or "").strip()
    sid = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "cluster").strip()) or "cluster"
    return os.path.join(root, "tools", "SmokeTest", "artifacts", f"gameserver-session-{sid}.json")

def _write_gameserver_session_marker(repo: str, pid: int, service_id: str = "") -> None:
    path = _gameserver_session_marker_path(repo, service_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(
            {"started_at": _now_iso(), "pid": int(pid), "epoch": time.time(), "service_id": str(service_id or "").strip()},
            fp,
        )

def _clear_gameserver_session_marker(repo: str = "", service_id: str = "") -> None:
    path = _gameserver_session_marker_path(repo, service_id)
    try:
        os.remove(path)
    except OSError:
        pass

def _read_gameserver_session_marker(repo: str = "", service_id: str = "") -> Dict[str, Any]:
    path = _gameserver_session_marker_path(repo, service_id)
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _find_pid_listening_on_port(port: int, host: str = "127.0.0.1") -> int:
    if port <= 0:
        return 0
    if os.name == "nt":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"$c = Get-NetTCPConnection -LocalAddress '{host}' -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | "
                    "Select-Object -First 1 -ExpandProperty OwningProcess; if ($c) { Write-Output $c }",
                ],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            for line in reversed((proc.stdout or "").splitlines()):
                text = line.strip()
                if text.isdigit():
                    return int(text)
        except Exception:
            pass
        try:
            proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=12, check=False)
            needle = f":{int(port)}"
            for line in (proc.stdout or "").splitlines():
                upper = line.upper()
                if "LISTENING" not in upper or needle not in line:
                    continue
                parts = line.split()
                if parts and parts[-1].isdigit():
                    return int(parts[-1])
        except Exception:
            pass
        return 0
    try:
        proc = subprocess.run(
            ["bash", "-lc", f"lsof -nP -iTCP:{int(port)} -sTCP:LISTEN -t 2>/dev/null | head -1"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        text = (proc.stdout or "").strip().splitlines()
        if text and text[0].strip().isdigit():
            return int(text[0].strip())
    except Exception:
        pass
    return 0

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

def _is_daemon_log_source(paths: List[str]) -> bool:
    if not paths:
        return False
    norm = [str(p or "").replace("\\", "/").lower() for p in paths]
    return all("/logs/daemons/" in p for p in norm)

def _gameserver_log_source_paths(current_session_only: bool = False, service_id: str = "") -> List[str]:
    """优先 UTF-8 结构化日志（ServerLogger 写入），再合并 nohup 控制台输出。"""
    repo = _resolve_game_server_repo()
    paths: List[str] = []
    sid = str(service_id or "").strip().lower()
    if sid in ("mongo-db-cn-1", "redis-cache-cn-1", "db-01"):
        daemon_path = _daemon_log_path(sid if sid != "db-01" else "mongo-db-cn-1")
        return [daemon_path] if os.path.isfile(daemon_path) else []
    def _cluster_log_sort_key(path: str) -> Tuple[float, str]:
        try:
            return (float(os.path.getmtime(path)), os.path.basename(path))
        except OSError:
            return (0.0, os.path.basename(path))

    all_cluster: List[str] = []
    if _is_gameserver_process_service_id(sid):
        inst_logs = os.path.join(_gameserver_instance_dir(repo, sid), "logs")
        if os.path.isdir(inst_logs):
            all_cluster.extend(
                os.path.join(inst_logs, name)
                for name in os.listdir(inst_logs)
                if name.startswith("cluster-") and name.endswith(".log")
            )
        cluster_paths = sorted(set(all_cluster), key=_cluster_log_sort_key, reverse=True)[:1]
        paths.extend(cluster_paths)
        launcher_log = _gameserver_service_log_path(repo, sid)
        if os.path.isfile(launcher_log):
            paths.append(launcher_log)
        return paths
    for sub in (
        os.path.join(repo, "game-server", "bin", "Debug", "logs"),
        os.path.join(repo, "game-server", "bin", "Release", "logs"),
    ):
        if not os.path.isdir(sub):
            continue
        all_cluster.extend(
            os.path.join(sub, name)
            for name in os.listdir(sub)
            if name.startswith("cluster-") and name.endswith(".log")
        )
    cluster_paths = sorted(set(all_cluster), key=_cluster_log_sort_key, reverse=True)[:1]
    if cluster_paths:
        paths.extend(cluster_paths)
        return paths
    out_path, err_path = _gameserver_log_artifact_paths()
    for p in (out_path, err_path):
        if os.path.isfile(p):
            paths.append(p)
    return paths

def _normalize_log_level(level: str) -> str:
    lv = str(level or "").strip().upper()
    if lv in ("WARN", "WARNING"):
        return "warn"
    if lv in ("ERROR", "FATAL"):
        return "error"
    if lv in ("DEBUG", "TRACE"):
        return "debug"
    return "info"

def _infer_log_level_from_text(level: str, raw_line: str, source_path: str = "") -> str:
    normalized = _normalize_log_level(level)
    if normalized in ("warn", "error", "debug"):
        return normalized
    text = str(raw_line or "")
    if _GS_LOG_ERROR_HINT.search(text):
        return "error"
    if _GS_LOG_WARN_HINT.search(text):
        return "warn"
    if str(source_path or "").endswith(".err.log"):
        return "error"
    return "info"

def _log_dedupe_key(raw_line: str) -> str:
    text = str(raw_line or "").strip()
    if not text:
        return ""
    stripped = re.sub(r"^\[[^\]]+\]", "", text, count=1).strip()
    stripped = re.sub(r"^\[(INFO|WARN|WARNING|ERROR|DEBUG|TRACE|FATAL)\]", "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"^\[[^\]]+\]", "", stripped, count=1).strip()
    return stripped.lower()

def _parse_gameserver_log_line(line: str, source_path: str = "") -> Dict[str, Any]:
    raw = str(line or "").rstrip("\n\r")
    if not raw.strip():
        return {"time": "", "level": "info", "category": "", "message": "", "raw": raw}
    match = _GS_LOG_LINE_RE.match(raw.strip())
    if not match:
        level = _infer_log_level_from_text("", raw, source_path)
        category = ""
        bracket = re.match(r"^\[(?P<cat>[^\]]+)\]", raw.strip())
        if bracket:
            category = bracket.group("cat")
        return {
            "time": "",
            "level": level,
            "category": category,
            "message": raw,
            "raw": raw,
        }
    level = _infer_log_level_from_text(match.group("level"), raw, source_path)
    return {
        "time": match.group("time"),
        "level": level,
        "category": match.group("category"),
        "message": match.group("message"),
        "raw": raw,
    }

def _service_log_line_matches(service_id: str, parsed: Dict[str, Any], raw_line: str) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return True
    hints = _SERVICE_LOG_HINTS.get(sid) or []
    if not hints:
        token = sid.split("-")[0]
        hints = [token] if token else []
    hay = f"{parsed.get('category') or ''} {parsed.get('message') or ''} {raw_line}".lower()
    if sid in hay:
        return True
    return any(h in hay for h in hints)

def _log_line_epoch(raw_line: str) -> float:
    text = str(raw_line or "")
    match = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", text)
    if not match:
        return 0.0
    token = match.group(1).replace(" ", "T")
    tail = text[match.end(): match.end() + 2]
    if tail.startswith("Z") or text[match.start(): match.end()].endswith("Z"):
        token += "Z"
    try:
        if token.endswith("Z"):
            return datetime.fromisoformat(token.replace("Z", "+00:00")).timestamp()
        return datetime.fromisoformat(token).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0

def _extract_line_iso_time(raw_line: str) -> str:
    text = str(raw_line or "")
    match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)", text)
    if match:
        return match.group(1)
    epoch = _log_line_epoch(text)
    if epoch > 0:
        return datetime.utcfromtimestamp(epoch).isoformat() + "Z"
    return ""

def _slice_merged_from_daemon_session(merged: List[Tuple[int, str, str]]) -> Tuple[List[Tuple[int, str, str]], str]:
    start_idx = 0
    started_at = ""
    for idx, (_, line, _) in enumerate(merged):
        if _DAEMON_SESSION_MARK.search(line):
            start_idx = idx
            started_at = _extract_line_iso_time(line)
    if start_idx <= 0:
        return merged, started_at
    return merged[start_idx:], started_at

def _filter_merged_from_session_epoch(
    merged: List[Tuple[int, str, str]],
    epoch: float,
    *,
    grace_sec: float = 8.0,
) -> Tuple[List[Tuple[int, str, str]], str]:
    if epoch <= 0 or not merged:
        return merged, ""
    cutoff = float(epoch) - max(0.0, float(grace_sec))
    kept: List[Tuple[int, str, str]] = []
    trailing_blank = 0
    for item in merged:
        ts = _log_line_epoch(item[1])
        if ts >= cutoff:
            kept.append(item)
            trailing_blank = 0
        elif ts <= 0 and kept and trailing_blank < 2:
            kept.append(item)
            trailing_blank += 1
    if kept:
        return kept, datetime.utcfromtimestamp(float(epoch)).isoformat() + "Z"
    return merged, ""

def _slice_merged_from_current_session(merged: List[Tuple[int, str, str]]) -> Tuple[List[Tuple[int, str, str]], str]:
    start_idx = 0
    started_at = ""
    for idx, (_, line, _) in enumerate(merged):
        if _GS_LOG_SESSION_START.search(line):
            start_idx = idx
            match = _GS_LOG_LINE_RE.match(line.strip())
            if match:
                started_at = match.group("time")
    if start_idx <= 0:
        return merged, started_at
    return merged[start_idx:], started_at

def _should_hide_lifecycle_log_line(raw_line: str) -> bool:
    text = str(raw_line or "")
    if not text.strip():
        return True
    return bool(_GS_LOG_LIFECYCLE_HIDE.search(text))

def _read_text_file_lines(path: str) -> List[str]:
    if not path or not os.path.isfile(path):
        return []
    raw = b""
    try:
        with open(path, "rb") as fp:
            raw = fp.read()
    except Exception:
        return []
    if not raw:
        return []
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(encoding)
        except Exception:
            continue
        if encoding.startswith("utf") and text.count("\ufffd") > max(3, len(text) // 200):
            continue
        return text.splitlines(keepends=True)
    return raw.decode("utf-8", errors="replace").splitlines(keepends=True)

def _read_gameserver_service_logs(
    service_id: str = "",
    *,
    level: str = "all",
    query: str = "",
    tail: int = 400,
    since_offset: int = 0,
    current_session_only: bool = False,
    hide_lifecycle: bool = False,
) -> Dict[str, Any]:
    paths = _gameserver_log_source_paths(current_session_only=current_session_only, service_id=service_id)
    if not paths:
        return {
            "lines": [],
            "total": 0,
            "next_offset": 0,
            "sources": [],
            "message": "未找到 GameServer 日志文件，请先启动 GameServer",
        }

    merged: List[Tuple[int, str, str]] = []
    offset = 0
    seen_keys: set = set()
    daemon_source = _is_daemon_log_source(paths)
    has_cluster_logs = any("cluster-" in os.path.basename(p) for p in paths)
    for path in paths:
        try:
            for line in _read_text_file_lines(path):
                if has_cluster_logs and line.count("\ufffd") >= 4:
                    continue
                if not daemon_source and not current_session_only and not has_cluster_logs:
                    key = _log_dedupe_key(line)
                    if key and key in seen_keys:
                        continue
                    if key:
                        seen_keys.add(key)
                merged.append((offset, line, path))
                offset += len(line.encode("utf-8", errors="replace"))
        except Exception:
            continue

    session_started_at = ""
    if current_session_only and merged:
        if daemon_source:
            merged, session_started_at = _slice_merged_from_daemon_session(merged)
        else:
            marker = _read_gameserver_session_marker(service_id=service_id)
            marker_epoch = float(marker.get("epoch") or 0) if isinstance(marker, dict) else 0.0
            if marker_epoch > 0:
                merged, session_started_at = _filter_merged_from_session_epoch(merged, marker_epoch)
                if marker.get("started_at"):
                    session_started_at = str(marker.get("started_at") or session_started_at)
            else:
                merged, session_started_at = _slice_merged_from_current_session(merged)

    lv_filter = str(level or "all").strip().lower()
    q = str(query or "").strip().lower()
    repo = _resolve_game_server_repo()
    sid_lower = str(service_id or "").strip().lower()
    instance_root = _gameserver_instance_dir(repo, sid_lower).replace("\\", "/").lower() if sid_lower else ""
    skip_service_filter = bool(
        instance_root
        and _is_gameserver_process_service_id(sid_lower)
        and any(instance_root in str(p or "").replace("\\", "/").lower() for p in paths)
    )
    parsed_rows: List[Dict[str, Any]] = []
    for byte_offset, line, path in merged:
        if since_offset > 0 and byte_offset < since_offset:
            continue
        if hide_lifecycle and _should_hide_lifecycle_log_line(line):
            continue
        parsed = _parse_gameserver_log_line(line, path)
        if lv_filter not in ("", "all") and parsed.get("level") != lv_filter:
            continue
        if service_id and not daemon_source and not skip_service_filter and not _service_log_line_matches(service_id, parsed, line):
            continue
        hay = f"{parsed.get('raw') or ''} {parsed.get('category') or ''} {parsed.get('message') or ''}".lower()
        if q and q not in hay:
            continue
        parsed_rows.append({
            **parsed,
            "offset": byte_offset,
            "source": os.path.basename(path),
        })

    def _log_row_epoch(row: Dict[str, Any]) -> float:
        text = str(row.get("time") or row.get("raw") or "")
        match = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", text)
        if not match:
            return 0.0
        try:
            return datetime.fromisoformat(match.group(1).replace(" ", "T")).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return 0.0

    if parsed_rows:
        parsed_rows.sort(key=_log_row_epoch)
    if tail > 0 and len(parsed_rows) > tail:
        parsed_rows = parsed_rows[-tail:]

    next_offset = merged[-1][0] + len(merged[-1][1].encode("utf-8", errors="replace")) if merged else 0
    counts = {"info": 0, "warn": 0, "error": 0, "debug": 0}
    for row in parsed_rows:
        key = str(row.get("level") or "info")
        if key in counts:
            counts[key] += 1

    return {
        "lines": parsed_rows,
        "total": len(parsed_rows),
        "next_offset": next_offset,
        "sources": [os.path.basename(p) for p in paths],
        "counts": counts,
        "service_id": service_id,
        "session_started_at": session_started_at,
        "filters": {
            "current_session_only": bool(current_session_only),
            "hide_lifecycle": bool(hide_lifecycle),
        },
    }

def _local_service_status_snapshot(project_id: str, topology_node_id: str, service_id: str) -> Dict[str, Any]:
    node = _resolve_ops_dispatch_node(project_id, topology_node_id)
    if not node:
        return {"ok": False, "message": "topology node not found"}
    port = int(node.get("port") or node.get("remote_game_server_port") or 0)
    cs_map = _fetch_cluster_runtime_status()
    raw_svc = {
        "service_id": service_id,
        "node_id": topology_node_id,
        "service_port": port,
        "remote_game_server_port": port,
        "service_type": node.get("role") or node.get("service_type") or "",
    }
    resolved = _resolve_service_runtime_state(raw_svc, host="127.0.0.1", cluster_status=cs_map)
    metrics = _sample_local_control_metrics()
    st = str(resolved.get("run_state") or resolved.get("status") or "UNKNOWN").upper()
    labels = {
        "RUNNING": "运行中",
        "ONLINE": "运行中",
        "READY": "运行中",
        "STARTING": "启动中",
        "STOPPED": "已停止",
        "OFFLINE": "离线",
        "UNKNOWN": "未知",
    }
    return {
        "ok": True,
        "message": f"{service_id} 当前状态：{labels.get(st, st)}",
        "data": {
            "service_id": service_id,
            "node_id": topology_node_id,
            "status": resolved.get("status"),
            "run_state": resolved.get("run_state"),
            "status_label": labels.get(st, st),
            "probe_status": resolved.get("probe_status"),
            "probe_method": resolved.get("probe_method"),
            "cluster_state": resolved.get("cluster_state"),
            "port": port,
            "host": "127.0.0.1",
            "metrics": metrics,
            "sampled_at": _now_iso(),
        },
        "mode": "direct-local",
    }

def _clear_gameserver_launch_slot(service_id: str) -> None:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return
    with _GAMESERVER_LAUNCH_GUARD:
        _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)

def _gameserver_launch_slot_active(service_id: str) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return False
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if not isinstance(slot, dict):
            return False
        if float(slot.get("until") or 0.0) <= time.monotonic():
            _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)
            return False
        return True

def _try_acquire_gameserver_launch_slot(service_id: str, ttl_sec: float = _GAMESERVER_LAUNCH_LOCK_TTL_SEC) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return False
    now = time.monotonic()
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if isinstance(slot, dict) and float(slot.get("until") or 0.0) > now:
            return False
        _GAMESERVER_LAUNCH_SLOTS[sid] = {
            "until": now + max(30.0, float(ttl_sec)),
            "thread": threading.current_thread().ident,
        }
        return True

def _release_gameserver_launch_slot(service_id: str) -> None:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return
    ident = threading.current_thread().ident
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if isinstance(slot, dict) and slot.get("thread") not in (None, ident):
            return
        _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)

def _launch_gameserver_service(
    service_id: str,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    _reconcile_gameserver_daemon_state(sid)
    if _gameserver_service_live(sid, node, probe_host=host):
        live_pid = _find_gameserver_pid_by_service(sid) or int((_get_daemon_state(sid).get("pid") or 0))
        tcp_port = _gameserver_tcp_probe_port(sid, node)
        repo = _resolve_game_server_repo()
        log_path = _gameserver_service_log_path(repo, sid)
        try:
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(
                    f"[{_now_iso()}] daemon start skipped: {sid} already running "
                    f"pid={live_pid or 0}{', port ' + str(tcp_port) if tcp_port > 0 else ''}\n"
                )
        except Exception:
            pass
        return {
            "success": True,
            "message": f"{sid} 已在运行 (pid {live_pid or '-'}{', port ' + str(tcp_port) if tcp_port > 0 else ''})",
            "data": {"service_id": sid, "pid": live_pid, "already_running": True, "live": True, "log": log_path},
        }
    if _gameserver_launch_slot_active(sid) and not _gameserver_service_live(sid, node, probe_host=host):
        _clear_gameserver_launch_slot(sid)
    if not _try_acquire_gameserver_launch_slot(sid, ttl_sec=max(60.0, float(timeout_sec) + 30.0)):
        return {"success": False, "message": f"{sid} 启动正在进行中，请稍候再试"}
    try:
        return _launch_gameserver_service_impl(sid, reason, wait_ready, timeout_sec, node, probe_host=host)
    finally:
        _release_gameserver_launch_slot(sid)

def _launch_all_gameserver_services_in_order(
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    last: Dict[str, Any] = {"success": False, "message": "no services"}
    for sid in _GAMESERVER_START_ORDER:
        last = _launch_gameserver_service(sid, reason, wait_ready, timeout_sec)
        if not last.get("success"):
            return last
        time.sleep(0.8)
    return last

def _launch_local_game_server(
    service_id: str = "",
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 180,
    node: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    if sid:
        return _launch_gameserver_service(sid, reason, wait_ready, timeout_sec, node)
    return _launch_all_gameserver_services_in_order(reason, wait_ready, timeout_sec)

def _sync_gameserver_runtime_config(repo: str, cfg_dir: str) -> None:
    import shutil

    src_cfg = os.path.join(repo, "config")
    os.makedirs(cfg_dir, exist_ok=True)
    os.makedirs(os.path.join(cfg_dir, "config"), exist_ok=True)
    for name in ("cluster.json", "appsettings.json"):
        src = os.path.join(src_cfg, name)
        if not os.path.isfile(src):
            continue
        for dst in (os.path.join(cfg_dir, name), os.path.join(cfg_dir, "config", name)):
            try:
                if os.path.isfile(dst):
                    with open(src, "rb") as sfp, open(dst, "rb") as dfp:
                        if sfp.read() == dfp.read():
                            continue
                shutil.copy2(src, dst)
            except Exception:
                pass

def _gameserver_instance_dir(repo: str, service_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "gameserver").strip()) or "gameserver"
    return os.path.join(repo, "tools", "SmokeTest", "artifacts", "instances", safe)

def _prepare_gameserver_instance(repo: str, service_id: str) -> Tuple[str, str]:
    """为每个服务准备独立运行目录，避免多进程争用同一份 cluster 日志。"""
    import shutil

    src_exe, src_dir = _resolve_gameserver_executable(repo)
    if not src_exe:
        return "", ""
    inst_dir = _gameserver_instance_dir(repo, service_id)
    inst_exe = os.path.join(inst_dir, os.path.basename(src_exe))
    src_stamp = str(int(os.path.getmtime(src_exe)))
    stamp_file = os.path.join(inst_dir, ".build_stamp")
    need_copy = not os.path.isfile(inst_exe)
    if os.path.isfile(stamp_file):
        try:
            with open(stamp_file, "r", encoding="utf-8") as fp:
                need_copy = need_copy or fp.read().strip() != src_stamp
        except Exception:
            need_copy = True
    else:
        need_copy = True
    if need_copy:
        if os.path.isdir(inst_dir):
            shutil.rmtree(inst_dir, ignore_errors=True)
        shutil.copytree(src_dir, inst_dir)
        os.makedirs(os.path.join(inst_dir, "logs"), exist_ok=True)
        with open(stamp_file, "w", encoding="utf-8") as fp:
            fp.write(src_stamp)
    _sync_gameserver_runtime_config(repo, inst_dir)
    return inst_exe, inst_dir

def _resolve_gameserver_executable(repo: str) -> Tuple[str, str]:
    names = ("GameServer.GameServerApp.exe", "GameServer.GameServerApp") if os.name == "nt" else (
        "GameServer.GameServerApp",
        "GameServer.GameServerApp.exe",
    )
    for config in ("Debug", "Release"):
        cfg_dir = os.path.join(repo, "game-server", "bin", config)
        for name in names:
            exe = os.path.join(cfg_dir, name)
            if os.path.isfile(exe):
                return exe, cfg_dir
        dll = os.path.join(cfg_dir, "GameServer.GameServerApp.dll")
        if os.path.isfile(dll):
            return dll, cfg_dir
    return "", ""

def _launch_gameserver_unified_all(
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    """Windows 本地 E2E/业务测试：单进程 --all 启动，避免 Partial 多实例无法 WS 登录路由。"""
    repo = _resolve_game_server_repo()
    exe, cfg_dir = _resolve_gameserver_executable(repo)
    if not exe:
        return {"success": False, "message": "未找到 GameServer.GameServerApp.exe，请先编译 game-server Debug/Release"}
    if _probe_tcp_open("127.0.0.1", 15050, timeout=0.35) and _ws_handshake_probe()[0]:
        gs_count = _count_gameserver_processes()
        if gs_count == 1:
            return {
                "success": True,
                "message": "GameServer --all 已在运行 (ws://127.0.0.1:15050/ws/)",
                "data": {"mode": "unified-all", "already_running": True, "live": True},
            }
    _stop_local_game_server()
    time.sleep(1.2)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "unified-all"
    log_path = os.path.join(repo, "game-server", "bin", "Debug", "logs", "ops-unified-all.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cmd = [exe, "--all", "--headless", "--headless-seconds=86400"]
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(f"\n[{_now_iso()}] unified-all launch reason={reason_note} cmd={' '.join(cmd)}\n")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cfg_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception as ex:
        return {"success": False, "message": f"GameServer --all 启动失败: {ex}"}
    if not wait_ready:
        return {
            "success": True,
            "message": f"GameServer --all 已在后台启动 (pid {proc.pid})",
            "data": {"pid": int(proc.pid), "mode": "unified-all", "starting": True},
        }
    deadline = time.time() + max(25, int(timeout_sec))
    exit_code: Optional[int] = None
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        ws_ok, _ = _ws_handshake_probe()
        if ws_ok and _probe_tcp_open("127.0.0.1", 5504, timeout=0.35):
            for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
                _set_daemon_state(sid, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            return {
                "success": True,
                "message": f"GameServer --all 已就绪 (pid {proc.pid}, ws 15050, ops 5504)",
                "data": {"pid": int(proc.pid), "mode": "unified-all", "live": True, "log": log_path},
            }
        time.sleep(1.0)
    if exit_code is not None:
        return {"success": False, "message": f"GameServer --all 进程退出 code={exit_code}", "data": {"returncode": exit_code}}
    return {"success": False, "message": "GameServer --all 启动超时：15050/5504 未就绪", "data": {"pid": int(proc.pid)}}

def _should_use_unified_gameserver_all(app_ids: List[str], service_bindings: Dict[str, str]) -> bool:
    """Dev-only escape hatch; distributed multi-process is the default orchestration path."""
    if str(os.getenv("OPS_DEV_UNIFIED_GAMESERVER_ALL") or "").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    if os.name != "nt":
        return False
    gs_nodes = {
        str((service_bindings or {}).get(nid) or nid).strip().lower()
        for nid in (app_ids or [])
    }
    return bool(gs_nodes & set(_GAMESERVER_PROCESS_SERVICE_IDS))

def _wait_gameserver_tcp_port_free(
    port: int,
    timeout_sec: float = 20.0,
    probe_host: str = DEFAULT_LOOPBACK,
) -> bool:
    if port <= 0:
        return True
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    deadline = time.time() + max(1.0, float(timeout_sec))
    while time.time() < deadline:
        if not _probe_tcp_open(host, port, timeout=0.25):
            return True
        time.sleep(0.4)
    return not _probe_tcp_open(host, port, timeout=0.25)

def _latest_instance_cluster_log_path(repo: str, service_id: str) -> str:
    inst_logs = os.path.join(_gameserver_instance_dir(repo, service_id), "logs")
    if not os.path.isdir(inst_logs):
        return ""
    candidates = [
        os.path.join(inst_logs, name)
        for name in os.listdir(inst_logs)
        if name.startswith("cluster-") and name.endswith(".log")
    ]
    if not candidates:
        return ""
    try:
        return max(candidates, key=lambda p: os.path.getmtime(p))
    except Exception:
        return candidates[0]

def _sanitize_user_facing_text(text: str, max_len: int = 200) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\uFFFD]", "", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    noise = ("可用命令", "cluster>", "--servers=", "--all", "--gm", "windows-native launch")
    if any(token in cleaned for token in noise):
        return ""
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned

def _extract_cluster_error_hint(cluster_log_path: str, since_pos: int = 0) -> str:
    if not cluster_log_path or not os.path.isfile(cluster_log_path):
        return ""
    try:
        lines = _read_text_file_lines(cluster_log_path)
        chunk = "".join(lines)
        if since_pos > 0 and since_pos < len(chunk.encode("utf-8", errors="replace")):
            chunk = chunk[max(0, since_pos // 2):]
    except Exception:
        return ""
    hints: List[str] = []
    for line in chunk.splitlines():
        text = line.strip()
        if not text:
            continue
        upper = text.upper()
        if not any(token in text for token in ("[ERROR]", "异常", "失败", "FATAL", "IOException", "冲突")) and \
                not any(token in upper for token in ("[ERROR]", "[FATAL]", "FAIL")):
            continue
        parsed = _sanitize_user_facing_text(text, max_len=180)
        if parsed:
            hints.append(parsed)
    return hints[-1] if hints else ""

def _format_gameserver_launch_failure(
    service_id: str,
    *,
    exit_code: Optional[int],
    live: bool,
    tcp_port: int,
    repo: str,
    log_path: str,
    cluster_log_pos: int = 0,
) -> str:
    sid = str(service_id or "").strip()
    parts: List[str] = []
    if exit_code is not None and int(exit_code) != 0:
        unsigned = int(exit_code) & 0xFFFFFFFF
        if unsigned in (3221225794, 3221225477):
            parts.append("进程初始化失败，常见原因是端口残留或实例文件损坏")
        else:
            parts.append(f"进程退出码 {exit_code}")
    if tcp_port > 0 and not live:
        parts.append(f"端口 {tcp_port} 未就绪")
    cluster_hint = _extract_cluster_error_hint(_latest_instance_cluster_log_path(repo, sid), cluster_log_pos)
    if cluster_hint:
        parts.append(cluster_hint)
    if not parts:
        parts.append("请打开「查看日志」查看本次启动详情")
    return f"{sid} 启动失败：{'；'.join(parts)}"

def _launch_gameserver_service_impl(
    service_id: str,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {"success": False, "message": f"不支持的 GameServer 服务: {service_id}"}
    port = _gameserver_service_port(sid, node)
    tcp_port = _gameserver_tcp_probe_port(sid, node)
    if _gameserver_service_live(sid, node, probe_host=host):
        live_pid = _find_gameserver_pid_by_service(sid) or int((_get_daemon_state(sid).get("pid") or 0))
        return {
            "success": True,
            "message": f"{sid} 已在运行 (pid {live_pid or '-'}{', port ' + str(tcp_port) if tcp_port > 0 else ''})",
            "data": {"service_id": sid, "port": port, "pid": live_pid, "already_running": True, "live": True},
        }
    stale_pid = _find_gameserver_pid_by_service(sid)
    if stale_pid > 0:
        _kill_tracked_pid(stale_pid)
        time.sleep(0.8)
    if tcp_port > 0:
        if _find_gameserver_pid_by_service(sid) > 0 or _gameserver_service_live(sid, node, probe_host=host):
            _stop_gameserver_service(sid, node, probe_host=host)
        if _probe_tcp_open(host, tcp_port, timeout=0.25) and not _wait_gameserver_tcp_port_free(
            tcp_port, timeout_sec=20.0, probe_host=host
        ):
            return {
                "success": False,
                "message": f"{sid} 启动失败：端口 {tcp_port} 仍被占用，请稍后重试",
                "data": {"service_id": sid, "port": port, "live": False},
            }

    repo = _resolve_game_server_repo()
    log_path = _gameserver_service_log_path(repo, sid)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    if os.name == "nt":
        try:
            return _launch_gameserver_service_windows(
                repo, sid, port, reason, wait_ready, timeout_sec, log_path, probe_host=host
            )
        except Exception as ex:
            return {"success": False, "message": f"启动 {sid} 失败: {ex}"}

    exe, cfg_dir = _resolve_gameserver_executable(repo)
    if not exe:
        script = os.path.join(repo, "scripts", "Start-GameServer.sh")
        return {"success": False, "message": f"未找到 GameServer 可执行文件或脚本: {script}"}
    return _launch_gameserver_service_posix(
        repo, sid, port, reason, wait_ready, timeout_sec, log_path, exe, cfg_dir, probe_host=host
    )

def _launch_gameserver_service_posix(
    repo: str,
    service_id: str,
    port: int,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    log_path: str = "",
    exe: str = "",
    cfg_dir: str = "",
    probe_host: str = DEFAULT_LOOPBACK,
) -> Dict[str, Any]:
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    server_args = _gameserver_service_launch_args(service_id)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "service-action"
    launch_exe = str(exe or "").strip()
    launch_cwd = str(cfg_dir or repo).strip()
    cmd: List[str]
    if launch_exe.endswith(".dll"):
        cmd = ["dotnet", launch_exe, *server_args]
    else:
        cmd = [launch_exe, *server_args]
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(
            f"\n[{_now_iso()}] posix launch service={service_id} reason={reason_note} "
            f"cmd={' '.join(cmd)}\n"
        )
        log_fp.flush()
    proc = subprocess.Popen(cmd, cwd=launch_cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _set_daemon_state(service_id, {"status": "STARTING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    if not wait_ready:
        return {
            "success": True,
            "message": f"{service_id} 已在后台启动",
            "data": {"pid": int(proc.pid), "service_id": service_id, "log": log_path, "exe": launch_exe, "starting": True},
        }
    tcp_port = _gameserver_tcp_probe_port(service_id)
    deadline = time.time() + max(20, int(timeout_sec))
    exit_code: Optional[int] = None
    ready_after = time.time() + 4.0
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            if tcp_port > 0:
                live = _probe_tcp_open(host, tcp_port, timeout=0.35)
            else:
                live = time.time() >= ready_after
        else:
            live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
        if live and (tcp_port > 0 or time.time() >= ready_after):
            _write_gameserver_session_marker(repo, int(proc.pid), service_id)
            _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
            return {
                "success": True,
                "message": f"{service_id} 已就绪 ({ready_msg})",
                "data": {"pid": int(proc.pid), "service_id": service_id, "port": port, "live": True, "log": log_path, "exe": launch_exe},
            }
        time.sleep(0.8)
    if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
        live = _probe_tcp_open(host, tcp_port, timeout=0.5) if tcp_port > 0 else True
    else:
        live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
    ok = bool(live and exit_code is None)
    if ok:
        _write_gameserver_session_marker(repo, int(proc.pid), service_id)
        _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    else:
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            _kill_tracked_pid(int(proc.pid))
        _set_daemon_state(service_id, {"status": "ERROR", "pid": 0, "last_action": "start", "last_error": "launch failed"})
    ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
    msg = f"{service_id} 已就绪 ({ready_msg})" if ok else f"{service_id} 启动失败"
    return {"success": ok, "message": msg, "data": {"returncode": exit_code, "service_id": service_id, "port": port, "live": live, "log": log_path, "exe": launch_exe}}

def _launch_gameserver_service_windows(
    repo: str,
    service_id: str,
    port: int,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    log_path: str = "",
    probe_host: str = DEFAULT_LOOPBACK,
) -> Dict[str, Any]:
    """Windows 原生启动单个 GameServer 节点，禁止走 bash/WSL。"""
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    exe, cfg_dir = _prepare_gameserver_instance(repo, service_id)
    if not exe:
        return {"success": False, "message": "未找到 GameServer.GameServerApp.exe，请先在 game-server 目录编译 Debug/Release"}
    server_args = _gameserver_service_launch_args(service_id)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "service-action"
    cluster_log_path = _latest_instance_cluster_log_path(repo, service_id)
    cluster_log_pos = 0
    try:
        if cluster_log_path and os.path.isfile(cluster_log_path):
            cluster_log_pos = os.path.getsize(cluster_log_path)
    except Exception:
        cluster_log_pos = 0
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(
            f"\n[{_now_iso()}] windows-native launch service={service_id} reason={reason_note} "
            f"exe={exe} args={' '.join(server_args)}\n"
        )
        log_fp.flush()
    proc = subprocess.Popen(
        [exe, *server_args],
        cwd=cfg_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    _set_daemon_state(service_id, {"status": "STARTING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    if not wait_ready:
        return {
            "success": True,
            "message": f"{service_id} 已在后台启动",
            "data": {"pid": int(proc.pid), "service_id": service_id, "log": log_path, "exe": exe, "starting": True},
        }
    tcp_port = _gameserver_tcp_probe_port(service_id)
    deadline = time.time() + max(20, int(timeout_sec))
    exit_code: Optional[int] = None
    ready_after = time.time() + 4.0
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            if tcp_port > 0:
                live = _probe_tcp_open(host, tcp_port, timeout=0.35)
            else:
                live = time.time() >= ready_after
        else:
            live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
        if live and (tcp_port > 0 or time.time() >= ready_after):
            _write_gameserver_session_marker(repo, int(proc.pid), service_id)
            _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
            return {
                "success": True,
                "message": f"{service_id} 已就绪 ({ready_msg})",
                "data": {"pid": int(proc.pid), "service_id": service_id, "port": port, "live": True, "log": log_path, "exe": exe},
            }
        time.sleep(0.8)
    if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
        live = _probe_tcp_open(host, tcp_port, timeout=0.5) if tcp_port > 0 else True
    else:
        live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
    ok = bool(live and exit_code is None)
    if ok:
        _write_gameserver_session_marker(repo, int(proc.pid), service_id)
        _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    else:
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            _kill_tracked_pid(int(proc.pid))
        _set_daemon_state(service_id, {"status": "ERROR", "pid": 0, "last_action": "start", "last_error": "launch failed"})
    ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
    msg = (
        f"{service_id} 已就绪 ({ready_msg})"
        if ok
        else _format_gameserver_launch_failure(
            service_id,
            exit_code=exit_code,
            live=live,
            tcp_port=tcp_port,
            repo=repo,
            log_path=log_path,
            cluster_log_pos=cluster_log_pos,
        )
    )
    return {
        "success": ok,
        "message": msg,
        "data": {
            "returncode": exit_code,
            "service_id": service_id,
            "port": port,
            "live": live,
            "log": log_path,
            "exe": exe,
        },
    }

def _stop_gameserver_service(
    service_id: str,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {"success": False, "message": f"不支持的 GameServer 服务: {service_id}"}
    _clear_gameserver_launch_slot(sid)
    port = _gameserver_service_port(sid, node)
    tcp_port = _gameserver_tcp_probe_port(sid, node)
    state = _get_daemon_state(sid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    if pid <= 0 or not _is_process_running(pid):
        pid = _find_gameserver_pid_by_service(sid)
    for _ in range(4):
        if pid > 0:
            _kill_tracked_pid(pid)
        pid = _find_gameserver_pid_by_service(sid)
        if pid <= 0 and tcp_port > 0:
            port_pid = _find_pid_listening_on_port(tcp_port)
            if port_pid > 4:
                pid = port_pid
        if pid <= 0:
            break
        time.sleep(0.4)
    deadline = time.time() + 15.0
    while time.time() < deadline:
        if not _gameserver_service_live(sid, node, probe_host=host):
            _set_daemon_state(sid, {"status": "STOPPED", "pid": 0, "last_action": "stop", "last_error": ""})
            _clear_gameserver_session_marker(service_id=sid)
            detail = f"port {tcp_port}" if tcp_port > 0 else "process"
            return {"success": True, "message": f"已停止 {sid} 独立进程 ({detail})"}
        time.sleep(0.4)
    return {"success": False, "message": f"{sid} 仍在运行，停止未完成"}

def _stop_all_gameserver_services() -> Dict[str, Any]:
    try:
        for sid in reversed(_GAMESERVER_START_ORDER):
            _stop_gameserver_service(sid)
        if os.name == "nt":
            for cmd in (
                ["taskkill", "/F", "/IM", "GameServer.GameServerApp.exe"],
                ["taskkill", "/F", "/T", "/FI", "IMAGENAME eq GameServer.GameServerApp.exe"],
            ):
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
        else:
            subprocess.call(["pkill", "-f", "GameServer.GameServerApp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
            _clear_gameserver_session_marker(service_id=sid)
        open_ports = [p for p in _GAMESERVER_DEFAULT_PORTS.values() if _probe_tcp_open("127.0.0.1", p, timeout=0.25)]
        if open_ports:
            return {"success": False, "message": f"仍有 GameServer 端口在监听: {open_ports}"}
        return {"success": True, "message": "已停止全部 GameServer 独立进程"}
    except Exception as ex:
        return {"success": False, "message": f"停止 GameServer 失败: {ex}"}

def _stop_local_game_server() -> Dict[str, Any]:
    return _stop_all_gameserver_services()

def _daemon_probe_proto(node: Dict[str, Any]) -> str:
    role = str(node.get("role") or "").strip().lower()
    return "redis_ping" if role in ("cache", "redis") else "mongo_ping"

def _daemon_node_port(node: Dict[str, Any]) -> int:
    if not isinstance(node, dict):
        return 0
    port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or node.get("port") or 0)
    if port > 0:
        return port
    try:
        contract = _resolve_node_contract_for_topology_node(node)
        port = int(_resolve_topology_node_port(node, contract, None, None) or 0)
        if port > 0:
            return port
    except Exception:
        pass
    nid = str(node.get("id") or "").strip().lower()
    role = str(node.get("role") or "").strip().lower()
    if role in ("cache", "redis") or "redis" in nid:
        return 6379
    if role in ("database", "mongo") or "mongo" in nid:
        return 27017
    return 0

def _resolve_mongod_executable() -> str:
    if os.name != "nt":
        return ""
    try:
        import glob

        hits = sorted(glob.glob(r"C:\Program Files\MongoDB\Server\*\bin\mongod.exe"), reverse=True)
        if hits:
            return str(hits[0])
    except Exception:
        pass
    return ""

def _wait_daemon_port_open(node: Dict[str, Any], timeout_sec: float = 30.0) -> bool:
    port = _daemon_node_port(node)
    if port <= 0:
        return False
    proto = _daemon_probe_proto(node)
    deadline = time.time() + max(2.0, float(timeout_sec))
    while time.time() < deadline:
        if _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            return True
        time.sleep(0.5)
    return False

def _start_external_daemon_node(node: Dict[str, Any], act: str = "start") -> Dict[str, Any]:
    """本机守护进程启动：Windows 走服务/可执行文件，避免 Test-NetConnection 拖慢与误报成功。"""
    nid = str(node.get("id") or "")
    port = _daemon_node_port(node)
    role = str(node.get("role") or "").strip().lower()
    log_path = _daemon_log_path(nid)
    lines: List[str] = [f"[{_now_iso()}] daemon {act} begin port={port} role={role}"]

    if port > 0 and _probe_by_protocol("127.0.0.1", port, _daemon_probe_proto(node)).get("ok"):
        try:
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(f"[{_now_iso()}] daemon {act} skipped: port {port} already listening\n")
        except Exception:
            pass
        state = _set_daemon_state(nid, {"status": "RUNNING", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path})
        return {
            "success": True,
            "message": f"daemon already running on port {port}",
            "data": {"node_id": nid, "status": "RUNNING", "pid": 0, "state": state, "log_path": log_path},
        }

    if os.name == "nt":
        if role in ("database", "mongo") or port == 27017:
            db_dir = _gomeku_mongo_dbpath()
            os.makedirs(db_dir, exist_ok=True)
            svc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Start-Service MongoDB -ErrorAction SilentlyContinue; "
                    "if ((Get-Service MongoDB -ErrorAction SilentlyContinue).Status -eq 'Running') { exit 0 } else { exit 1 }",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            lines.append(f"Start-Service MongoDB rc={svc.returncode} out={(svc.stdout or '').strip()} err={(svc.stderr or '').strip()}")
            if svc.returncode != 0:
                mongod = _resolve_mongod_executable()
                if mongod:
                    subprocess.Popen(
                        [mongod, "--dbpath", db_dir, "--port", str(port or 27017), "--bind_ip", "127.0.0.1"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
                    lines.append(f"fallback mongod={mongod}")
        elif role in ("cache", "redis") or port == 6379:
            svc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$s = Get-Service Memurai,MemuraiDeveloper,Redis -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.Status -eq 'Stopped' } | Select-Object -First 1; "
                    "if ($s) { Start-Service $s.Name -ErrorAction SilentlyContinue }; "
                    "if ((Get-Service Memurai,MemuraiDeveloper -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.Status -eq 'Running' } | Select-Object -First 1)) { exit 0 } else { exit 1 }",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            lines.append(f"Start-Service redis/memurai rc={svc.returncode} out={(svc.stdout or '').strip()} err={(svc.stderr or '').strip()}")
    else:
        start_cmd = str(node.get("daemon_start_cmd") or "").strip()
        if start_cmd:
            subprocess.Popen(start_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            lines.append(f"shell cmd={start_cmd[:200]}")

    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write("\n".join(lines) + "\n")

    live = _wait_daemon_port_open(node, timeout_sec=30.0)
    if live:
        state = _set_daemon_state(
            nid,
            {"status": "RUNNING", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path},
        )
        return {
            "success": True,
            "message": f"daemon {act} ok, port {port} listening",
            "data": {"node_id": nid, "status": "RUNNING", "pid": 0, "state": state, "log_path": log_path},
        }

    state = _set_daemon_state(
        nid,
        {"status": "ERROR", "pid": 0, "last_error": f"port {port} not listening", "last_action": act, "log_path": log_path},
    )
    return {
        "success": False,
        "message": f"daemon {act} failed: port {port} not listening (请检查 MongoDB/Memurai 服务是否已安装并可启动)",
        "data": {"node_id": nid, "status": "ERROR", "state": state, "log_path": log_path},
    }

def _wait_daemon_port_closed(node: Dict[str, Any], timeout_sec: float = 12.0) -> bool:
    port = _daemon_node_port(node)
    if port <= 0:
        return True
    proto = _daemon_probe_proto(node)
    deadline = time.time() + max(1.0, float(timeout_sec))
    while time.time() < deadline:
        if not _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            return True
        time.sleep(0.5)
    return False

def _kill_tracked_pid(pid: int) -> bool:
    if pid <= 0 or not _is_process_running(pid):
        return False
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return proc.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False

def _daemon_cmd_looks_unix_only(cmd: str) -> bool:
    """Windows 上跳过明显只能在 Unix/macOS 执行的守护进程命令。"""
    text = str(cmd or "").strip().lower()
    if not text:
        return False
    unix_markers = (
        "/tmp/",
        "/opt/homebrew/",
        "/usr/local/",
        "mongosh ",
        "redis-cli -p",
        " --fork",
        " --daemonize",
        "bash -lc",
        "pkill ",
    )
    if any(marker in text for marker in unix_markers):
        return True
    if text.startswith("mongod ") and "--dbpath /tmp" in text:
        return True
    return False

def _stop_external_daemon_node(node: Dict[str, Any], act: str = "stop") -> Dict[str, Any]:
    """停止本机 Mongo/Redis 等守护节点：优先 stop_cmd，再杀残留 PID，以端口关闭为准。"""
    nid = str(node.get("id") or "")
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    state = _get_daemon_state(nid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    log_path = _daemon_log_path(nid)
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(f"[{_now_iso()}] daemon {act} stop pid={pid} cmd={stop_cmd}\n")

    if stop_cmd and not (os.name == "nt" and _daemon_cmd_looks_unix_only(stop_cmd)):
        subprocess.call(stop_cmd, shell=True)

    _kill_tracked_pid(pid)

    port = _daemon_node_port(node)
    closed = _wait_daemon_port_closed(node, timeout_sec=12.0)
    if not closed and stop_cmd and not (os.name == "nt" and _daemon_cmd_looks_unix_only(stop_cmd)):
        subprocess.call(stop_cmd, shell=True)
        closed = _wait_daemon_port_closed(node, timeout_sec=8.0)

    if not closed and os.name == "nt":
        role = str(node.get("role") or "").strip().lower()
        kill_images: List[str] = []
        if role in ("database", "mongo") or port == 27017:
            kill_images = ["mongod.exe"]
        elif role in ("cache", "redis") or port == 6379:
            kill_images = ["memurai.exe", "redis-server.exe"]
        for image in kill_images:
            subprocess.run(
                ["taskkill", "/F", "/IM", image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        closed = _wait_daemon_port_closed(node, timeout_sec=8.0)

    if closed or port <= 0:
        state = _set_daemon_state(nid, {"status": "STOPPED", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path})
        return {
            "success": True,
            "message": "daemon stopped",
            "data": {"node_id": nid, "status": "STOPPED", "pid": 0, "state": state, "log_path": log_path},
        }

    state = _set_daemon_state(
        nid,
        {"status": "ERROR", "pid": 0, "last_error": f"port {port} still listening", "last_action": act, "log_path": log_path},
    )
    return {
        "success": False,
        "message": f"daemon stop failed: port {port} still listening",
        "data": {"node_id": nid, "status": "ERROR", "state": state, "log_path": log_path},
    }

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

def _windows_control_metrics() -> Dict[str, Any]:
    now = _now_iso()
    if os.name != "nt":
        return {"source": "runtime.sample", "updated_at": now}
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
                "$disk = Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\"; "
                "$mem = if ($os.TotalVisibleMemorySize -gt 0) { "
                "(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize) * 100 } else { 0 }; "
                "$dsk = if ($disk -and $disk.Size -gt 0) { (($disk.Size - $disk.FreeSpace) / $disk.Size) * 100 } else { 0 }; "
                "[pscustomobject]@{cpu=[double]$cpu; mem=[double]$mem; disk=[double]$dsk} | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            return {"source": "runtime.sample", "updated_at": now}
        payload = json.loads(raw)
        return {
            "cpu_percent": round(float(payload.get("cpu") or 0.0), 1),
            "mem_percent": round(float(payload.get("mem") or 0.0), 1),
            "disk_percent": round(float(payload.get("disk") or 0.0), 1),
            "source": "runtime.sample",
            "updated_at": now,
        }
    except Exception:
        return {"source": "runtime.sample", "updated_at": now}

def _fallback_local_control_metrics() -> Dict[str, Any]:
    """psutil 不可用时的轻量采样。"""
    now = _now_iso()
    if os.name == "nt":
        sample = _windows_control_metrics()
        if any(sample.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent")):
            return sample
    out: Dict[str, Any] = {"source": "runtime.sample", "updated_at": now}
    try:
        if sys.platform == "darwin":
            load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
            cores = max(1, os.cpu_count() or 1)
            out["cpu_percent"] = round(min(100.0, (float(load) / float(cores)) * 100.0), 1)
        proc = subprocess.run(["df", "-k", "/"], capture_output=True, text=True, timeout=2)
        if proc.returncode == 0:
            lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
            if len(lines) >= 2:
                parts = lines[-1].split()
                if len(parts) >= 5 and parts[-2].endswith("%"):
                    out["disk_percent"] = round(float(parts[-2].rstrip("%")), 1)
    except Exception:
        pass
    return out

def _refresh_services_live_state(
    services: List[Dict[str, Any]],
    host: str = "127.0.0.1",
    project_id: str = "",
    cluster_status: Optional[Dict[str, str]] = None,
    agent: Optional[Dict[str, Any]] = None,
    fast_probe: bool = False,
    probe_timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    sample = {} if fast_probe else _sample_local_control_metrics()
    cs_map = cluster_status if isinstance(cluster_status, dict) else {}
    if not cs_map and project_id and not fast_probe:
        try:
            cs_map = _fetch_cluster_runtime_status_cached(_agents_v2_for_project(project_id))
        except Exception:
            cs_map = {}
    pt = float(probe_timeout) if probe_timeout is not None else (0.12 if fast_probe else 0.35)
    rows = [raw for raw in (services or []) if isinstance(raw, dict)]

    def _probe_one(raw: Dict[str, Any]) -> Dict[str, Any]:
        svc_host = _resolve_agent_probe_host(agent, raw) if agent else host
        svc = _resolve_service_runtime_state(
            raw,
            host=svc_host,
            cluster_status=cs_map,
            probe_timeout=pt,
            fast_probe=fast_probe,
        )
        if not fast_probe:
            metrics = svc.get("metrics") if isinstance(svc.get("metrics"), dict) else {}
            merged = dict(metrics)
            if str(svc.get("probe_status") or "").upper() == "PASS":
                for key in ("cpu_percent", "mem_percent", "disk_percent", "source", "updated_at"):
                    if sample.get(key) is not None and merged.get(key) is None:
                        merged[key] = sample.get(key)
            if merged:
                svc["metrics"] = merged
            svc["updated_at"] = str(svc.get("updated_at") or sample.get("updated_at") or _now_iso())
        return svc

    if len(rows) <= 1:
        return [_probe_one(raw) for raw in rows]
    out: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(rows))) as pool:
        for svc in pool.map(_probe_one, rows):
            out.append(svc)
    return out

def _execute_canonical_service_action(
    project_id: str,
    topology_node_id: str,
    service_id: str,
    action: str,
    operator: str,
    reason: str,
    ticket_id: str,
    body_payload: Dict[str, Any],
) -> Dict[str, Any]:
    act = str(action or "").strip().lower()
    node = _resolve_ops_dispatch_node(project_id, topology_node_id)
    if not node:
        return {"ok": False, "message": "topology node not found", "mode": "direct"}

    if _is_external_daemon_node(node):
        result = _ops_platform_daemon_action(node, act, reason, ticket_id, operator)
        ok = bool(result.get("success"))
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if not ok:
            return {
                "ok": False,
                "message": str(result.get("message") or "daemon action failed"),
                "data": data,
                "mode": "daemon",
            }
        if ok:
            contract = _resolve_node_contract_for_topology_node(node if isinstance(node, dict) else {})
            port = _resolve_topology_node_port(node if isinstance(node, dict) else {}, contract, None, None)
            role = str(node.get("role") or contract.get("role") or "").strip().lower()
            probe_proto = str(contract.get("probe_strategy") or "tcp").strip().lower()
            if role in ("cache", "redis"):
                probe_proto = "redis_ping"
            elif role in ("database", "mongo"):
                probe_proto = "mongo_ping"
            live = False
            if port > 0:
                for attempt in range(24 if act in ("start", "restart") else 1):
                    probe = _probe_by_protocol("127.0.0.1", port, probe_proto)
                    live = bool(probe.get("ok"))
                    if live or act not in ("start", "restart"):
                        break
                    time.sleep(0.5)
            if act == "stop":
                st = "STOPPED"
            elif live:
                st = "RUNNING"
            elif act in ("start", "restart"):
                st = "STARTING"
            else:
                st = "STOPPED"
            _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="PASS" if live else "FAIL")
        return {"ok": ok, "message": str(result.get("message") or ""), "data": result.get("data") or {}, "mode": "daemon"}

    if act == "status":
        return _local_service_status_snapshot(project_id, topology_node_id, service_id)

    if act == "logs":
        log_payload = _read_gameserver_service_logs(service_id, tail=500)
        return {
            "ok": True,
            "message": f"已读取 GameServer 日志（{log_payload.get('total', 0)} 条）",
            "data": log_payload,
            "mode": "direct-local",
        }

    if _is_gameserver_process_service_id(service_id) and act in ("start", "stop", "restart"):
        _reconcile_gameserver_daemon_state(service_id)
        port = _gameserver_service_port(service_id, node)
        if act == "restart":
            stop_res = _stop_gameserver_service(service_id, node)
            if not stop_res.get("success"):
                return {
                    "ok": False,
                    "message": str(stop_res.get("message") or "restart stop failed"),
                    "data": {},
                    "mode": "direct-local-process",
                }
            act = "start"
        if act == "stop":
            stop_res = _stop_gameserver_service(service_id, node)
            ok = bool(stop_res.get("success"))
            metrics = _sample_local_control_metrics()
            if ok:
                _apply_service_runtime_after_action(service_id, status="STOPPED", live=False, metrics=metrics)
            else:
                _update_canonical_service_runtime(
                    service_id,
                    status="ERROR",
                    run_state="ERROR",
                    probe_status="FAIL",
                    last_action="stop",
                    metrics=metrics,
                )
            canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
            if isinstance(canonical, dict):
                _append_realtime_agent_sample(canonical)
            return {
                "ok": ok,
                "message": str(stop_res.get("message") or ("已停止" if ok else "停止失败")),
                "data": {"service_id": service_id, "port": port, "status": "STOPPED" if ok else "ERROR", "last_action": "stop"},
                "mode": "direct-local-process",
            }
        launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
        ok = bool(launch.get("success"))
        live = bool((launch.get("data") or {}).get("live")) or _gameserver_service_live(service_id, node)
        metrics = _sample_local_control_metrics()
        if ok:
            st = "RUNNING" if live else "STARTING"
            _apply_service_runtime_after_action(service_id, status=st, live=live, metrics=metrics)
            _update_canonical_service_runtime(service_id, last_action="start")
        else:
            _update_canonical_service_runtime(
                service_id,
                status="ERROR",
                run_state="ERROR",
                probe_status="FAIL",
                last_action="start",
                metrics=metrics,
            )
        canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
        if isinstance(canonical, dict):
            _append_realtime_agent_sample(canonical)
        return {
            "ok": ok,
            "message": str(launch.get("message") or ("启动成功" if ok else "启动失败")),
            "data": {
                **(launch.get("data") if isinstance(launch.get("data"), dict) else {}),
                "status": "RUNNING" if ok and live else ("STARTING" if ok else "ERROR"),
                "last_action": "start",
            },
            "mode": "direct-local-process",
        }

    ops_node = _resolve_ops_dispatch_node(project_id, "ops-cn-1") or node
    map_action = {"start": "start", "stop": "stop", "restart": "restart", "status": "status", "probe": "health_check", "logs": "log_tail"}.get(act, act)
    result = ops_gateway.execute_platform_action(
        ops_node,
        action_type=map_action,
        target=service_id,
        payload=body_payload,
        actor=operator,
        reason=reason,
        ticket_id=ticket_id,
        dry_run=False,
    )
    ok = bool(result.get("success"))

    if not ok and act == "start" and _is_gameserver_process_service_id(service_id):
        launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
        if launch.get("success"):
            live = bool((launch.get("data") or {}).get("live")) or _gameserver_service_live(service_id, node)
            ok = True
            result = {
                "success": True,
                "message": str(launch.get("message") or ("服务已在运行" if live else "服务启动中")),
                "data": dict(launch.get("data") or {}, starting=not live),
            }
        else:
            result = launch

    if not ok and act in ("stop", "restart") and _is_gameserver_process_service_id(service_id):
        stop_res = _stop_gameserver_service(service_id, node)
        if stop_res.get("success"):
            ok = act == "stop"
            result = stop_res
            if act == "restart":
                launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
                ok = bool(launch.get("success"))
                result = launch
        else:
            result = stop_res

    if not ok and act == "stop":
        port = int(node.get("port") or node.get("remote_game_server_port") or 0)
        if port > 0:
            time.sleep(1.2)
            if not _probe_tcp_open("127.0.0.1", port):
                ok = True
                result = {"success": True, "message": "服务端口已释放", "data": {"status": "STOPPED"}}

    if ok:
        live = _gameserver_service_live(service_id, node) if _is_gameserver_process_service_id(service_id) else (
            _probe_tcp_open("127.0.0.1", int(node.get("port") or node.get("remote_game_server_port") or 0))
            if int(node.get("port") or node.get("remote_game_server_port") or 0) > 0
            else bool((result.get("data") or {}).get("starting"))
        )
        st = "STARTING" if (result.get("data") or {}).get("starting") else ("RUNNING" if act != "stop" and live else ("STOPPED" if act == "stop" else "RUNNING"))
        metrics = _sample_local_control_metrics()
        _apply_service_runtime_after_action(service_id, status=st, live=live, metrics=metrics)
        canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
        if isinstance(canonical, dict):
            _append_realtime_agent_sample(canonical)

    return {
        "ok": ok,
        "message": str(result.get("message") or ("success" if ok else "service action failed")),
        "data": result.get("data") if isinstance(result.get("data"), dict) else {},
        "mode": "direct",
    }

def _ops_platform_daemon_action(node: Dict[str, Any], action: str, reason: str, ticket_id: str, operator: str) -> Dict[str, Any]:
    nid = str(node.get("id") or "")
    act = str(action or "").strip().lower()
    server_id = str(node.get("server_id") or "").strip()
    role = str(node.get("role") or "").strip()
    start_cmd = str(node.get("daemon_start_cmd") or "").strip()
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    state = _get_daemon_state(nid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    local_daemon = _is_external_daemon_node(node)

    # Prefer native Ops API path in distributed deployment.
    if server_id and act in ("start", "stop", "restart", "status") and not local_daemon:
        map_action = {"start": "start", "stop": "stop", "restart": "restart", "status": "status"}.get(act, "status")
        result = ops_gateway.execute_platform_action(
            node,
            action_type=map_action,
            target=server_id,
            payload={},
            actor=operator,
            reason=reason,
            ticket_id=ticket_id,
            dry_run=False,
        )
        ok = bool(result.get("success"))
        if ok:
            new_status = "RUNNING" if act in ("start", "restart", "status") else "STOPPED"
            _set_daemon_state(nid, {"status": new_status, "last_error": "", "last_action": act})
        else:
            _set_daemon_state(nid, {"status": "ERROR", "last_error": str(result.get("message") or ""), "last_action": act})
        return result

    if act == "status":
        port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or 0)
        probe_role = str(node.get("role") or role or "").strip().lower()
        proto = "redis_ping" if probe_role in ("cache", "redis") else "mongo_ping"
        port_live = bool(_probe_by_protocol("127.0.0.1", port, proto).get("ok")) if port > 0 else False
        proc_live = _is_process_running(pid) if pid > 0 else False
        if port_live:
            now_status = "RUNNING"
            state = _set_daemon_state(nid, {"status": now_status, "last_error": "", "last_action": "status", "pid": pid if proc_live else 0})
        elif proc_live:
            now_status = "RUNNING"
        elif pid > 0:
            now_status = "CRASHED"
            state = _set_daemon_state(nid, {"status": now_status, "last_error": "process not alive", "pid": 0, "last_action": "status"})
        else:
            now_status = str(state.get("status") or "ADDED")
        return {"success": True, "message": "daemon status (local fallback)", "data": {"node_id": nid, "status": now_status, "pid": pid, "state": state}}

    port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or 0)
    if act in ("start", "restart") and port > 0:
        role = str(node.get("role") or "").strip().lower()
        proto = "redis_ping" if role in ("cache", "redis") else "mongo_ping"
        if _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            log_path = _daemon_log_path(nid)
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(f"[{_now_iso()}] daemon {act} skipped: port {port} already listening\n")
            state = _set_daemon_state(nid, {"status": "RUNNING", "pid": pid or 0, "last_error": "", "last_action": act, "log_path": log_path})
            return {
                "success": True,
                "message": f"daemon already running on port {port}",
                "data": {"node_id": nid, "status": "RUNNING", "pid": pid, "state": state, "log_path": log_path},
            }

    if act == "restart":
        stop_res = _stop_external_daemon_node(node, "restart")
        if not stop_res.get("success"):
            return stop_res
        act = "start"
        state = _get_daemon_state(nid)
        pid = 0

    if act in ("start", "restart") and (local_daemon or start_cmd):
        return _start_external_daemon_node(node, act)

    if act == "stop":
        return _stop_external_daemon_node(node, "stop")

    return {"success": False, "message": "no daemon control profile configured for this node", "data": {"node_id": nid, "role": role}}

def _run_flow_step(node: Dict[str, Any], step: Dict[str, Any]) -> Dict[str, Any]:
    action_type = str(step.get("action_type") or "").strip()
    target = str(step.get("target") or node.get("server_id") or "").strip()
    ticket_id = str(step.get("ticket_id") or "OPS-FLOW").strip()
    reason = str(step.get("reason") or "flow step").strip()
    payload = step.get("payload") if isinstance(step.get("payload"), dict) else {}
    dry_run = bool(step.get("dry_run"))
    operator = str(session.get("user") or "intranet-ops")
    return ops_gateway.execute_platform_action(
        node,
        action_type=action_type,
        target=target,
        payload=payload,
        actor=operator,
        reason=reason,
        ticket_id=ticket_id,
        dry_run=dry_run,
    )

def _ops_topology_meta_structured(topo: Dict[str, Any]) -> None:
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    spacing = meta.get("layout_spacing") if isinstance(meta.get("layout_spacing"), dict) else None
    spacing_customized = bool(meta.get("layout_spacing_customized"))
    meta["layout_mode"] = "structured"
    meta["updated_at"] = _now_iso()
    if spacing is not None:
        meta["layout_spacing"] = _normalize_layout_spacing(spacing)
    if spacing_customized:
        meta["layout_spacing_customized"] = True
    topo["meta"] = meta

def _ops_topology_node_map(topo: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(n.get("id") or ""): n for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "")}

def _ops_topology_edge_list(topo: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = edges
    return edges

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

def _is_critical_topology_node(topo: Dict[str, Any], node_id: str) -> bool:
    nodes = [x for x in (topo.get("nodes") or []) if isinstance(x, dict)]
    edges = [x for x in (topo.get("edges") or []) if isinstance(x, dict)]
    target = None
    for n in nodes:
        if str(n.get("id") or "") == node_id:
            target = n
            break
    if not target:
        return False

    kind = str(target.get("kind") or "standard")
    linked_edges = [e for e in edges if str(e.get("from") or "") == node_id or str(e.get("to") or "") == node_id]
    if not linked_edges:
        return False

    if kind == "entry":
        other_entry = [n for n in nodes if str(n.get("id") or "") != node_id and str(n.get("kind") or "") == "entry"]
        if not other_entry:
            return True
    if kind == "terminal":
        other_terminal = [n for n in nodes if str(n.get("id") or "") != node_id and str(n.get("kind") or "") == "terminal"]
        if not other_terminal:
            return True

    incoming = list({str(e.get("from") or "") for e in edges if str(e.get("to") or "") == node_id})
    outgoing = list({str(e.get("to") or "") for e in edges if str(e.get("from") or "") == node_id})
    incoming = [x for x in incoming if x]
    outgoing = [x for x in outgoing if x]
    if incoming and outgoing:
        for s in incoming:
            for t in outgoing:
                if not _can_reach_without_node(edges, s, t, node_id):
                    return True
    return False

def _is_critical_topology_edge(topo: Dict[str, Any], edge_id: str) -> bool:
    nodes = [x for x in (topo.get("nodes") or []) if isinstance(x, dict)]
    edges = [x for x in (topo.get("edges") or []) if isinstance(x, dict)]
    if not nodes or not edges:
        return False
    target = None
    for e in edges:
        if str(e.get("id") or "") == edge_id:
            target = e
            break
    if not target:
        return False

    entry_ids = [str(n.get("id") or "") for n in nodes if str(n.get("kind") or "") == "entry"]
    term_ids = [str(n.get("id") or "") for n in nodes if str(n.get("kind") or "") == "terminal"]
    if not entry_ids or not term_ids:
        return False

    def _reachable(edge_rows: List[Dict[str, Any]], roots: List[str]) -> set:
        graph: Dict[str, List[str]] = {}
        for e in edge_rows:
            a = str(e.get("from") or "")
            b = str(e.get("to") or "")
            if not a or not b:
                continue
            graph.setdefault(a, []).append(b)
        seen = set(roots)
        queue = list(roots)
        while queue:
            cur = queue.pop(0)
            for nxt in graph.get(cur, []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return seen

    before = _reachable(edges, entry_ids)
    after = _reachable([e for e in edges if str(e.get("id") or "") != edge_id], entry_ids)
    for tid in term_ids:
        if tid in before and tid not in after:
            return True
    return False
