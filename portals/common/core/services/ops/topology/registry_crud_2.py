def _execute_canonical_service_action(
    project_id: str,
    topology_node_id: str,
    service_id: str,
    action: str,
    operator: str,
    reason: str,
    ticket_id: str,
    body_payload: Dict[str, Any],
) -> Dict[str, Any]:
    act = str(action or "").strip().lower()
    node = _resolve_ops_dispatch_node(project_id, topology_node_id)
    if not node:
        return {"ok": False, "message": "topology node not found", "mode": "direct"}

    if _is_external_daemon_node(node):
        result = _ops_platform_daemon_action(node, act, reason, ticket_id, operator)
        ok = bool(result.get("success"))
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if not ok:
            return {
                "ok": False,
                "message": str(result.get("message") or "daemon action failed"),
                "data": data,
                "mode": "daemon",
            }
        if ok:
            contract = _resolve_node_contract_for_topology_node(node if isinstance(node, dict) else {})
            port = _resolve_topology_node_port(node if isinstance(node, dict) else {}, contract, None, None)
            role = str(node.get("role") or contract.get("role") or "").strip().lower()
            probe_proto = str(contract.get("probe_strategy") or "tcp").strip().lower()
            if role in ("cache", "redis"):
                probe_proto = "redis_ping"
            elif role in ("database", "mongo"):
                probe_proto = "mongo_ping"
            live = False
            if port > 0:
                for attempt in range(24 if act in ("start", "restart") else 1):
                    probe = _probe_by_protocol("127.0.0.1", port, probe_proto)
                    live = bool(probe.get("ok"))
                    if live or act not in ("start", "restart"):
                        break
                    time.sleep(0.5)
            if act == "stop":
                st = "STOPPED"
            elif live:
                st = "RUNNING"
            elif act in ("start", "restart"):
                st = "STARTING"
            else:
                st = "STOPPED"
            _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="PASS" if live else "FAIL")
        return {"ok": ok, "message": str(result.get("message") or ""), "data": result.get("data") or {}, "mode": "daemon"}

    if act == "status":
        return _local_service_status_snapshot(project_id, topology_node_id, service_id)

    if act == "logs":
        log_payload = _read_gameserver_service_logs(service_id, tail=500)
        return {
            "ok": True,
            "message": f"已读取 GameServer 日志（{log_payload.get('total', 0)} 条）",
            "data": log_payload,
            "mode": "direct-local",
        }

    if _is_gameserver_process_service_id(service_id) and act in ("start", "stop", "restart"):
        _reconcile_gameserver_daemon_state(service_id)
        port = _gameserver_service_port(service_id, node)
        if act == "restart":
            stop_res = _stop_gameserver_service(service_id, node)
            if not stop_res.get("success"):
                return {
                    "ok": False,
                    "message": str(stop_res.get("message") or "restart stop failed"),
                    "data": {},
                    "mode": "direct-local-process",
                }
            act = "start"
        if act == "stop":
            stop_res = _stop_gameserver_service(service_id, node)
            ok = bool(stop_res.get("success"))
            metrics = _sample_local_control_metrics()
            if ok:
                _apply_service_runtime_after_action(service_id, status="STOPPED", live=False, metrics=metrics)
            else:
                _update_canonical_service_runtime(
                    service_id,
                    status="ERROR",
                    run_state="ERROR",
                    probe_status="FAIL",
                    last_action="stop",
                    metrics=metrics,
                )
            canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
            if isinstance(canonical, dict):
                _append_realtime_agent_sample(canonical)
            return {
                "ok": ok,
                "message": str(stop_res.get("message") or ("已停止" if ok else "停止失败")),
                "data": {"service_id": service_id, "port": port, "status": "STOPPED" if ok else "ERROR", "last_action": "stop"},
                "mode": "direct-local-process",
            }
        launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
        ok = bool(launch.get("success"))
        live = bool((launch.get("data") or {}).get("live")) or _gameserver_service_live(service_id, node)
        metrics = _sample_local_control_metrics()
        if ok:
            st = "RUNNING" if live else "STARTING"
            _apply_service_runtime_after_action(service_id, status=st, live=live, metrics=metrics)
            _update_canonical_service_runtime(service_id, last_action="start")
        else:
            _update_canonical_service_runtime(
                service_id,
                status="ERROR",
                run_state="ERROR",
                probe_status="FAIL",
                last_action="start",
                metrics=metrics,
            )
        canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
        if isinstance(canonical, dict):
            _append_realtime_agent_sample(canonical)
        return {
            "ok": ok,
            "message": str(launch.get("message") or ("启动成功" if ok else "启动失败")),
            "data": {
                **(launch.get("data") if isinstance(launch.get("data"), dict) else {}),
                "status": "RUNNING" if ok and live else ("STARTING" if ok else "ERROR"),
                "last_action": "start",
            },
            "mode": "direct-local-process",
        }

    ops_node = _resolve_ops_dispatch_node(project_id, "ops-cn-1") or node
    map_action = {"start": "start", "stop": "stop", "restart": "restart", "status": "status", "probe": "health_check", "logs": "log_tail"}.get(act, act)
    result = ops_gateway.execute_platform_action(
        ops_node,
        action_type=map_action,
        target=service_id,
        payload=body_payload,
        actor=operator,
        reason=reason,
        ticket_id=ticket_id,
        dry_run=False,
    )
    ok = bool(result.get("success"))

    if not ok and act == "start" and _is_gameserver_process_service_id(service_id):
        launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
        if launch.get("success"):
            live = bool((launch.get("data") or {}).get("live")) or _gameserver_service_live(service_id, node)
            ok = True
            result = {
                "success": True,
                "message": str(launch.get("message") or ("服务已在运行" if live else "服务启动中")),
                "data": dict(launch.get("data") or {}, starting=not live),
            }
        else:
            result = launch

    if not ok and act in ("stop", "restart") and _is_gameserver_process_service_id(service_id):
        stop_res = _stop_gameserver_service(service_id, node)
        if stop_res.get("success"):
            ok = act == "stop"
            result = stop_res
            if act == "restart":
                launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
                ok = bool(launch.get("success"))
                result = launch
        else:
            result = stop_res

    if not ok and act == "stop":
        port = int(node.get("port") or node.get("remote_game_server_port") or 0)
        if port > 0:
            time.sleep(1.2)
            if not _probe_tcp_open("127.0.0.1", port):
                ok = True
                result = {"success": True, "message": "服务端口已释放", "data": {"status": "STOPPED"}}

    if ok:
        live = _gameserver_service_live(service_id, node) if _is_gameserver_process_service_id(service_id) else (
            _probe_tcp_open("127.0.0.1", int(node.get("port") or node.get("remote_game_server_port") or 0))
            if int(node.get("port") or node.get("remote_game_server_port") or 0) > 0
            else bool((result.get("data") or {}).get("starting"))
        )
        st = "STARTING" if (result.get("data") or {}).get("starting") else ("RUNNING" if act != "stop" and live else ("STOPPED" if act == "stop" else "RUNNING"))
        metrics = _sample_local_control_metrics()
        _apply_service_runtime_after_action(service_id, status=st, live=live, metrics=metrics)
        canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
        if isinstance(canonical, dict):
            _append_realtime_agent_sample(canonical)

    return {
        "ok": ok,
        "message": str(result.get("message") or ("success" if ok else "service action failed")),
        "data": result.get("data") if isinstance(result.get("data"), dict) else {},
        "mode": "direct",
    }


def _run_flow_step(node: Dict[str, Any], step: Dict[str, Any]) -> Dict[str, Any]:
    action_type = str(step.get("action_type") or "").strip()
    target = str(step.get("target") or node.get("server_id") or "").strip()
    ticket_id = str(step.get("ticket_id") or "OPS-FLOW").strip()
    reason = str(step.get("reason") or "flow step").strip()
    payload = step.get("payload") if isinstance(step.get("payload"), dict) else {}
    dry_run = bool(step.get("dry_run"))
    operator = str(session.get("user") or "intranet-ops")
    return ops_gateway.execute_platform_action(
        node,
        action_type=action_type,
        target=target,
        payload=payload,
        actor=operator,
        reason=reason,
        ticket_id=ticket_id,
        dry_run=dry_run,
    )
