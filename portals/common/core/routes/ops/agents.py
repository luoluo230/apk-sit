# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
from routes.ops import deps as ops_helpers
from routes.ops import bp

@bp.route("/api/ops-platform/agents/stream")
@admin_required("gm_ops")
def ops_platform_agents_stream():
    """SSE 推送端点：前端用 EventSource 订阅，状态变化时推送完整 payload。"""
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    ops_helpers._ensure_probe_bg_started()

    q: _queue_mod.Queue = _queue_mod.Queue(maxsize=64)
    with ops_helpers._sse_sub_lock:
        ops_helpers._sse_subscribers.append(q)

    def _generate():
        # 先推一次全量快照
        snap = None
        try:
            with ops_helpers._probe_cache_lock:
                snap = ops_helpers._build_sse_payload(
                    ops_helpers._probe_cache_agents, ops_helpers._probe_cache
                ) if ops_helpers._probe_cache_agents else None
        except Exception as exc:
            import logging
            logging.getLogger("ops.agent_stream").warning("build initial SSE payload failed: %s", exc, exc_info=True)
        if snap:
            yield f"event: full\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n"

        # 后续增量推送
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"event: change\ndata: {msg}\n\n"
                except _queue_mod.Empty:
                    # 心跳：30s 无变化也推一次，防止连接超时
                    yield f": heartbeat {int(ops_helpers._time_mod.time())}\n\n"
        finally:
            with ops_helpers._sse_sub_lock:
                try:
                    ops_helpers._sse_subscribers.remove(q)
                except ValueError:
                    pass

    from flask import Response
    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )








































































@bp.route("/api/ops-platform/agents")
@admin_required("gm_ops")
def ops_platform_agents_list():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    ops_helpers._ensure_probe_bg_started()
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    force_live = str(request.args.get("live") or "").strip().lower() in ("1", "true", "yes", "on")
    status = str(request.args.get("status") or "").strip().upper()
    device_id = str(request.args.get("device_id") or "").strip()
    host_ip = str(request.args.get("host_ip") or "").strip().lower()
    region = str(request.args.get("region") or "").strip().lower()
    bound = str(request.args.get("bound") or "").strip().lower()
    resolved_bindings = ops_helpers._resolve_scope_agent_bindings_for_scope(topology_id, project_id, env_key)
    resolved_service_bindings = ops_helpers._resolve_scope_service_bindings_for_scope(topology_id, project_id, env_key)
    rows = ops_helpers._logical_agents_for_project(project_id, env_key)
    # Agent is a project-owned infrastructure asset. When the selected
    # environment has no dedicated registration, still expose project agents
    # so operators can bind them instead of presenting a contradictory empty
    # inventory while topology actions can already use the same Agent.
    if project_id and not rows:
        rows = ops_helpers._logical_agents_for_project(project_id)
        for row in rows:
            if isinstance(row, dict):
                row["scope_status"] = "available_for_binding"
                row["selected_env_key"] = env_key
    rows = [r for r in rows if not r.get("stale")]
    cluster_status_map: Dict[str, str] = {}
    if project_id and ops_helpers._project_uses_runtime_topology(project_id):
        try:
            if force_live and topology_id:
                cluster_status_map = {}
            elif force_live:
                cluster_status_map = ops_helpers._fetch_cluster_runtime_status(rows)
            else:
                cluster_status_map = ops_helpers._fetch_cluster_runtime_status_cached(rows)
        except Exception:
            cluster_status_map = {}
    bound_agent_ids = set(str(v or "") for v in resolved_bindings.values() if str(v or "").strip())
        # 走缓存：不再每次请求都探活，用后台引擎缓存结果
    with ops_helpers._probe_cache_lock:
        cached_probe = dict(ops_helpers._probe_cache)
    # 指标也走探活缓存（而不是 registry 里的旧 metrics）
    # device_snap = ops_helpers._device_metrics_snapshot(rows)  # 旧逻辑
    now_ts = datetime.utcnow().timestamp()
    out: List[Dict[str, Any]] = []
    for item in rows:
        if device_id and str(item.get("device_id") or "") != device_id:
            continue
        host_name = str(item.get("host_name") or "").lower()
        item_host_ip = str(item.get("host_ip") or item.get("host_name") or "").lower()
        if host_ip and host_ip not in host_name and host_ip not in str(item.get("device_id") or "").lower() and host_ip not in item_host_ip:
            continue
        if region and region != str(item.get("region") or "").lower():
            continue
        member_agent_ids = [str(x or "").strip() for x in (item.get("member_agent_ids") or []) if str(x or "").strip()]
        is_bound = any(agent_id in bound_agent_ids for agent_id in member_agent_ids) or str(item.get("agent_id") or "") in bound_agent_ids
        if bound == "yes" and not is_bound:
            continue
        if bound == "no" and is_bound:
            continue
        obj = dict(item)
        did = str(obj.get("device_id") or "unknown-device")
        # Agent heartbeat metrics are canonical. Probe metrics only fill missing values.
        aid = str(obj.get("agent_id") or "")
        cached_pr = cached_probe.get(aid)
        base_m = obj.get("metrics") if isinstance(obj.get("metrics"), dict) else {}
        base_c = base_m.get("control") if isinstance(base_m.get("control"), dict) else base_m
        base_b = base_m.get("business") if isinstance(base_m.get("business"), dict) else {}
        if cached_pr and isinstance(cached_pr.get("metrics"), dict):
            pr_m = cached_pr.get("metrics") or {}
            pr_c = pr_m.get("control") if isinstance(pr_m.get("control"), dict) else pr_m
            merged = {
                "cpu_percent": base_c.get("cpu_percent") if base_c.get("cpu_percent") is not None else pr_c.get("cpu_percent"),
                "mem_percent": base_c.get("mem_percent") if base_c.get("mem_percent") is not None else pr_c.get("mem_percent"),
                "disk_percent": base_c.get("disk_percent") if base_c.get("disk_percent") is not None else pr_c.get("disk_percent"),
                "qps": base_c.get("qps") if base_c.get("qps") is not None else pr_c.get("qps"),
                "rtt_ms": base_c.get("rtt_ms") if base_c.get("rtt_ms") is not None else pr_c.get("rtt_ms"),
                "service_cpu_percent": base_c.get("service_cpu_percent") if base_c.get("service_cpu_percent") is not None else pr_c.get("service_cpu_percent"),
                "service_memory_mb": base_c.get("service_memory_mb") if base_c.get("service_memory_mb") is not None else pr_c.get("service_memory_mb"),
                "updated_at": str(base_c.get("updated_at") or pr_c.get("updated_at") or ops_helpers._now_iso()),
                "source": str(base_c.get("source") or pr_c.get("source") or "agent"),
            }
            obj["metrics"] = {
                "control": merged,
                "business": base_b,
                **merged,
            }
            obj["metrics_live"] = True
            obj["metrics_missing"] = {"control": not any(merged.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")), "business": not any(base_b.get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"))}
        else:
            obj["metrics"] = {"control": base_c, "business": base_b, **base_c}
            obj["metrics_live"] = bool(obj.get("metrics_live"))
            obj["metrics_missing"] = {"control": not any(base_c.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")), "business": not any(base_b.get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"))}
        obj["device_metrics_snapshot"] = {}
        last_seen_raw = str(obj.get("last_seen") or "")
        try:
            last_seen_ts = datetime.fromisoformat(last_seen_raw.replace("Z", "")).timestamp()
            obj["last_seen_age_sec"] = max(0, int(now_ts - last_seen_ts))
        except Exception:
            obj["last_seen_age_sec"] = None
        obj["is_bound"] = is_bound
        obj["topology_group"] = str(obj.get("node_id") or "ungrouped").split("-", 1)[0]
        obj["placement"] = {
            "region": str(obj.get("region") or ""),
            "zone": str(obj.get("zone") or ""),
            "host_ip": str(obj.get("host_ip") or obj.get("host_name") or ""),
            "device_id": str(obj.get("device_id") or ""),
        }
        svc_rows = obj.get("services") if isinstance(obj.get("services"), list) else []
        if svc_rows:
            has_embedded = any(ops_helpers._is_embedded_cluster_service(s) for s in svc_rows if isinstance(s, dict))
            use_cached_services = (not force_live) and ops_helpers._should_use_cached_service_state(svc_rows, force_live=False)
            if use_cached_services:
                obj["services"] = svc_rows
            else:
                obj["services"] = ops_helpers._refresh_services_live_state(
                    svc_rows,
                    project_id=project_id,
                    cluster_status=cluster_status_map,
                    agent=obj,
                    fast_probe=bool(force_live or has_embedded),
                    probe_timeout=0.08 if (force_live or has_embedded) else 0.35,
                )
        if force_live:
            eff, probe = ops_helpers._derive_agent_probe_from_services(obj.get("services") or [])
            obj["effective_status"] = eff
            obj["probe_status"] = probe
            obj["probe_rtt_ms"] = float(cached_pr.get("rtt_ms") or 0.0) if cached_pr else 0.0
            obj["probe_at"] = ops_helpers._now_iso()
            obj["probe_source"] = "live-request"
        elif cached_pr:
            obj["effective_status"] = cached_pr.get("effective_status", "UNKNOWN")
            obj["probe_status"] = "PASS" if cached_pr.get("ok") else "FAIL"
            obj["probe_rtt_ms"] = cached_pr.get("rtt_ms", 0.0)
            obj["probe_at"] = str(cached_pr.get("probe_at") or "")
            obj["probe_source"] = "bg-engine"
        else:
            base_status = str(obj.get("status") or "UNKNOWN").upper()
            age_sec = obj.get("last_seen_age_sec")
            if age_sec is None:
                obj["effective_status"] = "UNKNOWN"
            elif age_sec > 300:
                obj["effective_status"] = "OFFLINE"
            else:
                obj["effective_status"] = base_status
            obj["probe_status"] = str(obj.get("probe_status") or ("PASS" if base_status in ("ONLINE", "RUNNING", "READY") else "FAIL")).upper()
            obj["probe_source"] = "registry-fallback"
        if status and str(obj.get("effective_status") or "").upper() != status:
            continue
        out.append(obj)
    # 同设备统一快照：同一 device_id 下所有卡片显示一致口径
    grouped_snap: Dict[str, Dict[str, Any]] = {}
    for a in out:
        did = str(a.get("device_id") or "unknown-device")
        m = a.get("metrics") if isinstance(a.get("metrics"), dict) else {}
        mc = m.get("control") if isinstance(m.get("control"), dict) else m
        mb = m.get("business") if isinstance(m.get("business"), dict) else {}
        snap = grouped_snap.get(did) if isinstance(grouped_snap.get(did), dict) else {
            "control": {"cpu_percent": None, "mem_percent": None, "disk_percent": None, "qps": None, "rtt_ms": None, "updated_at": "", "source": "missing"},
            "business": {"qps": None, "rtt_p95_ms": None, "rtt_p99_ms": None, "error_rate": None, "conn": None, "updated_at": "", "source": "missing"},
            "updated_at": "", "source": "missing"
        }
        for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"):
            if mc.get(k) is not None:
                snap["control"][k] = mc.get(k)
        for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"):
            if mb.get(k) is not None:
                snap["business"][k] = mb.get(k)
        if mc.get("updated_at"):
            snap["control"]["updated_at"] = str(mc.get("updated_at"))
            snap["updated_at"] = str(mc.get("updated_at"))
        if mc.get("source"):
            snap["control"]["source"] = str(mc.get("source"))
            snap["source"] = str(mc.get("source"))
        if mb.get("updated_at"):
            snap["business"]["updated_at"] = str(mb.get("updated_at"))
        if mb.get("source"):
            snap["business"]["source"] = str(mb.get("source"))
        grouped_snap[did] = snap
    for idx, a in enumerate(out):
        did = str(a.get("device_id") or "unknown-device")
        snap = grouped_snap.get(did) or {}
        a["device_metrics_snapshot"] = snap
        # Keep per-agent heartbeat metrics as the card truth.
        # Device snapshot is for group header only and must not overwrite agent values.
        m = a.get("metrics") if isinstance(a.get("metrics"), dict) else {}
        mc = m.get("control") if isinstance(m.get("control"), dict) else m
        mb = m.get("business") if isinstance(m.get("business"), dict) else {}
        a["metrics"] = {**mc, "control": mc, "business": mb}
        a["metrics_missing"] = {
            "control": not any(mc.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")),
            "business": not any(mb.get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn")),
        }
        member_ids = [str(x or "").strip() for x in (a.get("member_agent_ids") or []) if str(x or "").strip()]
        if not topology_id:
            out[idx] = ops_helpers._overlay_live_metrics(a, member_ids or [str(a.get("agent_id") or "")])
    return jsonify({
        "ok": True,
        "count": len(out),
        "agents": out,
        "bindings": resolved_bindings,
        "service_bindings": resolved_service_bindings,
        "force_live": bool(force_live),
    })



@bp.route("/api/ops-platform/agents/devices")
@admin_required("gm_ops")
def ops_platform_agents_devices():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    ops_helpers._ensure_probe_bg_started()
    project_id = str(request.args.get("project_id") or "").strip()
    rows = ops_helpers._agents_v2_for_project(project_id)
    rows = [r for r in rows if not r.get("stale")]
    # 走缓存
    with ops_helpers._probe_cache_lock:
        cached_probe = dict(ops_helpers._probe_cache)
    grouped: Dict[str, Dict[str, Any]] = {}
    now_ts = datetime.utcnow().timestamp()
    for item in rows:
        did = str(item.get("device_id") or "unknown-device")
        cur = grouped.get(did) if isinstance(grouped.get(did), dict) else {"device_id": did, "project_id": project_id, "agents": [], "online": 0, "total": 0}
        obj = dict(item)
        age_sec = None
        try:
            last_seen_ts = datetime.fromisoformat(str(obj.get("last_seen") or "").replace("Z", "")).timestamp()
            age_sec = max(0, int(now_ts - last_seen_ts))
        except Exception:
            age_sec = None
        obj["last_seen_age_sec"] = age_sec
        # 走缓存
        aid = str(obj.get("agent_id") or "")
        cached_pr = cached_probe.get(aid)
        if cached_pr:
            obj["effective_status"] = cached_pr.get("effective_status", "UNKNOWN")
            obj["probe_status"] = "PASS" if cached_pr.get("ok") else "FAIL"
            obj["probe_rtt_ms"] = cached_pr.get("rtt_ms", 0.0)
            obj["probe_at"] = str(cached_pr.get("probe_at") or "")
            obj["probe_source"] = "bg-engine"
            if isinstance(cached_pr.get("metrics"), dict):
                base_m = obj.get("metrics") if isinstance(obj.get("metrics"), dict) else {}
                pr_m = cached_pr.get("metrics") or {}
                merged = dict(base_m)
                for key in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"):
                    if merged.get(key) is None and pr_m.get(key) is not None:
                        merged[key] = pr_m.get(key)
                if not merged.get("updated_at"):
                    merged["updated_at"] = str(pr_m.get("updated_at") or "")
                if not merged.get("source"):
                    merged["source"] = str(pr_m.get("source") or "agent")
                obj["metrics"] = merged
        else:
            base_status = str(obj.get("status") or "UNKNOWN").upper()
            if age_sec is None:
                obj["effective_status"] = "UNKNOWN"
            elif age_sec > 300:
                obj["effective_status"] = "OFFLINE"
            else:
                obj["effective_status"] = base_status
            obj["probe_source"] = "fallback"
        obj["topology_group"] = str(obj.get("node_id") or "ungrouped").split("-", 1)[0]
        obj["placement"] = {
            "region": str(obj.get("region") or ""),
            "zone": str(obj.get("zone") or ""),
            "host_ip": str(obj.get("host_ip") or obj.get("host_name") or ""),
            "device_id": str(obj.get("device_id") or ""),
        }
        cur["agents"].append(obj)
        cur["total"] = int(cur.get("total") or 0) + 1
        if str(obj.get("effective_status") or "").upper() in ("ONLINE", "READY", "RUNNING"):
            cur["online"] = int(cur.get("online") or 0) + 1
        grouped[did] = cur
    out = list(grouped.values())
    for g in out:
        # 设备快照统一按同 device_id 聚合，避免卡片字段缺失/不一致
        snap = {
            "control": {"cpu_percent": None, "mem_percent": None, "disk_percent": None, "qps": None, "rtt_ms": None, "updated_at": "", "source": "missing"},
            "business": {"qps": None, "rtt_p95_ms": None, "rtt_p99_ms": None, "error_rate": None, "conn": None, "updated_at": "", "source": "missing"},
            "updated_at": "",
            "source": "missing",
        }
        for a in (g.get("agents") if isinstance(g.get("agents"), list) else []):
            m = a.get("metrics") if isinstance(a.get("metrics"), dict) else {}
            mc = m.get("control") if isinstance(m.get("control"), dict) else m
            mb = m.get("business") if isinstance(m.get("business"), dict) else {}
            for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"):
                if mc.get(k) is not None:
                    snap["control"][k] = mc.get(k)
            for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"):
                if mb.get(k) is not None:
                    snap["business"][k] = mb.get(k)
            if mc.get("updated_at"):
                snap["control"]["updated_at"] = str(mc.get("updated_at"))
                snap["updated_at"] = str(mc.get("updated_at"))
            if mc.get("source"):
                snap["control"]["source"] = str(mc.get("source"))
                snap["source"] = str(mc.get("source"))
            if mb.get("updated_at"):
                snap["business"]["updated_at"] = str(mb.get("updated_at"))
            if mb.get("source"):
                snap["business"]["source"] = str(mb.get("source"))
        snap["metrics_missing"] = {
            "control": not any((snap["control"]).get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")),
            "business": not any((snap["business"]).get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn")),
        }
        g["device_metrics_snapshot"] = snap
    out.sort(key=lambda x: str(x.get("device_id") or ""))
    return jsonify({"ok": True, "count": len(out), "devices": out})



@bp.route("/api/ops-platform/agents/upsert", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_upsert():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    agent_id = str(payload.get("agent_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    reg = ops_helpers._load_agent_registry_v2()
    hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else {}
    create_if_missing = bool(payload.get("create_if_missing"))
    if not hit:
        if not create_if_missing:
            return jsonify({"ok": False, "error": "agent_not_found"}), 404
        now = ops_helpers._now_iso()
        hit = {
            "agent_id": agent_id,
            "node_id": str(payload.get("node_id") or ""),
            "device_id": str(payload.get("device_id") or payload.get("host_name") or "unknown-device"),
            "host_name": str(payload.get("host_name") or ""),
            "project_id": str(payload.get("project_id") or ""),
            "status": str(payload.get("status") or "ONLINE"),
            "version": str(payload.get("version") or ""),
            "last_seen": now,
            "display_name": str(payload.get("display_name") or agent_id),
            "port": int(payload.get("port") or 0),
            "remote_game_server_port": int(payload.get("remote_game_server_port") or payload.get("port") or 0),
            "desc": str(payload.get("desc") or ""),
            "run_state": str(payload.get("run_state") or "ONLINE"),
            "region": str(payload.get("region") or ""),
            "zone": str(payload.get("zone") or ""),
            "rack": str(payload.get("rack") or ""),
            "host_ip": str(payload.get("host_ip") or payload.get("host_name") or ""),
            "probe_status": "",
            "probe_at": "",
            "probe_rtt_ms": 0.0,
            "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else [],
            "service_id": str(payload.get("service_id") or ""),
            "services": payload.get("services") if isinstance(payload.get("services"), list) else [],
            "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            "network": payload.get("network") if isinstance(payload.get("network"), dict) else {"endpoints": []},
            "updated_at": now,
            "transport": {"mode": "remote", "local_bus": {"enabled": False, "endpoint": "", "auth_mode": "token"}},
        }
    if "port" in payload:
        try:
            port_val = int(payload.get("port") or 0)
            if port_val < 0 or port_val > 65535:
                return jsonify({"ok": False, "error": "OPS_AGENT_PORT_INVALID", "error_code": "OPS_AGENT_PORT_INVALID"}), 400
            hit["port"] = port_val
        except Exception:
            return jsonify({"ok": False, "error": "OPS_AGENT_PORT_INVALID", "error_code": "OPS_AGENT_PORT_INVALID"}), 400
    for k in ("host_name", "device_id", "project_id", "node_id", "region", "zone", "rack", "host_ip"):
        if k in payload:
            hit[k] = str(payload.get(k) or "")
    if "remote_game_server_port" in payload:
        try:
            rgp = int(payload.get("remote_game_server_port") or 0)
            if rgp < 0 or rgp > 65535:
                return jsonify({"ok": False, "error": "OPS_AGENT_PORT_INVALID", "error_code": "OPS_AGENT_PORT_INVALID"}), 400
            hit["remote_game_server_port"] = rgp
        except Exception:
            return jsonify({"ok": False, "error": "OPS_AGENT_PORT_INVALID", "error_code": "OPS_AGENT_PORT_INVALID"}), 400
    if "network" in payload and isinstance(payload.get("network"), dict):
        hit["network"] = payload.get("network")
    for k in ("display_name", "desc", "run_state", "status"):
        if k in payload:
            hit[k] = str(payload.get(k) or "")
    hit["updated_at"] = ops_helpers._now_iso()
    reg[agent_id] = ops_helpers._normalize_agent_descriptor_v2(hit)
    ops_helpers._save_agent_registry_v2(reg)
    log_audit("ops_platform_agents_upsert", f"agent_id={agent_id}")
    return jsonify({"ok": True, "agent": reg[agent_id]})



@bp.route("/api/ops-platform/agents/probe", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_probe():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    agent_id = str(payload.get("agent_id") or "").strip()
    host = str(payload.get("host_name") or payload.get("ip") or "").strip()
    port_raw = payload.get("port")
    try:
        port = int(port_raw or 0)
    except Exception:
        port = 0
    if not host or port <= 0 or port > 65535:
        return jsonify({"ok": False, "error": "invalid_host_or_port", "message": "请提供有效的 IP 和端口"}), 400
    timeout_sec = 2.0
    start = datetime.utcnow()
    ok = False
    err = ""
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            ok = True
    except Exception as ex:
        err = str(ex)
    spent = max(0.0, (datetime.utcnow() - start).total_seconds() * 1000.0)
    out = {
            "ok": ok,
            "host_name": host,
            "port": port,
            "rtt_ms": round(spent, 1),
            "message": ("连通性正常" if ok else ("连通性失败: " + (err or "unknown"))),
            "error": ("" if ok else err),
        }
    if agent_id:
        reg = ops_helpers._load_agent_registry_v2()
        hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
        if hit:
            hit["probe_status"] = "PASS" if ok else "FAIL"
            hit["probe_at"] = ops_helpers._now_iso()
            hit["probe_rtt_ms"] = round(spent, 1)
            hit["updated_at"] = ops_helpers._now_iso()
            reg[agent_id] = ops_helpers._normalize_agent_descriptor_v2(hit)
            ops_helpers._save_agent_registry_v2(reg)
            out["agent_id"] = agent_id
            out["probe_status"] = hit["probe_status"]
    return jsonify(
        {
            **out
        }
    )



@bp.route("/api/ops-platform/agents/restart", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_restart():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400

    detail = ops_helpers._build_agent_detail(project_id, agent_id)
    if not detail:
        return jsonify({"ok": False, "error": "agent_not_found", "error_code": "OPS_AGENT_NOT_FOUND"}), 404

    agent = detail.get("agent") if isinstance(detail.get("agent"), dict) else {}
    member_node_ids = [str(x or "").strip() for x in (detail.get("member_node_ids") or []) if str(x or "").strip()]
    dispatch_node_id = str(agent.get("node_id") or (member_node_ids[0] if member_node_ids else "")).strip()
    if not dispatch_node_id:
        return jsonify({"ok": False, "error": "missing_dispatch_node_id", "error_code": "OPS_AGENT_DISPATCH_NODE_MISSING"}), 400

    node = ops_helpers._resolve_ops_dispatch_node(project_id, dispatch_node_id)
    if not node:
        return jsonify({"ok": False, "error": "dispatch_node_not_found", "error_code": "OPS_AGENT_DISPATCH_NODE_MISSING"}), 404

    primary_agent_id = str(agent.get("agent_id") or agent_id).strip()
    req = {
        "node_id": dispatch_node_id,
        "action_type": "restart",
        "target": primary_agent_id or dispatch_node_id,
        "ticket_id": "OPS-AGENT-" + uuid.uuid4().hex[:8],
        "reason": "Agent 进程重启",
        "approver": str(session.get("user") or "admin"),
        "run_mode": "agent",
        "via_agent": True,
        "agent_id": primary_agent_id,
        "payload": {
            "run_mode": "agent",
            "desired_role": "agent",
            "desired_agent_id": primary_agent_id,
            "desired_service_id": "",
            "desired_server_id": "",
            "restart_current_agent": True,
            "launch_visible_console": bool(payload.get("launch_visible_console", True)),
        },
    }
    validation = ops_helpers._validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing") or []}), 400

    result = ops_helpers._execute_validated(req, node, validation)
    if not result.get("ok"):
        return jsonify(
            {
                "ok": False,
                "error": "OPS_AGENT_RESTART_FAILED",
                "error_code": "OPS_AGENT_RESTART_FAILED",
                "message": str(result.get("message") or result.get("error") or "agent restart failed"),
            }
        ), 502
    return jsonify(
        {
            "ok": True,
            "agent_id": primary_agent_id,
            "node_id": dispatch_node_id,
            "job_id": ((result.get("data") or {}).get("job_id") if isinstance(result.get("data"), dict) else ""),
            "trace_id": str(result.get("trace_id") or ""),
            "launch_visible_console": bool(payload.get("launch_visible_console", True)),
        }
    )



@bp.route("/api/ops-platform/agents/probe-all", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_probe_all():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    rows = ops_helpers._agents_v2_for_project(project_id)
    probe_results = ops_helpers._probe_agents_batch(rows, timeout=2.0)
    reg = ops_helpers._load_agent_registry_v2()
    out: List[Dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    for item in rows:
        aid = str(item.get("agent_id") or "")
        host = str(item.get("probe_host") or item.get("host_name") or "").strip()
        port = int(item.get("remote_game_server_port") or item.get("port") or 0)
        pr = probe_results.get(aid) or {}
        ok = bool(pr.get("ok"))
        rtt_ms = float(pr.get("rtt_ms") or 0.0)
        err = str(pr.get("error") or "")
        method = str(pr.get("probe_method") or "tcp")
        hit = reg.get(aid) if isinstance(reg.get(aid), dict) else None
        if hit:
            hit["probe_status"] = "PASS" if ok else "FAIL"
            hit["probe_at"] = str(pr.get("probe_at") or ops_helpers._now_iso())
            hit["probe_rtt_ms"] = round(rtt_ms, 1)
            hit["updated_at"] = ops_helpers._now_iso()
            if ok and method == "cluster-embedded":
                hit["probe_source"] = "cluster-embedded"
            reg[aid] = ops_helpers._normalize_agent_descriptor_v2(hit)
        if ok:
            pass_count += 1
        else:
            fail_count += 1
        if ok:
            msg = "连通性正常" if method == "tcp" else "集群内嵌模块在线"
        else:
            msg = "连通性失败: " + (err or "unknown")
        out.append({
            "agent_id": aid,
            "host_name": host,
            "port": port,
            "ok": ok,
            "rtt_ms": round(rtt_ms, 1),
            "message": msg,
            "probe_method": method,
        })
    ops_helpers._save_agent_registry_v2(reg)
    return jsonify({"ok": True, "project_id": project_id, "pass_count": pass_count, "fail_count": fail_count, "results": out})



@bp.route("/api/ops-platform/agents/probe-repair", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_probe_repair():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    default_host = str(payload.get("default_host") or "127.0.0.1").strip() or "127.0.0.1"
    rows = ops_helpers._agents_v2_for_project(project_id)
    reg = ops_helpers._load_agent_registry_v2()
    out: List[Dict[str, Any]] = []
    fixed = 0
    pass_count = 0
    fail_count = 0
    for item in rows:
        aid = str(item.get("agent_id") or "")
        hit = reg.get(aid) if isinstance(reg.get(aid), dict) else None
        if not hit:
            continue
        host = str(hit.get("host_name") or "").strip()
        if not host or host == "0.0.0.0":
            host = default_host
            hit["host_name"] = host
            fixed += 1
        port = int(hit.get("port") or 0)
        if port <= 0:
            port = int(hit.get("remote_game_server_port") or 0)
            if port > 0:
                hit["port"] = port
                fixed += 1
        ok = False
        msg = ""
        rtt_ms = 0.0
        if host and port > 0:
            start = datetime.utcnow()
            try:
                with socket.create_connection((host, port), timeout=2.0):
                    ok = True
            except Exception as ex:
                ok = False
                msg = str(ex)
            rtt_ms = max(0.0, (datetime.utcnow() - start).total_seconds() * 1000.0)
        else:
            msg = "缺少 host/port"
        hit["probe_status"] = "PASS" if ok else "FAIL"
        hit["probe_at"] = ops_helpers._now_iso()
        hit["probe_rtt_ms"] = round(rtt_ms, 1)
        hit["updated_at"] = ops_helpers._now_iso()
        reg[aid] = ops_helpers._normalize_agent_descriptor_v2(hit)
        if ok:
            pass_count += 1
        else:
            fail_count += 1
        out.append({
            "agent_id": aid,
            "host_name": host,
            "port": port,
            "ok": ok,
            "rtt_ms": round(rtt_ms, 1),
            "message": ("连通性正常" if ok else ("连通性失败: " + (msg or "unknown"))),
        })
    ops_helpers._save_agent_registry_v2(reg)
    return jsonify({"ok": True, "project_id": project_id, "fixed_count": fixed, "pass_count": pass_count, "fail_count": fail_count, "results": out})



@bp.route("/api/ops-platform/agents/cleanup-expired", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_cleanup_expired():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    ttl_hours_raw = payload.get("ttl_hours", 24)
    try:
        ttl_hours = int(ttl_hours_raw)
    except Exception:
        ttl_hours = 24
    if ttl_hours < 1:
        ttl_hours = 1
    if ttl_hours > 24 * 30:
        ttl_hours = 24 * 30
    ttl_sec = int(ttl_hours * 3600)

    reg = ops_helpers._load_agent_registry_v2()
    now_ts = datetime.utcnow().timestamp()
    deleted_agent_ids: List[str] = []
    kept = 0

    for agent_id, row in list(reg.items()):
        if not isinstance(row, dict):
            continue
        aid = str(agent_id or "").strip()
        if not aid:
            continue
        row_project = str(row.get("project_id") or "").strip()
        if project_id and row_project and row_project != project_id:
            kept += 1
            continue
        last_seen_raw = str(row.get("last_seen") or "").strip()
        if not last_seen_raw:
            # 无心跳时间的老残留直接清理
            reg.pop(aid, None)
            deleted_agent_ids.append(aid)
            continue
        try:
            last_seen_ts = datetime.fromisoformat(last_seen_raw.replace("Z", "")).timestamp()
        except Exception:
            reg.pop(aid, None)
            deleted_agent_ids.append(aid)
            continue
        age = max(0, int(now_ts - last_seen_ts))
        if age > ttl_sec:
            reg.pop(aid, None)
            deleted_agent_ids.append(aid)
        else:
            kept += 1

    bindings = ops_helpers._load_node_agent_bindings()
    service_bindings = ops_helpers._load_node_service_bindings()
    removed_bindings = 0
    removed_service_bindings = 0
    if deleted_agent_ids:
        deleted_set = set(deleted_agent_ids)
        for node_id, aid in list(bindings.items()):
            if str(aid or "").strip() in deleted_set:
                bindings.pop(node_id, None)
                removed_bindings += 1
        services = ops_helpers._services_for_project(project_id)
        service_agent_map = {
            str(s.get("service_id") or "").strip(): str(s.get("agent_id") or "").strip()
            for s in services
            if isinstance(s, dict) and str(s.get("service_id") or "").strip()
        }
        for node_id, sid in list(service_bindings.items()):
            sid_text = str(sid or "").strip()
            if not sid_text:
                continue
            if service_agent_map.get(sid_text, "") in deleted_set:
                service_bindings.pop(node_id, None)
                removed_service_bindings += 1

    ops_helpers._save_agent_registry_v2(reg)
    ops_helpers._save_node_agent_bindings(bindings)
    ops_helpers._save_node_service_bindings(service_bindings)
    log_audit(
        "ops_platform_agents_cleanup_expired",
        f"project={project_id or '-'}; ttl_hours={ttl_hours}; deleted={len(deleted_agent_ids)}; unbound={removed_bindings}; unbound_service={removed_service_bindings}",
    )
    return jsonify(
        {
            "ok": True,
            "project_id": project_id,
            "ttl_hours": ttl_hours,
            "deleted_count": len(deleted_agent_ids),
            "removed_binding_count": removed_bindings,
            "removed_service_binding_count": removed_service_bindings,
            "kept_count": kept,
            "deleted_agent_ids": deleted_agent_ids[:80],
        }
    )



@bp.route("/api/ops-platform/agent/register", methods=["POST"])
def ops_platform_agent_register():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip() or ("agent-" + uuid.uuid4().hex[:8])
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    device_id = str(payload.get("device_id") or payload.get("host_name") or payload.get("hostname") or request.remote_addr or "unknown-device").strip()
    policy = ops_helpers._load_agent_policy()
    node = ops_helpers._auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    reg = ops_helpers._load_agent_registry()
    reg_v2 = ops_helpers._load_agent_registry_v2()
    existing = reg_v2.get(agent_id) if isinstance(reg_v2.get(agent_id), dict) else {}
    stored_node_id = "" if agent_id == CANONICAL_LOCAL_AGENT_ID else node_id
    if agent_id == CANONICAL_LOCAL_AGENT_ID:
        device_id = CANONICAL_LOCAL_DEVICE_ID
    now = ops_helpers._now_iso()
    reg[node_id] = {
        "node_id": node_id,
        "agent_id": agent_id,
        "status": "ONLINE",
        "version": str(payload.get("version") or ""),
        "hostname": str(payload.get("hostname") or ""),
        "ip": str(payload.get("ip") or request.remote_addr or ""),
        "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else [],
        "cert_fingerprint": cert_fp,
        "last_seen": now,
        "updated_at": now,
    }
    ops_helpers._save_agent_registry(reg)
    reg_v2[agent_id] = ops_helpers._normalize_agent_descriptor_v2(
        {
            "agent_id": agent_id,
            "device_id": device_id,
            "host_name": str(payload.get("host_name") or payload.get("hostname") or ""),
            "node_id": stored_node_id,
            "project_id": str(payload.get("project_id") or node.get("project_id") or ""),
            "status": "ONLINE",
            "version": str(payload.get("version") or existing.get("version") or ""),
            "last_seen": now,
            "display_name": str(payload.get("display_name") or existing.get("display_name") or agent_id),
            "port": int(payload.get("port") or existing.get("port") or 0),
            "remote_game_server_port": int(payload.get("remote_game_server_port") or payload.get("port") or existing.get("remote_game_server_port") or 0),
            "desc": str(payload.get("desc") or existing.get("desc") or ""),
            "run_state": str(payload.get("run_state") or existing.get("run_state") or "RUNNING"),
            "network": payload.get("network") if isinstance(payload.get("network"), dict) else (existing.get("network") if isinstance(existing.get("network"), dict) else {"endpoints": []}),
            "region": str(payload.get("region") or existing.get("region") or ""),
            "zone": str(payload.get("zone") or existing.get("zone") or ""),
            "rack": str(payload.get("rack") or existing.get("rack") or ""),
            "host_ip": str(payload.get("host_ip") or payload.get("host_name") or payload.get("hostname") or existing.get("host_ip") or ""),
            "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else (existing.get("capabilities") if isinstance(existing.get("capabilities"), list) else []),
            "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else (existing.get("metrics") if isinstance(existing.get("metrics"), dict) else {}),
            "services": existing.get("services") if isinstance(existing.get("services"), list) else [],
            "runtime": payload.get("runtime") if isinstance(payload.get("runtime"), dict) else (existing.get("runtime") if isinstance(existing.get("runtime"), dict) else {}),
            "transport": {
                "mode": str(payload.get("transport_mode") or "remote"),
                "local_bus": {
                    "enabled": bool(payload.get("local_bus_enabled", True)),
                    "endpoint": str(payload.get("local_bus_endpoint") or ""),
                    "auth_mode": str(payload.get("local_bus_auth_mode") or "token"),
                },
            },
            "registration_origin": "runtime.agent",
            "updated_at": now,
        }
    )
    reg_v2[agent_id]["stale"] = False
    reg_v2[agent_id].pop("stale_reason", None)
    reg_v2[agent_id].pop("superseded_by", None)
    ops_helpers._mark_duplicate_runtime_agents(reg_v2, agent_id, node_id)
    ops_helpers._append_realtime_agent_sample(reg_v2[agent_id])
    ops_helpers._save_agent_registry_v2(reg_v2)
    if agent_id == CANONICAL_LOCAL_AGENT_ID:
        ops_helpers._consolidate_runtime_agents_to_canonical(str(payload.get("project_id") or node.get("project_id") or ""))
    upgrade = ops_helpers._desired_agent_upgrade(agent_id, policy)
    return jsonify({"ok": True, "agent_id": agent_id, "node_id": node_id, "device_id": device_id, "poll_interval_sec": 5, "mtls_required": bool(policy.get("mtls_required")), "upgrade": upgrade})



@bp.route("/api/ops-platform/agent/heartbeat", methods=["POST"])
def ops_platform_agent_heartbeat():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    device_id = str(payload.get("device_id") or payload.get("host_name") or payload.get("hostname") or request.remote_addr or "unknown-device").strip()
    policy = ops_helpers._load_agent_policy()
    node = ops_helpers._auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    reg = ops_helpers._load_agent_registry()
    reg_v2 = ops_helpers._load_agent_registry_v2()
    cur = reg.get(node_id) if isinstance(reg.get(node_id), dict) else {}
    cur.update(
        {
            "node_id": node_id,
            "agent_id": agent_id or str(cur.get("agent_id") or ""),
            "status": str(payload.get("status") or "ONLINE"),
            "last_seen": ops_helpers._now_iso(),
            "updated_at": ops_helpers._now_iso(),
            "runtime": payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {},
            "version": str(payload.get("version") or cur.get("version") or ""),
            "cert_fingerprint": cert_fp or str(cur.get("cert_fingerprint") or ""),
        }
    )
    reg[node_id] = cur
    ops_helpers._save_agent_registry(reg)
    now = ops_helpers._now_iso()
    prev = reg_v2.get(agent_id) if isinstance(reg_v2.get(agent_id), dict) else {}
    reg_v2[agent_id] = ops_helpers._normalize_agent_descriptor_v2(
        {
            **prev,
            "agent_id": agent_id or str(prev.get("agent_id") or ""),
            "device_id": device_id or str(prev.get("device_id") or ""),
            "host_name": str(payload.get("host_name") or payload.get("hostname") or prev.get("host_name") or ""),
            "node_id": node_id,
            "project_id": str(payload.get("project_id") or prev.get("project_id") or node.get("project_id") or ""),
            "status": str(payload.get("status") or prev.get("status") or "ONLINE"),
            "version": str(payload.get("version") or prev.get("version") or ""),
            "last_seen": now,
            "display_name": str(payload.get("display_name") or prev.get("display_name") or agent_id),
            "port": int(payload.get("port") or prev.get("port") or 0),
            "remote_game_server_port": int(payload.get("remote_game_server_port") or prev.get("remote_game_server_port") or payload.get("port") or prev.get("port") or 0),
            "desc": str(payload.get("desc") or prev.get("desc") or ""),
            "run_state": str(payload.get("run_state") or prev.get("run_state") or ""),
            "network": payload.get("network") if isinstance(payload.get("network"), dict) else (prev.get("network") if isinstance(prev.get("network"), dict) else {"endpoints": []}),
            "region": str(payload.get("region") or prev.get("region") or ""),
            "zone": str(payload.get("zone") or prev.get("zone") or ""),
            "rack": str(payload.get("rack") or prev.get("rack") or ""),
            "host_ip": str(payload.get("host_ip") or payload.get("host_name") or payload.get("hostname") or prev.get("host_ip") or prev.get("host_name") or ""),
            "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else prev.get("capabilities") or [],
            "service_id": str(payload.get("service_id") or prev.get("service_id") or ""),
            "services": payload.get("services") if isinstance(payload.get("services"), list) else (prev.get("services") if isinstance(prev.get("services"), list) else []),
            "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else (prev.get("metrics") if isinstance(prev.get("metrics"), dict) else {}),
            "runtime": payload.get("runtime") if isinstance(payload.get("runtime"), dict) else (prev.get("runtime") if isinstance(prev.get("runtime"), dict) else {}),
            "transport": {
                "mode": str(payload.get("transport_mode") or ((prev.get("transport") or {}).get("mode") if isinstance(prev.get("transport"), dict) else "remote")),
                "local_bus": {
                    "enabled": bool(payload.get("local_bus_enabled", ((prev.get("transport") or {}).get("local_enabled") if isinstance(prev.get("transport"), dict) else True))),
                    "endpoint": str(payload.get("local_bus_endpoint") or ((prev.get("transport") or {}).get("local_endpoint") if isinstance(prev.get("transport"), dict) else "")),
                    "auth_mode": str(payload.get("local_bus_auth_mode") or ((prev.get("transport") or {}).get("local_auth_mode") if isinstance(prev.get("transport"), dict) else "token")),
                },
                "degraded": bool(payload.get("local_bus_degraded", False)),
                "degrade_reason": str(payload.get("local_bus_degrade_reason") or ""),
            },
            "registration_origin": "runtime.agent",
            "updated_at": now,
        }
    )
    reg_v2[agent_id]["stale"] = False
    reg_v2[agent_id].pop("stale_reason", None)
    reg_v2[agent_id].pop("superseded_by", None)
    ops_helpers._mark_duplicate_runtime_agents(reg_v2, agent_id, node_id)
    ops_helpers._append_realtime_agent_sample(reg_v2[agent_id])
    ops_helpers._save_agent_registry_v2(reg_v2)
    jobs = ops_helpers._load_agent_jobs()
    if ops_helpers._reconcile_agent_jobs(
        node_id,
        jobs,
        lease_timeout_sec=int(policy.get("lease_timeout_sec") or 60),
        max_retries=int(policy.get("max_retries") or 2),
    ):
        ops_helpers._save_agent_jobs(jobs)
    pending = len([x for x in jobs if isinstance(x, dict) and str(x.get("node_id") or "") == node_id and str(x.get("status") or "") == "PENDING"])
    upgrade = ops_helpers._desired_agent_upgrade(agent_id, policy)
    return jsonify({"ok": True, "pending_jobs": pending, "server_time": ops_helpers._now_iso(), "upgrade": upgrade})



@bp.route("/api/ops-platform/agent/pull", methods=["POST"])
def ops_platform_agent_pull():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    policy = ops_helpers._load_agent_policy()
    node = ops_helpers._auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    limit = max(1, min(20, int(payload.get("limit") or 5)))
    jobs = ops_helpers._load_agent_jobs()
    changed = ops_helpers._reconcile_agent_jobs(
        node_id,
        jobs,
        lease_timeout_sec=int(policy.get("lease_timeout_sec") or 60),
        max_retries=int(policy.get("max_retries") or 2),
        agent_id=agent_id,
    )
    out: List[Dict[str, Any]] = []
    now = ops_helpers._now_iso()
    node_max = int(node.get("agent_max_concurrency") or policy.get("default_node_concurrency") or 1)
    node_max = max(1, min(20, node_max))
    running = [
        x
        for x in jobs
        if isinstance(x, dict)
        and ops_helpers._job_matches_agent(x, agent_id, node_id)
        and str(x.get("status") or "").upper() == "RUNNING"
    ]
    slots = max(0, node_max - len(running))
    if slots <= 0:
        upgrade = ops_helpers._desired_agent_upgrade(agent_id, policy)
        if changed:
            ops_helpers._save_agent_jobs(jobs)
        return jsonify({"ok": True, "jobs": [], "count": 0, "upgrade": upgrade, "node_concurrency": node_max})

    # preempt: if there is high-priority pending preempt job, cancel one running
    preempt_candidate = None
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if not ops_helpers._job_matches_agent(item, agent_id, node_id) or str(item.get("status") or "") != "PENDING":
            continue
        if bool(item.get("preempt")):
            preempt_candidate = item
            break
    if preempt_candidate and running:
        victim = sorted(running, key=lambda x: str(x.get("updated_at") or ""))[0]
        victim["status"] = "CANCELED"
        victim["updated_at"] = ops_helpers._now_iso()
        victim["result"] = {"message": "preempted by higher priority job"}
        changed = True
        slots = max(1, slots)

    for item in jobs:
        if not isinstance(item, dict):
            continue
        if not ops_helpers._job_matches_agent(item, agent_id, node_id):
            continue
        if str(item.get("status") or "") != "PENDING":
            continue
        if bool(item.get("require_approval")) and (not bool(item.get("approved"))):
            approval_target_id = str(item.get("approval_target_id") or "").strip()
            if not approval_target_id:
                approval_target_id = ops_helpers._approval_target_id(
                    str(item.get("node_id") or ""),
                    str(item.get("action_type") or ""),
                    str(item.get("target") or ""),
                )
                item["approval_target_id"] = approval_target_id
                changed = True
            if approval_target_id:
                approved_ref = get_approved_approval("gm_ops_action", approval_target_id)
                if approved_ref:
                    item["approved"] = True
                    changed = True
            if not bool(item.get("approved")):
                continue
        if slots <= 0:
            break
        item["status"] = "RUNNING"
        item["updated_at"] = now
        item["lease"] = {"agent_id": agent_id, "leased_at": now}
        item["attempt"] = int(item.get("attempt") or 0)
        out.append(
            {
                "job_id": item.get("job_id"),
                "node_id": item.get("node_id"),
                "action_type": item.get("action_type"),
                "target": item.get("target"),
                "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
                "risk": item.get("risk"),
                "ticket_id": item.get("ticket_id"),
                "reason": item.get("reason"),
                "idempotency_key": item.get("idempotency_key"),
                "attempt": item.get("attempt"),
            }
        )
        changed = True
        slots -= 1
        if len(out) >= limit:
            break
    if changed:
        ops_helpers._save_agent_jobs(jobs)
    upgrade = ops_helpers._desired_agent_upgrade(agent_id, policy)
    return jsonify({"ok": True, "jobs": out, "count": len(out), "upgrade": upgrade, "node_concurrency": node_max})



@bp.route("/api/ops-platform/agent/report", methods=["POST"])
def ops_platform_agent_report():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    node = ops_helpers._auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    job_id = str(payload.get("job_id") or "").strip()
    status = str(payload.get("status") or "").strip().upper()
    if not job_id or status not in ("RUNNING", "SUCCESS", "FAILED", "CANCELED", "TIMEOUT"):
        return jsonify({"ok": False, "error": "invalid_report_payload"}), 400
    jobs = ops_helpers._load_agent_jobs()
    hit = None
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if str(item.get("job_id") or "") != job_id:
            continue
        if not ops_helpers._job_matches_agent(item, agent_id, node_id):
            continue
        hit = item
        break
    if not hit:
        return jsonify({"ok": False, "error": "job_not_found"}), 404
    hit["status"] = status
    hit["updated_at"] = ops_helpers._now_iso()
    hit["lease"] = {"agent_id": agent_id, "updated_at": ops_helpers._now_iso()}
    hit["result"] = payload.get("result") if isinstance(payload.get("result"), dict) else {"message": str(payload.get("message") or "")}
    if status in ("FAILED", "TIMEOUT"):
        attempts = int(hit.get("attempt") or 0)
        max_retries = int(hit.get("max_retries") or ops_helpers._load_agent_policy().get("max_retries") or 2)
        if attempts < max_retries:
            hit["status"] = "PENDING"
            hit["attempt"] = attempts + 1
            hit["lease"] = {}
            hit["updated_at"] = ops_helpers._now_iso()
            hit["result"] = {"message": "scheduled retry after failure", "last_status": status}
    ops_helpers._save_agent_jobs(jobs)
    reg_v2 = ops_helpers._load_agent_registry_v2()
    cur_agent = reg_v2.get(agent_id) if isinstance(reg_v2.get(agent_id), dict) else {}
    if cur_agent:
        runtime = cur_agent.get("runtime") if isinstance(cur_agent.get("runtime"), dict) else {}
        action_type = str(hit.get("action_type") or "").strip().lower()
        hp = hit.get("payload") if isinstance(hit.get("payload"), dict) else {}
        desired_role = str(hp.get("desired_role") or "")
        if status == "RUNNING":
            runtime["state"] = "RUNNING"
        elif status == "SUCCESS":
            if action_type == "start":
                runtime["state"] = "RUNNING"
                if desired_role:
                    runtime["current_role"] = desired_role
            elif action_type == "stop":
                runtime["state"] = "STOPPED"
            elif action_type == "restart":
                runtime["state"] = "RUNNING"
                if desired_role:
                    runtime["current_role"] = desired_role
        elif status in ("FAILED", "TIMEOUT", "CANCELED"):
            runtime["state"] = "ERROR"
        runtime["last_job_id"] = job_id
        runtime["last_job_status"] = status
        runtime["updated_at"] = ops_helpers._now_iso()
        cur_agent["runtime"] = runtime
        cur_agent["run_state"] = runtime.get("state") or cur_agent.get("run_state") or ""
        cur_agent["updated_at"] = ops_helpers._now_iso()
        reg_v2[agent_id] = ops_helpers._normalize_agent_descriptor_v2(cur_agent)
        ops_helpers._save_agent_registry_v2(reg_v2)

    ops_helpers._append_event(
        {
            "id": "evt-" + uuid.uuid4().hex[:12],
            "time": ops_helpers._now_iso(),
            "severity": "info" if status in ("SUCCESS", "RUNNING") else "critical",
            "status": "resolved" if ops_helpers._agent_status_terminal(status) and status == "SUCCESS" else "open",
            "title": f"Agent 任务状态更新：{hit.get('action_type')}",
            "message": f"node={node_id}; job={job_id}; agent={agent_id}; status={status}",
            "trace_id": "",
            "node_id": node_id,
            "agent_id": agent_id,
            "action_type": str(hit.get("action_type") or ""),
            "target": str(hit.get("target") or ""),
            "job_id": job_id,
        }
    )
    return jsonify({"ok": True, "job_id": job_id, "status": status})



@bp.route("/api/ops-platform/agent/jobs")
@admin_required("gm_ops")
def ops_platform_agent_jobs():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    node_id = str(request.args.get("node_id") or "").strip()
    status = str(request.args.get("status") or "").strip().upper()
    limit = max(1, min(200, int(request.args.get("limit") or 50)))
    rows = ops_helpers._load_agent_jobs()
    out: List[Dict[str, Any]] = []
    for item in reversed(rows):
        if not isinstance(item, dict):
            continue
        if node_id and str(item.get("node_id") or "") != node_id:
            continue
        if status and str(item.get("status") or "").upper() != status:
            continue
        out.append(item)
        if len(out) >= limit:
            break
    reg = ops_helpers._load_agent_registry_v2()
    return jsonify({"ok": True, "count": len(out), "jobs": out, "agents": [ops_helpers._normalize_agent_descriptor_v2(x) for x in reg.values() if isinstance(x, dict)], "policy": ops_helpers._load_agent_policy()})



@bp.route("/api/ops-platform/agent/detail")
@admin_required("gm_ops")
def ops_platform_agent_detail():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    ops_helpers._ensure_probe_bg_started()
    project_id = str(request.args.get("project_id") or "").strip()
    agent_id = str(request.args.get("agent_id") or "").strip()
    include = str(request.args.get("include") or "all").strip()
    force_live = str(request.args.get("live") or "").strip().lower() in ("1", "true", "yes")
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    detail = ops_helpers._build_agent_detail(project_id, agent_id, include=include, force_live=force_live)
    if not detail:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    return jsonify({"ok": True, **detail})



@bp.route("/api/ops-platform/agent/audit")
@admin_required("gm_ops")
def ops_platform_agent_audit():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    agent_id = str(request.args.get("agent_id") or "").strip()
    limit = max(1, min(200, int(request.args.get("limit") or 60)))
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    detail = ops_helpers._build_agent_detail(project_id, agent_id)
    if not detail:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    return jsonify(
        {
            "ok": True,
            "count": min(limit, len(detail.get("audits") or [])),
            "audits": (detail.get("audits") or [])[:limit],
            "traces": (detail.get("traces") or [])[:limit],
        }
    )



@bp.route("/api/ops-platform/agent/policy", methods=["GET", "POST"])
@admin_required("gm_ops")
def ops_platform_agent_policy():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    if request.method == "GET":
        return jsonify({"ok": True, "policy": ops_helpers._load_agent_policy()})
    payload = request.get_json(silent=True) or {}
    current = ops_helpers._load_agent_policy()
    merged = dict(current)
    for k in ("mtls_required", "lease_timeout_sec", "max_retries", "default_node_concurrency"):
        if k in payload:
            merged[k] = payload.get(k)
    if isinstance(payload.get("rollout"), dict):
        rollout = merged.get("rollout") if isinstance(merged.get("rollout"), dict) else {}
        rollout.update(payload.get("rollout"))
        merged["rollout"] = rollout
    ops_helpers._save_agent_policy(merged)
    log_audit("ops_platform_agent_policy_update", f"user={session.get('user')}; policy_updated=true")
    return jsonify({"ok": True, "policy": ops_helpers._load_agent_policy()})



@bp.route("/api/ops-platform/agent/complete-server-deploy", methods=["POST"])
def ops_platform_agent_complete_server_deploy():
    """Agent callback after deploy_server_artifact job (P2-01)."""
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    node = ops_helpers._auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403

    project_id = str(payload.get("project_id") or "").strip()
    server_release_id = str(payload.get("server_release_id") or "").strip()
    service_id = str(payload.get("service_id") or node_id or "").strip()
    if not project_id or not server_release_id:
        return jsonify({"ok": False, "error": "missing_project_or_release_id"}), 400

    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
    detail["node_id"] = node_id
    if agent_id:
        detail["agent_id"] = agent_id

    from services.release import server_release_service as srs

    try:
        row = srs.complete_deploy_server_release(
            project_id,
            server_release_id,
            ok=bool(payload.get("ok", True)),
            actor=f"agent:{node_id}",
            detail=detail,
            service_id=service_id,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "data": row})


@bp.route("/api/ops-platform/agent/upgrade/report", methods=["POST"])
def ops_platform_agent_upgrade_report():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    node = ops_helpers._auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    reg = ops_helpers._load_agent_registry()
    cur = reg.get(node_id) if isinstance(reg.get(node_id), dict) else {}
    cur["version"] = str(payload.get("version") or cur.get("version") or "")
    cur["upgrade_status"] = str(payload.get("status") or "")
    cur["upgrade_message"] = str(payload.get("message") or "")
    cur["last_seen"] = ops_helpers._now_iso()
    cur["updated_at"] = ops_helpers._now_iso()
    reg[node_id] = cur
    ops_helpers._save_agent_registry(reg)
    return jsonify({"ok": True, "node_id": node_id, "version": cur.get("version")})


