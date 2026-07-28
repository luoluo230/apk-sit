# -*- coding: utf-8 -*-
"""cluster.json import and sync to agents/topology."""

from __future__ import annotations

from services.ops import shared_bootstrap as _boot

globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})

def _gomeku_mongo_dbpath() -> str:
    """Mongo 数据目录：全平台统一使用项目 DATA_DIR。"""
    return os.path.join(DATA_DIR, "gomeku-mongo")

def _gameserver_repo_has_executable(repo: str) -> bool:
    root = str(repo or "").strip()
    if not root or not os.path.isdir(root):
        return False
    names = ("GameServer.GameServerApp.exe", "GameServer.GameServerApp")
    for config in ("Debug", "Release"):
        cfg_dir = os.path.join(root, "game-server", "bin", config)
        for name in names:
            if os.path.isfile(os.path.join(cfg_dir, name)):
                return True
        if os.path.isfile(os.path.join(cfg_dir, "GameServer.GameServerApp.dll")):
            return True
    return False

def _resolve_game_server_repo() -> str:
    env = str(os.getenv("GAME_SERVER_REPO") or "").strip()
    if env and os.path.isdir(env):
        return env
    candidates: List[str] = [os.path.join(os.path.expanduser("~"), "game-server")]
    if os.name == "nt":
        candidates.extend([r"E:\maclient\game-server", r"D:\maclient\game-server"])
    else:
        candidates.append(os.path.join(os.path.expanduser("~"), "GameClient", "game-server"))
    seen: set = set()
    ordered: List[str] = []
    for path in candidates:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        ordered.append(path)
    for path in ordered:
        if _gameserver_repo_has_executable(path):
            return path
    for path in ordered:
        if os.path.isdir(path):
            return path
    return env or ordered[0]


CLUSTER_JSON_PATH = os.path.join(_resolve_game_server_repo(), "config", "cluster.json")


def _load_cluster_json() -> List[Dict[str, Any]]:
    """从 game-server 的 cluster.json 读取集群拓扑定义。"""
    path = CLUSTER_JSON_PATH
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        servers = data.get("Servers") if isinstance(data, dict) else []
        return servers if isinstance(servers, list) else []
    except Exception:
        return []

def _cluster_node_category(server_type: str) -> str:
    """将 game-server 节点类型映射为 agent 管理中心的分类。"""
    t = str(server_type or "").strip().lower()
    app_types = {"gateway", "auth", "game", "cross", "ops"}
    transport_types = {"tcp", "kcp", "httptransport"}
    daemon_types = {"daemon"}
    gm_types = {"gm"}
    if t in app_types:
        return "application"
    if t in transport_types:
        return "transport"
    if t in daemon_types:
        return "infrastructure"
    if t in gm_types:
        return "management"
    return "other"

def _cluster_node_capabilities(server: Dict[str, Any]) -> List[str]:
    """根据节点类型推断支持的操作。"""
    t = str(server.get("Type") or "").strip().lower()
    cat = _cluster_node_category(t)
    base = ["health_check", "status"]
    if cat == "application" or cat == "transport":
        base += ["start", "stop", "restart", "smoke_test"]
    if cat == "infrastructure":
        base += ["start", "stop", "restart"]
    if t == "ops":
        base += ["stress_test"]
    supported = server.get("SupportedActions")
    if isinstance(supported, list) and supported:
        return [str(x) for x in supported if str(x).strip()]
    return base

def _sync_cluster_to_nodes(servers: List[Dict[str, Any]], project_id: str = "GomeKu") -> None:
    """
    从 cluster.json 同步拓扑到 nodes 配置（OpsPlatformGateway 需要用 ops_base_url 连 game-server）。
    每个 cluster.json 里的 Ops 类型节点会生成一个 node 条目，ops_base_url 指向其 Ops 端口。
    如果 cluster.json 里有 Ops 节点，用它的 host:port 作为所有 node 的 ops_base_url。
    """
    if not servers:
        return
    # 找到 Ops 节点的地址作为 ops_base_url
    ops_host = "127.0.0.1"
    ops_port = 5504
    for srv in servers:
        srv_type = str(srv.get("Type") or "").strip().lower()
        if srv_type == "ops":
            ops_host = str(srv.get("ProbeHost") or srv.get("Host") or "127.0.0.1").strip()
            ops_port = int(srv.get("Port") or 5504)
            break
    ops_base_url = f"http://{ops_host}:{ops_port}"

    # 生成新的 nodes 列表
    new_nodes: List[Dict[str, Any]] = []
    for srv in servers:
        srv_id = str(srv.get("ServerId") or "").strip()
        if not srv_id:
            continue
        srv_type = str(srv.get("Type") or "").strip()
        role = str(srv.get("Role") or srv_type.lower()).strip()
        host = str(srv.get("ProbeHost") or srv.get("Host") or "127.0.0.1").strip()
        port = int(srv.get("Port") or 0)
        new_nodes.append(_normalize_node({
            "id": srv_id,
            "name": str(srv.get("DisplayName") or srv_id),
            "base_url": f"http://{host}:{port}" if port else ops_base_url,
            "ops_base_url": ops_base_url,
            "ops_read_key": "ops-read-key-2026",
            "ops_write_key": "ops-write-key-2026",
            "ops_actor": "local-ops",
            "ops_role": "SuperAdmin",
            "server_id": srv_id,
            "project_id": project_id,
            "owner": "ops-admin",
            "role": role,
            "description": str(srv.get("Description") or ""),
            "enabled": True,
            "env": "prod",
            "channel": "1001",
        }))
    if new_nodes:
        _save_nodes(new_nodes)

def _sync_cluster_to_agents(project_id: str = "GomeKu") -> Dict[str, Any]:
    """
    从 game-server cluster.json 同步拓扑到 agent registry v2。
    以 cluster.json 为唯一 Source of Truth：
    - cluster.json 里有但 registry 没有的 → 自动创建
    - cluster.json 里有的 → 更新 host/port/capabilities 等字段
    - cluster.json 里没有的老节点 → 标记 stale=True
    返回同步统计。
    """
    servers = _load_cluster_json()
    if not servers:
        return {"synced": 0, "added": 0, "updated": 0, "stale": 0, "error": "no cluster.json data"}

    pid = str(project_id or "GomeKu").strip()
    if _project_uses_runtime_topology(pid):
        services: List[Dict[str, Any]] = []
        active_node_ids: set = set()
        host = "127.0.0.1"
        ops_port = 5504
        now = _now_iso()
        for srv in servers:
            srv_id = str(srv.get("ServerId") or "").strip()
            if not srv_id:
                continue
            active_node_ids.add(srv_id)
            probe_host = str(srv.get("ProbeHost") or srv.get("Host") or host).strip()
            host = probe_host or host
            port = int(srv.get("Port") or 0)
            role = str(srv.get("Role") or srv.get("Type") or "").strip().lower()
            if srv_id == "ops-cn-1":
                ops_port = port or ops_port
            services.append(
                {
                    "service_id": srv_id,
                    "node_id": srv_id,
                    "agent_id": CANONICAL_LOCAL_AGENT_ID,
                    "device_id": CANONICAL_LOCAL_DEVICE_ID,
                    "project_id": pid,
                    "display_name": str(srv.get("DisplayName") or srv_id),
                    "service_type": role,
                    "service_port": port,
                    "remote_game_server_port": port,
                    "status": "UNKNOWN",
                    "run_state": "UNKNOWN",
                    "probe_status": "",
                    "probe_rtt_ms": 0.0,
                    "metrics": {},
                    "updated_at": now,
                    "registration_origin": "cluster.sync",
                }
            )
        try:
            ctx = _resolve_topology_context(pid, "production", "")
            topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
            topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
            if topo_meta.get("runtime_topology") or topo_meta.get("cluster_source"):
                for node in topo.get("nodes") if isinstance(topo.get("nodes"), list) else []:
                    if not isinstance(node, dict):
                        continue
                    nid = str(node.get("server_id") or node.get("id") or "").strip()
                    role = str(node.get("role") or "").strip().lower()
                    if nid and role in ("database", "cache", "mongo", "redis", "search", "mq"):
                        active_node_ids.add(nid)
                        if not any(str(s.get("node_id") or "") == nid for s in services):
                            services.append(_service_dict_from_topology_node(pid, node, now))
        except Exception:
            pass
        _ensure_canonical_local_agent(pid, services, host=host, ops_port=ops_port)
        reg = _load_agent_registry_v2()
        stale_count = 0
        for aid, item in reg.items():
            if not isinstance(item, dict) or aid == CANONICAL_LOCAL_AGENT_ID:
                continue
            if str(item.get("project_id") or "") not in ("", pid):
                continue
            nid = str(item.get("node_id") or "").strip()
            if (nid and nid in active_node_ids) or str(aid).endswith("-cn-1"):
                item["stale"] = True
                item["stale_reason"] = "consolidated_to_canonical"
                item["superseded_by"] = CANONICAL_LOCAL_AGENT_ID
                item["updated_at"] = now
                stale_count += 1
        _save_agent_registry_v2(reg)
        _sync_cluster_to_nodes(servers, pid)
        topo_stat = _sync_cluster_to_topology(pid, servers)
        return {
            "synced": len(servers),
            "added": 0,
            "updated": len(services),
            "stale": stale_count,
            "topology": topo_stat,
            "canonical": True,
        }

    reg = _load_agent_registry_v2()
    now = _now_iso()

    # 建立 node_id → agent_id 的现有映射
    existing_by_node: Dict[str, str] = {}
    for aid, entry in reg.items():
        if isinstance(entry, dict):
            nid = str(entry.get("node_id") or "").strip()
            if nid:
                existing_by_node[nid] = aid

    # cluster.json 中的有效 node_id 集合
    active_node_ids: set = set()
    added = 0
    updated = 0

    for srv in servers:
        srv_id = str(srv.get("ServerId") or "").strip()
        if not srv_id:
            continue
        active_node_ids.add(srv_id)

        host = str(srv.get("Host") or "127.0.0.1").strip()
        # ProbeHost: 探活地址，分布式部署时填实际可达 IP；不填则用 Host
        # 0.0.0.0 绑定是合法的（监听所有网卡），但探活需要具体 IP
        probe_host = str(srv.get("ProbeHost") or host).strip()
        port = int(srv.get("Port") or 0)
        srv_type = str(srv.get("Type") or "").strip()
        display_name = str(srv.get("DisplayName") or srv_id).strip()
        desc = str(srv.get("Description") or "").strip()
        category = str(srv.get("Category") or _cluster_node_category(srv_type)).strip()
        capabilities = _cluster_node_capabilities(srv)
        role = str(srv.get("Role") or srv_type.lower()).strip()
        state_config = str(srv.get("State") or "").strip().upper()

        agent_id = f"agent-{srv_id}"
        hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None

        if hit:
            # 更新已有 agent 的关键字段（以 cluster.json 为准）
            changed = False
            for k, v in [("host_name", host), ("probe_host", probe_host),
                         ("port", port),
                         ("remote_game_server_port", port),
                         ("display_name", display_name),
                         ("desc", desc),
                         ("node_id", srv_id),
                         ("project_id", project_id),
                         ("category", category),
                         ("role", role),
                         ("server_type", srv_type),
                         ("capabilities", capabilities)]:
                if hit.get(k) != v:
                    hit[k] = v
                    changed = True
            hit["registration_origin"] = "cluster.sync"
            hit.pop("stale_reason", None)
            hit.pop("superseded_by", None)
            # 同步配置状态
            if state_config:
                hit["config_state"] = state_config
            # KCP 用 UDP 探活
            if srv_type.upper() == "KCP":
                hit["probe_proto"] = "udp"
            if changed:
                hit["updated_at"] = now
                updated += 1
        else:
            # 新建 agent
            reg[agent_id] = _normalize_agent_descriptor_v2({
                "agent_id": agent_id,
                "device_id": "local-game-server",
                "host_name": host,
                "probe_host": probe_host,
                "node_id": srv_id,
                "project_id": project_id,
                "status": "UNKNOWN",
                "version": "game-server-cluster-v1",
                "last_seen": now,
                "display_name": display_name,
                "port": port,
                "remote_game_server_port": port,
                "desc": desc,
                "run_state": "UNKNOWN",
                "probe_status": "",
                "probe_at": "",
                "probe_rtt_ms": 0.0,
                "capabilities": capabilities,
                "metrics": {},
                "network": {"endpoints": [f"{host}:{port}"] if port else []},
                "transport": {"mode": "remote", "local_bus": {"enabled": True, "endpoint": f"pipe://local-game-server/{agent_id}", "auth_mode": "token"}},
                "config_state": state_config,
                "category": category,
                "role": role,
                "server_type": srv_type,
                "probe_proto": "udp" if srv_type.upper() == "KCP" else "tcp",
                "registration_origin": "cluster.sync",
                "updated_at": now,
            })
            added += 1

    # runtime 拓扑中的基础设施节点（Mongo/Redis 等）不在 cluster.json，但仍应视为有效 Agent
    try:
        ctx = _resolve_topology_context(project_id, "production", "")
        topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
        topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        if topo_meta.get("runtime_topology") or topo_meta.get("cluster_source"):
            for node in topo.get("nodes") if isinstance(topo.get("nodes"), list) else []:
                if not isinstance(node, dict):
                    continue
                nid = str(node.get("server_id") or node.get("id") or "").strip()
                role = str(node.get("role") or "").strip().lower()
                if nid and role in ("database", "cache", "mongo", "redis", "search", "mq"):
                    active_node_ids.add(nid)
    except Exception:
        pass

    # 标记不在 cluster.json 中的老节点为 stale
    # 同一 project_id 下，cluster.json 里的 node_id 是唯一有效集合
    # 老节点（如 gateway_http 等）不在 cluster.json 中 → stale
    stale_count = 0
    for aid, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        entry_project = str(entry.get("project_id") or "").strip()
        # 只处理同一 project 的节点
        if entry_project and entry_project != project_id:
            continue
        nid = str(entry.get("node_id") or "").strip()
        if not nid:
            # 没有 node_id 的老条目也标记 stale
            entry["stale"] = True
            entry["updated_at"] = now
            stale_count += 1
            continue
        if nid not in active_node_ids:
            entry["stale"] = True
            entry["updated_at"] = now
            stale_count += 1
        else:
            entry.pop("stale", None)

    # 合并 Agent 心跳上报的 metrics 到 cluster.json 同步的 agent
    # Agent 注册的 agent_id 可能跟 cluster.json 同步的 agent_id 不同，但 node_id 相同
    for aid, entry in reg.items():
        if not isinstance(entry, dict) or entry.get("stale"):
            continue
        entry_nid = str(entry.get("node_id") or "").strip()
        if not entry_nid or entry_nid in active_node_ids:
            continue
        # 这个 agent 的 node_id 不在 cluster.json active set — 可能是 Agent 自己注册的
        cluster_aid = f"agent-{entry_nid}"
        cluster_entry = reg.get(cluster_aid) if isinstance(reg.get(cluster_aid), dict) else None
        if cluster_entry and not cluster_entry.get("stale"):
            # 合并 metrics、last_seen、run_state
            for mk in ["cpu_percent", "mem_percent", "qps", "rtt_ms", "updated_at"]:
                if entry.get("metrics", {}).get(mk) is not None:
                    cluster_entry.setdefault("metrics", {})[mk] = entry["metrics"][mk]
            if entry.get("last_seen"):
                cluster_entry["last_seen"] = entry["last_seen"]
            if entry.get("run_state") and entry.get("run_state") != "UNKNOWN":
                cluster_entry["run_state"] = entry["run_state"]
            if entry.get("status") and entry.get("status") != "UNKNOWN":
                cluster_entry["status"] = entry["status"]
            # 标记 Agent 自身条目为 stale（数据已合并）
            entry["stale"] = True
            entry["updated_at"] = now
            stale_count += 1

    _save_agent_registry_v2(reg)

    # 同步 nodes 配置（OpsPlatformGateway 用 ops_base_url 连 game-server）
    _sync_cluster_to_nodes(servers, project_id)
    topo_stat = _sync_cluster_to_topology(project_id, servers)
    canonical_stat = _consolidate_runtime_agents_to_canonical(project_id)

    return {"synced": len(servers), "added": added, "updated": updated, "stale": stale_count, "topology": topo_stat, "canonical": canonical_stat}

def _cluster_topology_role_kind(srv: Dict[str, Any]) -> Tuple[str, str]:
    srv_type = str(srv.get("Type") or "").strip().lower()
    role = str(srv.get("Role") or srv_type or "business").strip().lower()
    if srv_type == "gateway":
        return "gateway", "gateway"
    if srv_type == "auth":
        return "auth", "auth"
    if srv_type == "ops":
        return "ops", "admin"
    if srv_type in ("tcp", "kcp", "httptransport"):
        return "transport", "terminal"
    if srv_type == "game":
        return "business", "game"
    kind = _infer_node_kind(role, "")
    return role, kind

def _build_cluster_topology_content(servers: List[Dict[str, Any]], project_id: str = "") -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    nodes: List[Dict[str, Any]] = []
    valid_ids: set = set()
    for idx, srv in enumerate(servers):
        if not isinstance(srv, dict):
            continue
        sid = str(srv.get("ServerId") or "").strip()
        if not sid:
            continue
        valid_ids.add(sid)
        role, kind = _cluster_topology_role_kind(srv)
        srv_type = str(srv.get("Type") or "").strip().lower()
        layout_key = srv_type if srv_type in _CLUSTER_TOPOLOGY_LAYOUT else role
        x, y = _CLUSTER_TOPOLOGY_LAYOUT.get(layout_key, (72 + (idx % 3) * 260, 48 + (idx // 3) * 180))
        port = int(srv.get("Port") or 0)
        display = str(srv.get("DisplayName") or sid).strip()
        desc = str(srv.get("Description") or display).strip()
        ui_ports = _normalize_ports(kind, None)
        nodes.append({
            "id": sid,
            "name": display,
            "server_id": sid,
            "project_id": pid,
            "env": "production",
            "role": role,
            "kind": kind,
            "desc": desc,
            "bizStatus": "normal",
            "owner": "cluster.sync",
            "group": str(srv.get("Category") or "application"),
            "x": float(x),
            "y": float(y),
            "tags": [srv_type] if srv_type else [],
            "ui": {
                "x": float(x),
                "y": float(y),
                "w": 220,
                "h": 90,
                "locked": False,
                "ports": ui_ports,
                "remote": {"port": port} if port > 0 else {},
                "network": {"endpoints": [f"127.0.0.1:{port}"]} if port > 0 else {},
            },
        })

    edges: List[Dict[str, Any]] = []
    seen_edges: set = set()

    def _append_cluster_edge(from_id: str, to_id: str, note: str = "") -> None:
        frm = str(from_id or "").strip()
        to = str(to_id or "").strip()
        if not frm or not to or frm not in valid_ids or to not in valid_ids or frm == to:
            return
        edge_id = f"edge-{frm}-{to}"
        if edge_id in seen_edges:
            return
        seen_edges.add(edge_id)
        edges.append({
            "id": edge_id,
            "from": frm,
            "to": to,
            "from_port": "out-1",
            "to_port": "in-1",
            "type": "depends_on",
            "note": str(note or ""),
        })

    for srv in servers:
        if not isinstance(srv, dict):
            continue
        sid = str(srv.get("ServerId") or "").strip()
        if not sid:
            continue
        port = int(srv.get("Port") or 0)
        downstream = srv.get("DownstreamServerIds") if isinstance(srv.get("DownstreamServerIds"), list) else []
        for target in downstream:
            to_id = str(target or "").strip()
            _append_cluster_edge(sid, to_id, f"tcp:{port}" if port else "")
        upstream = srv.get("UpstreamServerIds") if isinstance(srv.get("UpstreamServerIds"), list) else []
        for source in upstream:
            from_id = str(source or "").strip()
            _append_cluster_edge(from_id, sid, f"tcp:{port}" if port else "")

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "layout_mode": "structured",
            "layout_locked": False,
            "cluster_source": True,
            "cluster_sync_at": _now_iso(),
            "layout_spacing": {"rank_gap": 268, "row_gap": 128},
            "updated_at": _now_iso(),
        },
    }

def _sync_cluster_to_topology(project_id: str, servers: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """将 cluster.json ServerId merge 到项目默认拓扑（保留用户添加的非 cluster 节点）。"""
    pid = str(project_id or "").strip()
    rows = servers if isinstance(servers, list) else _load_cluster_json()
    if not pid or not rows:
        return {"updated": False, "reason": "missing_project_or_cluster"}

    _migrate_topology_storage_if_needed()
    registry_rows = _load_topology_registry()
    target = None
    for item in registry_rows:
        if not isinstance(item, dict):
            continue
        row = _normalize_topology_registry_row(item)
        if row.get("project_id") == pid and row.get("is_default"):
            target = row
            break
    if target is None:
        target = _normalize_topology_registry_row({
            "topology_id": f"topology-{pid.replace('/', '-').replace(' ', '-').lower()}-production",
            "project_id": pid,
            "env_key": "production",
            "name": "生产主拓扑",
            "version_label": "cluster-v1",
            "owner": "cluster.sync",
            "description": "由 cluster.json 自动同步",
            "is_default": True,
            "status": "running",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })
        registry_rows.append(target)
        _save_topology_registry(registry_rows)

    tid = str(target.get("topology_id") or "").strip()
    if not tid:
        return {"updated": False, "reason": "missing_topology_id"}

    contents = _load_topology_contents()
    existing = contents.get(tid) if isinstance(contents.get(tid), dict) else {}
    existing_meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else {}
    existing_nodes = existing.get("nodes") if isinstance(existing.get("nodes"), list) else []
    existing_edges = existing.get("edges") if isinstance(existing.get("edges"), list) else []

    cluster_topo = _build_cluster_topology_content(rows, pid)
    cluster_nodes = cluster_topo.get("nodes") if isinstance(cluster_topo.get("nodes"), list) else []
    cluster_edges = cluster_topo.get("edges") if isinstance(cluster_topo.get("edges"), list) else []
    cluster_ids = {str(n.get("id") or "").strip() for n in cluster_nodes if isinstance(n, dict) and str(n.get("id") or "").strip()}
    minimal_default = (
        pid == "GomeKu"
        and bool(target.get("is_default"))
        and _normalize_env_key(str(target.get("env_key") or "")) == "production"
    )

    merged_nodes: List[Dict[str, Any]] = []
    merged_by_id: Dict[str, Dict[str, Any]] = {}

    if minimal_default:
        pos_by_id = {}
        for item in existing_nodes:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "").strip()
            if not nid:
                continue
            ui = item.get("ui") if isinstance(item.get("ui"), dict) else {}
            pos_by_id[nid] = (
                float(item.get("x") if item.get("x") is not None else ui.get("x") or 0),
                float(item.get("y") if item.get("y") is not None else ui.get("y") or 0),
            )
        for node in cluster_nodes:
            if not isinstance(node, dict):
                continue
            nid = str(node.get("id") or "").strip()
            if not nid:
                continue
            if nid in pos_by_id:
                x, y = pos_by_id[nid]
                node["x"] = x
                node["y"] = y
                ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
                ui["x"] = x
                ui["y"] = y
                node["ui"] = ui
            node_meta = node.get("meta") if isinstance(node.get("meta"), dict) else {}
            node_meta["cluster_source"] = True
            node["meta"] = node_meta
            merged_nodes.append(node)
            merged_by_id[nid] = node
        merged_edges = list(cluster_edges)
        merged_edge_ids = {str(e.get("id") or "") for e in merged_edges if isinstance(e, dict)}
    else:
        for item in existing_nodes:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "").strip()
            if not nid:
                continue
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
            is_cluster = bool(meta.get("cluster_source")) or nid in cluster_ids
            if is_cluster and nid in cluster_ids:
                continue
            if not is_cluster:
                merged_nodes.append(item)
                merged_by_id[nid] = item

        pos_by_id = {}
        for item in existing_nodes:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "").strip()
            if not nid:
                continue
            ui = item.get("ui") if isinstance(item.get("ui"), dict) else {}
            pos_by_id[nid] = (
                float(item.get("x") if item.get("x") is not None else ui.get("x") or 0),
                float(item.get("y") if item.get("y") is not None else ui.get("y") or 0),
            )

        for node in cluster_nodes:
            if not isinstance(node, dict):
                continue
            nid = str(node.get("id") or "").strip()
            if not nid:
                continue
            if nid in pos_by_id:
                x, y = pos_by_id[nid]
                node["x"] = x
                node["y"] = y
                ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
                ui["x"] = x
                ui["y"] = y
                node["ui"] = ui
            node_meta = node.get("meta") if isinstance(node.get("meta"), dict) else {}
            node_meta["cluster_source"] = True
            node["meta"] = node_meta
            merged_nodes.append(node)
            merged_by_id[nid] = node

        merged_edge_ids = set()
        merged_edges = []
        valid_ids = set(merged_by_id.keys())

        for edge in existing_edges:
            if not isinstance(edge, dict):
                continue
            frm = str(edge.get("from") or "").strip()
            to = str(edge.get("to") or "").strip()
            eid = str(edge.get("id") or f"edge-{frm}-{to}")
            if frm in cluster_ids and to in cluster_ids:
                continue
            if frm in valid_ids and to in valid_ids and eid not in merged_edge_ids:
                merged_edges.append(edge)
                merged_edge_ids.add(eid)

        for edge in cluster_edges:
            if not isinstance(edge, dict):
                continue
            eid = str(edge.get("id") or "")
            if eid and eid not in merged_edge_ids:
                merged_edges.append(edge)
                merged_edge_ids.add(eid)

    meta = cluster_topo.get("meta") if isinstance(cluster_topo.get("meta"), dict) else {}
    if existing_meta.get("viewport"):
        meta["viewport"] = existing_meta.get("viewport")
    if existing_meta.get("layout_spacing"):
        meta["layout_spacing"] = existing_meta.get("layout_spacing")
    if existing_meta.get("layout_spacing_customized"):
        meta["layout_spacing_customized"] = existing_meta.get("layout_spacing_customized")
    meta["cluster_sync_at"] = _now_iso()
    meta["updated_at"] = _now_iso()
    meta["runtime_topology"] = True
    meta["cluster_source"] = True
    if existing_meta.get("description"):
        meta["description"] = str(existing_meta.get("description") or "")

    merged_edges = _repair_runtime_topology_edges(merged_nodes, merged_edges, meta)
    topo = {"nodes": merged_nodes, "edges": merged_edges, "meta": meta}
    if pid == "GomeKu":
        env_for_topo = _normalize_env_key(str(target.get("env_key") or "production"))
        topo = _append_runtime_infra_stack(topo, pid, env_for_topo)
        merged_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else merged_nodes
        merged_edges = _repair_runtime_topology_edges(merged_nodes, topo.get("edges") or merged_edges, meta)
        meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else meta
        topo = {"nodes": merged_nodes, "edges": merged_edges, "meta": meta}
    contents[tid] = topo
    _save_topology_contents(contents)
    target["updated_at"] = _now_iso()
    _save_topology_registry(registry_rows)
    return {
        "updated": True,
        "topology_id": tid,
        "node_count": len(merged_nodes),
        "edge_count": len(merged_edges),
        "merged_user_nodes": len([n for n in existing_nodes if isinstance(n, dict) and str(n.get("id") or "") not in cluster_ids]),
    }
