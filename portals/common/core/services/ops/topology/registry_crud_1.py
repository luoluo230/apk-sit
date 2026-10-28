def _project_has_cluster_json(project_id: str = "") -> bool:
    pid = str(project_id or "").strip()
    if pid and pid != "GomeKu":
        return False
    return bool(_load_cluster_json())


def _resolve_ops_project_id(raw: str = "") -> str:
    pid = str(raw or "").strip()
    if pid:
        return pid
    pid = str(session.get("ops_last_project") or "").strip()
    if pid:
        return pid
    return "GomeKu"


def _resolve_ops_env_key(raw: str = "") -> str:
    env = str(raw or "").strip()
    if env:
        return _normalize_env_key(env)
    env = str(session.get("ops_last_env") or "").strip()
    if env:
        return _normalize_env_key(env)
    return "production"


def _agent_matches_env(item: Dict[str, Any], env_key: str = "") -> bool:
    if not env_key:
        return True
    env = _normalize_env_key(env_key)
    if isinstance(item, dict):
        aid = str(item.get("agent_id") or "").strip()
        pid = str(item.get("project_id") or "").strip()
        if aid == CANONICAL_LOCAL_AGENT_ID and pid and _project_uses_runtime_topology(pid):
            return True
    agent_env = _normalize_env_key(str((item or {}).get("env_key") or (item or {}).get("env") or "production"))
    return agent_env == env


def _normalize_layout_spacing(raw: Any) -> Dict[str, int]:
    row = raw if isinstance(raw, dict) else {}
    try:
        rank_gap = int(row.get("rank_gap") or 268)
    except Exception:
        rank_gap = 268
    try:
        row_gap = int(row.get("row_gap") or 128)
    except Exception:
        row_gap = 128
    return {
        "rank_gap": max(160, min(480, rank_gap)),
        "row_gap": max(80, min(240, row_gap)),
    }


def _connect_rule_meta(node: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(node or {})
    role = str(row.get("role") or "business").strip().lower()
    preset_rules = _preset_role_rules(role)
    row["role"] = role
    row["allowed_upstream_roles"] = list(preset_rules["allowed_upstream_roles"])
    row["allowed_downstream_roles"] = list(preset_rules["allowed_downstream_roles"])
    return row


def _extract_line_iso_time(raw_line: str) -> str:
    text = str(raw_line or "")
    match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)", text)
    if match:
        return match.group(1)
    epoch = _log_line_epoch(text)
    if epoch > 0:
        return datetime.utcfromtimestamp(epoch).isoformat() + "Z"
    return ""


def _filter_merged_from_session_epoch(
    merged: List[Tuple[int, str, str]],
    epoch: float,
    *,
    grace_sec: float = 8.0,
) -> Tuple[List[Tuple[int, str, str]], str]:
    if epoch <= 0 or not merged:
        return merged, ""
    cutoff = float(epoch) - max(0.0, float(grace_sec))
    kept: List[Tuple[int, str, str]] = []
    trailing_blank = 0
    for item in merged:
        ts = _log_line_epoch(item[1])
        if ts >= cutoff:
            kept.append(item)
            trailing_blank = 0
        elif ts <= 0 and kept and trailing_blank < 2:
            kept.append(item)
            trailing_blank += 1
    if kept:
        return kept, datetime.utcfromtimestamp(float(epoch)).isoformat() + "Z"
    return merged, ""


def _slice_merged_from_current_session(merged: List[Tuple[int, str, str]]) -> Tuple[List[Tuple[int, str, str]], str]:
    start_idx = 0
    started_at = ""
    for idx, (_, line, _) in enumerate(merged):
        if _GS_LOG_SESSION_START.search(line):
            start_idx = idx
            match = _GS_LOG_LINE_RE.match(line.strip())
            if match:
                started_at = match.group("time")
    if start_idx <= 0:
        return merged, started_at
    return merged[start_idx:], started_at


def _read_text_file_lines(path: str) -> List[str]:
    if not path or not os.path.isfile(path):
        return []
    raw = b""
    try:
        with open(path, "rb") as fp:
            raw = fp.read()
    except Exception:
        return []
    if not raw:
        return []
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(encoding)
        except Exception:
            continue
        if encoding.startswith("utf") and text.count("\ufffd") > max(3, len(text) // 200):
            continue
        return text.splitlines(keepends=True)
    return raw.decode("utf-8", errors="replace").splitlines(keepends=True)


def _local_service_status_snapshot(project_id: str, topology_node_id: str, service_id: str) -> Dict[str, Any]:
    node = _resolve_ops_dispatch_node(project_id, topology_node_id)
    if not node:
        return {"ok": False, "message": "topology node not found"}
    port = int(node.get("port") or node.get("remote_game_server_port") or 0)
    cs_map = _fetch_cluster_runtime_status()
    raw_svc = {
        "service_id": service_id,
        "node_id": topology_node_id,
        "service_port": port,
        "remote_game_server_port": port,
        "service_type": node.get("role") or node.get("service_type") or "",
    }
    resolved = _resolve_service_runtime_state(raw_svc, host="127.0.0.1", cluster_status=cs_map)
    metrics = _sample_local_control_metrics()
    st = str(resolved.get("run_state") or resolved.get("status") or "UNKNOWN").upper()
    labels = {
        "RUNNING": "运行中",
        "ONLINE": "运行中",
        "READY": "运行中",
        "STARTING": "启动中",
        "STOPPED": "已停止",
        "OFFLINE": "离线",
        "UNKNOWN": "未知",
    }
    return {
        "ok": True,
        "message": f"{service_id} 当前状态：{labels.get(st, st)}",
        "data": {
            "service_id": service_id,
            "node_id": topology_node_id,
            "status": resolved.get("status"),
            "run_state": resolved.get("run_state"),
            "status_label": labels.get(st, st),
            "probe_status": resolved.get("probe_status"),
            "probe_method": resolved.get("probe_method"),
            "cluster_state": resolved.get("cluster_state"),
            "port": port,
            "host": "127.0.0.1",
            "metrics": metrics,
            "sampled_at": _now_iso(),
        },
        "mode": "direct-local",
    }


def _launch_local_game_server(
    service_id: str = "",
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 180,
    node: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    if sid:
        return _launch_gameserver_service(sid, reason, wait_ready, timeout_sec, node)
    return _launch_all_gameserver_services_in_order(reason, wait_ready, timeout_sec)


def _sanitize_user_facing_text(text: str, max_len: int = 200) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\uFFFD]", "", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    noise = ("可用命令", "cluster>", "--servers=", "--all", "--gm", "windows-native launch")
    if any(token in cleaned for token in noise):
        return ""
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned


def _stop_local_game_server() -> Dict[str, Any]:
    return _stop_all_gameserver_services()


def _kill_tracked_pid(pid: int) -> bool:
    if pid <= 0 or not _is_process_running(pid):
        return False
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return proc.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


def _windows_control_metrics() -> Dict[str, Any]:
    now = _now_iso()
    if os.name != "nt":
        return {"source": "runtime.sample", "updated_at": now}
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
                "$disk = Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\"; "
                "$mem = if ($os.TotalVisibleMemorySize -gt 0) { "
                "(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize) * 100 } else { 0 }; "
                "$dsk = if ($disk -and $disk.Size -gt 0) { (($disk.Size - $disk.FreeSpace) / $disk.Size) * 100 } else { 0 }; "
                "[pscustomobject]@{cpu=[double]$cpu; mem=[double]$mem; disk=[double]$dsk} | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            return {"source": "runtime.sample", "updated_at": now}
        payload = json.loads(raw)
        return {
            "cpu_percent": round(float(payload.get("cpu") or 0.0), 1),
            "mem_percent": round(float(payload.get("mem") or 0.0), 1),
            "disk_percent": round(float(payload.get("disk") or 0.0), 1),
            "source": "runtime.sample",
            "updated_at": now,
        }
    except Exception:
        return {"source": "runtime.sample", "updated_at": now}


def _fallback_local_control_metrics() -> Dict[str, Any]:
    """psutil 不可用时的轻量采样。"""
    now = _now_iso()
    if os.name == "nt":
        sample = _windows_control_metrics()
        if any(sample.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent")):
            return sample
    out: Dict[str, Any] = {"source": "runtime.sample", "updated_at": now}
    try:
        if sys.platform == "darwin":
            load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
            cores = max(1, os.cpu_count() or 1)
            out["cpu_percent"] = round(min(100.0, (float(load) / float(cores)) * 100.0), 1)
        proc = subprocess.run(["df", "-k", "/"], capture_output=True, text=True, timeout=2)
        if proc.returncode == 0:
            lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
            if len(lines) >= 2:
                parts = lines[-1].split()
                if len(parts) >= 5 and parts[-2].endswith("%"):
                    out["disk_percent"] = round(float(parts[-2].rstrip("%")), 1)
    except Exception:
        pass
    return out


def _refresh_services_live_state(
    services: List[Dict[str, Any]],
    host: str = "127.0.0.1",
    project_id: str = "",
    cluster_status: Optional[Dict[str, str]] = None,
    agent: Optional[Dict[str, Any]] = None,
    fast_probe: bool = False,
    probe_timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    sample = {} if fast_probe else _sample_local_control_metrics()
    cs_map = cluster_status if isinstance(cluster_status, dict) else {}
    if not cs_map and project_id and not fast_probe:
        try:
            cs_map = _fetch_cluster_runtime_status_cached(_agents_v2_for_project(project_id))
        except Exception:
            cs_map = {}
    pt = float(probe_timeout) if probe_timeout is not None else (0.12 if fast_probe else 0.35)
    rows = [raw for raw in (services or []) if isinstance(raw, dict)]

    def _probe_one(raw: Dict[str, Any]) -> Dict[str, Any]:
        svc_host = _resolve_agent_probe_host(agent, raw) if agent else host
        svc = _resolve_service_runtime_state(
            raw,
            host=svc_host,
            cluster_status=cs_map,
            probe_timeout=pt,
            fast_probe=fast_probe,
        )
        if not fast_probe:
            metrics = svc.get("metrics") if isinstance(svc.get("metrics"), dict) else {}
            merged = dict(metrics)
            if str(svc.get("probe_status") or "").upper() == "PASS":
                for key in ("cpu_percent", "mem_percent", "disk_percent", "source", "updated_at"):
                    if sample.get(key) is not None and merged.get(key) is None:
                        merged[key] = sample.get(key)
            if merged:
                svc["metrics"] = merged
            svc["updated_at"] = str(svc.get("updated_at") or sample.get("updated_at") or _now_iso())
        return svc

    if len(rows) <= 1:
        return [_probe_one(raw) for raw in rows]
    out: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(rows))) as pool:
        for svc in pool.map(_probe_one, rows):
            out.append(svc)
    return out
