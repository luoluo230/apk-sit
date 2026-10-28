def _cluster_state_is_online(state: Any) -> bool:
    text = str(state or "").strip().upper()
    return text in ("RUNNING", "READY", "ONLINE", "ACTIVE", "0") or str(state or "").strip() == "0"


def _is_daemon_infra_service(service: Dict[str, Any]) -> bool:
    if not isinstance(service, dict):
        return False
    sid = str(service.get("service_id") or service.get("node_id") or "").strip().lower()
    stype = str(service.get("service_type") or service.get("role") or "").strip().lower()
    return sid in ("mongo-db-cn-1", "redis-cache-cn-1") or stype in ("database", "cache", "mongo", "redis")


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
