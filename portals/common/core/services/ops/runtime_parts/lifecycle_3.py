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


def _gameserver_service_launch_args(service_id: str) -> List[str]:
    sid = str(service_id or "").strip()
    # 当前 Windows 构建仅识别 --headless-seconds；裸 --headless 需重编译后才常驻。
    return [f"--servers={sid}", "--headless", "--headless-seconds=86400"]
