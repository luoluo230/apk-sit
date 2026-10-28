def _launch_gameserver_service_posix(
    repo: str,
    service_id: str,
    port: int,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    log_path: str = "",
    exe: str = "",
    cfg_dir: str = "",
    probe_host: str = DEFAULT_LOOPBACK,
) -> Dict[str, Any]:
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    server_args = _gameserver_service_launch_args(service_id)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "service-action"
    launch_exe = str(exe or "").strip()
    launch_cwd = str(cfg_dir or repo).strip()
    cmd: List[str]
    if launch_exe.endswith(".dll"):
        cmd = ["dotnet", launch_exe, *server_args]
    else:
        cmd = [launch_exe, *server_args]
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(
            f"\n[{_now_iso()}] posix launch service={service_id} reason={reason_note} "
            f"cmd={' '.join(cmd)}\n"
        )
        log_fp.flush()
    proc = subprocess.Popen(cmd, cwd=launch_cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _set_daemon_state(service_id, {"status": "STARTING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    if not wait_ready:
        return {
            "success": True,
            "message": f"{service_id} 已在后台启动",
            "data": {"pid": int(proc.pid), "service_id": service_id, "log": log_path, "exe": launch_exe, "starting": True},
        }
    tcp_port = _gameserver_tcp_probe_port(service_id)
    deadline = time.time() + max(20, int(timeout_sec))
    exit_code: Optional[int] = None
    ready_after = time.time() + 4.0
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            if tcp_port > 0:
                live = _probe_tcp_open(host, tcp_port, timeout=0.35)
            else:
                live = time.time() >= ready_after
        else:
            live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
        if live and (tcp_port > 0 or time.time() >= ready_after):
            _write_gameserver_session_marker(repo, int(proc.pid), service_id)
            _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
            return {
                "success": True,
                "message": f"{service_id} 已就绪 ({ready_msg})",
                "data": {"pid": int(proc.pid), "service_id": service_id, "port": port, "live": True, "log": log_path, "exe": launch_exe},
            }
        time.sleep(0.8)
    if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
        live = _probe_tcp_open(host, tcp_port, timeout=0.5) if tcp_port > 0 else True
    else:
        live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
    ok = bool(live and exit_code is None)
    if ok:
        _write_gameserver_session_marker(repo, int(proc.pid), service_id)
        _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    else:
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            _kill_tracked_pid(int(proc.pid))
        _set_daemon_state(service_id, {"status": "ERROR", "pid": 0, "last_action": "start", "last_error": "launch failed"})
    ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
    msg = f"{service_id} 已就绪 ({ready_msg})" if ok else f"{service_id} 启动失败"
    return {"success": ok, "message": msg, "data": {"returncode": exit_code, "service_id": service_id, "port": port, "live": live, "log": log_path, "exe": launch_exe}}


def _launch_gameserver_service_windows(
    repo: str,
    service_id: str,
    port: int,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    log_path: str = "",
    probe_host: str = DEFAULT_LOOPBACK,
) -> Dict[str, Any]:
    """Windows 原生启动单个 GameServer 节点，禁止走 bash/WSL。"""
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    exe, cfg_dir = _prepare_gameserver_instance(repo, service_id)
    if not exe:
        return {"success": False, "message": "未找到 GameServer.GameServerApp.exe，请先在 game-server 目录编译 Debug/Release"}
    server_args = _gameserver_service_launch_args(service_id)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "service-action"
    cluster_log_path = _latest_instance_cluster_log_path(repo, service_id)
    cluster_log_pos = 0
    try:
        if cluster_log_path and os.path.isfile(cluster_log_path):
            cluster_log_pos = os.path.getsize(cluster_log_path)
    except Exception:
        cluster_log_pos = 0
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(
            f"\n[{_now_iso()}] windows-native launch service={service_id} reason={reason_note} "
            f"exe={exe} args={' '.join(server_args)}\n"
        )
        log_fp.flush()
    proc = subprocess.Popen(
        [exe, *server_args],
        cwd=cfg_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    _set_daemon_state(service_id, {"status": "STARTING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    if not wait_ready:
        return {
            "success": True,
            "message": f"{service_id} 已在后台启动",
            "data": {"pid": int(proc.pid), "service_id": service_id, "log": log_path, "exe": exe, "starting": True},
        }
    tcp_port = _gameserver_tcp_probe_port(service_id)
    deadline = time.time() + max(20, int(timeout_sec))
    exit_code: Optional[int] = None
    ready_after = time.time() + 4.0
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            if tcp_port > 0:
                live = _probe_tcp_open(host, tcp_port, timeout=0.35)
            else:
                live = time.time() >= ready_after
        else:
            live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
        if live and (tcp_port > 0 or time.time() >= ready_after):
            _write_gameserver_session_marker(repo, int(proc.pid), service_id)
            _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
            return {
                "success": True,
                "message": f"{service_id} 已就绪 ({ready_msg})",
                "data": {"pid": int(proc.pid), "service_id": service_id, "port": port, "live": True, "log": log_path, "exe": exe},
            }
        time.sleep(0.8)
    if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
        live = _probe_tcp_open(host, tcp_port, timeout=0.5) if tcp_port > 0 else True
    else:
        live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
    ok = bool(live and exit_code is None)
    if ok:
        _write_gameserver_session_marker(repo, int(proc.pid), service_id)
        _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    else:
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            _kill_tracked_pid(int(proc.pid))
        _set_daemon_state(service_id, {"status": "ERROR", "pid": 0, "last_action": "start", "last_error": "launch failed"})
    ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
    msg = (
        f"{service_id} 已就绪 ({ready_msg})"
        if ok
        else _format_gameserver_launch_failure(
            service_id,
            exit_code=exit_code,
            live=live,
            tcp_port=tcp_port,
            repo=repo,
            log_path=log_path,
            cluster_log_pos=cluster_log_pos,
        )
    )
    return {
        "success": ok,
        "message": msg,
        "data": {
            "returncode": exit_code,
            "service_id": service_id,
            "port": port,
            "live": live,
            "log": log_path,
            "exe": exe,
        },
    }


def _stop_gameserver_service(
    service_id: str,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {"success": False, "message": f"不支持的 GameServer 服务: {service_id}"}
    _clear_gameserver_launch_slot(sid)
    port = _gameserver_service_port(sid, node)
    tcp_port = _gameserver_tcp_probe_port(sid, node)
    state = _get_daemon_state(sid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    if pid <= 0 or not _is_process_running(pid):
        pid = _find_gameserver_pid_by_service(sid)
    for _ in range(4):
        if pid > 0:
            _kill_tracked_pid(pid)
        pid = _find_gameserver_pid_by_service(sid)
        if pid <= 0 and tcp_port > 0:
            port_pid = _find_pid_listening_on_port(tcp_port)
            if port_pid > 4:
                pid = port_pid
        if pid <= 0:
            break
        time.sleep(0.4)
    deadline = time.time() + 15.0
    while time.time() < deadline:
        if not _gameserver_service_live(sid, node, probe_host=host):
            _set_daemon_state(sid, {"status": "STOPPED", "pid": 0, "last_action": "stop", "last_error": ""})
            _clear_gameserver_session_marker(service_id=sid)
            detail = f"port {tcp_port}" if tcp_port > 0 else "process"
            return {"success": True, "message": f"已停止 {sid} 独立进程 ({detail})"}
        time.sleep(0.4)
    return {"success": False, "message": f"{sid} 仍在运行，停止未完成"}


def _stop_all_gameserver_services() -> Dict[str, Any]:
    try:
        for sid in reversed(_GAMESERVER_START_ORDER):
            _stop_gameserver_service(sid)
        if os.name == "nt":
            for cmd in (
                ["taskkill", "/F", "/IM", "GameServer.GameServerApp.exe"],
                ["taskkill", "/F", "/T", "/FI", "IMAGENAME eq GameServer.GameServerApp.exe"],
            ):
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
        else:
            subprocess.call(["pkill", "-f", "GameServer.GameServerApp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
            _clear_gameserver_session_marker(service_id=sid)
        open_ports = [p for p in _GAMESERVER_DEFAULT_PORTS.values() if _probe_tcp_open("127.0.0.1", p, timeout=0.25)]
        if open_ports:
            return {"success": False, "message": f"仍有 GameServer 端口在监听: {open_ports}"}
        return {"success": True, "message": "已停止全部 GameServer 独立进程"}
    except Exception as ex:
        return {"success": False, "message": f"停止 GameServer 失败: {ex}"}
