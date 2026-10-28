def _set_daemon_state(node_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    data = _load_daemon_state()
    nid = str(node_id or "").strip()
    cur = data.get(nid) if isinstance(data.get(nid), dict) else {}
    merged = dict(cur)
    merged.update(patch or {})
    merged["updated_at"] = _now_iso()
    data[nid] = merged
    _save_daemon_state(data)
    return merged


def _get_daemon_state(node_id: str) -> Dict[str, Any]:
    data = _load_daemon_state()
    nid = str(node_id or "").strip()
    return data.get(nid) if isinstance(data.get(nid), dict) else {}


def _is_process_running(pid: int) -> bool:
    value = int(pid or 0)
    if value <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, value)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return int(exit_code.value) == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(value, 0)
        return True
    except Exception:
        return False


def _service_runtime_cache_fresh(services: List[Dict[str, Any]], max_age_sec: float = _AGENT_DETAIL_SERVICE_CACHE_MAX_AGE_SEC) -> bool:
    if not services:
        return False
    now = _time_mod.time()
    for svc in services:
        if not isinstance(svc, dict):
            return False
        run = str(svc.get("run_state") or svc.get("status") or "").strip().upper()
        if run in ("STARTING", "STOPPING", "RESTARTING"):
            return False
        ts = _parse_iso_ts(svc.get("updated_at"))
        if ts <= 0 or (now - ts) > max(4.0, float(max_age_sec)):
            return False
    return True


def _should_use_cached_service_state(services: List[Dict[str, Any]], force_live: bool = False) -> bool:
    if force_live:
        return False
    if any(_is_embedded_cluster_service(s) for s in (services or []) if isinstance(s, dict)):
        return False
    if _probe_service_cache_fresh():
        return True
    return _service_runtime_cache_fresh(services)


def _embedded_process_gateway_up(host: str = DEFAULT_LOOPBACK, timeout: float = 0.15) -> bool:
    probe_host = str(host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    return bool(
        _probe_tcp_open(probe_host, _RUNTIME_GATEWAY_PROBE_PORT, timeout=timeout)
        or _probe_tcp_open(probe_host, _RUNTIME_OPS_PROBE_PORT, timeout=timeout)
    )


def _daemon_log_path(node_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(node_id or "daemon").strip()) or "daemon"
    log_dir = os.path.join(DATA_DIR, "logs", "daemons")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"{safe}.log")


def _gameserver_log_artifact_paths() -> Tuple[str, str]:
    repo = _resolve_game_server_repo()
    log_dir = os.path.join(repo, "tools", "SmokeTest", "artifacts")
    return (
        os.path.join(log_dir, "server-live.out.log"),
        os.path.join(log_dir, "server-live.err.log"),
    )


def _is_gameserver_process_service_id(service_id: str) -> bool:
    return str(service_id or "").strip().lower() in _GAMESERVER_PROCESS_SERVICE_IDS


def _gameserver_service_port(service_id: str, node: Optional[Dict[str, Any]] = None) -> int:
    if isinstance(node, dict):
        port = int(node.get("port") or node.get("remote_game_server_port") or 0)
        if port > 0:
            return port
    return int(_GAMESERVER_DEFAULT_PORTS.get(str(service_id or "").strip().lower(), 0))


def _find_gameserver_pid_by_service(service_id: str) -> int:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return 0
    now = _time_mod.time()
    cached = _gameserver_pid_cache.get(sid)
    if cached and (now - float(cached[0] or 0.0)) < _GAMESERVER_PID_CACHE_TTL_SEC:
        return int(cached[1] or 0)
    needle = f"--servers={sid}"
    if os.name == "nt":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='GameServer.GameServerApp.exe'\" | "
                    "Select-Object ProcessId,CommandLine | ForEach-Object { "
                    f"if ($_.CommandLine -like '*{needle}*') {{ $_.ProcessId }} }}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            pid = 0
            for line in reversed((proc.stdout or "").splitlines()):
                text = line.strip()
                if text.isdigit():
                    pid = int(text)
                    break
            _gameserver_pid_cache[sid] = (now, pid)
            return pid
        except Exception:
            pass
        _gameserver_pid_cache[sid] = (now, 0)
        return 0
    try:
        proc = subprocess.run(
            ["bash", "-lc", "ps -eo pid=,args= | grep GameServer.GameServerApp | grep -F -- " + sid],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.strip().split(None, 1)
            if parts and parts[0].isdigit() and needle in (parts[1] if len(parts) > 1 else ""):
                pid = int(parts[0])
                _gameserver_pid_cache[sid] = (now, pid)
                return pid
    except Exception:
        pass
    _gameserver_pid_cache[sid] = (now, 0)
    return 0


def _is_gameserver_process_alive(service_id: str) -> bool:
    sid = str(service_id or "").strip().lower()
    state = _get_daemon_state(sid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    if pid > 0 and _is_process_running(pid):
        return True
    found = _find_gameserver_pid_by_service(sid)
    if found > 0 and _is_process_running(found):
        _set_daemon_state(sid, {"pid": found, "status": "RUNNING"})
        return True
    if found > 0:
        _set_daemon_state(sid, {"pid": 0, "status": "STOPPED"})
    return False


def _gameserver_service_live(
    service_id: str,
    node: Optional[Dict[str, Any]] = None,
    pid: int = 0,
    fast: bool = False,
    probe_host: str = "",
) -> bool:
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    port = _gameserver_tcp_probe_port(service_id, node)
    probe_timeout = 0.12 if fast else 0.35
    if port > 0:
        if not _probe_tcp_open(host, port, timeout=probe_timeout):
            return False
        if fast:
            return True
        active_pid = pid if pid > 0 and _is_process_running(pid) else _find_gameserver_pid_by_service(service_id)
        return bool(active_pid > 0 and _is_process_running(active_pid))
    if fast:
        state = _get_daemon_state(str(service_id or "").strip().lower())
        cached_pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
        return bool(cached_pid > 0 and _is_process_running(cached_pid))
    return _is_gameserver_process_alive(service_id)


def _gameserver_service_log_path(repo: str, service_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "gameserver").strip()) or "gameserver"
    return os.path.join(repo, "tools", "SmokeTest", "artifacts", f"apk-site-service-{safe}.log")
