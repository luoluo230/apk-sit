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


def _validate_topology_id(topology_id: str) -> str:
    import re
    tid = str(topology_id or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", tid):
        raise ValueError("拓扑 ID 须为 3–64 位小写字母、数字、下划线或连字符，且以字母或数字开头")
    return tid


def _topology_id_exists(topology_id: str) -> bool:
    tid = str(topology_id or "").strip()
    if not tid:
        return False
    for item in _load_topology_registry():
        if isinstance(item, dict) and str(item.get("topology_id") or "").strip() == tid:
            return True
    return False


def _get_topology_registry_row(topology_id: str) -> Optional[Dict[str, Any]]:
    tid = str(topology_id or "").strip()
    for item in _load_topology_registry():
        if isinstance(item, dict) and str(item.get("topology_id") or "").strip() == tid:
            return _normalize_topology_registry_row(item)
    return None
