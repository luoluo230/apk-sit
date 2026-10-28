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
