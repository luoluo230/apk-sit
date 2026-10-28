def _probe_topology_node_live(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    *,
    gateway_live: bool = False,
    ops_live: bool = False,
    probe_host: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
    contract = _resolve_node_contract_for_topology_node(topo_node)
    host = str(probe_host or "").strip() or _resolve_orchestration_probe_host(pid, tid, topo_node, agent_bindings)
    probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
    if _is_embedded_topology_node(topo_node, contract):
        live = bool(gateway_live or ops_live)
        return (
            live,
            f"gateway:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if gateway_live else 'FAIL'} "
            f"ops:{_RUNTIME_OPS_PROBE_PORT}={'PASS' if ops_live else 'FAIL'} @{host}",
        )
    if probe_port > 0:
        live = _probe_tcp_open(host, probe_port)
        return live, f"tcp:{host}:{probe_port}={'PASS' if live else 'FAIL'}"
    role = str(node.get("role") or "").strip().lower()
    if role in ("auth", "game", "business", "admin", "ops", "gateway", "edge"):
        live = bool(gateway_live or ops_live)
        return (
            live,
            f"gateway:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if gateway_live else 'FAIL'} "
            f"ops:{_RUNTIME_OPS_PROBE_PORT}={'PASS' if ops_live else 'FAIL'} @{host}",
        )
    return False, "no probe target"


def _probe_service_cache_fresh(max_age_sec: float = PROBE_INTERVAL_SEC * 3) -> bool:
    with _probe_cache_lock:
        cache_ts = float(_probe_cache_ts or 0.0)
    if cache_ts <= 0:
        return False
    return (_time_mod.time() - cache_ts) <= max(6.0, float(max_age_sec))


def _probe_tcp_open(host: str, port: int, timeout: float = 0.8) -> bool:
    host_name = str(host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port_val = int(port or 0)
    except Exception:
        return False
    if port_val <= 0:
        return False
    try:
        with socket.create_connection((host_name, port_val), timeout=max(0.05, float(timeout))):
            return True
    except Exception:
        return False
