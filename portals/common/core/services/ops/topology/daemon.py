def _is_external_daemon_node(node: Dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        return False
    profile = str(node.get("daemon_profile") or "").strip().lower()
    role = str(node.get("role") or "").strip().lower()
    return profile == "external_daemon" or role in ("database", "cache", "mongo", "redis")


def _is_daemon_log_source(paths: List[str]) -> bool:
    if not paths:
        return False
    norm = [str(p or "").replace("\\", "/").lower() for p in paths]
    return all("/logs/daemons/" in p for p in norm)


def _slice_merged_from_daemon_session(merged: List[Tuple[int, str, str]]) -> Tuple[List[Tuple[int, str, str]], str]:
    start_idx = 0
    started_at = ""
    for idx, (_, line, _) in enumerate(merged):
        if _DAEMON_SESSION_MARK.search(line):
            start_idx = idx
            started_at = _extract_line_iso_time(line)
    if start_idx <= 0:
        return merged, started_at
    return merged[start_idx:], started_at


def _daemon_probe_proto(node: Dict[str, Any]) -> str:
    role = str(node.get("role") or "").strip().lower()
    return "redis_ping" if role in ("cache", "redis") else "mongo_ping"


def _daemon_node_port(node: Dict[str, Any]) -> int:
    if not isinstance(node, dict):
        return 0
    port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or node.get("port") or 0)
    if port > 0:
        return port
    try:
        contract = _resolve_node_contract_for_topology_node(node)
        port = int(_resolve_topology_node_port(node, contract, None, None) or 0)
        if port > 0:
            return port
    except Exception:
        pass
    nid = str(node.get("id") or "").strip().lower()
    role = str(node.get("role") or "").strip().lower()
    if role in ("cache", "redis") or "redis" in nid:
        return 6379
    if role in ("database", "mongo") or "mongo" in nid:
        return 27017
    return 0


def _resolve_mongod_executable() -> str:
    if os.name != "nt":
        return ""
    try:
        import glob

        hits = sorted(glob.glob(r"C:\Program Files\MongoDB\Server\*\bin\mongod.exe"), reverse=True)
        if hits:
            return str(hits[0])
    except Exception:
        pass
    return ""


def _wait_daemon_port_open(node: Dict[str, Any], timeout_sec: float = 30.0) -> bool:
    port = _daemon_node_port(node)
    if port <= 0:
        return False
    proto = _daemon_probe_proto(node)
    deadline = time.time() + max(2.0, float(timeout_sec))
    while time.time() < deadline:
        if _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            return True
        time.sleep(0.5)
    return False


def _start_external_daemon_node(node: Dict[str, Any], act: str = "start") -> Dict[str, Any]:
    """本机守护进程启动：Windows 走服务/可执行文件，避免 Test-NetConnection 拖慢与误报成功。"""
    nid = str(node.get("id") or "")
    port = _daemon_node_port(node)
    role = str(node.get("role") or "").strip().lower()
    log_path = _daemon_log_path(nid)
    lines: List[str] = [f"[{_now_iso()}] daemon {act} begin port={port} role={role}"]

    if port > 0 and _probe_by_protocol("127.0.0.1", port, _daemon_probe_proto(node)).get("ok"):
        try:
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(f"[{_now_iso()}] daemon {act} skipped: port {port} already listening\n")
        except Exception:
            pass
        state = _set_daemon_state(nid, {"status": "RUNNING", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path})
        return {
            "success": True,
            "message": f"daemon already running on port {port}",
            "data": {"node_id": nid, "status": "RUNNING", "pid": 0, "state": state, "log_path": log_path},
        }

    if os.name == "nt":
        if role in ("database", "mongo") or port == 27017:
            db_dir = _gomeku_mongo_dbpath()
            os.makedirs(db_dir, exist_ok=True)
            svc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Start-Service MongoDB -ErrorAction SilentlyContinue; "
                    "if ((Get-Service MongoDB -ErrorAction SilentlyContinue).Status -eq 'Running') { exit 0 } else { exit 1 }",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            lines.append(f"Start-Service MongoDB rc={svc.returncode} out={(svc.stdout or '').strip()} err={(svc.stderr or '').strip()}")
            if svc.returncode != 0:
                mongod = _resolve_mongod_executable()
                if mongod:
                    subprocess.Popen(
                        [mongod, "--dbpath", db_dir, "--port", str(port or 27017), "--bind_ip", "127.0.0.1"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
                    lines.append(f"fallback mongod={mongod}")
        elif role in ("cache", "redis") or port == 6379:
            svc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$s = Get-Service Memurai,MemuraiDeveloper,Redis -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.Status -eq 'Stopped' } | Select-Object -First 1; "
                    "if ($s) { Start-Service $s.Name -ErrorAction SilentlyContinue }; "
                    "if ((Get-Service Memurai,MemuraiDeveloper -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.Status -eq 'Running' } | Select-Object -First 1)) { exit 0 } else { exit 1 }",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            lines.append(f"Start-Service redis/memurai rc={svc.returncode} out={(svc.stdout or '').strip()} err={(svc.stderr or '').strip()}")
    else:
        start_cmd = str(node.get("daemon_start_cmd") or "").strip()
        if start_cmd:
            subprocess.Popen(start_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            lines.append(f"shell cmd={start_cmd[:200]}")

    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write("\n".join(lines) + "\n")

    live = _wait_daemon_port_open(node, timeout_sec=30.0)
    if live:
        state = _set_daemon_state(
            nid,
            {"status": "RUNNING", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path},
        )
        return {
            "success": True,
            "message": f"daemon {act} ok, port {port} listening",
            "data": {"node_id": nid, "status": "RUNNING", "pid": 0, "state": state, "log_path": log_path},
        }

    state = _set_daemon_state(
        nid,
        {"status": "ERROR", "pid": 0, "last_error": f"port {port} not listening", "last_action": act, "log_path": log_path},
    )
    return {
        "success": False,
        "message": f"daemon {act} failed: port {port} not listening (请检查 MongoDB/Memurai 服务是否已安装并可启动)",
        "data": {"node_id": nid, "status": "ERROR", "state": state, "log_path": log_path},
    }


def _wait_daemon_port_closed(node: Dict[str, Any], timeout_sec: float = 12.0) -> bool:
    port = _daemon_node_port(node)
    if port <= 0:
        return True
    proto = _daemon_probe_proto(node)
    deadline = time.time() + max(1.0, float(timeout_sec))
    while time.time() < deadline:
        if not _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            return True
        time.sleep(0.5)
    return False


def _daemon_cmd_looks_unix_only(cmd: str) -> bool:
    """Windows 上跳过明显只能在 Unix/macOS 执行的守护进程命令。"""
    text = str(cmd or "").strip().lower()
    if not text:
        return False
    unix_markers = (
        "/tmp/",
        "/opt/homebrew/",
        "/usr/local/",
        "mongosh ",
        "redis-cli -p",
        " --fork",
        " --daemonize",
        "bash -lc",
        "pkill ",
    )
    if any(marker in text for marker in unix_markers):
        return True
    if text.startswith("mongod ") and "--dbpath /tmp" in text:
        return True
    return False


def _stop_external_daemon_node(node: Dict[str, Any], act: str = "stop") -> Dict[str, Any]:
    """停止本机 Mongo/Redis 等守护节点：优先 stop_cmd，再杀残留 PID，以端口关闭为准。"""
    nid = str(node.get("id") or "")
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    state = _get_daemon_state(nid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    log_path = _daemon_log_path(nid)
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(f"[{_now_iso()}] daemon {act} stop pid={pid} cmd={stop_cmd}\n")

    if stop_cmd and not (os.name == "nt" and _daemon_cmd_looks_unix_only(stop_cmd)):
        subprocess.call(stop_cmd, shell=True)

    _kill_tracked_pid(pid)

    port = _daemon_node_port(node)
    closed = _wait_daemon_port_closed(node, timeout_sec=12.0)
    if not closed and stop_cmd and not (os.name == "nt" and _daemon_cmd_looks_unix_only(stop_cmd)):
        subprocess.call(stop_cmd, shell=True)
        closed = _wait_daemon_port_closed(node, timeout_sec=8.0)

    if not closed and os.name == "nt":
        role = str(node.get("role") or "").strip().lower()
        kill_images: List[str] = []
        if role in ("database", "mongo") or port == 27017:
            kill_images = ["mongod.exe"]
        elif role in ("cache", "redis") or port == 6379:
            kill_images = ["memurai.exe", "redis-server.exe"]
        for image in kill_images:
            subprocess.run(
                ["taskkill", "/F", "/IM", image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        closed = _wait_daemon_port_closed(node, timeout_sec=8.0)

    if closed or port <= 0:
        state = _set_daemon_state(nid, {"status": "STOPPED", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path})
        return {
            "success": True,
            "message": "daemon stopped",
            "data": {"node_id": nid, "status": "STOPPED", "pid": 0, "state": state, "log_path": log_path},
        }

    state = _set_daemon_state(
        nid,
        {"status": "ERROR", "pid": 0, "last_error": f"port {port} still listening", "last_action": act, "log_path": log_path},
    )
    return {
        "success": False,
        "message": f"daemon stop failed: port {port} still listening",
        "data": {"node_id": nid, "status": "ERROR", "state": state, "log_path": log_path},
    }


def _ops_platform_daemon_action(node: Dict[str, Any], action: str, reason: str, ticket_id: str, operator: str) -> Dict[str, Any]:
    nid = str(node.get("id") or "")
    act = str(action or "").strip().lower()
    server_id = str(node.get("server_id") or "").strip()
    role = str(node.get("role") or "").strip()
    start_cmd = str(node.get("daemon_start_cmd") or "").strip()
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    state = _get_daemon_state(nid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    local_daemon = _is_external_daemon_node(node)

    # Prefer native Ops API path in distributed deployment.
    if server_id and act in ("start", "stop", "restart", "status") and not local_daemon:
        map_action = {"start": "start", "stop": "stop", "restart": "restart", "status": "status"}.get(act, "status")
        result = ops_gateway.execute_platform_action(
            node,
            action_type=map_action,
            target=server_id,
            payload={},
            actor=operator,
            reason=reason,
            ticket_id=ticket_id,
            dry_run=False,
        )
        ok = bool(result.get("success"))
        if ok:
            new_status = "RUNNING" if act in ("start", "restart", "status") else "STOPPED"
            _set_daemon_state(nid, {"status": new_status, "last_error": "", "last_action": act})
        else:
            _set_daemon_state(nid, {"status": "ERROR", "last_error": str(result.get("message") or ""), "last_action": act})
        return result

    if act == "status":
        port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or 0)
        probe_role = str(node.get("role") or role or "").strip().lower()
        proto = "redis_ping" if probe_role in ("cache", "redis") else "mongo_ping"
        port_live = bool(_probe_by_protocol("127.0.0.1", port, proto).get("ok")) if port > 0 else False
        proc_live = _is_process_running(pid) if pid > 0 else False
        if port_live:
            now_status = "RUNNING"
            state = _set_daemon_state(nid, {"status": now_status, "last_error": "", "last_action": "status", "pid": pid if proc_live else 0})
        elif proc_live:
            now_status = "RUNNING"
        elif pid > 0:
            now_status = "CRASHED"
            state = _set_daemon_state(nid, {"status": now_status, "last_error": "process not alive", "pid": 0, "last_action": "status"})
        else:
            now_status = str(state.get("status") or "ADDED")
        return {"success": True, "message": "daemon status (local fallback)", "data": {"node_id": nid, "status": now_status, "pid": pid, "state": state}}

    port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or 0)
    if act in ("start", "restart") and port > 0:
        role = str(node.get("role") or "").strip().lower()
        proto = "redis_ping" if role in ("cache", "redis") else "mongo_ping"
        if _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            log_path = _daemon_log_path(nid)
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(f"[{_now_iso()}] daemon {act} skipped: port {port} already listening\n")
            state = _set_daemon_state(nid, {"status": "RUNNING", "pid": pid or 0, "last_error": "", "last_action": act, "log_path": log_path})
            return {
                "success": True,
                "message": f"daemon already running on port {port}",
                "data": {"node_id": nid, "status": "RUNNING", "pid": pid, "state": state, "log_path": log_path},
            }

    if act == "restart":
        stop_res = _stop_external_daemon_node(node, "restart")
        if not stop_res.get("success"):
            return stop_res
        act = "start"
        state = _get_daemon_state(nid)
        pid = 0

    if act in ("start", "restart") and (local_daemon or start_cmd):
        return _start_external_daemon_node(node, act)

    if act == "stop":
        return _stop_external_daemon_node(node, "stop")

    return {"success": False, "message": "no daemon control profile configured for this node", "data": {"node_id": nid, "role": role}}
