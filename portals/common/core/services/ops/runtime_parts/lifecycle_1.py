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
