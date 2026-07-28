# -*- coding: utf-8 -*-
"""Runtime start/stop orchestration and probes."""

from __future__ import annotations

from services.ops import shared_bootstrap as _boot

globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})

from services.ops.topology_service import _normalize_env_key, _runtime_default_topology_id

def _tcp_probe(host: str, port: int, timeout: float = 1.5) -> Dict[str, Any]:
    """TCP connect 探活，返回 {ok, rtt_ms, error}。"""
    if not host or port <= 0:
        return {"ok": False, "rtt_ms": 0.0, "error": "invalid host/port"}
    start = datetime.now(timezone.utc)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        rtt = max(0.0, (datetime.now(timezone.utc) - start).total_seconds() * 1000.0)
        return {"ok": True, "rtt_ms": round(rtt, 1), "error": ""}
    except Exception as ex:
        return {"ok": False, "rtt_ms": 0.0, "error": str(ex)}

def _udp_probe(host: str, port: int, timeout: float = 1.5) -> Dict[str, Any]:
    """UDP 探活：发送空包检测端口是否可达（KCP 等协议）。"""
    if not host or port <= 0:
        return {"ok": False, "rtt_ms": 0.0, "error": "invalid host/port"}
    start = datetime.now(timezone.utc)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        # 发送一个空 UDP 包，如果端口没监听会收到 ICMP Port Unreachable
        # 如果端口在监听，包会被静默丢弃（KCP 等协议不响应空包）
        # 所以只要没收到 ICMP unreachable 就认为端口可达
        sock.sendto(b"", (host, port))
        # 尝试接收（KCP 可能回握手包）
        try:
            sock.recvfrom(64)
        except socket.timeout:
            # 超时 = 端口可达但无响应，算作在线
            pass
        rtt = max(0.0, (datetime.now(timezone.utc) - start).total_seconds() * 1000.0)
        sock.close()
        return {"ok": True, "rtt_ms": round(rtt, 1), "error": ""}
    except OSError as ex:
        # ICMP Port Unreachable → 端口未监听
        try:
            sock.close()
        except Exception:
            pass
        return {"ok": False, "rtt_ms": 0.0, "error": str(ex)}
    except Exception as ex:
        try:
            sock.close()
        except Exception:
            pass
        return {"ok": False, "rtt_ms": 0.0, "error": str(ex)}

def _redis_cli_candidates() -> List[str]:
    if os.name == "nt":
        return ["memurai-cli", "redis-cli"]
    return ["redis-cli"]

def _redis_ping_probe(host: str, port: int, timeout: float = 1.5) -> Dict[str, Any]:
    if not host or port <= 0:
        return {"ok": False, "rtt_ms": 0.0, "error": "invalid host/port"}
    tcp_fast = _tcp_probe(host, port, min(0.45, float(timeout)))
    if not tcp_fast.get("ok"):
        return tcp_fast
    start = datetime.now(timezone.utc)
    for cli in _redis_cli_candidates():
        try:
            proc = subprocess.run(
                [cli, "-h", host, "-p", str(port), "ping"],
                capture_output=True,
                text=True,
                timeout=max(0.6, min(1.0, float(timeout))),
            )
            ok = proc.returncode == 0 and "PONG" in (proc.stdout or "").upper()
            rtt = max(0.0, (datetime.now(timezone.utc) - start).total_seconds() * 1000.0)
            if ok:
                return {"ok": True, "rtt_ms": round(rtt, 1), "error": "", "method": cli}
        except FileNotFoundError:
            continue
        except Exception:
            break
    return {"ok": True, "rtt_ms": round(float(tcp_fast.get("rtt_ms") or 0.0), 1), "error": "", "method": "tcp-fallback"}

def _probe_by_protocol(host: str, port: int, proto: str = "tcp", timeout: float = 1.5) -> Dict[str, Any]:
    """根据协议类型选择探活方式。"""
    key = str(proto or "tcp").strip().lower()
    if key in ("udp",):
        return _udp_probe(host, port, timeout)
    if key in ("redis_ping", "redis"):
        return _redis_ping_probe(host, port, timeout)
    if key in ("mongo_ping", "mongo_tcp", "mongo"):
        return _tcp_probe(host, port, timeout)
    if key in ("kafka_tcp",):
        return _tcp_probe(host, port, timeout)
    if key in ("cluster_embedded",):
        host_str = str(host or "127.0.0.1").strip()
        probe_port = int(port or 0) or _CLUSTER_RELAY_PROBE_PORTS.get("game-cn-1", 15502)
        tcp = _tcp_probe(host_str, probe_port, timeout)
        if tcp.get("ok"):
            return {**tcp, "probe_method": "cluster-relay-tcp"}
        cluster = _fetch_cluster_runtime_status()
        online = any(_cluster_state_is_online(state) for state in cluster.values())
        return {
            "ok": online,
            "rtt_ms": tcp.get("rtt_ms", 0.0),
            "error": "" if online else "cluster embedded offline",
            "probe_method": "cluster-runtime-status",
        }
    return _tcp_probe(host, port, timeout)

def _cluster_state_is_online(state: Any) -> bool:
    text = str(state or "").strip().upper()
    return text in ("RUNNING", "READY", "ONLINE", "ACTIVE", "0") or str(state or "").strip() == "0"

def _is_daemon_infra_service(service: Dict[str, Any]) -> bool:
    if not isinstance(service, dict):
        return False
    sid = str(service.get("service_id") or service.get("node_id") or "").strip().lower()
    stype = str(service.get("service_type") or service.get("role") or "").strip().lower()
    return sid in ("mongo-db-cn-1", "redis-cache-cn-1") or stype in ("database", "cache", "mongo", "redis")

def _default_probe_host() -> str:
    return str(os.getenv("OPS_DEFAULT_PROBE_HOST") or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK

def _is_local_runtime_agent(agent_id: str = "", device_id: str = "") -> bool:
    aid = str(agent_id or "").strip()
    did = str(device_id or "").strip()
    return aid == CANONICAL_LOCAL_AGENT_ID or did == CANONICAL_LOCAL_DEVICE_ID

def _resolve_bound_agent(
    agent_bindings: Optional[Dict[str, str]],
    node_id: str,
    reg: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    nid = str(node_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else {}
    agent_id = str(bindings.get(nid) or "").strip()
    if not agent_id:
        return None
    registry = reg if isinstance(reg, dict) else _load_agent_registry_v2()
    hit = registry.get(agent_id) if isinstance(registry.get(agent_id), dict) else None
    return dict(hit) if isinstance(hit, dict) else None

def _resolve_agent_probe_host(
    agent: Optional[Dict[str, Any]] = None,
    service: Optional[Dict[str, Any]] = None,
    topo_node: Optional[Dict[str, Any]] = None,
) -> str:
    """统一服务探活地址：probe_host 优先；本机 runtime / 守护进程固定 loopback。"""
    agent_obj = agent if isinstance(agent, dict) else {}
    service_obj = service if isinstance(service, dict) else {}
    node_obj = topo_node if isinstance(topo_node, dict) else {}
    ui = node_obj.get("ui") if isinstance(node_obj.get("ui"), dict) else {}
    remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
    network = ui.get("network") if isinstance(ui.get("network"), dict) else {}
    for candidate in (
        str(service_obj.get("probe_host") or "").strip(),
        str(agent_obj.get("probe_host") or "").strip(),
        str(remote.get("host") or remote.get("probe_host") or "").strip(),
        str(network.get("probe_host") or "").strip(),
    ):
        if candidate and candidate not in ("0.0.0.0", "*"):
            return candidate
    if _is_daemon_infra_service(service_obj) and _is_local_runtime_agent(
        str(agent_obj.get("agent_id") or ""),
        str(agent_obj.get("device_id") or ""),
    ):
        return DEFAULT_LOOPBACK
    if _is_local_runtime_agent(str(agent_obj.get("agent_id") or ""), str(agent_obj.get("device_id") or "")):
        return DEFAULT_LOOPBACK
    fallback = str(agent_obj.get("host_ip") or agent_obj.get("host_name") or "").strip()
    if fallback and fallback not in ("0.0.0.0", "*"):
        return fallback
    return _default_probe_host()

def _resolve_runtime_probe_host(
    agent: Optional[Dict[str, Any]] = None,
    service: Optional[Dict[str, Any]] = None,
    topo_node: Optional[Dict[str, Any]] = None,
) -> str:
    return _resolve_agent_probe_host(agent, service, topo_node)

def _is_embedded_topology_node(node: Dict[str, Any], contract: Optional[Dict[str, Any]] = None) -> bool:
    if not isinstance(node, dict):
        return False
    contract_obj = contract if isinstance(contract, dict) else _resolve_node_contract_for_topology_node(node)
    execution_model = str(contract_obj.get("execution_model") or "").strip().lower()
    probe_strategy = str(contract_obj.get("probe_strategy") or "").strip().lower()
    if execution_model == "embedded" or probe_strategy == "cluster_embedded":
        return True
    nid = str(node.get("id") or node.get("node_id") or "").strip().lower()
    if nid in ("auth-cn-1", "game-cn-1"):
        return True
    role = str(node.get("role") or contract_obj.get("role") or "").strip().lower()
    if role in ("auth", "business", "game") and (nid.startswith("auth-") or nid.startswith("game-")):
        return True
    return False

def _resolve_runtime_probe_ports(contract: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    return {
        "gateway": _RUNTIME_GATEWAY_PROBE_PORT,
        "ops": _RUNTIME_OPS_PROBE_PORT,
    }

def _resolve_orchestration_probe_host(
    project_id: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    agent_bindings: Optional[Dict[str, str]] = None,
    reg: Optional[Dict[str, Any]] = None,
) -> str:
    nid = str(topo_node.get("id") or "").strip()
    agent = _resolve_bound_agent(agent_bindings, nid, reg)
    if agent:
        return _resolve_runtime_probe_host(agent, None, topo_node)
    if _project_uses_runtime_topology(project_id):
        return DEFAULT_LOOPBACK
    return _default_probe_host()

def _resolve_orchestration_scope(
    project_id: str,
    topology_id: str,
    agent_bindings: Optional[Dict[str, str]] = None,
    reg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bindings = agent_bindings if isinstance(agent_bindings, dict) else {}
    registry = reg if isinstance(reg, dict) else _load_agent_registry_v2()
    hosts: List[str] = []
    has_remote = False
    for _nid, aid in bindings.items():
        agent_id = str(aid or "").strip()
        if not agent_id:
            continue
        if not _is_local_runtime_agent(agent_id):
            has_remote = True
        agent = registry.get(agent_id) if isinstance(registry.get(agent_id), dict) else {}
        hosts.append(_resolve_runtime_probe_host(agent, None, None))
    default_host = DEFAULT_LOOPBACK
    if has_remote and hosts:
        default_host = hosts[0]
    elif hosts:
        default_host = hosts[0]
    return {
        "default_probe_host": default_host,
        "has_remote_agents": has_remote,
        "probe_hosts": hosts,
    }

def _is_embedded_cluster_agent(agent: Dict[str, Any]) -> bool:
    srv_type = str(agent.get("server_type") or "").strip().lower()
    if srv_type in _EMBEDDED_CLUSTER_SERVER_TYPES:
        return True
    nid = str(agent.get("node_id") or "").strip().lower()
    return nid.startswith("auth-") or nid.startswith("game-")

def _is_embedded_cluster_service(service: Dict[str, Any]) -> bool:
    if not isinstance(service, dict):
        return False
    sid = str(service.get("service_id") or service.get("node_id") or "").strip().lower()
    stype = str(service.get("service_type") or service.get("type") or "").strip().lower()
    role = str(service.get("role") or "").strip().lower()
    if sid in ("auth-cn-1", "game-cn-1"):
        return True
    if stype in _EMBEDDED_CLUSTER_SERVER_TYPES:
        return True
    if sid.startswith("auth-") or sid.startswith("game-"):
        return True
    return role in ("auth", "business") and ("auth" in sid or "game" in sid)

def _resolve_service_runtime_state(
    service: Dict[str, Any],
    host: str = "127.0.0.1",
    cluster_status: Optional[Dict[str, str]] = None,
    probe_timeout: float = 0.8,
    fast_probe: bool = False,
) -> Dict[str, Any]:
    """统一服务级运行态：embedded 模块走 cluster 状态，其余走 TCP + cluster 兜底。"""
    svc = dict(service) if isinstance(service, dict) else {}
    sid = str(svc.get("service_id") or svc.get("node_id") or "").strip()
    prior_run = str(svc.get("run_state") or svc.get("status") or "").strip().upper()
    port = int(svc.get("service_port") or svc.get("remote_game_server_port") or 0)
    timeout = max(0.08, min(float(probe_timeout or 0.8), 2.0)) if fast_probe else max(0.2, min(float(probe_timeout or 0.8), 2.0))

    if _service_starting_grace_active(svc):
        if port > 0 and _probe_tcp_open(host, port, timeout=0.12 if fast_probe else 0.25):
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
            svc["probe_method"] = "grace-fast-tcp"
            svc["probe_host"] = str(host or "127.0.0.1").strip()
            return svc
        svc["probe_status"] = "FAIL"
        svc["status"] = "STARTING"
        svc["run_state"] = "STARTING"
        svc["probe_method"] = "starting-grace"
        svc["probe_host"] = str(host or "127.0.0.1").strip()
        return svc
    sid_lower = sid.lower()
    cs_map = cluster_status if isinstance(cluster_status, dict) else {}
    cs = str(cs_map.get(sid) or "").strip().upper()
    embedded = _is_embedded_cluster_service(svc)
    probe_method = "tcp"
    open_ok = False

    if embedded:
        probe_method = "cluster-embedded"
        gw_ops_up = _embedded_process_gateway_up(host, timeout=timeout)
        if cs and _cluster_state_is_online(cs):
            open_ok = True
        elif cs and not _cluster_state_is_online(cs):
            if gw_ops_up:
                open_ok = True
                probe_method = "cluster-embedded-process-up"
            else:
                open_ok = False
                probe_method = "cluster-embedded-offline"
        elif gw_ops_up:
            open_ok = True
            probe_method = "cluster-process-up-fast" if fast_probe else "cluster-process-up"
        else:
            open_ok = False
            probe_method = "cluster-embedded-offline"
        if open_ok:
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
        else:
            svc["probe_status"] = "FAIL"
            if prior_run == "STARTING":
                svc["status"] = "STARTING"
                svc["run_state"] = "STARTING"
            else:
                svc["status"] = "STOPPED"
                svc["run_state"] = "STOPPED"
        svc["probe_method"] = probe_method
        svc["probe_host"] = str(host or "127.0.0.1").strip()
        if cs:
            svc["cluster_state"] = cs
        return svc
    elif sid_lower in _GAMESERVER_PROCESS_SERVICE_IDS:
        tcp_port = _gameserver_tcp_probe_port(sid_lower)
        if tcp_port > 0:
            open_ok = _gameserver_service_live(sid_lower, fast=fast_probe)
            probe_method = "gameserver-tcp-fast" if fast_probe else "gameserver-tcp"
        elif fast_probe:
            gw_live = _probe_tcp_open(host, 15050, timeout=timeout)
            ops_live = _probe_tcp_open(host, 5504, timeout=timeout)
            open_ok = bool(gw_live or ops_live)
            probe_method = "gameserver-process-fast"
        else:
            open_ok = _is_gameserver_process_alive(sid_lower)
            probe_method = "gameserver-process"
        if open_ok:
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
        else:
            svc["probe_status"] = "FAIL"
            if prior_run == "STARTING":
                svc["status"] = "STARTING"
                svc["run_state"] = "STARTING"
            else:
                svc["status"] = "STOPPED"
                svc["run_state"] = "STOPPED"
        svc["probe_method"] = probe_method
        svc["probe_host"] = str(host or "127.0.0.1").strip()
        return svc
    elif _is_daemon_infra_service(svc):
        probe_method = "redis_ping" if "redis" in sid or str(svc.get("service_type") or "").lower() == "cache" else "mongo_ping"
        if port > 0:
            probe = _probe_by_protocol(host, port, probe_method, timeout=timeout)
            open_ok = bool(probe.get("ok"))
        else:
            open_ok = False
    else:
        open_ok = _probe_tcp_open(host, port, timeout=timeout) if port > 0 else False
        if not open_ok and cs and _cluster_state_is_online(cs):
            open_ok = True
            probe_method = "cluster-fallback"

    if open_ok:
        svc["probe_status"] = "PASS"
        svc["status"] = "RUNNING"
        svc["run_state"] = "RUNNING"
    elif embedded and not cs:
        # GameServer 进程内模块：Gateway/Ops 均不可达时与 Gateway 行一致显示已停止
        gw_live = _probe_tcp_open(host, 15050, timeout=timeout)
        ops_live = _probe_tcp_open(host, 5504, timeout=timeout)
        if not gw_live and not ops_live:
            svc["probe_status"] = "FAIL"
            svc["status"] = "STOPPED"
            svc["run_state"] = "STOPPED"
            probe_method = "cluster-embedded-offline"
        elif gw_live or ops_live:
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
            probe_method = "cluster-process-up"
        else:
            svc["probe_status"] = "FAIL"
            svc["status"] = "STOPPED"
            svc["run_state"] = "STOPPED"
            probe_method = "cluster-embedded-deferred"
    else:
        svc["probe_status"] = "FAIL"
        if prior_run == "STARTING" or _service_starting_grace_active(svc):
            svc["status"] = "STARTING"
            svc["run_state"] = "STARTING"
        else:
            svc["status"] = "STOPPED"
            svc["run_state"] = "STOPPED"
    svc["probe_method"] = probe_method
    svc["probe_host"] = str(host or "127.0.0.1").strip()
    if cs:
        svc["cluster_state"] = cs
    return svc

def _fetch_cluster_runtime_status(agents: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    cluster_status: Dict[str, str] = {}
    if not _probe_tcp_open("127.0.0.1", 5504, timeout=0.25):
        return cluster_status
    try:
        gw = OpsPlatformGateway()
        ops_node = _resolve_node(node_id="ops-cn-1")
        if not ops_node:
            for a in agents or []:
                nid = str(a.get("node_id") or "").strip()
                node_candidate = _resolve_node(node_id=nid)
                if node_candidate and node_candidate.get("ops_base_url"):
                    ops_node = node_candidate
                    break
        if not ops_node:
            ops_node = _resolve_ops_dispatch_node("", "ops-cn-1")
        if not ops_node:
            return cluster_status
        cluster_resp = gw.cluster(ops_node, actor="probe", reason="cluster-status", ticket_id="OPS-PROBE")
        if cluster_resp and cluster_resp.get("success"):
            cluster_data = cluster_resp.get("data") or {}
            servers = cluster_data.get("Servers") or cluster_data.get("servers") or []
            for srv in servers:
                if not isinstance(srv, dict):
                    continue
                sid = str(srv.get("ServerId") or srv.get("serverId") or "").strip()
                st = srv.get("State") if srv.get("State") is not None else srv.get("state")
                if sid and st is not None:
                    cluster_status[sid] = str(st).strip().upper()
    except Exception:
        pass
    return cluster_status

def _invalidate_runtime_probe_state() -> None:
    """停止/刷新后立即使探活与 cluster 缓存失效，避免 UI 长时间显示旧 PASS。"""
    global _probe_cache, _probe_cache_ts, _cluster_runtime_cache
    with _probe_cache_lock:
        _probe_cache = {}
        _probe_cache_ts = 0.0
        _cluster_runtime_cache["ts"] = 0.0
        _cluster_runtime_cache["map"] = {}

def _seed_probe_cache_from_registry() -> None:
    """将 registry 中最新 probe/status 写入探活缓存，供 agents 列表立即读取。"""
    global _probe_cache, _probe_cache_ts
    reg = _load_agent_registry_v2()
    seeded: Dict[str, Dict[str, Any]] = {}
    for aid, item in (reg.items() if isinstance(reg, dict) else []):
        if not isinstance(item, dict) or item.get("stale"):
            continue
        agent_id = str(aid or "").strip()
        if not agent_id:
            continue
        probe = str(item.get("probe_status") or "").upper()
        effective = str(item.get("effective_status") or item.get("status") or "UNKNOWN").upper()
        seeded[agent_id] = {
            "ok": probe == "PASS",
            "effective_status": effective,
            "rtt_ms": float(item.get("probe_rtt_ms") or 0.0),
            "probe_at": str(item.get("updated_at") or _now_iso()),
            "metrics": item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
        }
    with _probe_cache_lock:
        _probe_cache = seeded
        _probe_cache_ts = _time_mod.time()

def _derive_agent_probe_from_services(services: List[Dict[str, Any]]) -> Tuple[str, str]:
    rows = [s for s in (services or []) if isinstance(s, dict)]
    if not rows:
        return "UNKNOWN", "FAIL"
    any_pass = any(str(s.get("probe_status") or "").upper() == "PASS" for s in rows)
    any_starting = any(str(s.get("run_state") or s.get("status") or "").upper() == "STARTING" for s in rows)
    if any_pass:
        return "ONLINE", "PASS"
    if any_starting:
        return "STARTING", "FAIL"
    return "OFFLINE", "FAIL"

def _fetch_cluster_runtime_status_cached(agents: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    now = _time_mod.time()
    with _probe_cache_lock:
        cached_ts = float(_cluster_runtime_cache.get("ts") or 0.0)
        cached_map = _cluster_runtime_cache.get("map") if isinstance(_cluster_runtime_cache.get("map"), dict) else {}
        if now - cached_ts < _CLUSTER_RUNTIME_CACHE_TTL_SEC and cached_map:
            return dict(cached_map)
    fresh = _fetch_cluster_runtime_status(agents)
    with _probe_cache_lock:
        _cluster_runtime_cache["ts"] = now
        _cluster_runtime_cache["map"] = dict(fresh)
    return fresh

def _service_starting_grace_active(service: Dict[str, Any], grace_sec: float = 120.0) -> bool:
    if not isinstance(service, dict):
        return False
    run = str(service.get("run_state") or service.get("status") or "").strip().upper()
    if run != "STARTING":
        return False
    ts = _parse_iso_ts(service.get("updated_at"))
    if ts <= 0:
        return True
    return (_time_mod.time() - ts) <= max(10.0, float(grace_sec))

def _merge_probe_with_cluster_status(
    probe_info: Dict[str, Any],
    agent: Dict[str, Any],
    cluster_status: Dict[str, str],
) -> None:
    """Auth/Game 等业务模块不绑独立端口，TCP 失败时用 /ops/cluster 状态判定。"""
    nid = str(agent.get("node_id") or "").strip()
    config_state = str(agent.get("config_state") or "").strip().upper()
    cat = str(agent.get("category") or "").strip().lower()
    cs = cluster_status.get(nid, "")
    if nid and cs:
        if _cluster_state_is_online(cs):
            probe_info["effective_status"] = "ONLINE"
        elif cs in ("MAINTENANCE", "1"):
            probe_info["effective_status"] = "MAINTENANCE"
        elif cs in ("STOPPED", "OFFLINE", "DOWN", "2") and not probe_info.get("ok"):
            if cat in ("application", "service") and _is_embedded_cluster_agent(agent):
                probe_info["effective_status"] = "ONLINE"
            else:
                probe_info["effective_status"] = "OFFLINE"
    if config_state == "MAINTENANCE":
        probe_info["effective_status"] = "MAINTENANCE"
    if (
        not probe_info.get("ok")
        and probe_info.get("effective_status") == "ONLINE"
        and _is_embedded_cluster_agent(agent)
        and (not cs or _cluster_state_is_online(cs) or config_state in ("ONLINE", "0"))
    ):
        probe_info["ok"] = True
        probe_info["error"] = ""
        probe_info["probe_method"] = "cluster-embedded"

def _probe_agents_batch(agents: List[Dict[str, Any]], timeout: float = 2.0) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    if not agents:
        return results
    lock = threading.Lock()

    def _probe_one(agent: Dict[str, Any]) -> None:
        aid = str(agent.get("agent_id") or "")
        host = str(agent.get("probe_host") or agent.get("host_name") or "").strip()
        if host in ("0.0.0.0", "*"):
            host = "127.0.0.1"
        port = int(agent.get("port") or agent.get("remote_game_server_port") or 0)
        proto = str(agent.get("probe_strategy") or agent.get("probe_proto") or "tcp").strip().lower()
        probe = _probe_by_protocol(host, port, proto=proto, timeout=timeout)
        probe["probe_at"] = _now_iso()
        probe["effective_status"] = "ONLINE" if probe.get("ok") else "OFFLINE"
        with lock:
            results[aid] = probe

    threads = []
    for agent in agents:
        t = threading.Thread(target=_probe_one, args=(agent,))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=max(3.0, timeout + 1.0))

    cluster_status = _fetch_cluster_runtime_status(agents)
    for agent in agents:
        aid = str(agent.get("agent_id") or "")
        probe_info = results.get(aid)
        if isinstance(probe_info, dict):
            _merge_probe_with_cluster_status(probe_info, agent, cluster_status)
    return results

def _probe_agents_realtime(agents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    批量实时探活：对每个 agent 执行 TCP connect 检测。
    返回 {agent_id: {ok, rtt_ms, error, effective_status}} 字典。
    同时尝试从 game-server /ops/cluster 拉取集群实际状态。
    """
    results: Dict[str, Dict[str, Any]] = {}
    if not agents:
        return results

    # 并行 TCP 探活
    lock = threading.Lock()
    def _probe_one(agent: Dict[str, Any]) -> None:
        aid = str(agent.get("agent_id") or "")
        # 探活地址优先用 probe_host（分布式部署时填可达 IP），fallback 用 host_name
        host = str(agent.get("probe_host") or agent.get("host_name") or "").strip()
        port = int(agent.get("port") or agent.get("remote_game_server_port") or 0)
        proto = str(agent.get("probe_strategy") or agent.get("probe_proto") or "tcp").strip().lower()
        probe = _probe_by_protocol(host, port, proto=proto)
        # 根据探活结果确定 effective_status
        if probe["ok"]:
            probe["effective_status"] = "ONLINE"
        else:
            probe["effective_status"] = "OFFLINE"
        with lock:
            results[aid] = probe

    threads = []
    for a in agents:
        t = threading.Thread(target=_probe_one, args=(a,))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=3.0)

    # 合并 cluster 状态：如果 cluster.json 里配了 Maintenance 但端口通，标记为 MAINTENANCE
    cluster_status = _fetch_cluster_runtime_status(agents)
    for aid, probe_info in results.items():
        for a in agents:
            if str(a.get("agent_id") or "") == aid:
                _merge_probe_with_cluster_status(probe_info, a, cluster_status)
                break

    return results

def _probe_background_tick() -> None:
    """后台探活一轮：线程池并发探测所有 agent，结果写入缓存，变化时通知 SSE。"""
    global _probe_cache, _probe_cache_agents, _probe_cache_ts, _probe_cache_sync_ts, _probe_change_seq

    # --- 1. 定期同步 cluster.json → agent registry ---
    now = _time_mod.time()
    if now - _probe_cache_sync_ts >= PROBE_SYNC_INTERVAL_SEC:
        try:
            _sync_cluster_to_agents()
            _probe_cache_sync_ts = now
        except Exception:
            pass

    # --- 2. 加载 agent 列表 ---
    reg = _load_agent_registry_v2()
    agents = [_normalize_agent_descriptor_v2(x) for x in reg.values() if isinstance(x, dict)]
    agents = [a for a in agents if not a.get("stale")]

    # --- 3. 线程池并发探活 ---
    probe_results: Dict[str, Dict[str, Any]] = {}
    futures = {}
    for a in agents:
        aid = str(a.get("agent_id") or "")
        host = str(a.get("probe_host") or a.get("host_name") or "").strip()
        port = int(a.get("port") or a.get("remote_game_server_port") or 0)
        proto = str(a.get("probe_strategy") or a.get("probe_proto") or "tcp").strip().lower()
        future = _probe_pool.submit(_probe_by_protocol, host, port, proto)
        futures[future] = aid

    # 尝试从 game-server /ops/health + /ops/cluster 拉取集群运行状态和指标
    # 所有 game-server 节点共享同一个 Ops API，只需调一次
    cluster_status: Dict[str, str] = {}
    cluster_metrics: Dict[str, Dict[str, Any]] = {}  # node_id -> metrics
    try:
        gw = OpsPlatformGateway()
        # 找到任一有 ops_base_url 的 node
        ops_node = None
        for a in agents:
            nid = str(a.get("node_id") or "").strip()
            node_candidate = _resolve_node(node_id=nid)
            if node_candidate and node_candidate.get("ops_base_url"):
                ops_node = node_candidate
                break
        if not ops_node:
            ops_node = _resolve_node(node_id="ops-cn-1")
        if ops_node:
            # /ops/health
            try:
                health_resp = gw.health(ops_node, actor="probe", reason="bg-metrics", ticket_id="OPS-BG")
                if health_resp and health_resp.get("success"):
                    h_data = health_resp.get("data") or {}
                    tel = h_data.get("Telemetry") or {}
                    if isinstance(tel, dict):
                        # health 返回的是 ops-cn-1 的指标
                        ops_nid = str(h_data.get("ServerId") or "ops-cn-1").strip()
                        cluster_metrics[ops_nid] = {
                            "cpu_percent": None,
                            "mem_percent": None,
                            "qps": tel.get("Qps"),
                            "rtt_ms": tel.get("P99Ms"),
                            "total_requests": tel.get("TotalRequests"),
                            "total_responses": tel.get("TotalResponses"),
                            "queue_depth": tel.get("QueueDepth"),
                            "reconnect_success_rate": tel.get("ReconnectSuccessRate"),
                            "source": "runtime.sample",
                        }
            except Exception:
                pass
            # /ops/cluster — 拉取所有节点状态
            try:
                cluster_resp = gw.cluster(ops_node, actor="probe", reason="bg-health", ticket_id="OPS-BG")
                if cluster_resp and cluster_resp.get("success"):
                    cluster_data = cluster_resp.get("data") or {}
                    c_servers = cluster_data.get("Servers") or cluster_data.get("servers") or []
                    for srv in c_servers:
                        sid = str(srv.get("ServerId") or srv.get("serverId") or "").strip()
                        st = str(srv.get("State") or srv.get("state") or "").strip().upper()
                        if sid and st:
                            cluster_status[sid] = st
                        # 从 cluster 响应提取各节点指标
                        srv_metrics = srv.get("Metrics") or srv.get("metrics") or {}
                        if isinstance(srv_metrics, dict) and any(v is not None for v in srv_metrics.values()):
                            cluster_metrics[sid] = {
                                "cpu_percent": srv_metrics.get("CpuPercent"),
                                "mem_percent": srv_metrics.get("MemPercent"),
                                "qps": srv_metrics.get("Qps"),
                                "rtt_ms": srv_metrics.get("P99Ms"),
                                "total_requests": srv_metrics.get("TotalRequests"),
                                "total_responses": srv_metrics.get("TotalResponses"),
                                "queue_depth": srv_metrics.get("QueueDepth"),
                                "reconnect_success_rate": srv_metrics.get("ReconnectSuccessRate"),
                                "source": "runtime.sample",
                            }
            except Exception:
                pass
    except Exception:
        pass

    # 采集本机指标（Redis/MongoDB/Daemon 等非 game-server 节点）
    try:
        import psutil
        disk_pct = None
        try:
            disk_pct = round(float(psutil.disk_usage("/").percent), 1)
        except Exception:
            try:
                disk_pct = round(float(psutil.disk_usage("C:\\").percent), 1)
            except Exception:
                disk_pct = None
        proc_metrics = {
            "cpu_percent": round(psutil.cpu_percent(interval=0.1), 1),
            "mem_percent": round(psutil.virtual_memory().percent, 1),
            "disk_percent": disk_pct,
            "source": "runtime.sample",
            "updated_at": _now_iso(),
        }
    except ImportError:
        proc_metrics = _fallback_local_control_metrics()
    except Exception:
        proc_metrics = _fallback_local_control_metrics()
    if not any(proc_metrics.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent")):
        proc_metrics = _fallback_local_control_metrics()

    # 收集探活结果
    for future in as_completed(futures, timeout=PROBE_INTERVAL_SEC):
        aid = futures[future]
        probe = future.result()
        probe["probe_at"] = _now_iso()
        if probe["ok"]:
            probe["effective_status"] = "ONLINE"
        else:
            probe["effective_status"] = "OFFLINE"
        probe["metrics"] = {}
        probe_results[aid] = probe

    # 合并 cluster 状态 + 指标
    for aid, probe_info in probe_results.items():
        for a in agents:
            if str(a.get("agent_id") or "") == aid:
                _merge_probe_with_cluster_status(probe_info, a, cluster_status)
                nid = str(a.get("node_id") or "").strip()
                config_state = str(a.get("config_state") or "").strip().upper()
                if config_state == "MAINTENANCE":
                    probe_info["effective_status"] = "MAINTENANCE"
                # 指标：优先 game-server 上报的，fallback 本机
                if nid and nid in cluster_metrics:
                    probe_info["metrics"] = cluster_metrics[nid]
                    probe_info["metrics"]["source"] = "real"
                else:
                    # 非集群节点或集群没上报指标的，用本机指标
                    if probe_info.get("effective_status") == "ONLINE" and proc_metrics:
                        probe_info["metrics"] = dict(proc_metrics)
                        probe_info["metrics"]["source"] = "local"
                break

    # --- 4. 检测变化，更新缓存 ---
    changed = False
    with _probe_cache_lock:
        for aid, new_pr in probe_results.items():
            old_pr = _probe_cache.get(aid)
            # 状态变化 或 指标变化 都算 changed
            if old_pr is None:
                changed = True
            elif old_pr.get("effective_status") != new_pr.get("effective_status"):
                changed = True
            elif old_pr.get("metrics") != new_pr.get("metrics"):
                changed = True
        _probe_cache = probe_results
        _probe_cache_agents = agents
        _probe_cache_ts = _time_mod.time()
        if changed:
            _probe_change_seq += 1

    # --- 4b. 更新 canonical agent 的服务级探活与指标采样 ---
    try:
        _reconcile_all_gameserver_daemon_states()
        tick_now = _now_iso()
        reg = _load_agent_registry_v2()
        canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else {}
        if canonical and not canonical.get("stale"):
            host = str(canonical.get("probe_host") or canonical.get("host_name") or "127.0.0.1").strip()
            services = canonical.get("services") if isinstance(canonical.get("services"), list) else []
            svc_changed = False
            refreshed_services: List[Dict[str, Any]] = []
            for svc in services:
                if not isinstance(svc, dict):
                    continue
                resolved = _resolve_service_runtime_state(svc, host=host, cluster_status=cluster_status)
                nid = str(resolved.get("node_id") or resolved.get("service_id") or "").strip()
                if nid and nid in cluster_metrics:
                    resolved["metrics"] = dict(cluster_metrics[nid])
                    resolved["metrics"]["source"] = "runtime.sample"
                elif resolved.get("probe_status") == "PASS" and proc_metrics:
                    resolved["metrics"] = dict(proc_metrics)
                    resolved["metrics"]["source"] = "runtime.sample"
                resolved["updated_at"] = tick_now
                refreshed_services.append(resolved)
                svc_changed = True
            services = refreshed_services
            merged_control: Dict[str, Any] = _sample_local_control_metrics()
            if proc_metrics:
                for key, val in proc_metrics.items():
                    if val is not None:
                        merged_control[key] = val
            for nid, cm in cluster_metrics.items():
                if isinstance(cm, dict):
                    for key in ("cpu_percent", "mem_percent", "qps", "rtt_ms", "queue_depth"):
                        if cm.get(key) is not None:
                            merged_control[key] = cm.get(key)
            if merged_control:
                merged_control["updated_at"] = tick_now
                merged_control["source"] = "runtime.sample"
                canonical["metrics"] = {"control": merged_control, **merged_control}
                canonical["metrics_live"] = True
            canonical["services"] = services
            canonical["last_seen"] = tick_now
            canonical["updated_at"] = tick_now
            pr_main = probe_results.get(CANONICAL_LOCAL_AGENT_ID) or {}
            if pr_main:
                canonical["probe_status"] = "PASS" if pr_main.get("ok") else "FAIL"
                canonical["probe_rtt_ms"] = float(pr_main.get("rtt_ms") or 0.0)
            _append_realtime_agent_sample(canonical)
            reg[CANONICAL_LOCAL_AGENT_ID] = canonical
            _save_agent_registry_v2(reg)
            if svc_changed:
                with _probe_cache_lock:
                    _probe_change_seq += 1
    except Exception:
        pass

    # --- 5. 每轮都推送（参数实时滚动） ---
    payload = _build_sse_payload(agents, probe_results)
    _sse_broadcast(payload)

def _build_sse_payload(agents: List[Dict[str, Any]], probe_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """构造推送给前端的完整 payload。"""
    now_iso = _now_iso()
    jobs = _load_agent_jobs()
    queue: Dict[str, int] = {"PENDING": 0, "RUNNING": 0, "SUCCESS": 0, "FAILED": 0, "CANCELED": 0, "TIMEOUT": 0}
    for item in jobs:
        if not isinstance(item, dict):
            continue
        st = str(item.get("status") or "").upper()
        if st in queue:
            queue[st] += 1
    online = 0
    out_agents: List[Dict[str, Any]] = []
    bindings = _load_node_agent_bindings()
    bound_agent_ids = set(str(v or "") for v in bindings.values() if str(v or "").strip())
    for a in agents:
        obj = dict(a)
        aid = str(obj.get("agent_id") or "")
        pr = probe_results.get(aid) or {}
        obj["effective_status"] = pr.get("effective_status", "UNKNOWN")
        obj["probe_status"] = "PASS" if pr.get("ok") else "FAIL"
        obj["probe_rtt_ms"] = pr.get("rtt_ms", 0.0)
        obj["probe_source"] = "bg-engine"
        obj["probe_at"] = str(pr.get("probe_at") or now_iso)
        obj["is_bound"] = aid in bound_agent_ids
        # Heartbeat metrics are the source of truth. Probe metrics may be stale or
        # synthetic, so only fill fields that the agent did not report.
        pr_metrics = pr.get("metrics") or {}
        base_m = obj.get("metrics") if isinstance(obj.get("metrics"), dict) else {}
        merged_metrics = dict(base_m)
        if pr_metrics:
            for key in (
                "cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms",
                "service_cpu_percent", "service_memory_mb", "total_requests",
                "total_responses", "queue_depth", "reconnect_success_rate",
            ):
                if merged_metrics.get(key) is None and pr_metrics.get(key) is not None:
                    merged_metrics[key] = pr_metrics.get(key)
            if not merged_metrics.get("updated_at"):
                merged_metrics["updated_at"] = str(pr_metrics.get("updated_at") or now_iso)
            if not merged_metrics.get("source"):
                merged_metrics["source"] = str(pr_metrics.get("source") or "probe")
        if merged_metrics:
            control_metrics = {
                "cpu_percent": merged_metrics.get("cpu_percent"),
                "mem_percent": merged_metrics.get("mem_percent"),
                "disk_percent": merged_metrics.get("disk_percent"),
                "qps": merged_metrics.get("qps"),
                "rtt_ms": merged_metrics.get("rtt_ms"),
                "service_cpu_percent": merged_metrics.get("service_cpu_percent"),
                "service_memory_mb": merged_metrics.get("service_memory_mb"),
                "total_requests": merged_metrics.get("total_requests"),
                "total_responses": merged_metrics.get("total_responses"),
                "queue_depth": merged_metrics.get("queue_depth"),
                "reconnect_success_rate": merged_metrics.get("reconnect_success_rate"),
                "updated_at": str(merged_metrics.get("updated_at") or now_iso),
                "source": str(merged_metrics.get("source") or "agent"),
            }
            business_metrics = (base_m.get("business") if isinstance(base_m.get("business"), dict) else {})
            obj["metrics"] = {**control_metrics, "control": control_metrics, "business": business_metrics}
            obj["metrics_missing"] = {
                "control": not any(control_metrics.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")),
                "business": not any(business_metrics.get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn")),
            }
        else:
            obj["metrics_missing"] = {"control": True, "business": True}
        if str(obj.get("effective_status") or "").upper() in ("ONLINE", "READY", "RUNNING"):
            online += 1
        out_agents.append(obj)
    device_snaps: Dict[str, Dict[str, Any]] = {}
    for item in out_agents:
        did = str(item.get("device_id") or "unknown-device")
        m = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        mc = m.get("control") if isinstance(m.get("control"), dict) else m
        mb = m.get("business") if isinstance(m.get("business"), dict) else {}
        snap = device_snaps.get(did) if isinstance(device_snaps.get(did), dict) else {
            "control": {"cpu_percent": None, "mem_percent": None, "disk_percent": None, "qps": None, "rtt_ms": None, "service_cpu_percent": None, "service_memory_mb": None, "updated_at": "", "source": "missing"},
            "business": {"qps": None, "rtt_p95_ms": None, "rtt_p99_ms": None, "error_rate": None, "conn": None, "updated_at": "", "source": "missing"},
            "updated_at": "", "source": "missing",
        }
        for key in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"):
            if mc.get(key) is not None:
                snap["control"][key] = mc.get(key)
        for key in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"):
            if mb.get(key) is not None:
                snap["business"][key] = mb.get(key)
        if mc.get("updated_at"):
            snap["control"]["updated_at"] = str(mc.get("updated_at"))
            snap["updated_at"] = str(mc.get("updated_at"))
        if mc.get("source"):
            snap["control"]["source"] = str(mc.get("source"))
            snap["source"] = str(mc.get("source"))
        device_snaps[did] = snap
    for item in out_agents:
        snap = device_snaps.get(str(item.get("device_id") or "unknown-device")) or {}
        item["device_metrics_snapshot"] = snap
        item["metrics"] = {**(snap.get("control") or {}), "control": (snap.get("control") or {}), "business": (snap.get("business") or {})}
        item["metrics_missing"] = {"control": not any((snap.get("control") or {}).get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")), "business": not any((snap.get("business") or {}).get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"))}
    return {
        "ok": True,
        "metrics": {
            "agents_total": len(agents),
            "agents_online": online,
            "jobs_pending": queue.get("PENDING", 0),
            "jobs_running": queue.get("RUNNING", 0),
        },
        "queue": queue,
        "agents": out_agents,
        "bindings": bindings,
        "policy": _load_agent_policy(),
        "probe_seq": _probe_change_seq,
        "pushed_at": now_iso,
    }

def _sse_broadcast(payload: Dict[str, Any]) -> None:
    """向所有 SSE 订阅者广播 payload。"""
    msg = json.dumps(payload, ensure_ascii=False)
    dead: List[_queue_mod.Queue] = []
    with _sse_sub_lock:
        for q in _sse_subscribers:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                _sse_subscribers.remove(q)
            except ValueError:
                pass

def _probe_bg_loop(app_ref) -> None:
    """后台探活主循环，daemon 线程。"""
    while True:
        with app_ref.app_context():
            try:
                _probe_background_tick()
            except Exception as exc:
                import logging
                logging.getLogger("ops.probe").warning("probe tick failed: %s", exc, exc_info=True)
        _time_mod.sleep(PROBE_INTERVAL_SEC)

def _ensure_probe_bg_started() -> None:
    """确保后台探活线程已启动。在首次 API 请求时调用。"""
    global _probe_bg_started
    if _probe_bg_started:
        return
    _probe_bg_started = True
    from flask import current_app
    app_ref = current_app._get_current_object()
    t = threading.Thread(target=_probe_bg_loop, args=(app_ref,), name="ops-probe-bg", daemon=True)
    t.start()

def _business_test_repo() -> str:
    return _resolve_game_server_repo()

def _biz_key_variants(key: str) -> List[str]:
    k = str(key or "").strip()
    if not k:
        return []
    variants = [k]
    if "_" in k:
        variants.append("".join(part[:1].upper() + part[1:] for part in k.split("_") if part))
    else:
        variants.append(k[:1].upper() + k[1:])
    return variants

def _biz_step_get(step: Dict[str, Any], *keys: str) -> Any:
    if not isinstance(step, dict):
        return None
    for key in keys:
        for variant in _biz_key_variants(key):
            if variant in step:
                return step.get(variant)
    return None

def _biz_run_get(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    if not isinstance(data, dict):
        return default
    for variant in _biz_key_variants(key):
        if variant in data:
            return data.get(variant)
    return default

def _normalize_business_steps(steps: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(steps, list):
        return out
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        server_raw = _biz_step_get(raw, "server") or {}
        client_raw = _biz_step_get(raw, "client") or {}
        out.append({
            "step_id": _biz_step_get(raw, "step_id", "id"),
            "protocol": _biz_step_get(raw, "protocol"),
            "message_id": _biz_step_get(raw, "message_id"),
            "result": _biz_step_get(raw, "result"),
            "blocked_reason": _biz_step_get(raw, "blocked_reason"),
            "client": {
                "request_json": _biz_step_get(client_raw, "request_json") if isinstance(client_raw, dict) else None,
                "transport": _biz_step_get(client_raw, "transport") if isinstance(client_raw, dict) else None,
                "seq": _biz_step_get(client_raw, "seq") if isinstance(client_raw, dict) else None,
            },
            "server": {
                "response_json": _biz_step_get(server_raw, "response_json") if isinstance(server_raw, dict) else None,
                "error_code": _biz_step_get(server_raw, "error_code") if isinstance(server_raw, dict) else None,
                "latency_ms": _biz_step_get(server_raw, "latency_ms") if isinstance(server_raw, dict) else None,
                "data_type": _biz_step_get(server_raw, "data_type") if isinstance(server_raw, dict) else None,
            },
        })
    return out

def _count_gameserver_processes() -> int:
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq GameServer.GameServerApp.exe", "/NH"],
                text=True,
                errors="replace",
            )
            return sum(1 for line in out.splitlines() if "GameServer.GameServerApp" in line)
    except Exception:
        pass
    return -1

def _ws_handshake_probe(host: str = "127.0.0.1", port: int = 15050, path: str = "/ws/", timeout_sec: float = 3.0) -> Tuple[bool, str]:
    import base64
    import secrets

    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")
    try:
        with socket.create_connection((host, port), timeout=timeout_sec) as sock:
            sock.settimeout(timeout_sec)
            sock.sendall(req)
            resp = b""
            while b"\r\n\r\n" not in resp and len(resp) < 8192:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp += chunk
            ok = b"101" in resp.split(b"\r\n", 1)[0] if resp else False
            return ok, ("ws_open" if ok else "ws_handshake_failed")
    except OSError as ex:
        return False, "ws_connect_failed:" + str(ex)

def _resolve_business_test_gateway_endpoint(
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    explicit = body.get("gateway_endpoint") if isinstance(body.get("gateway_endpoint"), dict) else {}
    if explicit.get("ws_url") or explicit.get("host"):
        return dict(explicit)
    project_id = str(body.get("project_id") or "").strip()
    env_key = _normalize_env_key(body.get("env_key") or "production")
    topology_id = str(body.get("topology_id") or "").strip()
    if not topology_id and project_id:
        topology_id = _runtime_default_topology_id(project_id, env_key)
    if topology_id:
        scoped = _load_topology_scoped(project_id, env_key, topology_id)
        topo = {
            "nodes": scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else [],
            "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
        }
        bindings = _load_scope_agent_bindings(topology_id)
        return resolve_gateway_endpoint(topo, bindings, str(body.get("transport") or "websocket"))
    return resolve_gateway_endpoint(None, None, str(body.get("transport") or "websocket"))

def _business_test_login_probe(
    gateway_host: str,
    gateway_port: int = 15050,
    relay_host: str = "",
    relay_port: int = 15501,
) -> Tuple[bool, str]:
    host = str(gateway_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    ws_ok, detail = _ws_handshake_probe(host, int(gateway_port or 15050))
    if not ws_ok:
        return False, "gateway_ws_failed:" + detail
    rh = str(relay_host or host).strip() or host
    rp = int(relay_port or 0)
    if rp > 0 and not _probe_tcp_open(rh, rp, timeout=0.6):
        return False, f"auth_cluster_relay_unreachable:{rh}:{rp}"
    return True, "gateway_ws_and_auth_relay_ok"

def _business_test_preflight(
    transport: str,
    gateway_endpoint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    transport = str(transport or "websocket").strip().lower()
    endpoint = gateway_endpoint if isinstance(gateway_endpoint, dict) else {}
    host = str(endpoint.get("host") or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    port = int(endpoint.get("port") or 15050)
    ws_url = str(endpoint.get("ws_url") or f"ws://{host}:{port}/ws/")
    gs_count = _count_gameserver_processes()
    issues: List[str] = []
    warnings: List[str] = []
    transport_ok = False
    login_probe_ok = False
    login_detail = ""
    if transport == "websocket":
        transport_ok, detail = _ws_handshake_probe(host, port)
        if not transport_ok:
            issues.append(f"WebSocket 握手失败: {ws_url} ({detail})")
        else:
            login_probe_ok, login_detail = _business_test_login_probe(host, port, host, 15501)
            if not login_probe_ok:
                issues.append(
                    "Login 前置探针失败: " + login_detail
                    + "；请检查 Gateway 集群转发与 Auth ClusterRelay 端口 (15501)"
                )
    elif transport == "tcp":
        tcp_host = str(endpoint.get("tcp_host") or host).strip() or host
        tcp_port = int(endpoint.get("tcp_port") or 5601)
        try:
            with socket.create_connection((tcp_host, tcp_port), timeout=2):
                transport_ok = True
        except OSError as ex:
            issues.append(f"TCP {tcp_host}:{tcp_port} 不可达: {ex}")
    else:
        transport_ok = True
        login_probe_ok = True
    if gs_count == 0 and not transport_ok:
        issues.append("未检测到 GameServer 进程且传输探针失败，请先「一键启动全流程」启动分布式拓扑")
    elif gs_count == 0 and transport_ok:
        warnings.append("未从 tasklist 解析到 GameServer 进程名，但传输探针已通过（可能为进程名截断）")
    elif gs_count > 1 and transport_ok and login_probe_ok:
        warnings.append(f"检测到 {gs_count} 个 GameServer 进程（分布式多进程模式）")
    return {
        "ok": len(issues) == 0,
        "transport": transport,
        "transport_ok": transport_ok,
        "login_probe_ok": login_probe_ok,
        "login_probe_detail": login_detail,
        "gateway_endpoint": endpoint,
        "gateway_ws_url": ws_url,
        "gameserver_process_count": gs_count,
        "issues": issues,
        "warnings": warnings,
        "message": "; ".join(issues) if issues else ("; ".join(warnings) if warnings else "preflight passed"),
    }

def _summarize_business_test_failure(result: Dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return "business test failed"
    parts: List[str] = []
    err = str(result.get("error") or "").strip()
    if err:
        parts.append(err)
    exit_code = result.get("exit_code")
    if exit_code not in (None, 0):
        parts.append("exit_code=" + str(exit_code))
    biz = result.get("business_run") if isinstance(result.get("business_run"), dict) else {}
    biz_err = str((biz or {}).get("error") or "").strip()
    if biz_err:
        parts.append("runner_error=" + biz_err)
    steps = _normalize_business_steps(result.get("steps"))
    result["steps"] = steps
    failed_steps = [s for s in steps if str(s.get("result") or "") == "failed"]
    if failed_steps:
        s0 = failed_steps[0]
        proto = str(s0.get("protocol") or "-")
        reason = str(s0.get("blocked_reason") or s0.get("step_id") or "unknown")
        server = s0.get("server") if isinstance(s0.get("server"), dict) else {}
        latency = server.get("latency_ms")
        parts.append("failed_step=" + proto + " reason=" + reason + (f" latency_ms={latency}" if latency is not None else ""))
        if proto == "Login_c2s" and reason == "timeout":
            parts.append(
                "hint=Login 超时无响应：请检查 Gateway 集群转发、Auth ClusterRelay(15501) 与 Mongo/Redis 可达；"
                "确认业务测试连接的 Gateway 端点来自拓扑 probe_host"
            )
    preflight = result.get("preflight") if isinstance(result.get("preflight"), dict) else {}
    for issue in (preflight.get("issues") or []) if isinstance(preflight.get("issues"), list) else []:
        parts.append("preflight=" + str(issue))
    stderr = str(result.get("stderr") or "").strip()
    if stderr:
        tail = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
        if tail:
            parts.append("stderr_tail=" + tail[-1][:240])
    stdout = str(result.get("stdout") or "").strip()
    if stdout and not failed_steps:
        tail = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        if tail:
            parts.append("stdout_tail=" + tail[-1][:240])
    if not parts:
        return "business test failed (no detail; check stderr/stdout in response JSON)"
    return "; ".join(parts)

def _run_business_test_runner(
    plan_id: str,
    transport: str,
    plan_override: Optional[Dict[str, Any]] = None,
    user_prefix: str = "biztest",
    server_id: str = "game-cn-1",
    gateway_endpoint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    repo = _business_test_repo()
    paths = resolve_paths(repo)
    runner_py = paths.get("runner_py") or ""
    if not os.path.isfile(runner_py):
        return {"ok": False, "error": "runner_missing", "message": "run-business-test.py not found", "path": runner_py}
    out_dir = os.path.join(DATA_DIR, "business_test_runs", plan_id + "-" + uuid.uuid4().hex[:8])
    os.makedirs(out_dir, exist_ok=True)
    endpoint = gateway_endpoint if isinstance(gateway_endpoint, dict) else {}
    ws_url = str(endpoint.get("ws_url") or "").strip()
    tcp_host = str(endpoint.get("tcp_host") or endpoint.get("host") or "").strip()
    tcp_port = int(endpoint.get("tcp_port") or 0)
    py_cmds = [
        "py", "-3", runner_py, "--transport", transport, "--output", out_dir,
        "--user-prefix", user_prefix, "--server-id", server_id, "--timeout-ms", "15000",
    ]
    if ws_url and transport == "websocket":
        py_cmds.extend(["--ws", ws_url])
    if tcp_host and transport == "tcp":
        py_cmds.extend(["--tcp-host", tcp_host])
        if tcp_port > 0:
            py_cmds.extend(["--tcp-port", str(tcp_port)])
    if plan_override and isinstance(plan_override, dict):
        plan_copy = dict(plan_override)
        if ws_url and transport == "websocket":
            plan_copy["endpoint"] = dict(plan_copy.get("endpoint") or {})
            plan_copy["endpoint"]["ws"] = ws_url
        inline_path = os.path.join(out_dir, "plan-inline.json")
        with open(inline_path, "w", encoding="utf-8") as f:
            json.dump(plan_copy, f, ensure_ascii=False, indent=2)
        py_cmds.extend(["--plan-path", inline_path])
    elif plan_id:
        py_cmds.extend(["--plan", plan_id])
    else:
        return {"ok": False, "error": "missing_plan", "message": "plan_id or plan_override required"}
    started = time.time()
    try:
        proc = subprocess.run(py_cmds, cwd=os.path.dirname(runner_py), capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "message": "business test timed out", "artifact_dir": out_dir}
    except FileNotFoundError:
        py_cmds[0] = "python"
        proc = subprocess.run(py_cmds, cwd=os.path.dirname(runner_py), capture_output=True, text=True, timeout=600)
    elapsed = round(time.time() - started, 3)
    run_json_path = os.path.join(out_dir, "business-run.json")
    report_json_path = os.path.join(out_dir, "business-report.json")
    run_data: Dict[str, Any] = {}
    if os.path.isfile(run_json_path):
        try:
            with open(run_json_path, "r", encoding="utf-8") as f:
                run_data = json.load(f)
        except Exception:
            run_data = {}
    ok = proc.returncode == 0 and bool(_biz_run_get(run_data, "passed", proc.returncode == 0))
    server_log_tail = ""
    try:
        log_dir = os.path.join(repo, "game-server", "bin", "Debug", "logs")
        if os.path.isdir(log_dir):
            logs = sorted(
                [os.path.join(log_dir, n) for n in os.listdir(log_dir) if n.startswith("cluster-") and n.endswith(".log")],
                key=os.path.getmtime,
                reverse=True,
            )
            if logs:
                with open(logs[0], "r", encoding="utf-8", errors="replace") as lf:
                    lines = lf.readlines()
                server_log_tail = "".join(lines[-40:])
    except Exception:
        server_log_tail = ""
    raw_steps = _biz_run_get(run_data, "steps") or []
    if not isinstance(raw_steps, list):
        raw_steps = []
    norm_steps = _normalize_business_steps(raw_steps)
    result: Dict[str, Any] = {
        "ok": ok,
        "exit_code": proc.returncode,
        "seconds": elapsed,
        "plan_id": plan_id,
        "transport": transport,
        "artifact_dir": out_dir,
        "business_run": run_data,
        "steps": norm_steps,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
        "server_log_tail": server_log_tail,
        "report_json": report_json_path if os.path.isfile(report_json_path) else "",
        "run_json": run_json_path if os.path.isfile(run_json_path) else "",
    }
    if not ok:
        result["summary"] = _summarize_business_test_failure(result)
        result["message"] = result["summary"]
    return result

def _cancel_runtime_start_runs_for_scope(
    project_id: str,
    env_key: str,
    topology_id: str,
    except_run_id: str = "",
) -> int:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    skip = str(except_run_id or "").strip()
    rows = _load_runtime_runs()
    changed = 0
    now = _now_iso()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if pid and str(row.get("project_id") or "") != pid:
            continue
        if env and _normalize_env_key(row.get("env_key") or "") != env:
            continue
        if tid and str(row.get("topology_id") or "") != tid:
            continue
        if str(row.get("op") or "").lower() != "start":
            continue
        if str(row.get("status") or "").lower() not in ("running", "queued"):
            continue
        if skip and str(row.get("run_id") or "") == skip:
            continue
        row["status"] = "canceled"
        row["updated_at"] = now
        changed += 1
    if changed:
        _save_runtime_runs(rows)
    return changed

def _mark_project_runtime_services_stopped(project_id: str) -> None:
    pid = str(project_id or "").strip()
    for svc in _services_for_project(pid):
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or "").strip()
        if sid:
            _update_canonical_service_runtime(sid, status="STOPPED", run_state="STOPPED", probe_status="FAIL")
    reg = _load_agent_registry_v2()
    canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else None
    if isinstance(canonical, dict):
        canonical["status"] = "OFFLINE"
        canonical["effective_status"] = "OFFLINE"
        canonical["run_state"] = "STOPPED"
        canonical["probe_status"] = "FAIL"
        canonical["updated_at"] = _now_iso()
        reg[CANONICAL_LOCAL_AGENT_ID] = canonical
        _save_agent_registry_v2(reg)
    _invalidate_runtime_probe_state()
    _seed_probe_cache_from_registry()

def _runtime_cluster_stop_all(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    actor: str,
    run_id: str,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    ticket_id = "OPS-RUN-" + str(run_id or "")[-6:]
    reason = "拓扑运行模式一键停止"
    logs: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    ordered = [n for n in (topo_nodes or []) if isinstance(n, dict)]
    ordered.reverse()

    for topo_node in ordered:
        nid = str(topo_node.get("id") or "").strip()
        if not nid:
            continue
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        if not node:
            logs.append({"ts": _now_iso(), "level": "error", "node_id": nid, "message": "节点不存在，已跳过"})
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "FAILED", "mode": "direct"})
            continue
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        if _is_external_daemon_node(node):
            result = _ops_platform_daemon_action(node, "stop", reason, ticket_id, actor)
            ok = bool(result.get("success"))
            if service_id:
                st = "STOPPED" if ok else "FAILED"
                _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="FAIL")
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS" if ok else "FAILED", "mode": "daemon"})
            logs.append(
                {
                    "ts": _now_iso(),
                    "level": "info" if ok else "error",
                    "node_id": nid,
                    "message": str(result.get("message") or ("daemon stop ok" if ok else "daemon stop failed")),
                }
            )
            continue
        result = _execute_canonical_service_action(
            pid,
            nid,
            service_id,
            "stop",
            actor,
            reason,
            ticket_id,
            {"run_mode": "direct", "via_agent": False},
        )
        ok = bool(result.get("ok"))
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS" if ok else "FAILED", "mode": "direct"})
        logs.append(
            {
                "ts": _now_iso(),
                "level": "info" if ok else "error",
                "node_id": nid,
                "message": str(result.get("message") or ("stop ok" if ok else "stop failed")),
            }
        )

    gs_stop = _stop_local_game_server()
    logs.append(
        {
            "ts": _now_iso(),
            "level": "info" if gs_stop.get("success") else "warn",
            "node_id": "cluster",
            "message": str(gs_stop.get("message") or "GameServer stop signal sent"),
        }
    )
    _mark_project_runtime_services_stopped(pid)
    fail = len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() != "SUCCESS"])
    logs.append(
        {
            "ts": _now_iso(),
            "level": "info" if fail == 0 else "warn",
            "node_id": "cluster",
            "message": f"集群级停止完成: success={len(items) - fail}, failed={fail}",
        }
    )
    return {"items": items, "logs": logs, "failed": fail}

def _topo_order_node_ids(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], reverse: bool = False) -> List[str]:
    ids = [str(n.get("id") or "").strip() for n in (nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()]
    if not ids:
        return []
    indeg = {i: 0 for i in ids}
    adj = {i: [] for i in ids}
    for edge in edges or []:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if frm in indeg and to in indeg:
            adj[frm].append(to)
            indeg[to] += 1
    q = [i for i in ids if indeg[i] == 0]
    out: List[str] = []
    while q:
        cur = q.pop(0)
        out.append(cur)
        for nx in adj.get(cur, []):
            indeg[nx] -= 1
            if indeg[nx] == 0:
                q.append(nx)
    if len(out) != len(ids):
        out = ids
    if reverse:
        out.reverse()
    return out

def _refresh_runtime_service_probes_from_topology(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    scope = _resolve_orchestration_scope(pid, tid, bindings)
    default_host = str(scope.get("default_probe_host") or DEFAULT_LOOPBACK)
    gateway_live = _probe_tcp_open(default_host, _RUNTIME_GATEWAY_PROBE_PORT)
    ops_live = _probe_tcp_open(default_host, _RUNTIME_OPS_PROBE_PORT)
    live_count = 0
    total = 0
    for topo_node in topo_nodes or []:
        if not isinstance(topo_node, dict):
            continue
        nid = str(topo_node.get("id") or "").strip()
        if not nid:
            continue
        total += 1
        node = _build_runtime_node_from_topology_node(pid, env_key, topo_node, topology_id)
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        if _is_embedded_topology_node(topo_node, contract):
            live = gateway_live or ops_live
        elif probe_port > 0:
            live = _probe_tcp_open(host, probe_port)
        else:
            role = str(node.get("role") or "").strip().lower()
            live = (gateway_live or ops_live) if role in ("auth", "game", "business", "admin", "ops") else False
        if live:
            live_count += 1
        st = "RUNNING" if live else "STOPPED"
        if service_id:
            _update_canonical_service_runtime(
                service_id,
                status=st,
                run_state=st,
                probe_status="PASS" if live else "FAIL",
                metrics=_sample_local_control_metrics() if live else {},
            )
    reg = _load_agent_registry_v2()
    canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else None
    if isinstance(canonical, dict):
        any_live = live_count > 0 and (gateway_live or ops_live)
        canonical["status"] = "ONLINE" if any_live else "OFFLINE"
        canonical["effective_status"] = canonical["status"]
        canonical["run_state"] = canonical["status"]
        canonical["probe_status"] = "PASS" if gateway_live else ("WARN" if ops_live else "FAIL")
        canonical["updated_at"] = _now_iso()
        canonical["metrics"] = _sample_local_control_metrics()
        reg[CANONICAL_LOCAL_AGENT_ID] = canonical
        _save_agent_registry_v2(reg)
        _append_realtime_agent_sample(canonical)
    return {"live_count": live_count, "total": total, "gateway_live": gateway_live, "ops_live": ops_live}

def _ensure_runtime_infra_ports(
    timeout_sec: float = 45.0,
    project_id: str = "",
    env_key: str = "",
    topology_id: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    """确保 Mongo/Redis 基础设施端口可用；Windows 走本机守护进程启动逻辑。"""

    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    mongo_host = _resolve_orchestration_probe_host(
        str(project_id or ""), tid, {"id": "mongo-db-cn-1"}, bindings
    )
    redis_host = _resolve_orchestration_probe_host(
        str(project_id or ""), tid, {"id": "redis-cache-cn-1"}, bindings
    )

    def _ports_snapshot() -> Tuple[bool, str]:
        mongo_ok = _probe_tcp_open(mongo_host, 27017, timeout=0.15)
        redis_ok = _probe_tcp_open(redis_host, 6379, timeout=0.15)
        msg = (
            f"mongo:{mongo_host}:27017={'PASS' if mongo_ok else 'FAIL'} "
            f"redis:{redis_host}:6379={'PASS' if redis_ok else 'FAIL'}"
        )
        return bool(mongo_ok and redis_ok), msg

    ok, msg = _ports_snapshot()
    if ok:
        return True, msg

    pid = str(project_id or "GomeKu").strip()
    env = _normalize_env_key(env_key or "production")
    tid = str(topology_id or "").strip()
    scoped_nodes: List[Dict[str, Any]] = []
    try:
        scoped = _load_topology_scoped(pid, env, tid) if tid else {}
        scoped_nodes = [n for n in (scoped.get("nodes") or []) if isinstance(n, dict)]
    except Exception:
        scoped_nodes = []

    def _infra_node(nid: str, role: str, port: int) -> Dict[str, Any]:
        hit = next((n for n in scoped_nodes if str(n.get("id") or "") == nid), None)
        if isinstance(hit, dict):
            return _build_runtime_node_from_topology_node(pid, env, hit, tid)
        return {
            "id": nid,
            "role": role,
            "port": port,
            "daemon_profile": "external_daemon",
        }

    for nid, role, port in (
        ("mongo-db-cn-1", "database", 27017),
        ("redis-cache-cn-1", "cache", 6379),
    ):
        infra_host = mongo_host if role == "database" else redis_host
        if _probe_tcp_open(infra_host, port, timeout=0.12):
            continue
        node = _infra_node(nid, role, port)
        if os.name == "nt":
            _start_external_daemon_node(node, "start")
        else:
            if role == "database":
                db_dir = _gomeku_mongo_dbpath()
                os.makedirs(db_dir, exist_ok=True)
                for cmd in (
                    ["mongod", "--dbpath", db_dir, "--port", "27017", "--bind_ip", "127.0.0.1", "--fork", "--logpath", f"{db_dir}/mongod.log"],
                    ["/opt/homebrew/bin/mongod", "--dbpath", db_dir, "--port", "27017", "--bind_ip", "127.0.0.1", "--fork", "--logpath", f"{db_dir}/mongod.log"],
                    ["/usr/local/bin/mongod", "--dbpath", db_dir, "--port", "27017", "--bind_ip", "127.0.0.1", "--fork", "--logpath", f"{db_dir}/mongod.log"],
                ):
                    try:
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                    except Exception:
                        pass
                    if _probe_tcp_open(mongo_host, 27017, timeout=0.15):
                        break
            else:
                for cmd in (
                    ["redis-server", "--daemonize", "yes", "--port", "6379", "--bind", "127.0.0.1"],
                    ["/opt/homebrew/bin/redis-server", "--daemonize", "yes", "--port", "6379", "--bind", "127.0.0.1"],
                ):
                    try:
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                    except Exception:
                        pass
                    if _probe_tcp_open(redis_host, 6379, timeout=0.15):
                        break

    deadline = time.time() + max(5.0, float(timeout_sec))
    last = msg
    while time.time() < deadline:
        ok, last = _ports_snapshot()
        if ok:
            return True, last
        time.sleep(0.5)
    return False, last

def _runtime_run_patch(
    run_id: str,
    *,
    items: Optional[List[Dict[str, Any]]] = None,
    logs_append: Optional[List[Dict[str, Any]]] = None,
    status: Optional[str] = None,
) -> None:
    rid = str(run_id or "").strip()
    if not rid:
        return
    with _runtime_orchestrator_lock:
        run = _find_runtime_run(rid)
        if not isinstance(run, dict):
            return
        if items is not None:
            run["items"] = items
        if logs_append:
            run_logs = run.get("logs") if isinstance(run.get("logs"), list) else []
            run_logs.extend(logs_append)
            if len(run_logs) > 400:
                run_logs = run_logs[-400:]
            run["logs"] = run_logs
        if status:
            run["status"] = status
        run["updated_at"] = _now_iso()
        _upsert_runtime_run(run)

def _runtime_orchestrator_log(run_id: str, node_id: str, level: str, message: str) -> None:
    _runtime_run_patch(
        run_id,
        logs_append=[{"ts": _now_iso(), "level": level, "node_id": node_id, "message": message}],
    )

def _runtime_orchestrator_set_item(items: List[Dict[str, Any]], node_id: str, status: str, **extra: Any) -> None:
    nid = str(node_id or "").strip()
    for item in items:
        if isinstance(item, dict) and str(item.get("node_id") or "") == nid:
            item["status"] = status
            for k, v in extra.items():
                item[k] = v
            return

def _wait_agent_job_terminal(job_id: str, timeout_sec: float = 120.0) -> Tuple[bool, Dict[str, Any]]:
    jid = str(job_id or "").strip()
    if not jid:
        return False, {"status": "FAILED", "message": "missing job_id"}
    deadline = time.time() + max(5.0, float(timeout_sec))
    while time.time() < deadline:
        jobs = _load_agent_jobs()
        hit = next((j for j in jobs if isinstance(j, dict) and str(j.get("job_id") or "") == jid), None)
        if isinstance(hit, dict):
            st = str(hit.get("status") or "").upper()
            if _agent_status_terminal(st):
                return st == "SUCCESS", hit
        time.sleep(1.0)
    return False, {"status": "TIMEOUT", "job_id": jid}

def _orchestrate_remote_node_action(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    action: str,
    actor: str,
    reason: str,
    ticket_id: str,
) -> Tuple[bool, str, str]:
    act = str(action or "start").strip().lower()
    nid = str(topo_node.get("id") or "").strip()
    node = _build_runtime_node_from_topology_node(project_id, env_key, topo_node, topology_id)
    service_id = str((service_bindings or {}).get(nid) or nid).strip()
    req = {
        "node_id": nid,
        "action_type": act,
        "target": nid,
        "ticket_id": ticket_id,
        "reason": reason,
        "approver": actor,
        "run_mode": "agent",
        "via_agent": True,
        "payload": {
            "run_mode": "agent",
            "desired_role": str(node.get("role") or ""),
            "desired_server_id": str(node.get("server_id") or nid),
            "desired_service_id": service_id,
            "switch_required": act in ("start", "restart"),
            "launch_visible_console": False,
        },
    }
    validation = _validate_ops_request(req, node)
    if not validation.get("ok"):
        return False, "validation_failed: " + str(validation.get("missing") or ""), ""
    if validation.get("require_approval") and not validation.get("approved"):
        validation = dict(validation)
        validation["approved"] = True
    result = _execute_validated(req, node, validation)
    if not result.get("ok"):
        return False, str(result.get("message") or result.get("error") or "remote action failed"), ""
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    job_id = str(data.get("job_id") or "")
    if job_id:
        ok, job = _wait_agent_job_terminal(job_id, timeout_sec=180.0 if act == "start" else 90.0)
        job_result = job.get("result") if isinstance(job.get("result"), dict) else {}
        msg = str(job_result.get("message") or job.get("status") or result.get("message") or "")
        return ok, msg, job_id
    return True, str(result.get("message") or "ok"), job_id

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

def _orchestration_post_launch_wait(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    contract: Dict[str, Any],
    service_id: str,
    launch_detail: str,
    *,
    probe_host: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
    timeout_sec: float = 25.0,
) -> Tuple[bool, str]:
    """编排逐步启动后的就绪等待：embedded 以进程存活为准，不依赖 5501/5502。"""
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    sid = str(service_id or topo_node.get("id") or "").strip().lower()
    detail = str(launch_detail or "").strip()
    role = str(topo_node.get("role") or contract.get("role") or "").strip().lower()
    cluster_type = _cluster_type_for_contract(contract, role)
    relay_port = int(_CLUSTER_RELAY_PROBE_PORTS.get(sid) or _cluster_relay_port_for_type(cluster_type, role) or 0)
    if role in ("gateway", "edge") or cluster_type.lower() == "gateway":
        ws_ok, ws_detail = _ws_handshake_probe(host, _RUNTIME_GATEWAY_PROBE_PORT)
        tcp_ok = _probe_tcp_open(host, _RUNTIME_GATEWAY_PROBE_PORT, timeout=0.35)
        if ws_ok and tcp_ok:
            return True, detail or f"gateway ws/tcp PASS @{host}:{_RUNTIME_GATEWAY_PROBE_PORT}"
        return False, (
            f"{detail}; gateway ws={'PASS' if ws_ok else 'FAIL'} ({ws_detail}) "
            f"tcp:{host}:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if tcp_ok else 'FAIL'}"
        )
    if relay_port > 0 and role in ("auth", "game", "business"):
        relay_ok = _probe_tcp_open(host, relay_port, timeout=0.5)
        if relay_ok:
            return True, detail or f"cluster-relay:{host}:{relay_port}=PASS"
        pid = _find_gameserver_pid_by_service(sid)
        if pid > 0 and _is_process_running(pid):
            return True, detail or f"{sid} pid {pid} alive (relay pending)"
        return False, f"{detail}; cluster-relay:{host}:{relay_port}=FAIL"
    if _is_embedded_topology_node(topo_node, contract):
        if _gameserver_service_live(sid, probe_host=host):
            return True, detail or f"{sid} process live"
        pid = _find_gameserver_pid_by_service(sid)
        if pid > 0 and _is_process_running(pid):
            return True, detail or f"{sid} pid {pid} alive"
        if "alive" in detail.lower() and "pid" in detail.lower():
            return True, detail
        gw = _probe_tcp_open(host, _RUNTIME_GATEWAY_PROBE_PORT, timeout=0.2)
        ops = _probe_tcp_open(host, _RUNTIME_OPS_PROBE_PORT, timeout=0.2)
        if gw or ops:
            return True, (
                f"gateway:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if gw else 'FAIL'} "
                f"ops:{_RUNTIME_OPS_PROBE_PORT}={'PASS' if ops else 'FAIL'} @{host}"
            )
        return False, (
            f"{detail}; embedded {sid} not live; "
            f"gateway:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if gw else 'FAIL'} "
            f"ops:{_RUNTIME_OPS_PROBE_PORT}={'PASS' if ops else 'FAIL'} @{host}"
        )
    return _wait_topology_node_live(
        project_id,
        env_key,
        topology_id,
        topo_node,
        timeout_sec=timeout_sec,
        probe_host=host,
        agent_bindings=agent_bindings,
    )

def _wait_topology_node_live(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    *,
    timeout_sec: float = 35.0,
    gateway_live: bool = False,
    ops_live: bool = False,
    probe_host: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    host = str(probe_host or "").strip() or _resolve_orchestration_probe_host(
        project_id, topology_id, topo_node, agent_bindings
    )
    deadline = time.time() + max(3.0, float(timeout_sec))
    last = ""
    while time.time() < deadline:
        gw = gateway_live or _probe_tcp_open(host, _RUNTIME_GATEWAY_PROBE_PORT)
        ops = ops_live or _probe_tcp_open(host, _RUNTIME_OPS_PROBE_PORT)
        ok, msg = _probe_topology_node_live(
            project_id,
            env_key,
            topology_id,
            topo_node,
            gateway_live=gw,
            ops_live=ops,
            probe_host=host,
            agent_bindings=agent_bindings,
        )
        last = msg
        if ok:
            return True, msg
        time.sleep(1.0)
    return False, last or "probe timeout"

def _wait_topology_node_down(
    port: int,
    timeout_sec: float = 15.0,
    probe_host: str = DEFAULT_LOOPBACK,
) -> Tuple[bool, str]:
    if port <= 0:
        return True, "no port"
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    deadline = time.time() + max(2.0, float(timeout_sec))
    while time.time() < deadline:
        if not _probe_tcp_open(host, port):
            return True, f"port {port} closed on {host}"
        time.sleep(0.8)
    return False, f"port {port} still open on {host}"

def _runtime_orchestrate_start_worker(
    run_id: str,
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
) -> None:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    ticket_id = "OPS-RUN-" + str(run_id or "")[-6:]
    reason = "拓扑运行模式一键启动"
    run = _find_runtime_run(run_id)
    items = run.get("items") if isinstance(run, dict) and isinstance(run.get("items"), list) else []
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    ordered_ids = [str(x.get("node_id") or "") for x in items if isinstance(x, dict) and str(x.get("node_id") or "")]
    if not ordered_ids:
        ordered_ids = _topo_order_node_ids(topo_nodes, topo_edges, reverse=False)
        items = []
        for seq, nid in enumerate(ordered_ids, start=1):
            topo_node = id_to_node.get(nid) or {}
            node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid) if topo_node else {}
            mode = "daemon" if topo_node and _is_external_daemon_node(node) else "direct"
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "PENDING", "mode": mode, "seq": seq, "step_total": len(ordered_ids)})
        _runtime_run_patch(run_id, items=items)
    total = len(ordered_ids)
    fail = 0

    _runtime_orchestrator_log(run_id, "cluster", "info", "Step 0/{}: 清理旧 GameServer 进程".format(total))
    _stop_local_game_server()
    time.sleep(1.2)

    _runtime_orchestrator_log(run_id, "cluster", "info", "Step 0/{}: 检查并启动 Mongo/Redis 基础设施".format(total))
    infra_ok, infra_msg = _ensure_runtime_infra_ports(
        timeout_sec=45.0, project_id=pid, env_key=env, topology_id=tid, agent_bindings=bindings
    )
    _runtime_orchestrator_log(
        run_id,
        "cluster",
        "info" if infra_ok else "error",
        "基础设施探活: " + infra_msg,
    )
    if not infra_ok:
        for nid in ordered_ids:
            _runtime_orchestrator_set_item(items, nid, "FAILED")
        _runtime_run_patch(run_id, items=items, status="failed")
        return

    for seq, nid in enumerate(ordered_ids, start=1):
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            _runtime_orchestrator_set_item(items, nid, "FAILED")
            _runtime_orchestrator_log(run_id, nid, "error", f"Step {seq}/{total}: 节点配置缺失")
            fail += 1
            break

        _runtime_orchestrator_set_item(items, nid, "RUNNING", step=seq, step_total=total)
        _runtime_run_patch(run_id, items=items)
        _runtime_orchestrator_log(run_id, nid, "info", f"Step {seq}/{total}: 开始启动节点 {nid}")

        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        bound_agent_id = str((bindings or {}).get(nid) or CANONICAL_LOCAL_AGENT_ID).strip()
        ok = False
        detail = ""
        job_id = ""

        if _is_external_daemon_node(node):
            result = _ops_platform_daemon_action(node, "start", reason, ticket_id, actor)
            ok = bool(result.get("success"))
            detail = str(result.get("message") or "")
            if not ok and probe_port > 0 and _probe_tcp_open(probe_host, probe_port):
                ok = True
                detail = f"daemon 端口已监听 ({probe_host}:{probe_port})"
            if ok:
                wait_ok, wait_msg = _wait_topology_node_live(
                    pid, env, tid, topo_node, timeout_sec=20.0, probe_host=probe_host, agent_bindings=bindings
                )
                ok = wait_ok
                detail = wait_msg if wait_ok else (detail + "; " + wait_msg)
        elif not _is_local_runtime_agent(bound_agent_id):
            _runtime_orchestrator_log(run_id, "cluster", "info", f"Step {seq}/{total}: 远端 Agent 启动 {nid}")
            ok, detail, job_id = _orchestrate_remote_node_action(
                pid, env, tid, topo_node, service_bindings, bindings, "start", actor, reason, ticket_id
            )
            if ok:
                wait_ok, wait_msg = _wait_topology_node_live(
                    pid, env, tid, topo_node, timeout_sec=25.0, probe_host=probe_host, agent_bindings=bindings
                )
                ok = wait_ok
                detail = wait_msg if wait_ok else (detail + "; " + wait_msg)
        else:
            service_id = str((service_bindings or {}).get(nid) or nid).strip()
            _runtime_orchestrator_log(run_id, "cluster", "info", f"Step {seq}/{total}: 启动独立进程 {service_id}")
            launch = _launch_gameserver_service(
                service_id, reason, wait_ready=True, timeout_sec=120, node=node, probe_host=probe_host
            )
            ok = bool(launch.get("success"))
            detail = str(launch.get("message") or "")
            if ok:
                wait_ok, wait_msg = _orchestration_post_launch_wait(
                    pid,
                    env,
                    tid,
                    topo_node,
                    contract,
                    service_id,
                    detail,
                    probe_host=probe_host,
                    agent_bindings=bindings,
                    timeout_sec=25.0,
                )
                ok = wait_ok
                detail = wait_msg if wait_ok else (detail + "; " + wait_msg)

        if ok:
            _runtime_orchestrator_set_item(items, nid, "SUCCESS", step=seq, step_total=total, job_id=job_id)
            _runtime_orchestrator_log(run_id, nid, "info", f"Step {seq}/{total}: 节点 {nid} 启动成功 — {detail}")
            _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
        else:
            _runtime_orchestrator_set_item(items, nid, "FAILED", step=seq, step_total=total, detail=detail)
            _runtime_orchestrator_log(run_id, nid, "error", f"Step {seq}/{total}: 节点 {nid} 启动失败 — {detail}")
            fail += 1
            for rest in ordered_ids[seq:]:
                if str(rest) != nid:
                    _runtime_orchestrator_set_item(items, rest, "SKIPPED")
            break

        _runtime_run_patch(run_id, items=items)
        time.sleep(0.35)

    probe_stat = _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
    gateway_live = bool(probe_stat.get("gateway_live"))
    game_ok = bool(fail == 0 and gateway_live)
    _consolidate_runtime_agents_to_canonical(pid)
    if fail > 0 and gateway_live and int(probe_stat.get("live_count") or 0) >= max(1, int(probe_stat.get("total") or 0) - 1):
        final_status = "success"
        _runtime_orchestrator_log(
            run_id,
            "cluster",
            "info",
            f"启动编排降级成功: gateway_live={gateway_live}, live={probe_stat.get('live_count')}/{probe_stat.get('total')}, step_fail={fail}",
        )
    else:
        final_status = "success" if fail == 0 else "failed"
    _runtime_orchestrator_log(
        run_id,
        "cluster",
        "info" if fail == 0 else "error",
        f"启动编排结束: status={final_status}, gateway_live={gateway_live}, live={probe_stat.get('live_count')}/{probe_stat.get('total')}, failed={fail}",
    )
    _runtime_run_patch(run_id, items=items, status=final_status)

def _spawn_runtime_start_orchestration(
    run_id: str,
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    ordered_ids = _topo_order_node_ids(topo_nodes, topo_edges, reverse=False)
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    items: List[Dict[str, Any]] = []
    for seq, nid in enumerate(ordered_ids, start=1):
        topo_node = id_to_node.get(nid) or {}
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid) if topo_node else {}
        mode = "daemon" if topo_node and _is_external_daemon_node(node) else "direct"
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "PENDING", "mode": mode, "seq": seq, "step_total": len(ordered_ids)})
    logs = [
        {
            "ts": _now_iso(),
            "level": "info",
            "node_id": "cluster",
            "message": f"启动编排已入队，共 {len(ordered_ids)} 个节点，将按拓扑序逐节点启动",
        }
    ]
    _runtime_run_patch(run_id, items=items, logs_append=logs, status="running")
    threading.Thread(
        target=_runtime_orchestrate_start_worker,
        args=(run_id, pid, env, tid, topo_nodes, topo_edges, service_bindings, agent_bindings, actor),
        daemon=True,
    ).start()
    return {"items": items, "logs": logs, "failed": 0, "status": "running", "async": True}

def _runtime_orchestrate_stop_worker(
    run_id: str,
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
) -> None:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    ticket_id = "OPS-RUN-" + str(run_id or "")[-6:]
    reason = "拓扑运行模式一键停止"
    run = _find_runtime_run(run_id)
    items = run.get("items") if isinstance(run, dict) and isinstance(run.get("items"), list) else []
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    ordered_ids = [str(x.get("node_id") or "") for x in items if isinstance(x, dict) and str(x.get("node_id") or "")]
    if not ordered_ids:
        ordered_ids = list(reversed(_topo_order_node_ids(topo_nodes, topo_edges, reverse=False)))
        items = []
        for seq, nid in enumerate(ordered_ids, start=1):
            topo_node = id_to_node.get(nid) or {}
            node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid) if topo_node else {}
            mode = "daemon" if topo_node and _is_external_daemon_node(node) else "direct"
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "PENDING", "mode": mode, "seq": seq, "step_total": len(ordered_ids)})
        _runtime_run_patch(run_id, items=items)
    total = len(ordered_ids)
    fail = 0
    for seq, nid in enumerate(ordered_ids, start=1):
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            _runtime_orchestrator_set_item(items, nid, "FAILED")
            fail += 1
            continue

        _runtime_orchestrator_set_item(items, nid, "RUNNING", step=seq, step_total=total)
        _runtime_run_patch(run_id, items=items)
        _runtime_orchestrator_log(run_id, nid, "info", f"Step {seq}/{total}: 开始停止节点 {nid}")

        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        bound_agent_id = str((bindings or {}).get(nid) or CANONICAL_LOCAL_AGENT_ID).strip()
        ok = False
        detail = ""

        if _is_external_daemon_node(node):
            result = _ops_platform_daemon_action(node, "stop", reason, ticket_id, actor)
            ok = bool(result.get("success"))
            detail = str(result.get("message") or "")
            if probe_port > 0:
                down_ok, down_msg = _wait_topology_node_down(probe_port, timeout_sec=12.0, probe_host=probe_host)
                ok = ok and down_ok
                detail = detail + "; " + down_msg
            if service_id:
                st = "STOPPED" if ok else "FAILED"
                _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="FAIL")
        elif not _is_local_runtime_agent(bound_agent_id):
            ok, detail, _job_id = _orchestrate_remote_node_action(
                pid, env, tid, topo_node, service_bindings, bindings, "stop", actor, reason, ticket_id
            )
            if service_id:
                st = "STOPPED" if ok else "FAILED"
                _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="FAIL")
        else:
            stop_res = _stop_gameserver_service(service_id, node, probe_host=probe_host)
            ok = bool(stop_res.get("success"))
            detail = str(stop_res.get("message") or "")
            if probe_port > 0:
                down_ok, down_msg = _wait_topology_node_down(probe_port, timeout_sec=12.0, probe_host=probe_host)
                ok = ok and down_ok
                detail = detail + "; " + down_msg
            if service_id:
                st = "STOPPED" if ok else "FAILED"
                _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="FAIL")

        if ok:
            _runtime_orchestrator_set_item(items, nid, "SUCCESS", step=seq, step_total=total)
            _runtime_orchestrator_log(run_id, nid, "info", f"Step {seq}/{total}: 节点 {nid} 已停止 — {detail}")
        else:
            _runtime_orchestrator_set_item(items, nid, "FAILED", step=seq, step_total=total, detail=detail)
            _runtime_orchestrator_log(run_id, nid, "error", f"Step {seq}/{total}: 节点 {nid} 停止失败 — {detail}")
            fail += 1

        _runtime_run_patch(run_id, items=items)
        time.sleep(0.35)

    _mark_project_runtime_services_stopped(pid)
    _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
    final_status = "success" if fail == 0 else "failed"
    _runtime_orchestrator_log(
        run_id,
        "cluster",
        "info" if fail == 0 else "warn",
        f"停止编排结束: status={final_status}, failed={fail}",
    )
    _runtime_run_patch(run_id, items=items, status=final_status)

def _spawn_runtime_stop_orchestration(
    run_id: str,
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    ordered_ids = list(reversed(_topo_order_node_ids(topo_nodes, topo_edges, reverse=False)))
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    items: List[Dict[str, Any]] = []
    for seq, nid in enumerate(ordered_ids, start=1):
        topo_node = id_to_node.get(nid) or {}
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid) if topo_node else {}
        mode = "daemon" if topo_node and _is_external_daemon_node(node) else "direct"
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "PENDING", "mode": mode, "seq": seq, "step_total": len(ordered_ids)})
    logs = [
        {
            "ts": _now_iso(),
            "level": "info",
            "node_id": "cluster",
            "message": f"停止编排已入队，共 {len(ordered_ids)} 个节点，将按逆拓扑序逐节点停止",
        }
    ]
    _runtime_run_patch(run_id, items=items, logs_append=logs, status="running")
    threading.Thread(
        target=_runtime_orchestrate_stop_worker,
        args=(run_id, pid, env, tid, topo_nodes, topo_edges, service_bindings, agent_bindings, actor),
        daemon=True,
    ).start()
    return {"items": items, "logs": logs, "failed": 0, "status": "running", "async": True}

def _runtime_cluster_start_all(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
    run_id: str,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    ticket_id = "OPS-RUN-" + str(run_id or "")[-6:]
    reason = "拓扑运行模式一键启动"
    logs: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    ordered_ids = _topo_order_node_ids(topo_nodes, topo_edges, reverse=False)
    daemon_ids = [nid for nid in ordered_ids if isinstance(id_to_node.get(nid), dict) and _is_external_daemon_node(_build_runtime_node_from_topology_node(pid, env, id_to_node[nid], tid))]
    app_ids = [nid for nid in ordered_ids if nid not in daemon_ids]

    logs.append({"ts": _now_iso(), "level": "info", "node_id": "cluster", "message": "清理旧 GameServer 进程，准备全新启动"})
    _stop_local_game_server()
    time.sleep(1.5)

    infra_ok, infra_msg = _ensure_runtime_infra_ports(
        timeout_sec=45.0, project_id=pid, env_key=env, topology_id=tid, agent_bindings=bindings
    )
    logs.append(
        {
            "ts": _now_iso(),
            "level": "info" if infra_ok else "error",
            "node_id": "cluster",
            "message": "基础设施探活: " + infra_msg,
        }
    )
    if not infra_ok:
        for nid in daemon_ids + app_ids:
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "FAILED", "mode": "direct"})
        logs.append({"ts": _now_iso(), "level": "error", "node_id": "cluster", "message": "Mongo/Redis 未就绪，已中止 GameServer 启动"})
        _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
        return {"items": items, "logs": logs, "failed": max(1, len(items)), "gateway_live": False}

    unified_launch: Optional[Dict[str, Any]] = None
    unified_ok = False
    if _should_use_unified_gameserver_all(app_ids, service_bindings):
        logs.append({"ts": _now_iso(), "level": "info", "node_id": "cluster", "message": "Windows 本地：使用 GameServer --all 单进程启动（业务测试/E2E 需要）"})
        unified_launch = _launch_gameserver_unified_all(reason, wait_ready=True, timeout_sec=120)
        unified_ok = bool(unified_launch.get("success"))
        logs.append(
            {
                "ts": _now_iso(),
                "level": "info" if unified_ok else "error",
                "node_id": "cluster",
                "message": str(unified_launch.get("message") or "unified-all launch"),
            }
        )

    for nid in daemon_ids:
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            continue
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        result = _ops_platform_daemon_action(node, "start", reason, ticket_id, actor)
        ok = bool(result.get("success"))
        if not ok and probe_port > 0 and _probe_tcp_open(probe_host, probe_port):
            ok = True
            result = {"success": True, "message": f"daemon 端口已监听 ({probe_host}:{probe_port})"}
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS" if ok else "FAILED", "mode": "daemon"})
        logs.append(
            {
                "ts": _now_iso(),
                "level": "info" if ok else "warn",
                "node_id": nid,
                "message": str(result.get("message") or ("daemon start ok" if ok else "daemon start failed")),
            }
        )

    for nid in app_ids:
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            continue
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        if unified_launch is not None and service_id.strip().lower() in _GAMESERVER_PROCESS_SERVICE_IDS:
            ok = unified_ok
            launch = {
                "success": ok,
                "message": str((unified_launch or {}).get("message") or "unified-all"),
                "data": {"live": ok, "mode": "unified-all"},
            }
        else:
            launch = _launch_gameserver_service(
                service_id, reason, wait_ready=True, timeout_sec=120, node=node, probe_host=probe_host
            )
        ok = bool(launch.get("success"))
        launch_msg = str(launch.get("message") or "")
        unified_node = unified_launch is not None and service_id.strip().lower() in _GAMESERVER_PROCESS_SERVICE_IDS
        if ok and not unified_node:
            wait_ok, wait_msg = _orchestration_post_launch_wait(
                pid,
                env,
                tid,
                topo_node,
                contract,
                service_id,
                launch_msg,
                probe_host=probe_host,
                agent_bindings=bindings,
                timeout_sec=25.0,
            )
            ok = wait_ok
            launch = {"success": ok, "message": wait_msg, "data": launch.get("data")}
        elif unified_node and unified_ok:
            ok = True
            launch = {"success": True, "message": launch_msg, "data": {"live": True, "mode": "unified-all"}}
        live = bool((launch.get("data") or {}).get("live")) or _gameserver_service_live(service_id, node, probe_host=probe_host)
        if unified_node and unified_ok:
            live = _ws_handshake_probe()[0]
        ok = ok and live
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS" if ok else "FAILED", "mode": "direct"})
        logs.append(
            {
                "ts": _now_iso(),
                "level": "info" if ok else "error",
                "node_id": nid,
                "message": str(launch.get("message") or (f"{'live' if live else 'down'} port={probe_port or '-'}")),
            }
        )

    probe_stat = _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
    gateway_live = bool(probe_stat.get("gateway_live"))

    for nid in daemon_ids:
        if any(str(x.get("node_id") or "") == nid and str(x.get("status") or "").upper() == "FAILED" for x in items if isinstance(x, dict)):
            continue
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            continue
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        live = _probe_tcp_open(probe_host, probe_port) if probe_port > 0 else False
        for item in items:
            if isinstance(item, dict) and str(item.get("node_id") or "") == nid:
                item["status"] = "SUCCESS" if live else str(item.get("status") or "FAILED")

    _consolidate_runtime_agents_to_canonical(pid)
    item_fail = len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() != "SUCCESS"])
    game_ok = bool(gateway_live and item_fail == 0)
    fail = item_fail
    logs.append(
        {
            "ts": _now_iso(),
            "level": "info" if fail == 0 else "error",
            "node_id": "cluster",
            "message": f"集群级启动完成: game_ok={game_ok}, gateway_live={gateway_live}, live={probe_stat.get('live_count')}/{probe_stat.get('total')}, failed={fail}",
        }
    )
    return {"items": items, "logs": logs, "failed": fail, "gateway_live": gateway_live and game_ok}

def _load_daemon_state() -> Dict[str, Any]:
    raw = get_system_config(OPS_DAEMON_STATE_KEY, {})
    return raw if isinstance(raw, dict) else {}

def _save_daemon_state(state: Dict[str, Any]) -> None:
    _save_json_config(OPS_DAEMON_STATE_KEY, state if isinstance(state, dict) else {}, description="Ops daemon process state")

def _set_daemon_state(node_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    data = _load_daemon_state()
    nid = str(node_id or "").strip()
    cur = data.get(nid) if isinstance(data.get(nid), dict) else {}
    merged = dict(cur)
    merged.update(patch or {})
    merged["updated_at"] = _now_iso()
    data[nid] = merged
    _save_daemon_state(data)
    return merged

def _get_daemon_state(node_id: str) -> Dict[str, Any]:
    data = _load_daemon_state()
    nid = str(node_id or "").strip()
    return data.get(nid) if isinstance(data.get(nid), dict) else {}

def _is_process_running(pid: int) -> bool:
    value = int(pid or 0)
    if value <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, value)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return int(exit_code.value) == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(value, 0)
        return True
    except Exception:
        return False

def _service_runtime_cache_fresh(services: List[Dict[str, Any]], max_age_sec: float = _AGENT_DETAIL_SERVICE_CACHE_MAX_AGE_SEC) -> bool:
    if not services:
        return False
    now = _time_mod.time()
    for svc in services:
        if not isinstance(svc, dict):
            return False
        run = str(svc.get("run_state") or svc.get("status") or "").strip().upper()
        if run in ("STARTING", "STOPPING", "RESTARTING"):
            return False
        ts = _parse_iso_ts(svc.get("updated_at"))
        if ts <= 0 or (now - ts) > max(4.0, float(max_age_sec)):
            return False
    return True

def _probe_service_cache_fresh(max_age_sec: float = PROBE_INTERVAL_SEC * 3) -> bool:
    with _probe_cache_lock:
        cache_ts = float(_probe_cache_ts or 0.0)
    if cache_ts <= 0:
        return False
    return (_time_mod.time() - cache_ts) <= max(6.0, float(max_age_sec))

def _should_use_cached_service_state(services: List[Dict[str, Any]], force_live: bool = False) -> bool:
    if force_live:
        return False
    if any(_is_embedded_cluster_service(s) for s in (services or []) if isinstance(s, dict)):
        return False
    if _probe_service_cache_fresh():
        return True
    return _service_runtime_cache_fresh(services)

def _embedded_process_gateway_up(host: str = DEFAULT_LOOPBACK, timeout: float = 0.15) -> bool:
    probe_host = str(host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    return bool(
        _probe_tcp_open(probe_host, _RUNTIME_GATEWAY_PROBE_PORT, timeout=timeout)
        or _probe_tcp_open(probe_host, _RUNTIME_OPS_PROBE_PORT, timeout=timeout)
    )

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

def _daemon_log_path(node_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(node_id or "daemon").strip()) or "daemon"
    log_dir = os.path.join(DATA_DIR, "logs", "daemons")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"{safe}.log")

def _gameserver_log_artifact_paths() -> Tuple[str, str]:
    repo = _resolve_game_server_repo()
    log_dir = os.path.join(repo, "tools", "SmokeTest", "artifacts")
    return (
        os.path.join(log_dir, "server-live.out.log"),
        os.path.join(log_dir, "server-live.err.log"),
    )

def _is_gameserver_process_service_id(service_id: str) -> bool:
    return str(service_id or "").strip().lower() in _GAMESERVER_PROCESS_SERVICE_IDS

def _gameserver_service_port(service_id: str, node: Optional[Dict[str, Any]] = None) -> int:
    if isinstance(node, dict):
        port = int(node.get("port") or node.get("remote_game_server_port") or 0)
        if port > 0:
            return port
    return int(_GAMESERVER_DEFAULT_PORTS.get(str(service_id or "").strip().lower(), 0))

def _find_gameserver_pid_by_service(service_id: str) -> int:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return 0
    now = _time_mod.time()
    cached = _gameserver_pid_cache.get(sid)
    if cached and (now - float(cached[0] or 0.0)) < _GAMESERVER_PID_CACHE_TTL_SEC:
        return int(cached[1] or 0)
    needle = f"--servers={sid}"
    if os.name == "nt":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='GameServer.GameServerApp.exe'\" | "
                    "Select-Object ProcessId,CommandLine | ForEach-Object { "
                    f"if ($_.CommandLine -like '*{needle}*') {{ $_.ProcessId }} }}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            pid = 0
            for line in reversed((proc.stdout or "").splitlines()):
                text = line.strip()
                if text.isdigit():
                    pid = int(text)
                    break
            _gameserver_pid_cache[sid] = (now, pid)
            return pid
        except Exception:
            pass
        _gameserver_pid_cache[sid] = (now, 0)
        return 0
    try:
        proc = subprocess.run(
            ["bash", "-lc", "ps -eo pid=,args= | grep GameServer.GameServerApp | grep -F -- " + sid],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.strip().split(None, 1)
            if parts and parts[0].isdigit() and needle in (parts[1] if len(parts) > 1 else ""):
                pid = int(parts[0])
                _gameserver_pid_cache[sid] = (now, pid)
                return pid
    except Exception:
        pass
    _gameserver_pid_cache[sid] = (now, 0)
    return 0

def _is_gameserver_process_alive(service_id: str) -> bool:
    sid = str(service_id or "").strip().lower()
    state = _get_daemon_state(sid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    if pid > 0 and _is_process_running(pid):
        return True
    found = _find_gameserver_pid_by_service(sid)
    if found > 0 and _is_process_running(found):
        _set_daemon_state(sid, {"pid": found, "status": "RUNNING"})
        return True
    if found > 0:
        _set_daemon_state(sid, {"pid": 0, "status": "STOPPED"})
    return False

def _gameserver_service_live(
    service_id: str,
    node: Optional[Dict[str, Any]] = None,
    pid: int = 0,
    fast: bool = False,
    probe_host: str = "",
) -> bool:
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    port = _gameserver_tcp_probe_port(service_id, node)
    probe_timeout = 0.12 if fast else 0.35
    if port > 0:
        if not _probe_tcp_open(host, port, timeout=probe_timeout):
            return False
        if fast:
            return True
        active_pid = pid if pid > 0 and _is_process_running(pid) else _find_gameserver_pid_by_service(service_id)
        return bool(active_pid > 0 and _is_process_running(active_pid))
    if fast:
        state = _get_daemon_state(str(service_id or "").strip().lower())
        cached_pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
        return bool(cached_pid > 0 and _is_process_running(cached_pid))
    return _is_gameserver_process_alive(service_id)

def _gameserver_service_log_path(repo: str, service_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "gameserver").strip()) or "gameserver"
    return os.path.join(repo, "tools", "SmokeTest", "artifacts", f"apk-site-service-{safe}.log")

def _gameserver_service_launch_args(service_id: str) -> List[str]:
    sid = str(service_id or "").strip()
    # 当前 Windows 构建仅识别 --headless-seconds；裸 --headless 需重编译后才常驻。
    return [f"--servers={sid}", "--headless", "--headless-seconds=86400"]
