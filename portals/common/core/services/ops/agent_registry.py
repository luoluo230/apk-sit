# -*- coding: utf-8 -*-
"""Agent registry merge, heartbeat, and stale handling."""

from __future__ import annotations

from services.ops import shared_bootstrap as _boot

globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})

def _is_design_demo_agent_row(item: Dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    aid = str(item.get("agent_id") or "").strip()
    nid = str(item.get("node_id") or "").strip()
    if aid in _DESIGN_DEMO_AGENT_IDS:
        return True
    if nid in _DESIGN_DEMO_NODE_IDS:
        return True
    if str(item.get("device_id") or "") == "device-game-01":
        return True
    for svc in item.get("services") if isinstance(item.get("services"), list) else []:
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or "")
        if sid.startswith("svc-game-01-"):
            return True
    return False

def _service_dict_from_topology_node(project_id: str, node: Dict[str, Any], now: str = "") -> Dict[str, Any]:
    node_id = str(node.get("server_id") or node.get("id") or "").strip()
    contract = _resolve_node_contract_for_topology_node(node)
    role = str(node.get("role") or contract.get("role") or "business").strip().lower()
    if role == "admin":
        role = "ops"
    port = _resolve_topology_node_port(node, contract, None, None)
    ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
    network = ui.get("network") if isinstance(ui.get("network"), dict) else {}
    remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
    endpoints = network.get("endpoints") if isinstance(network.get("endpoints"), list) else []
    host = _resolve_agent_probe_host(None, None, node)
    if host in ("0.0.0.0", "*", ""):
        host = "127.0.0.1"
    if endpoints and host == DEFAULT_LOOPBACK:
        ep = str(endpoints[0] or "")
        if ":" in ep:
            host = ep.split(":")[0].strip() or host
    elif str(remote.get("host") or remote.get("probe_host") or "").strip():
        host = str(remote.get("host") or remote.get("probe_host") or "").strip()
    cluster_type = _cluster_type_for_contract(contract, role)
    relay_port = _cluster_relay_port_for_type(cluster_type, role)
    return {
        "service_id": node_id,
        "node_id": node_id,
        "agent_id": CANONICAL_LOCAL_AGENT_ID,
        "device_id": CANONICAL_LOCAL_DEVICE_ID,
        "project_id": str(project_id or ""),
        "env_key": _normalize_env_key(node.get("env_key") or node.get("env") or "production"),
        "display_name": str(node.get("name") or node_id),
        "service_type": role,
        "service_port": int(port or 0),
        "remote_game_server_port": int(port or 0),
        "probe_host": host,
        "cluster_relay_port": relay_port,
        "run_state": "UNKNOWN",
        "status": "UNKNOWN",
        "probe_status": "",
        "probe_rtt_ms": 0.0,
        "metrics": {},
        "endpoints": endpoints or ([f"{host}:{port}"] if port else []),
        "public_ports": {"gateway": 15050, "relay": relay_port} if relay_port else {"gateway": port if role == "gateway" else 0},
        "updated_at": now or _now_iso(),
        "registration_origin": "topology.save",
    }

def _service_dict_from_agent_member(item: Dict[str, Any]) -> Dict[str, Any]:
    node_id = str(item.get("node_id") or "").strip()
    sid = str(item.get("service_id") or node_id or item.get("agent_id") or "").strip()
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    return {
        "service_id": sid,
        "node_id": node_id or sid,
        "agent_id": CANONICAL_LOCAL_AGENT_ID,
        "device_id": CANONICAL_LOCAL_DEVICE_ID,
        "project_id": str(item.get("project_id") or ""),
        "display_name": str(item.get("display_name") or sid),
        "service_type": str(item.get("role") or item.get("category") or ""),
        "service_port": int(item.get("port") or item.get("remote_game_server_port") or 0),
        "remote_game_server_port": int(item.get("remote_game_server_port") or item.get("port") or 0),
        "run_state": str(item.get("run_state") or ""),
        "status": _effective_runtime_status(item.get("status"), item.get("run_state"), item.get("probe_status")),
        "probe_status": str(item.get("probe_status") or ""),
        "probe_rtt_ms": float(item.get("probe_rtt_ms") or 0.0),
        "metrics": metrics,
        "endpoints": ((item.get("network") or {}).get("endpoints") if isinstance(item.get("network"), dict) else []) or [],
        "updated_at": str(item.get("updated_at") or item.get("last_seen") or _now_iso()),
        "registration_origin": _member_registration_origin(item),
    }

def _ensure_canonical_local_agent(
    project_id: str,
    services: List[Dict[str, Any]],
    host: str = "127.0.0.1",
    ops_port: int = 5504,
) -> str:
    """一台设备一个 Agent，多个服务挂在 services 下。"""
    pid = str(project_id or "").strip()
    reg = _load_agent_registry_v2()
    now = _now_iso()
    hit = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else {}
    merged_services: Dict[str, Dict[str, Any]] = {}
    for svc in services or []:
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or svc.get("node_id") or "").strip()
        if not sid:
            continue
        merged_services[sid] = dict(svc)
    runtime_topology = _project_uses_runtime_topology(pid)
    for svc in (hit.get("services") if isinstance(hit.get("services"), list) else []):
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or svc.get("node_id") or "").strip()
        if runtime_topology and sid in _DESIGN_DEMO_NODE_IDS:
            continue
        if sid and sid not in merged_services:
            merged_services[sid] = dict(svc)
    service_rows = list(merged_services.values())
    for svc in service_rows:
        if str(svc.get("node_id") or "") == "ops-cn-1":
            ops_port = int(svc.get("service_port") or svc.get("remote_game_server_port") or ops_port or 5504)
            break
    payload = _normalize_agent_descriptor_v2(
        {
            "agent_id": CANONICAL_LOCAL_AGENT_ID,
            "device_id": CANONICAL_LOCAL_DEVICE_ID,
            "node_id": "",
            "host_name": host,
            "host_ip": host,
            "probe_host": host,
            "project_id": pid,
            "status": str(hit.get("status") or "ONLINE"),
            "version": str(hit.get("version") or "canonical-local-v1"),
            "last_seen": str(hit.get("last_seen") or now),
            "display_name": "本地 GameServer Agent",
            "port": int(ops_port or 5504),
            "remote_game_server_port": int(ops_port or 5504),
            "desc": "单 Agent 管理本机全部拓扑服务节点",
            "run_state": str(hit.get("run_state") or "RUNNING"),
            "probe_status": str(hit.get("probe_status") or ""),
            "probe_at": str(hit.get("probe_at") or ""),
            "probe_rtt_ms": float(hit.get("probe_rtt_ms") or 0.0),
            "capabilities": ["health_check", "start", "stop", "restart", "probe", "daemon"],
            "metrics": hit.get("metrics") if isinstance(hit.get("metrics"), dict) else {},
            "network": {"endpoints": [f"{host}:{ops_port}"] if ops_port else []},
            "transport": {
                "mode": "remote",
                "local_bus": {"enabled": True, "endpoint": f"pipe://{CANONICAL_LOCAL_DEVICE_ID}/{CANONICAL_LOCAL_AGENT_ID}", "auth_mode": "token"},
            },
            "registration_origin": "canonical.local",
            "services": service_rows,
            "updated_at": now,
        }
    )
    payload.pop("stale", None)
    payload.pop("stale_reason", None)
    payload.pop("superseded_by", None)
    reg[CANONICAL_LOCAL_AGENT_ID] = payload
    _append_realtime_agent_sample(reg[CANONICAL_LOCAL_AGENT_ID])
    _save_agent_registry_v2(reg)
    return CANONICAL_LOCAL_AGENT_ID

def _consolidate_runtime_agents_to_canonical(project_id: str) -> Dict[str, Any]:
    """将 runtime 拓扑下的 per-node agent 合并为单 Agent + 多 services。"""
    pid = str(project_id or "").strip()
    if not pid or not _project_uses_runtime_topology(pid):
        return {"ok": False, "skipped": True}
    reg = _load_agent_registry_v2()
    services_map: Dict[str, Dict[str, Any]] = {}
    host = "127.0.0.1"
    ops_port = 5504
    stale_count = 0
    for aid, item in reg.items():
        if not isinstance(item, dict) or item.get("stale"):
            continue
        if str(item.get("project_id") or "") not in ("", pid):
            continue
        if aid == CANONICAL_LOCAL_AGENT_ID:
            for svc in item.get("services") if isinstance(item.get("services"), list) else []:
                if isinstance(svc, dict):
                    sid = str(svc.get("service_id") or svc.get("node_id") or "").strip()
                    if sid:
                        services_map[sid] = dict(svc)
            continue
        nid = str(item.get("node_id") or "").strip()
        if not nid:
            continue
        svc = _service_dict_from_agent_member(item)
        services_map[str(svc.get("service_id") or nid)] = svc
        if nid == "ops-cn-1":
            ops_port = int(item.get("port") or item.get("remote_game_server_port") or ops_port)
        host = str(item.get("probe_host") or item.get("host_name") or item.get("host_ip") or host)
    if not services_map:
        return {"ok": False, "reason": "no_services"}
    _ensure_canonical_local_agent(pid, list(services_map.values()), host=host, ops_port=ops_port)
    reg = _load_agent_registry_v2()
    now = _now_iso()
    for aid, item in reg.items():
        if not isinstance(item, dict) or aid == CANONICAL_LOCAL_AGENT_ID:
            continue
        if str(item.get("project_id") or "") not in ("", pid):
            continue
        nid = str(item.get("node_id") or "").strip()
        if nid and nid in services_map:
            item["stale"] = True
            item["stale_reason"] = "consolidated_to_canonical"
            item["superseded_by"] = CANONICAL_LOCAL_AGENT_ID
            item["updated_at"] = now
            stale_count += 1
    _save_agent_registry_v2(reg)
    return {"ok": True, "agent_id": CANONICAL_LOCAL_AGENT_ID, "services": len(services_map), "stale": stale_count}

def _upsert_agents_from_topology(project_id: str, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """拓扑保存后同步到 canonical local agent 的 services 列表。"""
    pid = str(project_id or "").strip()
    if not pid:
        return {"updated": 0, "added": 0}
    now = _now_iso()
    services = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("server_id") or node.get("id") or "").strip()
        if not node_id:
            continue
        services.append(_service_dict_from_topology_node(pid, node, now))
    if _project_uses_runtime_topology(pid):
        stat = _consolidate_runtime_agents_to_canonical(pid)
        if services:
            _ensure_canonical_local_agent(pid, services)
        return {"updated": len(services), "added": 0, "active": len(services), "canonical": stat}
    reg = _load_agent_registry_v2()
    added = 0
    updated = 0
    for svc in services:
        agent_id = f"agent-{svc['node_id']}"
        hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
        payload = _normalize_agent_descriptor_v2(
            {
                "agent_id": agent_id,
                "device_id": CANONICAL_LOCAL_DEVICE_ID,
                "host_name": "127.0.0.1",
                "probe_host": "127.0.0.1",
                "node_id": svc["node_id"],
                "project_id": pid,
                "env_key": _normalize_env_key(svc.get("env_key") or svc.get("env") or "production"),
                "status": "UNKNOWN",
                "display_name": svc["display_name"],
                "port": svc["service_port"],
                "remote_game_server_port": svc["remote_game_server_port"],
                "desc": svc["display_name"],
                "registration_origin": "topology.save",
                "updated_at": now,
            }
        )
        if hit:
            hit.update({k: v for k, v in payload.items() if k not in ("agent_id",)})
            hit.pop("stale", None)
            updated += 1
        else:
            reg[agent_id] = payload
            added += 1
    _save_agent_registry_v2(reg)
    return {"updated": updated, "added": added, "active": len(services)}

def _agent_token_for_node(node: Dict[str, Any]) -> str:
    tok = str(node.get("ops_write_key") or node.get("ops_read_key") or "").strip()
    # 如果数据库里的 node 没有 key，从默认 nodes 里取
    if not tok:
        for dn in _default_nodes():
            if str(dn.get("id") or "") == str(node.get("id") or ""):
                tok = str(dn.get("ops_write_key") or dn.get("ops_read_key") or "").strip()
                break
    return tok

def _auth_agent_node(node_id: str, token: str, cert_fp: str = "") -> Optional[Dict[str, Any]]:
    nid = str(node_id or "").strip()
    tok = str(token or "").strip()
    if not nid or not tok:
        print(f"[auth_agent] missing nid or tok: nid={nid} tok={tok[:8] if tok else ''}")
        return None
    node = _resolve_node(node_id=nid)
    if not node:
        print(f"[auth_agent] node not found: {nid}")
        return None
    expected = _agent_token_for_node(node)
    if not expected or expected != tok:
        print(f"[auth_agent] token mismatch: expected={expected[:16] if expected else 'EMPTY'} got={tok[:16]} node_id={nid} node_keys={list(node.keys())}")
        return None
    policy = _load_agent_policy()
    mtls_required = bool(policy.get("mtls_required"))
    allow_fp = node.get("agent_cert_fingerprints") if isinstance(node.get("agent_cert_fingerprints"), list) else []
    if mtls_required:
        fp = str(cert_fp or "").strip().lower()
        if not fp:
            return None
        if allow_fp:
            normalized = [str(x or "").strip().lower() for x in allow_fp if str(x or "").strip()]
            if normalized and fp not in normalized:
                return None
    return node

def _idempotency_key(node_id: str, action_type: str, target: str, payload: Dict[str, Any], ticket_id: str) -> str:
    body = {
        "node_id": str(node_id or ""),
        "action_type": str(action_type or ""),
        "target": str(target or ""),
        "payload": payload if isinstance(payload, dict) else {},
        "ticket_id": str(ticket_id or ""),
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

def _enqueue_agent_job(node_id: str, action_type: str, target: str, payload: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    jobs = _load_agent_jobs()
    idem_key = _idempotency_key(node_id, action_type, target, payload, str(validation.get("ticket_id") or ""))
    for x in reversed(jobs):
        if not isinstance(x, dict):
            continue
        if str(x.get("idempotency_key") or "") != idem_key:
            continue
        st = str(x.get("status") or "").upper()
        if st in ("PENDING", "RUNNING", "SUCCESS"):
            return x
    job_id = "job-" + uuid.uuid4().hex[:16]
    now = _now_iso()
    item = {
        "job_id": job_id,
        "node_id": str(node_id or ""),
        "action_type": str(action_type or ""),
        "target": str(target or ""),
        "payload": payload if isinstance(payload, dict) else {},
        "risk": str(validation.get("risk") or ""),
        "ticket_id": str(validation.get("ticket_id") or ""),
        "reason": str(validation.get("reason") or ""),
        "requested_by": str(session.get("user") or "intranet-ops"),
        "require_approval": bool(validation.get("require_approval")),
        "approved": bool(validation.get("approved")),
        "approval_target_id": str(validation.get("approval_target_id") or ""),
        "status": "PENDING",
        "created_at": now,
        "updated_at": now,
        "lease": {},
        "attempt": 0,
        "max_retries": int(_load_agent_policy().get("max_retries") or 2),
        "priority": int((payload or {}).get("priority") or 100),
        "preempt": bool((payload or {}).get("preempt") or False),
        "idempotency_key": idem_key,
        "result": {},
    }
    jobs.append(item)
    _save_agent_jobs(jobs)
    return item

def _agent_status_terminal(status: str) -> bool:
    s = str(status or "").upper()
    return s in ("SUCCESS", "FAILED", "CANCELED", "TIMEOUT")

def _parse_iso_datetime(value: str) -> Optional[datetime]:
    v = str(value or "").strip()
    if not v:
        return None
    try:
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v)
    except Exception:
        return None

def _agent_managed_service_ids(agent_id: str, pull_node_id: str = "") -> set:
    ids: set = set()
    pull_nid = str(pull_node_id or "").strip()
    if pull_nid:
        ids.add(pull_nid)
    aid = str(agent_id or "").strip()
    if not aid:
        return ids
    reg = _load_agent_registry_v2()
    agent = reg.get(aid) if isinstance(reg.get(aid), dict) else {}
    for svc in agent.get("services") if isinstance(agent.get("services"), list) else []:
        if not isinstance(svc, dict):
            continue
        for key in ("service_id", "node_id"):
            val = str(svc.get(key) or "").strip()
            if val:
                ids.add(val)
    if aid == CANONICAL_LOCAL_AGENT_ID:
        ids.update(_GAMESERVER_PROCESS_SERVICE_IDS)
    return ids

def _job_desired_service_id(job: Dict[str, Any]) -> str:
    if not isinstance(job, dict):
        return ""
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    for key in ("desired_server_id", "desired_service_id"):
        val = str(payload.get(key) or "").strip()
        if val:
            return val
    return str(job.get("target") or job.get("node_id") or "").strip()

def _job_matches_agent(job: Dict[str, Any], agent_id: str, pull_node_id: str) -> bool:
    if not isinstance(job, dict):
        return False
    job_nid = str(job.get("node_id") or "").strip()
    desired = _job_desired_service_id(job)
    service_ids = _agent_managed_service_ids(agent_id, pull_node_id)
    if job_nid and job_nid in service_ids:
        return True
    if desired and desired in service_ids:
        return True
    return False

def _reconcile_agent_jobs(
    node_id: str,
    jobs: List[Dict[str, Any]],
    *,
    lease_timeout_sec: int,
    max_retries: int,
    agent_id: str = "",
) -> bool:
    changed = False
    now = datetime.now(timezone.utc)
    service_ids = _agent_managed_service_ids(agent_id, node_id) if agent_id else {str(node_id or "").strip()}
    for item in jobs:
        if not isinstance(item, dict):
            continue
        job_nid = str(item.get("node_id") or "").strip()
        desired = _job_desired_service_id(item)
        if agent_id:
            if job_nid not in service_ids and desired not in service_ids:
                continue
        elif job_nid != node_id:
            continue
        status = str(item.get("status") or "").upper()
        if status != "RUNNING":
            continue
        lease = item.get("lease") if isinstance(item.get("lease"), dict) else {}
        leased_at = _parse_iso_datetime(str(lease.get("leased_at") or item.get("updated_at") or ""))
        if not leased_at:
            continue
        age = (now.replace(tzinfo=None) - leased_at.replace(tzinfo=None)).total_seconds()
        if age < max(5, int(lease_timeout_sec)):
            continue
        attempts = int(item.get("attempt") or 0)
        if attempts < max_retries:
            item["status"] = "PENDING"
            item["updated_at"] = _now_iso()
            item["attempt"] = attempts + 1
            item["lease"] = {}
        else:
            item["status"] = "TIMEOUT"
            item["updated_at"] = _now_iso()
            item["result"] = {"message": "lease timeout reached max retries"}
        changed = True
    return changed

def _desired_agent_upgrade(agent_id: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    rollout = policy.get("rollout") if isinstance(policy.get("rollout"), dict) else {}
    if not rollout.get("enabled"):
        return {"upgrade": False}
    desired_version = str(rollout.get("desired_version") or "").strip()
    if not desired_version:
        return {"upgrade": False}
    allow_ids = rollout.get("allow_ids") if isinstance(rollout.get("allow_ids"), list) else []
    channel = str(rollout.get("channel") or "stable")
    percent = int(rollout.get("percent") or 0)
    if allow_ids and agent_id in allow_ids:
        return {"upgrade": True, "desired_version": desired_version, "channel": channel}
    if percent <= 0:
        return {"upgrade": False}
    slot = int(hashlib.sha256(str(agent_id or "").encode("utf-8")).hexdigest()[:8], 16) % 100
    if slot < percent:
        return {"upgrade": True, "desired_version": desired_version, "channel": channel}
    return {"upgrade": False}

def _normalize_agent_descriptor_v2(item: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    transport = item.get("transport") if isinstance(item.get("transport"), dict) else {}
    local_bus = transport.get("local_bus") if isinstance(transport.get("local_bus"), dict) else {}
    raw_metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    raw_control = raw_metrics.get("control") if isinstance(raw_metrics.get("control"), dict) else {}
    raw_business = raw_metrics.get("business") if isinstance(raw_metrics.get("business"), dict) else {}
    raw_flat = raw_metrics if raw_control == {} and raw_business == {} else {}
    runtime_metrics = item.get("runtime") if isinstance(item.get("runtime"), dict) else {}
    cpu_val = raw_control.get("cpu_percent", raw_flat.get("cpu_percent", raw_flat.get("cpu")))
    mem_val = raw_control.get("mem_percent", raw_flat.get("mem_percent", raw_flat.get("mem")))
    disk_val = raw_control.get("disk_percent", raw_flat.get("disk_percent", raw_flat.get("disk")))
    qps_val = raw_control.get("qps", raw_flat.get("qps", raw_flat.get("throughput_qps")))
    rtt_val = raw_control.get("rtt_ms", raw_flat.get("rtt_ms", raw_flat.get("latency_ms")))
    svc_cpu_val = raw_control.get("service_cpu_percent", raw_flat.get("service_cpu_percent"))
    svc_mem_val = raw_control.get("service_memory_mb", raw_flat.get("service_memory_mb"))
    if cpu_val is None:
        cpu_val = runtime_metrics.get("cpu_percent", runtime_metrics.get("cpu"))
    if mem_val is None:
        mem_val = runtime_metrics.get("mem_percent", runtime_metrics.get("mem"))
    if disk_val is None:
        disk_val = runtime_metrics.get("disk_percent", runtime_metrics.get("disk"))
    if qps_val is None:
        qps_val = runtime_metrics.get("qps", runtime_metrics.get("throughput_qps"))
    if rtt_val is None:
        rtt_val = runtime_metrics.get("rtt_ms", runtime_metrics.get("latency_ms"))
    try:
        cpu_num = max(0.0, min(100.0, float(cpu_val))) if cpu_val is not None else None
    except Exception:
        cpu_num = None
    try:
        mem_num = max(0.0, min(100.0, float(mem_val))) if mem_val is not None else None
    except Exception:
        mem_num = None
    try:
        disk_num = max(0.0, min(100.0, float(disk_val))) if disk_val is not None else None
    except Exception:
        disk_num = None
    try:
        qps_num = max(0.0, float(qps_val)) if qps_val is not None else None
    except Exception:
        qps_num = None
    try:
        rtt_num = max(0.0, float(rtt_val)) if rtt_val is not None else None
    except Exception:
        rtt_num = None
    try:
        svc_cpu_num = max(0.0, min(100.0, float(svc_cpu_val))) if svc_cpu_val is not None else None
    except Exception:
        svc_cpu_num = None
    try:
        svc_mem_num = max(0.0, float(svc_mem_val)) if svc_mem_val is not None else None
    except Exception:
        svc_mem_num = None
    biz_qps_val = raw_business.get("qps", raw_flat.get("business_qps"))
    biz_p95_val = raw_business.get("rtt_p95_ms", raw_flat.get("business_rtt_p95_ms"))
    biz_p99_val = raw_business.get("rtt_p99_ms", raw_flat.get("business_rtt_p99_ms"))
    biz_err_val = raw_business.get("error_rate", raw_flat.get("business_error_rate"))
    biz_conn_val = raw_business.get("conn", raw_flat.get("business_conn"))
    try:
        biz_qps_num = max(0.0, float(biz_qps_val)) if biz_qps_val is not None else None
    except Exception:
        biz_qps_num = None
    try:
        biz_p95_num = max(0.0, float(biz_p95_val)) if biz_p95_val is not None else None
    except Exception:
        biz_p95_num = None
    try:
        biz_p99_num = max(0.0, float(biz_p99_val)) if biz_p99_val is not None else None
    except Exception:
        biz_p99_num = None
    try:
        biz_err_num = max(0.0, float(biz_err_val)) if biz_err_val is not None else None
    except Exception:
        biz_err_num = None
    try:
        biz_conn_num = max(0.0, float(biz_conn_val)) if biz_conn_val is not None else None
    except Exception:
        biz_conn_num = None
    return {
        "agent_id": str(item.get("agent_id") or ""),
        "device_id": str(item.get("device_id") or ""),
        "host_name": str(item.get("host_name") or item.get("hostname") or ""),
        "host_ip": str(item.get("host_ip") or item.get("host_name") or item.get("hostname") or ""),
        "region": str(item.get("region") or ""),
        "zone": str(item.get("zone") or ""),
        "rack": str(item.get("rack") or ""),
        "node_id": str(item.get("node_id") or ""),
        "project_id": str(item.get("project_id") or ""),
        "env_key": _normalize_env_key(item.get("env_key") or item.get("env") or "production"),
        "status": str(item.get("status") or "UNKNOWN").upper(),
        "version": str(item.get("version") or ""),
        "last_seen": str(item.get("last_seen") or ""),
        "display_name": str(item.get("display_name") or item.get("agent_id") or ""),
        "port": int(item.get("port") or 0),
        "remote_game_server_port": int(item.get("remote_game_server_port") or item.get("port") or 0),
        "desc": str(item.get("desc") or ""),
        "run_state": str(item.get("run_state") or ""),
        "probe_status": str(item.get("probe_status") or ""),
        "probe_at": str(item.get("probe_at") or ""),
        "probe_rtt_ms": float(item.get("probe_rtt_ms") or 0.0),
        "capabilities": item.get("capabilities") if isinstance(item.get("capabilities"), list) else [],
        "service_id": str(item.get("service_id") or ""),
        "services": item.get("services") if isinstance(item.get("services"), list) else [],
        "network": item.get("network") if isinstance(item.get("network"), dict) else {"endpoints": []},
        "transport": {
            "mode": str(transport.get("mode") or "remote").lower(),
            "local_endpoint": str(local_bus.get("endpoint") or transport.get("local_endpoint") or ""),
            "local_enabled": bool(local_bus.get("enabled", True)),
            "local_auth_mode": str(local_bus.get("auth_mode") or "token"),
            "degraded": bool(transport.get("degraded", False)),
            "degrade_reason": str(transport.get("degrade_reason") or ""),
        },
        "metrics": {
            "control": {
                "cpu_percent": cpu_num,
                "mem_percent": mem_num,
                "disk_percent": disk_num,
                "qps": qps_num,
                "rtt_ms": rtt_num,
                "service_cpu_percent": svc_cpu_num,
                "service_memory_mb": svc_mem_num,
                "updated_at": str(raw_control.get("updated_at") or raw_flat.get("updated_at") or runtime_metrics.get("updated_at") or item.get("last_seen") or ""),
                "source": str(raw_control.get("source") or raw_flat.get("source") or runtime_metrics.get("source") or "agent"),
            },
            "business": {
                "qps": biz_qps_num,
                "rtt_p95_ms": biz_p95_num,
                "rtt_p99_ms": biz_p99_num,
                "error_rate": biz_err_num,
                "conn": biz_conn_num,
                "updated_at": str(raw_business.get("updated_at") or item.get("last_seen") or ""),
                "source": str(raw_business.get("source") or "missing"),
            },
            "cpu_percent": cpu_num,
            "mem_percent": mem_num,
            "disk_percent": disk_num,
            "qps": qps_num,
            "rtt_ms": rtt_num,
            "updated_at": str(raw_control.get("updated_at") or raw_flat.get("updated_at") or runtime_metrics.get("updated_at") or item.get("last_seen") or ""),
            "source": str(raw_control.get("source") or raw_flat.get("source") or runtime_metrics.get("source") or "agent"),
        },
        "updated_at": str(item.get("updated_at") or ""),
        # cluster sync 附加字段
        "stale": bool(item.get("stale", False)),
        "stale_reason": str(item.get("stale_reason") or ""),
        "superseded_by": str(item.get("superseded_by") or ""),
        "registration_origin": str(item.get("registration_origin") or ""),
        "config_state": str(item.get("config_state") or "").upper(),
        "category": str(item.get("category") or "").strip(),
        "role": str(item.get("role") or "").strip(),
        "probe_host": str(item.get("probe_host") or item.get("host_name") or "").strip(),
        "probe_source": str(item.get("probe_source") or "").strip(),
        "probe_proto": str(item.get("probe_proto") or "tcp").strip().lower(),
    }

def _agents_v2_for_project(project_id: str = "", env_key: str = "") -> List[Dict[str, Any]]:
    rows = _load_agent_registry_v2()
    out: List[Dict[str, Any]] = []
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key) if str(env_key or "").strip() else ""
    for v in rows.values():
        if not isinstance(v, dict):
            continue
        item = _normalize_agent_descriptor_v2(v)
        if pid and item.get("project_id") and item.get("project_id") != pid:
            continue
        if env and not _agent_matches_env(item, env):
            continue
        if pid and _project_uses_runtime_topology(pid) and _is_design_demo_agent_row(item):
            continue
        if pid and _project_uses_runtime_topology(pid):
            aid = str(item.get("agent_id") or "").strip()
            if aid != CANONICAL_LOCAL_AGENT_ID:
                nid = str(item.get("node_id") or "").strip()
                if nid.endswith("-cn-1") or (aid.startswith("agent-") and aid.endswith("-cn-1")):
                    continue
        if item.get("stale"):
            continue
        item["registration_origin"] = _member_registration_origin(item)
        out.append(item)
    return out

def _services_for_project(project_id: str = "", env_key: str = "") -> List[Dict[str, Any]]:
    rows = _logical_agents_for_project(project_id, env_key)
    out: List[Dict[str, Any]] = []
    for a in rows:
        if not isinstance(a, dict):
            continue
        services = a.get("services") if isinstance(a.get("services"), list) else []
        if services:
            for s in services:
                if not isinstance(s, dict):
                    continue
                sid = str(s.get("service_id") or s.get("id") or "").strip()
                if not sid:
                    continue
                out.append(
                    {
                        "service_id": sid,
                        "node_id": str(s.get("node_id") or sid),
                        "agent_id": str(a.get("agent_id") or ""),
                        "device_id": str(a.get("device_id") or ""),
                        "project_id": str(a.get("project_id") or ""),
                        "service_type": str(s.get("service_type") or s.get("type") or ""),
                        "service_port": int(s.get("service_port") or s.get("port") or 0),
                        "remote_game_server_port": int(s.get("remote_game_server_port") or s.get("service_port") or s.get("port") or a.get("remote_game_server_port") or 0),
                        "run_state": str(s.get("run_state") or a.get("run_state") or ""),
                        "status": str(s.get("status") or a.get("status") or "UNKNOWN"),
                        "probe_status": str(s.get("probe_status") or a.get("probe_status") or ""),
                        "probe_rtt_ms": float(s.get("probe_rtt_ms") or a.get("probe_rtt_ms") or 0.0),
                        "metrics": s.get("metrics") if isinstance(s.get("metrics"), dict) else {},
                        "endpoints": s.get("endpoints") if isinstance(s.get("endpoints"), list) else [],
                        "updated_at": str(s.get("updated_at") or a.get("updated_at") or a.get("last_seen") or ""),
                        "source": "agent.services",
                    }
                )
        else:
            # Backward compatibility: one agent as one service instance.
            sid = str(a.get("service_id") or a.get("node_id") or a.get("agent_id") or "").strip()
            if not sid:
                continue
            m = a.get("metrics") if isinstance(a.get("metrics"), dict) else {}
            out.append(
                {
                    "service_id": sid,
                    "node_id": str(a.get("node_id") or sid),
                    "agent_id": str(a.get("agent_id") or ""),
                    "device_id": str(a.get("device_id") or ""),
                    "project_id": str(a.get("project_id") or ""),
                    "service_type": str(a.get("role") or a.get("node_id") or ""),
                    "service_port": int(a.get("port") or 0),
                    "remote_game_server_port": int(a.get("remote_game_server_port") or a.get("port") or 0),
                    "run_state": str(a.get("run_state") or ""),
                    "status": str(a.get("status") or "UNKNOWN"),
                    "probe_status": str(a.get("probe_status") or ""),
                    "probe_rtt_ms": float(a.get("probe_rtt_ms") or 0.0),
                    "metrics": m.get("business") if isinstance(m.get("business"), dict) else m,
                    "endpoints": ((a.get("network") or {}).get("endpoints") if isinstance(a.get("network"), dict) else []) or [],
                    "updated_at": str(a.get("updated_at") or a.get("last_seen") or ""),
                    "source": "agent.compat",
                }
            )
    if out and str(project_id or "").strip():
        try:
            out = _refresh_services_live_state(
                out,
                project_id=str(project_id or "").strip(),
                fast_probe=True,
                probe_timeout=0.25,
            )
        except Exception:
            pass
    return out

def _status_rank(status: str) -> int:
    value = str(status or "").upper()
    if value in ("DEGRADED", "ERROR", "FAILED"):
        return 4
    if value in ("OFFLINE", "TIMEOUT", "CANCELED"):
        return 3
    if value in ("MAINTENANCE", "STOPPED", "STOP"):
        return 2
    if value in ("ONLINE", "READY", "RUNNING", "SUCCESS"):
        return 1
    return 0

def _parse_iso_ts(value: Any) -> float:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "")).timestamp()
    except Exception:
        return 0.0

def _member_registration_origin(item: Dict[str, Any]) -> str:
    origin = str(item.get("registration_origin") or "").strip().lower()
    if origin:
        return origin
    if str(item.get("device_id") or "").strip() == "local-game-server":
        return "cluster.sync"
    if str(item.get("last_seen") or "").strip():
        return "runtime.agent"
    return "unknown"

def _effective_runtime_status(status: Any, run_state: Any, probe_status: Any = "") -> str:
    run = str(run_state or "").strip().upper()
    if run in ("STOPPED", "STOP"):
        return "STOPPED"
    probe = str(probe_status or "").strip().upper()
    if probe == "FAIL":
        return "OFFLINE"
    if run in ("RUNNING", "READY") and probe == "PASS":
        return "RUNNING"
    if run in ("STARTING", "STOPPING", "RESTARTING"):
        return run
    base = str(status or "").strip().upper()
    if base in ("STOPPED", "OFFLINE", "FAILED"):
        return base
    if probe == "PASS":
        return "ONLINE"
    if run in ("RUNNING", "READY"):
        return "UNKNOWN"
    if base:
        return base
    return "UNKNOWN"

def _extract_control_metrics(item: Dict[str, Any]) -> Dict[str, Any]:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    control = metrics.get("control") if isinstance(metrics.get("control"), dict) else metrics
    if not isinstance(control, dict):
        control = {}
    return {
        "cpu_percent": control.get("cpu_percent"),
        "mem_percent": control.get("mem_percent"),
        "disk_percent": control.get("disk_percent"),
        "qps": control.get("qps"),
        "rtt_ms": control.get("rtt_ms"),
        "service_cpu_percent": control.get("service_cpu_percent"),
        "service_memory_mb": control.get("service_memory_mb"),
        "updated_at": str(control.get("updated_at") or item.get("updated_at") or item.get("last_seen") or ""),
        "source": str(control.get("source") or "agent"),
    }

def _append_realtime_agent_sample(item: Dict[str, Any]) -> None:
    if not isinstance(item, dict):
        return
    agent_id = str(item.get("agent_id") or "").strip()
    if not agent_id:
        return
    sample = _extract_control_metrics(item)
    if not any(sample.get(key) is not None for key in ("cpu_percent", "mem_percent", "disk_percent")):
        return
    sample_time = _now_iso()
    point = {
        "time": sample_time,
        "cpu_percent": sample.get("cpu_percent"),
        "mem_percent": sample.get("mem_percent"),
        "disk_percent": sample.get("disk_percent"),
        "qps": sample.get("qps"),
        "rtt_ms": sample.get("rtt_ms"),
        "service_cpu_percent": sample.get("service_cpu_percent"),
        "service_memory_mb": sample.get("service_memory_mb"),
        "_ts": _parse_iso_ts(sample_time) or datetime.now(timezone.utc).timestamp(),
    }
    with _agent_metric_history_lock:
        bucket = _agent_metric_history.get(agent_id)
        if not isinstance(bucket, deque):
            bucket = deque(maxlen=OPS_AGENT_METRIC_MAX_POINTS)
            _agent_metric_history[agent_id] = bucket
        last = bucket[-1] if bucket else None
        if last and str(last.get("time") or "") == point["time"]:
            changed = any(last.get(key) != point.get(key) for key in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"))
            if not changed:
                return
        bucket.append(point)

def _realtime_metric_points(agent_ids: List[str], window_sec: int = OPS_AGENT_METRIC_WINDOW_SEC) -> List[Dict[str, Any]]:
    ids = [str(x or "").strip() for x in (agent_ids or []) if str(x or "").strip()]
    if not ids:
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - max(60, int(window_sec or OPS_AGENT_METRIC_WINDOW_SEC))
    merged: List[Dict[str, Any]] = []
    with _agent_metric_history_lock:
        for agent_id in ids:
            bucket = _agent_metric_history.get(agent_id)
            if not isinstance(bucket, deque):
                continue
            for point in list(bucket):
                if not isinstance(point, dict):
                    continue
                ts_val = float(point.get("_ts") or _parse_iso_ts(point.get("time")))
                if ts_val < cutoff:
                    continue
                merged.append(
                    {
                        "time": str(point.get("time") or ""),
                        "cpu_percent": point.get("cpu_percent"),
                        "mem_percent": point.get("mem_percent"),
                        "disk_percent": point.get("disk_percent"),
                        "qps": point.get("qps"),
                        "rtt_ms": point.get("rtt_ms"),
                        "service_cpu_percent": point.get("service_cpu_percent"),
                        "service_memory_mb": point.get("service_memory_mb"),
                        "_ts": ts_val,
                    }
                )
    merged.sort(key=lambda item: (float(item.get("_ts") or 0.0), str(item.get("time") or "")))
    return merged[-OPS_AGENT_METRIC_MAX_POINTS:]

def _latest_realtime_metric(agent_ids: List[str]) -> Dict[str, Any]:
    points = _realtime_metric_points(agent_ids, window_sec=OPS_AGENT_METRIC_WINDOW_SEC * 24)
    if not points:
        return {}
    latest = dict(points[-1])
    latest.pop("_ts", None)
    return latest

def _ensure_agent_metrics_live(agent: Dict[str, Any], member_agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """详情读路径：补齐 CPU/内存/磁盘指标并写入内存采样环，不写 registry。"""
    if not isinstance(agent, dict):
        return {}
    ids = [str(agent.get("agent_id") or "").strip()]
    ids.extend([str(x or "").strip() for x in (member_agent_ids or []) if str(x or "").strip()])
    _overlay_live_metrics(agent, ids)
    control = agent.get("metrics") if isinstance(agent.get("metrics"), dict) else {}
    nested = control.get("control") if isinstance(control.get("control"), dict) else control
    has_values = isinstance(nested, dict) and any(
        nested.get(key) is not None for key in ("cpu_percent", "mem_percent", "disk_percent")
    )
    if not has_values:
        _inject_live_control_metrics(agent)
    if any(
        (agent.get("metrics") or {}).get(key) is not None
        for key in ("cpu_percent", "mem_percent", "disk_percent")
    ) or any(
        ((agent.get("metrics") or {}).get("control") or {}).get(key) is not None
        for key in ("cpu_percent", "mem_percent", "disk_percent")
    ):
        agent["metrics_live"] = True
        _append_realtime_agent_sample(agent)
    else:
        agent["metrics_live"] = False
    return agent

def _apply_service_metrics_from_agent(services: List[Dict[str, Any]], agent: Dict[str, Any]) -> List[Dict[str, Any]]:
    sample = _extract_control_metrics(agent if isinstance(agent, dict) else {})
    if not any(sample.get(key) is not None for key in ("cpu_percent", "mem_percent", "disk_percent")):
        sample = _sample_local_control_metrics()
    out: List[Dict[str, Any]] = []
    for raw in services or []:
        if not isinstance(raw, dict):
            continue
        svc = dict(raw)
        if str(svc.get("probe_status") or "").upper() != "PASS":
            out.append(svc)
            continue
        metrics = svc.get("metrics") if isinstance(svc.get("metrics"), dict) else {}
        merged = dict(metrics)
        for key in ("cpu_percent", "mem_percent", "disk_percent", "service_cpu_percent", "service_memory_mb", "source", "updated_at"):
            if sample.get(key) is not None and merged.get(key) is None:
                merged[key] = sample.get(key)
        if merged:
            svc["metrics"] = merged
        out.append(svc)
    return out

def _overlay_live_metrics(agent: Dict[str, Any], agent_ids: List[str]) -> Dict[str, Any]:
    if not isinstance(agent, dict):
        return {}
    latest = _latest_realtime_metric(agent_ids)
    if not latest:
        return agent
    base_metrics = agent.get("metrics") if isinstance(agent.get("metrics"), dict) else {}
    control = base_metrics.get("control") if isinstance(base_metrics.get("control"), dict) else base_metrics
    business = base_metrics.get("business") if isinstance(base_metrics.get("business"), dict) else {}
    merged = dict(control) if isinstance(control, dict) else {}
    for key in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"):
        if latest.get(key) is not None:
            merged[key] = latest.get(key)
    merged["updated_at"] = str(latest.get("time") or merged.get("updated_at") or agent.get("updated_at") or agent.get("last_seen") or "")
    merged["source"] = "runtime.sample"
    agent["metrics"] = {"control": merged, "business": business, **merged}
    agent["metrics_live"] = True
    return agent

def _mark_duplicate_runtime_agents(registry: Dict[str, Any], canonical_agent_id: str, node_id: str) -> None:
    if not isinstance(registry, dict) or not canonical_agent_id or not node_id:
        return
    now = _now_iso()
    for agent_id, item in registry.items():
        if agent_id == canonical_agent_id or not isinstance(item, dict):
            continue
        if str(item.get("node_id") or "").strip() != node_id:
            continue
        if _member_registration_origin(item) == "cluster.sync":
            continue
        item["stale"] = True
        item["stale_reason"] = "duplicate_runtime_agent"
        item["superseded_by"] = canonical_agent_id
        item["updated_at"] = now

def _pick_primary_agent(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    def score(item: Dict[str, Any]) -> tuple:
        has_services = 1 if isinstance(item.get("services"), list) and item.get("services") else 0
        no_node = 1 if not str(item.get("node_id") or "").strip() else 0
        has_host = 1 if str(item.get("host_ip") or item.get("host_name") or "").strip() else 0
        updated = str(item.get("updated_at") or item.get("last_seen") or "")
        return (has_services, no_node, has_host, updated)
    return dict(sorted(rows, key=score, reverse=True)[0])

def _logical_agents_for_project(project_id: str = "", env_key: str = "") -> List[Dict[str, Any]]:
    rows = _agents_v2_for_project(project_id, env_key)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        group_key = str(item.get("device_id") or item.get("agent_id") or "").strip()
        if not group_key:
            continue
        groups.setdefault(group_key, []).append(item)

    out: List[Dict[str, Any]] = []
    for device_id, members in groups.items():
        primary = _pick_primary_agent(members)
        if not primary:
            continue

        services: List[Dict[str, Any]] = []
        service_seen: set = set()
        node_ids: List[str] = []
        member_agent_ids: List[str] = []
        origin_kinds: set = set()
        best_status = "UNKNOWN"
        best_status_rank = -1
        latest_seen = ""

        for member in members:
            member_agent_id = str(member.get("agent_id") or "").strip()
            if member_agent_id and member_agent_id not in member_agent_ids:
                member_agent_ids.append(member_agent_id)

            member_node_id = str(member.get("node_id") or "").strip()
            if member_node_id and member_node_id not in node_ids:
                node_ids.append(member_node_id)

            origin_kinds.add(_member_registration_origin(member))
            effective_status = str(member.get("effective_status") or member.get("status") or "UNKNOWN").upper()
            rank = _status_rank(effective_status)
            if rank > best_status_rank:
                best_status_rank = rank
                best_status = effective_status

            seen_at = str(member.get("last_seen") or "")
            if seen_at and seen_at > latest_seen:
                latest_seen = seen_at

            member_services = member.get("services") if isinstance(member.get("services"), list) else []
            if member_services:
                for svc in member_services:
                    if not isinstance(svc, dict):
                        continue
                    sid = str(svc.get("service_id") or svc.get("id") or "").strip()
                    if not sid or sid in service_seen:
                        continue
                    if _project_uses_runtime_topology(project_id) and sid in _DESIGN_DEMO_NODE_IDS:
                        continue
                    service_seen.add(sid)
                    services.append(
                        {
                            "service_id": sid,
                            "agent_id": member_agent_id,
                            "node_id": str(svc.get("node_id") or sid or member_node_id or "").strip(),
                            "device_id": device_id,
                            "project_id": str(member.get("project_id") or ""),
                            "display_name": str(svc.get("display_name") or sid),
                            "service_type": str(svc.get("service_type") or svc.get("type") or member.get("role") or ""),
                            "service_port": int(svc.get("service_port") or svc.get("port") or member.get("remote_game_server_port") or member.get("port") or 0),
                            "remote_game_server_port": int(svc.get("remote_game_server_port") or svc.get("service_port") or svc.get("port") or member.get("remote_game_server_port") or member.get("port") or 0),
                            "run_state": str(svc.get("run_state") or member.get("run_state") or ""),
                            "status": _effective_runtime_status(svc.get("status") or member.get("status"), svc.get("run_state") or member.get("run_state"), svc.get("probe_status") or member.get("probe_status")),
                            "probe_status": str(svc.get("probe_status") or member.get("probe_status") or ""),
                            "probe_rtt_ms": float(svc.get("probe_rtt_ms") or member.get("probe_rtt_ms") or 0.0),
                            "metrics": svc.get("metrics") if isinstance(svc.get("metrics"), dict) else (member.get("metrics") if isinstance(member.get("metrics"), dict) else {}),
                            "endpoints": svc.get("endpoints") if isinstance(svc.get("endpoints"), list) else [],
                            "updated_at": str(svc.get("updated_at") or member.get("updated_at") or member.get("last_seen") or ""),
                            "source": "logical.agent.services",
                            "registration_origin": _member_registration_origin(member),
                        }
                    )
            else:
                sid = str(member.get("service_id") or member.get("node_id") or member.get("agent_id") or "").strip()
                if sid and sid not in service_seen:
                    service_seen.add(sid)
                    m = member.get("metrics") if isinstance(member.get("metrics"), dict) else {}
                    services.append(
                        {
                            "service_id": sid,
                            "agent_id": member_agent_id,
                            "node_id": member_node_id,
                            "device_id": device_id,
                            "project_id": str(member.get("project_id") or ""),
                            "display_name": str(member.get("display_name") or sid),
                            "service_type": str(member.get("role") or member.get("category") or member_node_id or ""),
                            "service_port": int(member.get("port") or 0),
                            "remote_game_server_port": int(member.get("remote_game_server_port") or member.get("port") or 0),
                            "run_state": str(member.get("run_state") or ""),
                            "status": _effective_runtime_status(member.get("status"), member.get("run_state"), member.get("probe_status")),
                            "probe_status": str(member.get("probe_status") or ""),
                            "probe_rtt_ms": float(member.get("probe_rtt_ms") or 0.0),
                            "metrics": m.get("business") if isinstance(m.get("business"), dict) else m,
                            "endpoints": ((member.get("network") or {}).get("endpoints") if isinstance(member.get("network"), dict) else []) or [],
                            "updated_at": str(member.get("updated_at") or member.get("last_seen") or ""),
                            "source": "logical.agent.compat",
                            "registration_origin": _member_registration_origin(member),
                        }
                    )

        aggregated = dict(primary)
        aggregated["agent_id"] = str(primary.get("agent_id") or device_id)
        aggregated["device_id"] = device_id
        aggregated["display_name"] = (
            str(device_id)
            if len(members) > 1 and not any(isinstance(x.get("services"), list) and x.get("services") for x in members)
            else str(primary.get("display_name") or device_id)
        )
        aggregated["effective_status"] = best_status
        aggregated["last_seen"] = latest_seen or str(primary.get("last_seen") or "")
        aggregated["node_id"] = str(primary.get("node_id") or node_ids[0] if node_ids else "")
        aggregated["services"] = services
        aggregated["member_agent_ids"] = member_agent_ids
        aggregated["member_node_ids"] = node_ids
        aggregated["service_count"] = len(services)
        aggregated["registration_origin"] = _member_registration_origin(primary)
        aggregated["topology_relation"] = (
            "mixed_runtime"
            if "runtime.agent" in origin_kinds and "cluster.sync" in origin_kinds
            else "standalone_runtime"
            if "runtime.agent" in origin_kinds
            else "cluster_compat"
            if "cluster.sync" in origin_kinds
            else "unknown"
        )
        _overlay_live_metrics(aggregated, member_agent_ids)
        out.append(aggregated)

    out.sort(key=lambda x: str(x.get("device_id") or x.get("display_name") or x.get("agent_id") or ""))
    return out

def _resolve_agent_from_node(node_id: str) -> Dict[str, str]:
    service_bindings = _load_node_service_bindings()
    agent_bindings = _load_node_agent_bindings()
    service_id = str(service_bindings.get(node_id) or "").strip()
    agent_id = str(agent_bindings.get(node_id) or "").strip()
    if service_id and not agent_id:
        # derive agent from service map
        for s in _services_for_project(""):
            if str(s.get("service_id") or "") == service_id:
                agent_id = str(s.get("agent_id") or "")
                break
    return {"service_id": service_id, "agent_id": agent_id}

def _device_metrics_snapshot(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    snaps: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        did = str(item.get("device_id") or "unknown-device")
        m = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        mc = m.get("control") if isinstance(m.get("control"), dict) else m
        mb = m.get("business") if isinstance(m.get("business"), dict) else {}
        ts_raw = str(mc.get("updated_at") or m.get("updated_at") or item.get("last_seen") or "")
        try:
            ts_val = datetime.fromisoformat(ts_raw.replace("Z", "")).timestamp()
        except Exception:
            ts_val = 0.0
        cur = snaps.get(did) if isinstance(snaps.get(did), dict) else None
        if cur is None or float(cur.get("_ts") or 0.0) < ts_val:
            snaps[did] = {
                "_ts": ts_val,
                "control": {
                    "cpu_percent": mc.get("cpu_percent"),
                    "mem_percent": mc.get("mem_percent"),
                    "disk_percent": mc.get("disk_percent"),
                    "qps": mc.get("qps"),
                    "rtt_ms": mc.get("rtt_ms"),
                    "updated_at": ts_raw,
                    "source": str(mc.get("source") or m.get("source") or "agent"),
                },
                "business": {
                    "qps": mb.get("qps"),
                    "rtt_p95_ms": mb.get("rtt_p95_ms"),
                    "rtt_p99_ms": mb.get("rtt_p99_ms"),
                    "error_rate": mb.get("error_rate"),
                    "conn": mb.get("conn"),
                    "updated_at": str(mb.get("updated_at") or ""),
                    "source": str(mb.get("source") or "missing"),
                },
                "cpu_percent": mc.get("cpu_percent"),
                "mem_percent": mc.get("mem_percent"),
                "disk_percent": mc.get("disk_percent"),
                "qps": mc.get("qps"),
                "rtt_ms": mc.get("rtt_ms"),
                "updated_at": ts_raw,
                "source": str(mc.get("source") or m.get("source") or "agent"),
                "metrics_missing": {
                    "control": not any(x is not None for x in (mc.get("cpu_percent"), mc.get("mem_percent"), mc.get("disk_percent"), mc.get("qps"), mc.get("rtt_ms"))),
                    "business": not any(x is not None for x in (mb.get("qps"), mb.get("rtt_p95_ms"), mb.get("rtt_p99_ms"), mb.get("error_rate"), mb.get("conn"))),
                },
            }
    for did in list(snaps.keys()):
        snaps[did].pop("_ts", None)
    return snaps

def _item_matches_agent_scope(item: Dict[str, Any], agent: Dict[str, Any], service_ids: List[str]) -> bool:
    if not isinstance(item, dict):
        return False
    tokens = [
        str(agent.get("agent_id") or "").strip(),
        str(agent.get("node_id") or "").strip(),
        str(agent.get("device_id") or "").strip(),
        str(agent.get("host_ip") or "").strip(),
        str(agent.get("host_name") or "").strip(),
    ] + [str(x or "").strip() for x in (service_ids or [])]
    tokens = [x for x in tokens if x]
    if not tokens:
        return False
    direct_keys = ("agent_id", "node_id", "device_id", "host_ip", "service_id")
    for key in direct_keys:
        value = str(item.get(key) or "").strip()
        if value and value in tokens:
            return True
    for token in tokens:
        if _value_contains_token(item, token):
            return True
    return False

def _parse_agent_detail_include(raw: str) -> set:
    text = str(raw or "all").strip().lower()
    if not text or text == "all":
        return {"all"}
    return {part.strip() for part in text.split(",") if part.strip()}

def _agent_detail_include_wants(include_set: set, section: str) -> bool:
    return "all" in include_set or str(section or "").strip().lower() in include_set

def _build_agent_metric_series(agent: Dict[str, Any], member_agent_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    ids = [str(x or "").strip() for x in (member_agent_ids or []) if str(x or "").strip()]
    primary_agent_id = str(agent.get("agent_id") or "").strip()
    if primary_agent_id and primary_agent_id not in ids:
        ids.insert(0, primary_agent_id)
    points = _realtime_metric_points(ids)
    cleaned = [{k: v for k, v in point.items() if k != "_ts"} for point in points]
    return {
        "window": "1h",
        "points": cleaned,
        "cpu_percent": [{"time": p["time"], "value": p.get("cpu_percent")} for p in cleaned if p.get("cpu_percent") is not None],
        "mem_percent": [{"time": p["time"], "value": p.get("mem_percent")} for p in cleaned if p.get("mem_percent") is not None],
        "disk_percent": [{"time": p["time"], "value": p.get("disk_percent")} for p in cleaned if p.get("disk_percent") is not None],
        "has_history": len(cleaned) > 1,
        "source": "runtime.sample",
    }

def _build_agent_detail(
    project_id: str,
    agent_id: str,
    *,
    include: str = "all",
    force_live: bool = False,
) -> Optional[Dict[str, Any]]:
    target_agent_id = str(agent_id or "").strip()
    if not target_agent_id:
        return None
    logical_agents = _logical_agents_for_project(project_id)
    logical_hit = next(
        (
            item for item in logical_agents
            if str(item.get("agent_id") or "").strip() == target_agent_id
            or target_agent_id in [str(x or "").strip() for x in (item.get("member_agent_ids") or [])]
        ),
        None,
    )
    if not logical_hit:
        return None
    reg = _load_agent_registry_v2()
    primary_agent_id = str(logical_hit.get("agent_id") or "").strip()
    hit = reg.get(primary_agent_id) if isinstance(reg.get(primary_agent_id), dict) else {}
    agent = dict(logical_hit)
    if project_id and str(agent.get("project_id") or "").strip() and str(agent.get("project_id") or "").strip() != project_id:
        return None

    with _probe_cache_lock:
        cached_probe = dict(_probe_cache)
    cached_pr = cached_probe.get(primary_agent_id)
    if cached_pr:
        agent["effective_status"] = cached_pr.get("effective_status", agent.get("status") or "UNKNOWN")
        agent["probe_status"] = "PASS" if cached_pr.get("ok") else "FAIL"
        agent["probe_rtt_ms"] = cached_pr.get("rtt_ms", 0.0)
        agent["probe_at"] = str(cached_pr.get("probe_at") or "")
        if isinstance(cached_pr.get("metrics"), dict):
            base_m = agent.get("metrics") if isinstance(agent.get("metrics"), dict) else {}
            control = base_m.get("control") if isinstance(base_m.get("control"), dict) else base_m
            business = base_m.get("business") if isinstance(base_m.get("business"), dict) else {}
            pr_m = cached_pr.get("metrics") or {}
            merged = dict(control)
            for key in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"):
                if merged.get(key) is None and pr_m.get(key) is not None:
                    merged[key] = pr_m.get(key)
            if not merged.get("updated_at"):
                merged["updated_at"] = str(pr_m.get("updated_at") or "")
            if not merged.get("source"):
                merged["source"] = str(pr_m.get("source") or "agent")
            agent["metrics"] = {"control": merged, "business": business, **merged}
            agent["metrics_live"] = True
    else:
        agent["effective_status"] = str(agent.get("status") or "UNKNOWN").upper()

    include_set = _parse_agent_detail_include(include)
    want_core = _agent_detail_include_wants(include_set, "core")
    want_metrics = _agent_detail_include_wants(include_set, "metrics") or _agent_detail_include_wants(include_set, "core")
    want_jobs = _agent_detail_include_wants(include_set, "jobs")
    want_events = _agent_detail_include_wants(include_set, "events")
    want_audits = _agent_detail_include_wants(include_set, "audits")
    want_config = _agent_detail_include_wants(include_set, "config")
    want_node = _agent_detail_include_wants(include_set, "node")

    services = [dict(s) for s in (logical_hit.get("services") or []) if isinstance(s, dict)]
    services_from_cache = _should_use_cached_service_state(services, force_live=force_live)
    has_embedded = any(_is_embedded_cluster_service(s) for s in services)
    if force_live:
        _reconcile_all_gameserver_daemon_states()
    cluster_status_map = _fetch_cluster_runtime_status_cached()
    if not services_from_cache:
        services = _refresh_services_live_state(
            services,
            project_id=project_id,
            agent=agent,
            cluster_status=cluster_status_map,
            fast_probe=bool(force_live or has_embedded),
            probe_timeout=0.12 if (force_live or has_embedded) else 0.35,
        )
    service_ids = [str(s.get("service_id") or "").strip() for s in services if str(s.get("service_id") or "").strip()]
    member_agent_ids = [str(x or "").strip() for x in (logical_hit.get("member_agent_ids") or []) if str(x or "").strip()]
    member_node_ids = [str(x or "").strip() for x in (logical_hit.get("member_node_ids") or []) if str(x or "").strip()]
    if want_metrics or _agent_detail_include_wants(include_set, "all"):
        _ensure_agent_metrics_live(agent, member_agent_ids)
    elif not cached_pr:
        agent["metrics_live"] = False
    services = _apply_service_metrics_from_agent(services, agent)
    node_id = str(agent.get("node_id") or (member_node_ids[0] if member_node_ids else "")).strip()
    node = _resolve_ops_dispatch_node(project_id, node_id) if want_node or _agent_detail_include_wants(include_set, "all") else {}

    jobs: List[Dict[str, Any]] = []
    jobs_all = _load_agent_jobs() if want_jobs or _agent_detail_include_wants(include_set, "all") else []
    for item in reversed(jobs_all):
        if not isinstance(item, dict):
            continue
        if member_node_ids and str(item.get("node_id") or "").strip() not in member_node_ids:
            continue
        jobs.append(item)
        if len(jobs) >= 30:
            break

    events_merged: List[Dict[str, Any]] = []
    if want_events or _agent_detail_include_wants(include_set, "all"):
        snapshot = _load_json_config(OPS_ALERT_SNAPSHOT_KEY, {})
        alerts = snapshot.get("alerts") if isinstance(snapshot, dict) and isinstance(snapshot.get("alerts"), list) else []
        event_rows = _load_json_config(OPS_EVENT_LOG_KEY, [])
        events_merged.extend([x for x in alerts if isinstance(x, dict)])
        events_merged.extend([x for x in event_rows if isinstance(x, dict)])
        events_merged.sort(key=lambda x: str(x.get("time") or ""), reverse=True)

    scope_tokens = {
        str(agent.get("agent_id") or "").strip(),
        str(agent.get("device_id") or "").strip(),
        str(agent.get("host_ip") or "").strip(),
        str(agent.get("host_name") or "").strip(),
        *member_agent_ids,
        *member_node_ids,
        *service_ids,
    }
    scope_tokens = {x for x in scope_tokens if x}

    def _matches_logical_scope(item: Dict[str, Any]) -> bool:
        if not isinstance(item, dict):
            return False
        for key in ("agent_id", "node_id", "device_id", "host_ip", "service_id", "target", "desired_service_id", "desired_server_id"):
            value = str(item.get(key) or "").strip()
            if value and value in scope_tokens:
                return True
        for token in scope_tokens:
            if _value_contains_token(item, token):
                return True
        return False

    events: List[Dict[str, Any]] = []
    if want_events or _agent_detail_include_wants(include_set, "all"):
        events = [x for x in events_merged if _matches_logical_scope(x)][:30]

    traces: List[Dict[str, Any]] = []
    if want_events or _agent_detail_include_wants(include_set, "all"):
        traces_raw = _load_json_config(OPS_TRACE_LOG_KEY, [])
        traces = [x for x in traces_raw if isinstance(x, dict) and _matches_logical_scope(x)][:30]

    audits: List[Dict[str, Any]] = []
    if want_audits or _agent_detail_include_wants(include_set, "all"):
        for item in reversed(audit_log_db if isinstance(audit_log_db, list) else []):
            if not isinstance(item, dict):
                continue
            if _matches_logical_scope(item):
                audits.append(item)
            if len(audits) >= 40:
                break

    control_metrics = ((agent.get("metrics") or {}).get("control") if isinstance(agent.get("metrics"), dict) else {}) or {}
    service_summary = {"total": len(services), "online": 0, "stopped": 0, "abnormal": 0}
    for svc in services:
        eff = _effective_runtime_status(svc.get("status"), svc.get("run_state"), svc.get("probe_status"))
        run = str(svc.get("run_state") or "").upper()
        st = str(svc.get("status") or "").upper()
        if eff in ("ONLINE", "RUNNING", "READY"):
            service_summary["online"] += 1
        elif eff == "STOPPED" or run in ("STOPPED", "STOP") or st == "STOPPED":
            service_summary["stopped"] += 1
        elif eff in ("DEGRADED", "ERROR", "FAILED", "OFFLINE"):
            service_summary["abnormal"] += 1
        else:
            service_summary["stopped"] += 1

    current_alerts = len([x for x in events if str(x.get("status") or "").lower() not in ("resolved", "closed", "done", "recovered")])
    healthy_ratio = 100
    if service_summary["total"]:
        healthy_ratio = int(round((service_summary["online"] / max(1, service_summary["total"])) * 100))
    elif str(agent.get("effective_status") or "").upper() not in ("ONLINE", "RUNNING", "READY"):
        healthy_ratio = 0

    with _probe_cache_lock:
        cache_ts = float(_probe_cache_ts or 0.0)
    probe_cache_age_sec = round(max(0.0, _time_mod.time() - cache_ts), 1) if cache_ts > 0 else None

    detail: Dict[str, Any] = {
        "agent": agent,
        "services": services,
        "member_agent_ids": member_agent_ids,
        "member_node_ids": member_node_ids,
        "service_summary": service_summary,
        "overview": {
            "status": str(agent.get("effective_status") or agent.get("status") or "UNKNOWN").upper(),
            "healthy_ratio": healthy_ratio,
            "cpu_percent": control_metrics.get("cpu_percent"),
            "mem_percent": control_metrics.get("mem_percent"),
            "disk_percent": control_metrics.get("disk_percent"),
            "current_alerts": current_alerts,
            "resolved_alerts": len([x for x in events if str(x.get("status") or "").lower() in ("resolved", "closed", "done", "recovered")]),
            "recent_tasks": len(jobs),
            "audit_count": len(audits),
        },
        "actions": {
            "can_edit": True,
            "can_probe": True,
            "can_restart_agent": bool(primary_agent_id or member_agent_ids or member_node_ids),
            "can_restart_services": bool(services),
        },
        "meta": {
            "include": sorted(include_set),
            "force_live": bool(force_live),
            "services_from_cache": bool(services_from_cache),
            "probe_cache_age_sec": probe_cache_age_sec,
        },
    }
    if want_node or _agent_detail_include_wants(include_set, "all"):
        detail["node"] = node or {}
    if want_jobs or _agent_detail_include_wants(include_set, "all"):
        detail["jobs"] = jobs
    if want_events or _agent_detail_include_wants(include_set, "all"):
        detail["events"] = events
        detail["traces"] = traces
    if want_audits or _agent_detail_include_wants(include_set, "all"):
        detail["audits"] = audits
    if want_metrics or _agent_detail_include_wants(include_set, "all"):
        detail["metrics_history"] = _build_agent_metric_series(agent, member_agent_ids)
    if want_config or _agent_detail_include_wants(include_set, "all"):
        detail["config"] = {
            "policy": _load_agent_policy(),
            "transport": hit.get("transport") if isinstance(hit.get("transport"), dict) else {},
            "network": hit.get("network") if isinstance(hit.get("network"), dict) else {},
            "capabilities": hit.get("capabilities") if isinstance(hit.get("capabilities"), list) else [],
            "services": [{"service_id": s.get("service_id"), "service_type": s.get("service_type"), "network": s.get("network"), "endpoints": s.get("endpoints")} for s in services],
        }
    return detail

def _sample_local_control_metrics() -> Dict[str, Any]:
    now = _now_iso()
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        if cpu is None or (isinstance(cpu, float) and cpu <= 0.0):
            cpu = psutil.cpu_percent(interval=0.05)
        disk_pct = None
        try:
            disk_pct = round(float(psutil.disk_usage("/").percent), 1)
        except Exception:
            disk_pct = None
        return {
            "cpu_percent": round(float(cpu or 0.0), 1),
            "mem_percent": round(float(psutil.virtual_memory().percent), 1),
            "disk_percent": disk_pct,
            "source": "runtime.sample",
            "updated_at": now,
        }
    except Exception:
        pass
    sample = _fallback_local_control_metrics()
    if any(sample.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent")):
        return sample
    return {"source": "runtime.sample", "updated_at": now}

def _inject_live_control_metrics(item: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    probe = str(item.get("probe_status") or "").upper()
    if probe == "FAIL":
        item["metrics_live"] = False
        return item
    sample = _sample_local_control_metrics()
    base = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    control = base.get("control") if isinstance(base.get("control"), dict) else dict(base)
    business = base.get("business") if isinstance(base.get("business"), dict) else {}
    merged = dict(control)
    for key in ("cpu_percent", "mem_percent", "disk_percent", "source", "updated_at"):
        if sample.get(key) is not None:
            merged[key] = sample.get(key)
    for key in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"):
        if merged.get(key) is None and control.get(key) is not None:
            merged[key] = control.get(key)
    item["metrics"] = {**merged, "control": merged, "business": business}
    item["metrics_live"] = True
    return item
