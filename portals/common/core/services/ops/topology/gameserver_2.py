def _launch_gameserver_service(
    service_id: str,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    _reconcile_gameserver_daemon_state(sid)
    if _gameserver_service_live(sid, node, probe_host=host):
        live_pid = _find_gameserver_pid_by_service(sid) or int((_get_daemon_state(sid).get("pid") or 0))
        tcp_port = _gameserver_tcp_probe_port(sid, node)
        repo = _resolve_game_server_repo()
        log_path = _gameserver_service_log_path(repo, sid)
        try:
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(
                    f"[{_now_iso()}] daemon start skipped: {sid} already running "
                    f"pid={live_pid or 0}{', port ' + str(tcp_port) if tcp_port > 0 else ''}\n"
                )
        except Exception:
            pass
        return {
            "success": True,
            "message": f"{sid} 已在运行 (pid {live_pid or '-'}{', port ' + str(tcp_port) if tcp_port > 0 else ''})",
            "data": {"service_id": sid, "pid": live_pid, "already_running": True, "live": True, "log": log_path},
        }
    if _gameserver_launch_slot_active(sid) and not _gameserver_service_live(sid, node, probe_host=host):
        _clear_gameserver_launch_slot(sid)
    if not _try_acquire_gameserver_launch_slot(sid, ttl_sec=max(60.0, float(timeout_sec) + 30.0)):
        return {"success": False, "message": f"{sid} 启动正在进行中，请稍候再试"}
    try:
        return _launch_gameserver_service_impl(sid, reason, wait_ready, timeout_sec, node, probe_host=host)
    finally:
        _release_gameserver_launch_slot(sid)


def _launch_all_gameserver_services_in_order(
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    last: Dict[str, Any] = {"success": False, "message": "no services"}
    for sid in _GAMESERVER_START_ORDER:
        last = _launch_gameserver_service(sid, reason, wait_ready, timeout_sec)
        if not last.get("success"):
            return last
        time.sleep(0.8)
    return last


def _sync_gameserver_runtime_config(repo: str, cfg_dir: str) -> None:
    import shutil

    src_cfg = os.path.join(repo, "config")
    os.makedirs(cfg_dir, exist_ok=True)
    os.makedirs(os.path.join(cfg_dir, "config"), exist_ok=True)
    for name in ("cluster.json", "appsettings.json"):
        src = os.path.join(src_cfg, name)
        if not os.path.isfile(src):
            continue
        for dst in (os.path.join(cfg_dir, name), os.path.join(cfg_dir, "config", name)):
            try:
                if os.path.isfile(dst):
                    with open(src, "rb") as sfp, open(dst, "rb") as dfp:
                        if sfp.read() == dfp.read():
                            continue
                shutil.copy2(src, dst)
            except Exception:
                pass


def _gameserver_instance_dir(repo: str, service_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "gameserver").strip()) or "gameserver"
    return os.path.join(repo, "tools", "SmokeTest", "artifacts", "instances", safe)


def _prepare_gameserver_instance(repo: str, service_id: str) -> Tuple[str, str]:
    """为每个服务准备独立运行目录，避免多进程争用同一份 cluster 日志。"""
    import shutil

    src_exe, src_dir = _resolve_gameserver_executable(repo)
    if not src_exe:
        return "", ""
    inst_dir = _gameserver_instance_dir(repo, service_id)
    inst_exe = os.path.join(inst_dir, os.path.basename(src_exe))
    src_stamp = str(int(os.path.getmtime(src_exe)))
    stamp_file = os.path.join(inst_dir, ".build_stamp")
    need_copy = not os.path.isfile(inst_exe)
    if os.path.isfile(stamp_file):
        try:
            with open(stamp_file, "r", encoding="utf-8") as fp:
                need_copy = need_copy or fp.read().strip() != src_stamp
        except Exception:
            need_copy = True
    else:
        need_copy = True
    if need_copy:
        if os.path.isdir(inst_dir):
            shutil.rmtree(inst_dir, ignore_errors=True)
        shutil.copytree(src_dir, inst_dir)
        os.makedirs(os.path.join(inst_dir, "logs"), exist_ok=True)
        with open(stamp_file, "w", encoding="utf-8") as fp:
            fp.write(src_stamp)
    _sync_gameserver_runtime_config(repo, inst_dir)
    return inst_exe, inst_dir


def _resolve_gameserver_executable(repo: str) -> Tuple[str, str]:
    names = ("GameServer.GameServerApp.exe", "GameServer.GameServerApp") if os.name == "nt" else (
        "GameServer.GameServerApp",
        "GameServer.GameServerApp.exe",
    )
    for config in ("Debug", "Release"):
        cfg_dir = os.path.join(repo, "game-server", "bin", config)
        for name in names:
            exe = os.path.join(cfg_dir, name)
            if os.path.isfile(exe):
                return exe, cfg_dir
        dll = os.path.join(cfg_dir, "GameServer.GameServerApp.dll")
        if os.path.isfile(dll):
            return dll, cfg_dir
    return "", ""


def _launch_gameserver_unified_all(
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    """Windows 本地 E2E/业务测试：单进程 --all 启动，避免 Partial 多实例无法 WS 登录路由。"""
    repo = _resolve_game_server_repo()
    exe, cfg_dir = _resolve_gameserver_executable(repo)
    if not exe:
        return {"success": False, "message": "未找到 GameServer.GameServerApp.exe，请先编译 game-server Debug/Release"}
    if _probe_tcp_open("127.0.0.1", 15050, timeout=0.35) and _ws_handshake_probe()[0]:
        gs_count = _count_gameserver_processes()
        if gs_count == 1:
            return {
                "success": True,
                "message": "GameServer --all 已在运行 (ws://127.0.0.1:15050/ws/)",
                "data": {"mode": "unified-all", "already_running": True, "live": True},
            }
    _stop_local_game_server()
    time.sleep(1.2)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "unified-all"
    log_path = os.path.join(repo, "game-server", "bin", "Debug", "logs", "ops-unified-all.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cmd = [exe, "--all", "--headless", "--headless-seconds=86400"]
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(f"\n[{_now_iso()}] unified-all launch reason={reason_note} cmd={' '.join(cmd)}\n")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cfg_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception as ex:
        return {"success": False, "message": f"GameServer --all 启动失败: {ex}"}
    if not wait_ready:
        return {
            "success": True,
            "message": f"GameServer --all 已在后台启动 (pid {proc.pid})",
            "data": {"pid": int(proc.pid), "mode": "unified-all", "starting": True},
        }
    deadline = time.time() + max(25, int(timeout_sec))
    exit_code: Optional[int] = None
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        ws_ok, _ = _ws_handshake_probe()
        if ws_ok and _probe_tcp_open("127.0.0.1", 5504, timeout=0.35):
            for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
                _set_daemon_state(sid, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            return {
                "success": True,
                "message": f"GameServer --all 已就绪 (pid {proc.pid}, ws 15050, ops 5504)",
                "data": {"pid": int(proc.pid), "mode": "unified-all", "live": True, "log": log_path},
            }
        time.sleep(1.0)
    if exit_code is not None:
        return {"success": False, "message": f"GameServer --all 进程退出 code={exit_code}", "data": {"returncode": exit_code}}
    return {"success": False, "message": "GameServer --all 启动超时：15050/5504 未就绪", "data": {"pid": int(proc.pid)}}


def _should_use_unified_gameserver_all(app_ids: List[str], service_bindings: Dict[str, str]) -> bool:
    """Dev-only escape hatch; distributed multi-process is the default orchestration path."""
    if str(os.getenv("OPS_DEV_UNIFIED_GAMESERVER_ALL") or "").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    if os.name != "nt":
        return False
    gs_nodes = {
        str((service_bindings or {}).get(nid) or nid).strip().lower()
        for nid in (app_ids or [])
    }
    return bool(gs_nodes & set(_GAMESERVER_PROCESS_SERVICE_IDS))


def _wait_gameserver_tcp_port_free(
    port: int,
    timeout_sec: float = 20.0,
    probe_host: str = DEFAULT_LOOPBACK,
) -> bool:
    if port <= 0:
        return True
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    deadline = time.time() + max(1.0, float(timeout_sec))
    while time.time() < deadline:
        if not _probe_tcp_open(host, port, timeout=0.25):
            return True
        time.sleep(0.4)
    return not _probe_tcp_open(host, port, timeout=0.25)


def _latest_instance_cluster_log_path(repo: str, service_id: str) -> str:
    inst_logs = os.path.join(_gameserver_instance_dir(repo, service_id), "logs")
    if not os.path.isdir(inst_logs):
        return ""
    candidates = [
        os.path.join(inst_logs, name)
        for name in os.listdir(inst_logs)
        if name.startswith("cluster-") and name.endswith(".log")
    ]
    if not candidates:
        return ""
    try:
        return max(candidates, key=lambda p: os.path.getmtime(p))
    except Exception:
        return candidates[0]


def _extract_cluster_error_hint(cluster_log_path: str, since_pos: int = 0) -> str:
    if not cluster_log_path or not os.path.isfile(cluster_log_path):
        return ""
    try:
        lines = _read_text_file_lines(cluster_log_path)
        chunk = "".join(lines)
        if since_pos > 0 and since_pos < len(chunk.encode("utf-8", errors="replace")):
            chunk = chunk[max(0, since_pos // 2):]
    except Exception:
        return ""
    hints: List[str] = []
    for line in chunk.splitlines():
        text = line.strip()
        if not text:
            continue
        upper = text.upper()
        if not any(token in text for token in ("[ERROR]", "异常", "失败", "FATAL", "IOException", "冲突")) and \
                not any(token in upper for token in ("[ERROR]", "[FATAL]", "FAIL")):
            continue
        parsed = _sanitize_user_facing_text(text, max_len=180)
        if parsed:
            hints.append(parsed)
    return hints[-1] if hints else ""


def _format_gameserver_launch_failure(
    service_id: str,
    *,
    exit_code: Optional[int],
    live: bool,
    tcp_port: int,
    repo: str,
    log_path: str,
    cluster_log_pos: int = 0,
) -> str:
    sid = str(service_id or "").strip()
    parts: List[str] = []
    if exit_code is not None and int(exit_code) != 0:
        unsigned = int(exit_code) & 0xFFFFFFFF
        if unsigned in (3221225794, 3221225477):
            parts.append("进程初始化失败，常见原因是端口残留或实例文件损坏")
        else:
            parts.append(f"进程退出码 {exit_code}")
    if tcp_port > 0 and not live:
        parts.append(f"端口 {tcp_port} 未就绪")
    cluster_hint = _extract_cluster_error_hint(_latest_instance_cluster_log_path(repo, sid), cluster_log_pos)
    if cluster_hint:
        parts.append(cluster_hint)
    if not parts:
        parts.append("请打开「查看日志」查看本次启动详情")
    return f"{sid} 启动失败：{'；'.join(parts)}"


def _launch_gameserver_service_impl(
    service_id: str,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {"success": False, "message": f"不支持的 GameServer 服务: {service_id}"}
    port = _gameserver_service_port(sid, node)
    tcp_port = _gameserver_tcp_probe_port(sid, node)
    if _gameserver_service_live(sid, node, probe_host=host):
        live_pid = _find_gameserver_pid_by_service(sid) or int((_get_daemon_state(sid).get("pid") or 0))
        return {
            "success": True,
            "message": f"{sid} 已在运行 (pid {live_pid or '-'}{', port ' + str(tcp_port) if tcp_port > 0 else ''})",
            "data": {"service_id": sid, "port": port, "pid": live_pid, "already_running": True, "live": True},
        }
    stale_pid = _find_gameserver_pid_by_service(sid)
    if stale_pid > 0:
        _kill_tracked_pid(stale_pid)
        time.sleep(0.8)
    if tcp_port > 0:
        if _find_gameserver_pid_by_service(sid) > 0 or _gameserver_service_live(sid, node, probe_host=host):
            _stop_gameserver_service(sid, node, probe_host=host)
        if _probe_tcp_open(host, tcp_port, timeout=0.25) and not _wait_gameserver_tcp_port_free(
            tcp_port, timeout_sec=20.0, probe_host=host
        ):
            return {
                "success": False,
                "message": f"{sid} 启动失败：端口 {tcp_port} 仍被占用，请稍后重试",
                "data": {"service_id": sid, "port": port, "live": False},
            }

    repo = _resolve_game_server_repo()
    log_path = _gameserver_service_log_path(repo, sid)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    if os.name == "nt":
        try:
            return _launch_gameserver_service_windows(
                repo, sid, port, reason, wait_ready, timeout_sec, log_path, probe_host=host
            )
        except Exception as ex:
            return {"success": False, "message": f"启动 {sid} 失败: {ex}"}

    exe, cfg_dir = _resolve_gameserver_executable(repo)
    if not exe:
        script = os.path.join(repo, "scripts", "Start-GameServer.sh")
        return {"success": False, "message": f"未找到 GameServer 可执行文件或脚本: {script}"}
    return _launch_gameserver_service_posix(
        repo, sid, port, reason, wait_ready, timeout_sec, log_path, exe, cfg_dir, probe_host=host
    )
