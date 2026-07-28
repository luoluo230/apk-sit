# -*- coding: utf-8 -*-
"""Node contract registry, ports, and daemon commands."""

from __future__ import annotations

from services.ops import shared_bootstrap as _boot

globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})

def _node_contract_registry_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    return os.path.join(repo_root, "docs", "ops_alignment", "node_contract_registry.json")

def _load_node_contract_registry() -> Dict[str, Any]:
    global _NODE_CONTRACT_REGISTRY_CACHE
    if isinstance(_NODE_CONTRACT_REGISTRY_CACHE, dict) and _NODE_CONTRACT_REGISTRY_CACHE.get("contracts"):
        return _NODE_CONTRACT_REGISTRY_CACHE
    path = _node_contract_registry_path()
    data: Dict[str, Any] = {"contracts": [], "env_profiles": {}}
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                data = raw
    except Exception:
        pass
    _NODE_CONTRACT_REGISTRY_CACHE = data
    return data

def _load_node_contract(preset_id: str) -> Optional[Dict[str, Any]]:
    pid = str(preset_id or "").strip()
    if not pid:
        return None
    for item in _load_node_contract_registry().get("contracts") or []:
        if isinstance(item, dict) and str(item.get("preset_id") or "") == pid:
            return item
    return None

def _resolve_env_profile_name() -> str:
    if os.name == "nt":
        return "local_windows"
    if os.name == "posix":
        try:
            if os.uname().sysname == "Darwin":
                return "local_macos"
        except Exception:
            pass
        return "local_linux"
    return "local_macos"

def _format_contract_command(template: str, port: int, extras: Optional[Dict[str, Any]] = None) -> str:
    text = str(template or "").strip()
    if not text:
        return ""
    merged = {
        "port": int(port or 0),
        "qps": 300,
        "duration_sec": 180,
        "data_dir": _gomeku_mongo_dbpath(),
    }
    if isinstance(extras, dict):
        merged.update(extras)
    try:
        return text.format(**merged)
    except Exception:
        out = text.replace("{port}", str(int(port or 0)))
        return out.replace("{data_dir}", str(merged.get("data_dir") or _gomeku_mongo_dbpath()))

def _resolve_node_contract_for_topology_node(node: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    preset_id = str(node.get("preset_id") or "").strip()
    if preset_id:
        hit = _load_node_contract(preset_id)
        if hit:
            return hit
    nid = str(node.get("id") or "").strip()
    for preset in _load_node_presets():
        if not isinstance(preset, dict):
            continue
        pid = str(preset.get("preset_id") or "").strip()
        if pid and (nid == pid or nid.startswith(pid + "-")):
            hit = _load_node_contract(pid)
            if hit:
                return hit
    role = str(node.get("role") or "").strip().lower()
    if role == "admin":
        role = "ops"
    for item in _load_node_contract_registry().get("contracts") or []:
        if isinstance(item, dict) and str(item.get("role") or "").strip().lower() == role:
            return item
    return {}

def _contract_daemon_defaults(preset_id: str, port: int) -> Dict[str, str]:
    reg = _load_node_contract_registry()
    profiles = reg.get("env_profiles") if isinstance(reg.get("env_profiles"), dict) else {}
    profile_name = _resolve_env_profile_name()
    profile = profiles.get(profile_name) if isinstance(profiles.get(profile_name), dict) else {}
    raw = profile.get(preset_id) if isinstance(profile.get(preset_id), dict) else {}
    out: Dict[str, str] = {}
    for key in ("StartCommand", "StopCommand", "HealthCheckCommand", "StressCommand", "ScheduleCommand"):
        val = _format_contract_command(str(raw.get(key) or ""), port)
        if val:
            out[key] = val
    return out

def _cluster_type_for_contract(contract: Dict[str, Any], role: str) -> str:
    if isinstance(contract, dict) and str(contract.get("cluster_type") or "").strip():
        return str(contract.get("cluster_type") or "").strip()
    return _cluster_type_for_role(role)

def _cluster_type_for_role(role: str) -> str:
    mapping = {
        "gateway": "Gateway",
        "auth": "Auth",
        "business": "Game",
        "pressure": "Daemon",
        "database": "Daemon",
        "cache": "Daemon",
        "mq": "Daemon",
        "search": "Search",
        "scheduler": "Daemon",
        "admin": "Ops",
        "edge": "Gateway",
        "analytics": "Analytics",
        "ops": "Ops",
        "transport": "Tcp",
    }
    key = str(role or "").strip().lower()
    if key == "admin":
        key = "ops"
    return mapping.get(key, key.title() or "Game")

def _cluster_category_for_role(role: str) -> str:
    key = str(role or "").strip().lower()
    if key in ("database", "cache", "mq", "search"):
        return "middleware"
    if key in ("pressure",):
        return "test"
    if key in ("gateway", "edge", "transport"):
        return "network"
    return "application"

def _resolve_topology_node_port(
    node: Dict[str, Any],
    contract: Dict[str, Any],
    service: Optional[Dict[str, Any]],
    agent: Optional[Dict[str, Any]],
) -> int:
    ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
    remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
    for candidate in (
        int(node.get("daemon_port") or 0),
        int(remote.get("port") or 0),
        int((contract or {}).get("default_port") or 0),
        int((service or {}).get("service_port") or 0),
        int((service or {}).get("remote_game_server_port") or 0),
        int((agent or {}).get("remote_game_server_port") or 0) if isinstance(agent, dict) else 0,
        int((agent or {}).get("port") or 0) if isinstance(agent, dict) else 0,
    ):
        if candidate > 0:
            return candidate
    return 0

def _cluster_relay_port_for_type(cluster_type: str, role: str) -> int:
    t = str(cluster_type or "").strip().lower()
    r = str(role or "").strip().lower()
    if t == "auth" or r == "auth":
        return 15501
    if t in ("game", "cross") or r in ("game", "business"):
        return 15502 if t != "cross" else 15503
    return 0

def _enrich_cluster_relay_metadata(
    metadata: Dict[str, Any],
    cluster_type: str,
    role: str,
) -> Dict[str, Any]:
    meta = dict(metadata or {})
    relay_port = _cluster_relay_port_for_type(cluster_type, role)
    if relay_port > 0:
        meta.setdefault("ClusterRelayPort", str(relay_port))
    relay_token = _cluster_relay_token()
    if relay_token:
        meta.setdefault("ClusterRelayToken", relay_token)
    return meta

def _build_daemon_metadata(
    node: Dict[str, Any],
    contract: Dict[str, Any],
    port: int,
    base_meta: Dict[str, Any],
) -> Dict[str, Any]:
    meta = dict(base_meta or {})
    preset_id = str(node.get("preset_id") or contract.get("preset_id") or "").strip()
    execution_model = str(contract.get("execution_model") or "").strip().lower()
    if execution_model not in ("daemon", "worker"):
        return meta
    start_cmd = str(node.get("daemon_start_cmd") or "").strip()
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    defaults = _contract_daemon_defaults(preset_id, port) if preset_id else {}
    if not start_cmd:
        start_cmd = str(defaults.get("StartCommand") or "").strip()
    if not stop_cmd:
        stop_cmd = str(defaults.get("StopCommand") or "").strip()
    if start_cmd:
        meta["StartCommand"] = start_cmd
    if stop_cmd:
        meta["StopCommand"] = stop_cmd
    for key in ("HealthCheckCommand", "StressCommand", "ScheduleCommand"):
        node_val = str(node.get(key.lower()) or node.get(key) or "").strip()
        if not node_val:
            node_val = str(defaults.get(key) or "").strip()
        if node_val:
            meta[key] = node_val
    if preset_id:
        meta["PresetId"] = preset_id
    meta["ExecutionModel"] = execution_model
    return meta

def _validate_topology_contract(topo: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("disabled") or str(node.get("bizStatus") or "").lower() == "disabled":
            continue
        contract = _resolve_node_contract_for_topology_node(node)
        execution_model = str(contract.get("execution_model") or "").strip().lower()
        if execution_model not in ("daemon", "worker"):
            continue
        node_id = str(node.get("id") or node.get("server_id") or "").strip() or "unknown"
        port = _resolve_topology_node_port(node, contract, None, None)
        preset_id = str(node.get("preset_id") or contract.get("preset_id") or "").strip()
        start_cmd = str(node.get("daemon_start_cmd") or "").strip()
        if not start_cmd and preset_id:
            start_cmd = str(_contract_daemon_defaults(preset_id, port).get("StartCommand") or "").strip()
        if port <= 0:
            errors.append(f"节点 {node_id} 缺少有效端口（daemon/worker 类型需要 default_port 或 ui.remote.port）")
        if not start_cmd:
            errors.append(f"节点 {node_id} 缺少 StartCommand（请在检查器填写 daemon 启动命令）")
    return (len(errors) == 0, errors)

def _topology_to_cluster_payload(project_id: str, env_key: str, topology_id: str) -> Dict[str, Any]:
    scoped = _load_topology_scoped(project_id, env_key, topology_id)
    topo = {
        "nodes": scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else [],
        "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
        "meta": scoped.get("meta") if isinstance(scoped.get("meta"), dict) else {},
    }
    row = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    agent_bindings = _load_scope_agent_bindings(topology_id)
    service_bindings = _load_scope_service_bindings(topology_id)
    services = _services_for_project(project_id)
    services_map = {str(x.get("service_id") or "").strip(): x for x in services if isinstance(x, dict)}
    agents_map = {str(x.get("agent_id") or "").strip(): x for x in _agents_v2_for_project(project_id) if isinstance(x, dict)}
    edge_in: Dict[str, List[str]] = {}
    edge_out: Dict[str, List[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to:
            continue
        edge_out.setdefault(frm, []).append(to)
        edge_in.setdefault(to, []).append(frm)

    def _resolve_server_id(target_node: Optional[Dict[str, Any]]) -> str:
        if not isinstance(target_node, dict):
            return ""
        return str(target_node.get("server_id") or target_node.get("id") or "").strip()

    cluster_servers: List[Dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        contract = _resolve_node_contract_for_topology_node(node)
        role = str(node.get("role") or contract.get("role") or "business").strip().lower()
        if role == "admin":
            role = "ops"
        service_id = str(service_bindings.get(node_id) or "").strip()
        service = services_map.get(service_id) if service_id else None
        agent_id = str(agent_bindings.get(node_id) or (service or {}).get("agent_id") or "").strip()
        agent = agents_map.get(agent_id) if agent_id else None
        endpoints = []
        if isinstance(service, dict) and isinstance(service.get("endpoints"), list):
            endpoints = service.get("endpoints") or []
        elif isinstance(agent, dict) and isinstance(((agent.get("network") or {}).get("endpoints")), list):
            endpoints = ((agent.get("network") or {}).get("endpoints")) or []
        endpoint = str(endpoints[0] or "").strip() if endpoints else ""
        endpoint_host = endpoint.split(":")[0].strip() if endpoint and ":" in endpoint else endpoint
        service_port = _resolve_topology_node_port(node, contract, service, agent)
        remote_port = service_port
        runtime_status = str((service or {}).get("status") or (service or {}).get("run_state") or (agent or {}).get("status") or (agent or {}).get("run_state") or "UNKNOWN").upper()
        cluster_type = _cluster_type_for_contract(contract, role)
        probe_host = _resolve_agent_probe_host(agent, service, node)
        if probe_host in ("0.0.0.0", "*", ""):
            probe_host = endpoint_host or DEFAULT_LOOPBACK
        bind_host = endpoint_host or ("0.0.0.0" if role in ("gateway", "transport", "edge") else "127.0.0.1")
        relay_port = _cluster_relay_port_for_type(cluster_type, role)
        base_meta = {
            "ProjectId": str(project_id or ""),
            "EnvKey": _normalize_env_key(env_key),
            "TopologyId": str(topology_id or ""),
            "TopologyName": str(row.get("name") or ""),
            "VersionLabel": str(row.get("version_label") or ""),
            "NodeId": node_id,
            "AgentId": agent_id,
            "ServiceId": str((service or {}).get("service_id") or ""),
            "AgentWs": str(endpoint or ""),
            "RemoteGameServerPort": str(remote_port or ""),
            "ProbeHost": probe_host,
            "PresetId": str(node.get("preset_id") or contract.get("preset_id") or ""),
            "ProbeStrategy": str(contract.get("probe_strategy") or "tcp"),
        }
        if relay_port > 0:
            base_meta["ClusterRelayPort"] = str(relay_port)
        relay_token = _cluster_relay_token()
        if relay_token:
            base_meta["ClusterRelayToken"] = relay_token
        metadata = _enrich_cluster_relay_metadata(
            _build_daemon_metadata(node, contract, service_port, base_meta),
            cluster_type,
            role,
        )
        cluster_servers.append(
            {
                "ServerId": str(node.get("server_id") or node_id),
                "DisplayName": str(node.get("name") or node_id),
                "Type": cluster_type,
                "Role": role,
                "Category": _cluster_category_for_role(role),
                "Description": str(node.get("desc") or ""),
                "UpstreamServerIds": [
                    sid for sid in [
                        _resolve_server_id(next((x for x in nodes if isinstance(x, dict) and str(x.get("id") or "") == upstream_id), None))
                        for upstream_id in (edge_in.get(node_id) or [])
                    ] if sid
                ],
                "DownstreamServerIds": [
                    sid for sid in [
                        _resolve_server_id(next((x for x in nodes if isinstance(x, dict) and str(x.get("id") or "") == downstream_id), None))
                        for downstream_id in (edge_out.get(node_id) or [])
                    ] if sid
                ],
                "Host": bind_host,
                "ProbeHost": probe_host,
                "Port": service_port,
                "State": "Online" if runtime_status in ("ONLINE", "READY", "RUNNING", "SUCCESS") else "Offline",
                "Metadata": metadata,
            }
        )
    return {
        "project_id": str(project_id or ""),
        "env_key": _normalize_env_key(env_key),
        "topology_id": str(topology_id or ""),
        "topology_name": str(row.get("name") or ""),
        "version_label": str(row.get("version_label") or ""),
        "cluster": {
            "MaintenanceMessage": "Managed by Ops topology workbench.",
            "EnableHotReload": True,
            "Servers": cluster_servers,
        },
    }

def _cluster_relay_token() -> str:
    """Plan P0-01: relay token from env only; never hardcode in source."""
    return str(os.getenv("CLUSTER_RELAY_TOKEN") or "").strip()
