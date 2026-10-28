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


def _load_daemon_state() -> Dict[str, Any]:
    raw = get_system_config(OPS_DAEMON_STATE_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_daemon_state(state: Dict[str, Any]) -> None:
    _save_json_config(OPS_DAEMON_STATE_KEY, state if isinstance(state, dict) else {}, description="Ops daemon process state")
