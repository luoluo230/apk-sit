# -*- coding: utf-8 -*-
"""Agents route submodule."""
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
from routes.ops import deps as ops_helpers
from routes.ops import bp

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



