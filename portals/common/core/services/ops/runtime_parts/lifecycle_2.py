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
