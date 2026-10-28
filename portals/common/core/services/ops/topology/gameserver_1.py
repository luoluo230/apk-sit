def _blueprint_edge_instance_pairs(source_ids: List[str], target_ids: List[str], mode: str) -> List[Tuple[str, str]]:
    if not source_ids or not target_ids:
        return []
    m = str(mode or "round_robin").strip().lower()
    pairs: List[Tuple[str, str]] = []
    if m == "each_to_all":
        for sid in source_ids:
            for tid in target_ids:
                pairs.append((sid, tid))
    elif m == "each_to_first":
        tid = target_ids[0]
        for sid in source_ids:
            pairs.append((sid, tid))
    elif m == "indexed":
        for idx, sid in enumerate(source_ids):
            if idx < len(target_ids):
                pairs.append((sid, target_ids[idx]))
    else:
        for idx, sid in enumerate(source_ids):
            pairs.append((sid, target_ids[idx % len(target_ids)]))
    return pairs


def _gameserver_tcp_probe_port(service_id: str, node: Optional[Dict[str, Any]] = None) -> int:
    sid = str(service_id or "").strip().lower()
    if sid in _GAMESERVER_TCP_PROBE_PORTS:
        return int(_GAMESERVER_TCP_PROBE_PORTS.get(sid) or 0)
    return 0


def _reconcile_gameserver_daemon_state(service_id: str) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {}
    live = _gameserver_service_live(sid)
    state = _get_daemon_state(sid)
    cur_status = str(state.get("status") or "").strip().upper()
    pid = _find_gameserver_pid_by_service(sid) if live else 0
    if live:
        patch = {"status": "RUNNING", "pid": int(pid or state.get("pid") or 0), "last_error": ""}
    elif cur_status in ("STARTING", "STOPPING"):
        patch = {"status": "STOPPED", "pid": 0, "last_error": ""}
    else:
        patch = {"status": "STOPPED", "pid": 0}
    merged = _set_daemon_state(sid, patch)
    return merged


def _reconcile_all_gameserver_daemon_states() -> None:
    for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
        try:
            _reconcile_gameserver_daemon_state(sid)
        except Exception:
            pass


def _gameserver_session_marker_path(repo: str = "", service_id: str = "") -> str:
    root = str(repo or _resolve_game_server_repo() or "").strip()
    sid = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "cluster").strip()) or "cluster"
    return os.path.join(root, "tools", "SmokeTest", "artifacts", f"gameserver-session-{sid}.json")


def _write_gameserver_session_marker(repo: str, pid: int, service_id: str = "") -> None:
    path = _gameserver_session_marker_path(repo, service_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(
            {"started_at": _now_iso(), "pid": int(pid), "epoch": time.time(), "service_id": str(service_id or "").strip()},
            fp,
        )


def _clear_gameserver_session_marker(repo: str = "", service_id: str = "") -> None:
    path = _gameserver_session_marker_path(repo, service_id)
    try:
        os.remove(path)
    except OSError:
        pass


def _read_gameserver_session_marker(repo: str = "", service_id: str = "") -> Dict[str, Any]:
    path = _gameserver_session_marker_path(repo, service_id)
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _find_pid_listening_on_port(port: int, host: str = "127.0.0.1") -> int:
    if port <= 0:
        return 0
    if os.name == "nt":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"$c = Get-NetTCPConnection -LocalAddress '{host}' -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | "
                    "Select-Object -First 1 -ExpandProperty OwningProcess; if ($c) { Write-Output $c }",
                ],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            for line in reversed((proc.stdout or "").splitlines()):
                text = line.strip()
                if text.isdigit():
                    return int(text)
        except Exception:
            pass
        try:
            proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=12, check=False)
            needle = f":{int(port)}"
            for line in (proc.stdout or "").splitlines():
                upper = line.upper()
                if "LISTENING" not in upper or needle not in line:
                    continue
                parts = line.split()
                if parts and parts[-1].isdigit():
                    return int(parts[-1])
        except Exception:
            pass
        return 0
    try:
        proc = subprocess.run(
            ["bash", "-lc", f"lsof -nP -iTCP:{int(port)} -sTCP:LISTEN -t 2>/dev/null | head -1"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        text = (proc.stdout or "").strip().splitlines()
        if text and text[0].strip().isdigit():
            return int(text[0].strip())
    except Exception:
        pass
    return 0


def _gameserver_log_source_paths(current_session_only: bool = False, service_id: str = "") -> List[str]:
    """优先 UTF-8 结构化日志（ServerLogger 写入），再合并 nohup 控制台输出。"""
    repo = _resolve_game_server_repo()
    paths: List[str] = []
    sid = str(service_id or "").strip().lower()
    if sid in ("mongo-db-cn-1", "redis-cache-cn-1", "db-01"):
        daemon_path = _daemon_log_path(sid if sid != "db-01" else "mongo-db-cn-1")
        return [daemon_path] if os.path.isfile(daemon_path) else []
    def _cluster_log_sort_key(path: str) -> Tuple[float, str]:
        try:
            return (float(os.path.getmtime(path)), os.path.basename(path))
        except OSError:
            return (0.0, os.path.basename(path))

    all_cluster: List[str] = []
    if _is_gameserver_process_service_id(sid):
        inst_logs = os.path.join(_gameserver_instance_dir(repo, sid), "logs")
        if os.path.isdir(inst_logs):
            all_cluster.extend(
                os.path.join(inst_logs, name)
                for name in os.listdir(inst_logs)
                if name.startswith("cluster-") and name.endswith(".log")
            )
        cluster_paths = sorted(set(all_cluster), key=_cluster_log_sort_key, reverse=True)[:1]
        paths.extend(cluster_paths)
        launcher_log = _gameserver_service_log_path(repo, sid)
        if os.path.isfile(launcher_log):
            paths.append(launcher_log)
        return paths
    for sub in (
        os.path.join(repo, "game-server", "bin", "Debug", "logs"),
        os.path.join(repo, "game-server", "bin", "Release", "logs"),
    ):
        if not os.path.isdir(sub):
            continue
        all_cluster.extend(
            os.path.join(sub, name)
            for name in os.listdir(sub)
            if name.startswith("cluster-") and name.endswith(".log")
        )
    cluster_paths = sorted(set(all_cluster), key=_cluster_log_sort_key, reverse=True)[:1]
    if cluster_paths:
        paths.extend(cluster_paths)
        return paths
    out_path, err_path = _gameserver_log_artifact_paths()
    for p in (out_path, err_path):
        if os.path.isfile(p):
            paths.append(p)
    return paths


def _parse_gameserver_log_line(line: str, source_path: str = "") -> Dict[str, Any]:
    raw = str(line or "").rstrip("\n\r")
    if not raw.strip():
        return {"time": "", "level": "info", "category": "", "message": "", "raw": raw}
    match = _GS_LOG_LINE_RE.match(raw.strip())
    if not match:
        level = _infer_log_level_from_text("", raw, source_path)
        category = ""
        bracket = re.match(r"^\[(?P<cat>[^\]]+)\]", raw.strip())
        if bracket:
            category = bracket.group("cat")
        return {
            "time": "",
            "level": level,
            "category": category,
            "message": raw,
            "raw": raw,
        }
    level = _infer_log_level_from_text(match.group("level"), raw, source_path)
    return {
        "time": match.group("time"),
        "level": level,
        "category": match.group("category"),
        "message": match.group("message"),
        "raw": raw,
    }


def _read_gameserver_service_logs(
    service_id: str = "",
    *,
    level: str = "all",
    query: str = "",
    tail: int = 400,
    since_offset: int = 0,
    current_session_only: bool = False,
    hide_lifecycle: bool = False,
) -> Dict[str, Any]:
    paths = _gameserver_log_source_paths(current_session_only=current_session_only, service_id=service_id)
    if not paths:
        return {
            "lines": [],
            "total": 0,
            "next_offset": 0,
            "sources": [],
            "message": "未找到 GameServer 日志文件，请先启动 GameServer",
        }

    merged: List[Tuple[int, str, str]] = []
    offset = 0
    seen_keys: set = set()
    daemon_source = _is_daemon_log_source(paths)
    has_cluster_logs = any("cluster-" in os.path.basename(p) for p in paths)
    for path in paths:
        try:
            for line in _read_text_file_lines(path):
                if has_cluster_logs and line.count("\ufffd") >= 4:
                    continue
                if not daemon_source and not current_session_only and not has_cluster_logs:
                    key = _log_dedupe_key(line)
                    if key and key in seen_keys:
                        continue
                    if key:
                        seen_keys.add(key)
                merged.append((offset, line, path))
                offset += len(line.encode("utf-8", errors="replace"))
        except Exception:
            continue

    session_started_at = ""
    if current_session_only and merged:
        if daemon_source:
            merged, session_started_at = _slice_merged_from_daemon_session(merged)
        else:
            marker = _read_gameserver_session_marker(service_id=service_id)
            marker_epoch = float(marker.get("epoch") or 0) if isinstance(marker, dict) else 0.0
            if marker_epoch > 0:
                merged, session_started_at = _filter_merged_from_session_epoch(merged, marker_epoch)
                if marker.get("started_at"):
                    session_started_at = str(marker.get("started_at") or session_started_at)
            else:
                merged, session_started_at = _slice_merged_from_current_session(merged)

    lv_filter = str(level or "all").strip().lower()
    q = str(query or "").strip().lower()
    repo = _resolve_game_server_repo()
    sid_lower = str(service_id or "").strip().lower()
    instance_root = _gameserver_instance_dir(repo, sid_lower).replace("\\", "/").lower() if sid_lower else ""
    skip_service_filter = bool(
        instance_root
        and _is_gameserver_process_service_id(sid_lower)
        and any(instance_root in str(p or "").replace("\\", "/").lower() for p in paths)
    )
    parsed_rows: List[Dict[str, Any]] = []
    for byte_offset, line, path in merged:
        if since_offset > 0 and byte_offset < since_offset:
            continue
        if hide_lifecycle and _should_hide_lifecycle_log_line(line):
            continue
        parsed = _parse_gameserver_log_line(line, path)
        if lv_filter not in ("", "all") and parsed.get("level") != lv_filter:
            continue
        if service_id and not daemon_source and not skip_service_filter and not _service_log_line_matches(service_id, parsed, line):
            continue
        hay = f"{parsed.get('raw') or ''} {parsed.get('category') or ''} {parsed.get('message') or ''}".lower()
        if q and q not in hay:
            continue
        parsed_rows.append({
            **parsed,
            "offset": byte_offset,
            "source": os.path.basename(path),
        })

    def _log_row_epoch(row: Dict[str, Any]) -> float:
        text = str(row.get("time") or row.get("raw") or "")
        match = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", text)
        if not match:
            return 0.0
        try:
            return datetime.fromisoformat(match.group(1).replace(" ", "T")).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return 0.0

    if parsed_rows:
        parsed_rows.sort(key=_log_row_epoch)
    if tail > 0 and len(parsed_rows) > tail:
        parsed_rows = parsed_rows[-tail:]

    next_offset = merged[-1][0] + len(merged[-1][1].encode("utf-8", errors="replace")) if merged else 0
    counts = {"info": 0, "warn": 0, "error": 0, "debug": 0}
    for row in parsed_rows:
        key = str(row.get("level") or "info")
        if key in counts:
            counts[key] += 1

    return {
        "lines": parsed_rows,
        "total": len(parsed_rows),
        "next_offset": next_offset,
        "sources": [os.path.basename(p) for p in paths],
        "counts": counts,
        "service_id": service_id,
        "session_started_at": session_started_at,
        "filters": {
            "current_session_only": bool(current_session_only),
            "hide_lifecycle": bool(hide_lifecycle),
        },
    }


def _clear_gameserver_launch_slot(service_id: str) -> None:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return
    with _GAMESERVER_LAUNCH_GUARD:
        _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)


def _gameserver_launch_slot_active(service_id: str) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return False
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if not isinstance(slot, dict):
            return False
        if float(slot.get("until") or 0.0) <= time.monotonic():
            _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)
            return False
        return True


def _try_acquire_gameserver_launch_slot(service_id: str, ttl_sec: float = _GAMESERVER_LAUNCH_LOCK_TTL_SEC) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return False
    now = time.monotonic()
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if isinstance(slot, dict) and float(slot.get("until") or 0.0) > now:
            return False
        _GAMESERVER_LAUNCH_SLOTS[sid] = {
            "until": now + max(30.0, float(ttl_sec)),
            "thread": threading.current_thread().ident,
        }
        return True


def _release_gameserver_launch_slot(service_id: str) -> None:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return
    ident = threading.current_thread().ident
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if isinstance(slot, dict) and slot.get("thread") not in (None, ident):
            return
        _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)
