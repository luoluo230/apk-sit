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


def _default_probe_host() -> str:
    return str(os.getenv("OPS_DEFAULT_PROBE_HOST") or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK


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
