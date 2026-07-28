# -*- coding: utf-8 -*-
"""Ops diagnostics summaries and onboarding views."""

from __future__ import annotations

from services.ops import shared_bootstrap as _boot

globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})

def _load_change_freeze_state() -> Dict[str, Any]:
    raw = _load_json_config(OPS_CHANGE_FREEZE_KEY, {})
    return raw if isinstance(raw, dict) else {}

def _change_freeze_for_project(project_id: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid:
        return {"active": False}
    row = _load_change_freeze_state().get(pid)
    return row if isinstance(row, dict) else {"active": False}

def _save_change_freeze(project_id: str, active: bool, reason: str = "", actor: str = "") -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid:
        return {"active": False}
    state = _load_change_freeze_state()
    state[pid] = {
        "active": bool(active),
        "reason": str(reason or "").strip(),
        "updated_at": _now_iso(),
        "updated_by": str(actor or "").strip(),
    }
    _save_json_config(OPS_CHANGE_FREEZE_KEY, state, description="Ops change freeze window per project")
    return state[pid]

def _resolve_action_target_from_payload(payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """Resolve execute/validate target to a dispatch node (service > topology > agent > legacy node)."""
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "production")
    target_key = str(payload.get("target_key") or "").strip()
    target_type = str(payload.get("target_type") or "").strip().lower()
    target_id = ""
    if target_key and ":" in target_key:
        target_type, target_id = target_key.split(":", 1)
        target_type = target_type.strip().lower()
        target_id = target_id.strip()
    if not target_id:
        target_id = str(
            payload.get("service_id")
            or payload.get("topology_node_id")
            or payload.get("agent_id")
            or payload.get("node_id")
            or ""
        ).strip()
    if not target_type:
        if payload.get("service_id"):
            target_type = "service"
        elif payload.get("agent_id"):
            target_type = "agent"
        elif payload.get("topology_node_id"):
            target_type = "topology"
        else:
            target_type = "node"

    body_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    if not isinstance(payload.get("payload"), dict):
        payload["payload"] = body_payload

    if target_type == "service":
        service_hit = None
        for svc in _services_for_project(project_id):
            if isinstance(svc, dict) and str(svc.get("service_id") or "").strip() == target_id:
                service_hit = svc
                break
        if not service_hit:
            return None, "service_not_found"
        topology_node_id = str(payload.get("node_id") or service_hit.get("node_id") or target_id).strip()
        node = _resolve_ops_dispatch_node(project_id, topology_node_id, env_key)
        if not node:
            return None, "dispatch_node_not_found"
        payload["node_id"] = str(node.get("id") or topology_node_id)
        payload["service_id"] = target_id
        payload["target"] = str(payload.get("target") or target_id)
        payload["via_agent"] = bool(payload.get("via_agent", True))
        payload["run_mode"] = str(payload.get("run_mode") or "agent")
        body_payload.update({
            "desired_service_id": target_id,
            "desired_server_id": target_id,
            "topology_node_id": topology_node_id,
            "run_mode": "agent",
        })
        return node, ""

    if target_type == "topology":
        node = _resolve_ops_dispatch_node(project_id, target_id, env_key)
        if not node:
            return None, "topology_node_not_found"
        payload["node_id"] = str(node.get("id") or target_id)
        payload["topology_node_id"] = target_id
        payload["target"] = str(payload.get("target") or target_id)
        if "via_agent" not in payload:
            payload["via_agent"] = True
        return node, ""

    if target_type == "agent":
        reg = _load_agent_registry_v2()
        agent_desc = reg.get(target_id) if isinstance(reg.get(target_id), dict) else {}
        dispatch_id = str(agent_desc.get("node_id") or target_id).strip()
        node = _resolve_ops_dispatch_node(project_id, dispatch_id, env_key)
        if not node:
            return None, "agent_dispatch_node_not_found"
        payload["node_id"] = dispatch_id
        payload["agent_id"] = target_id
        payload["target"] = str(payload.get("target") or dispatch_id)
        payload["via_agent"] = True
        payload["run_mode"] = "agent"
        body_payload.setdefault("desired_agent_id", target_id)
        return node, ""

    node, err = _node_or_400(payload)
    if err:
        return None, "legacy_node_not_found"
    payload["node_id"] = str(node.get("id") or "")
    payload["target"] = str(payload.get("target") or payload["node_id"])
    return node, ""

def _action_target_or_400(payload: Dict[str, Any]):
    node, reason = _resolve_action_target_from_payload(payload)
    if not node:
        msg = {
            "service_not_found": "未找到目标服务",
            "dispatch_node_not_found": "服务对应拓扑节点不存在",
            "topology_node_not_found": "未找到拓扑节点",
            "agent_dispatch_node_not_found": "Agent 未绑定可调度节点",
            "legacy_node_not_found": "未找到 nodes 配置节点",
        }.get(reason, "未找到动作目标")
        return None, (jsonify({"ok": False, "error": reason or "target_not_found", "message": msg}), 400)
    return node, None

def _list_action_targets(project_id: str, env_key: str = "production") -> List[Dict[str, Any]]:
    pid = str(project_id or "").strip()
    env = _resolve_ops_env_key(env_key)
    out: List[Dict[str, Any]] = []
    seen = set()

    for svc in _services_for_project(pid, env):
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or "").strip()
        if not sid:
            continue
        key = f"service:{sid}"
        if key in seen:
            continue
        seen.add(key)
        nid = str(svc.get("node_id") or sid).strip()
        out.append({
            "target_type": "service",
            "target_key": key,
            "node_id": nid,
            "service_id": sid,
            "agent_id": str(svc.get("agent_id") or ""),
            "label": f"{svc.get('display_name') or sid} · 服务",
            "role": str(svc.get("service_type") or ""),
            "status": str(svc.get("status") or svc.get("run_state") or "UNKNOWN").upper(),
            "probe_status": str(svc.get("probe_status") or ""),
        })

    ctx = _resolve_topology_context(pid, env, "")
    topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    tid = str(row.get("topology_id") or "")
    bindings = _load_scope_agent_bindings(tid)
    agents_map = {
        str(a.get("agent_id") or ""): a
        for a in _agents_v2_for_project(pid, env)
        if isinstance(a, dict) and str(a.get("agent_id") or "")
    }
    for node in topo.get("nodes") if isinstance(topo.get("nodes"), list) else []:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or "").strip()
        if not nid:
            continue
        key = f"topology:{nid}"
        if key in seen:
            continue
        seen.add(key)
        aid = str(bindings.get(nid) or "")
        agent = agents_map.get(aid) or {}
        out.append({
            "target_type": "topology",
            "target_key": key,
            "node_id": nid,
            "service_id": nid,
            "agent_id": aid,
            "label": f"{node.get('name') or nid} · 拓扑",
            "role": str(node.get("role") or ""),
            "status": str(agent.get("effective_status") or agent.get("status") or "UNKNOWN").upper(),
            "probe_status": str(agent.get("probe_status") or ""),
        })

    for ag in _logical_agents_for_project(pid, env):
        if not isinstance(ag, dict) or ag.get("stale"):
            continue
        aid = str(ag.get("agent_id") or "").strip()
        if not aid:
            continue
        key = f"agent:{aid}"
        if key in seen:
            continue
        seen.add(key)
        nid = str(ag.get("node_id") or "").strip()
        out.append({
            "target_type": "agent",
            "target_key": key,
            "node_id": nid,
            "service_id": "",
            "agent_id": aid,
            "label": f"{ag.get('display_name') or aid} · Agent",
            "role": str(ag.get("role") or ag.get("category") or ""),
            "status": str(ag.get("effective_status") or ag.get("status") or "UNKNOWN").upper(),
            "probe_status": str(ag.get("probe_status") or ""),
        })

    for item in _load_nodes():
        if not isinstance(item, dict) or not item.get("enabled"):
            continue
        if pid and str(item.get("project_id") or "") not in ("", pid):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid:
            continue
        key = f"node:{nid}"
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "target_type": "node",
            "target_key": key,
            "node_id": nid,
            "service_id": str(item.get("server_id") or nid),
            "agent_id": "",
            "label": f"{item.get('name') or nid} · 配置",
            "role": str(item.get("role") or ""),
            "status": "UNKNOWN",
            "probe_status": "",
        })
    return out

def _diagnostics_fix_actions(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    target_key = str(row.get("target_key") or "")
    if not target_key:
        nid = str(row.get("node_id") or row.get("id") or "")
        if nid:
            target_key = f"service:{nid}" if row.get("service_id") else f"topology:{nid}"
    if not target_key:
        return actions
    status = str(row.get("status") or "").upper()
    probe = str(row.get("probe_status") or "").upper()
    issues = row.get("issues") if isinstance(row.get("issues"), list) else []
    actions.append({"label": "健康检查", "action_type": "health_check", "target_key": target_key, "risk": "low"})
    if status in ("OFFLINE", "UNKNOWN", "DEGRADED") or probe != "PASS":
        actions.append({"label": "就绪检查", "action_type": "ready_check", "target_key": target_key, "risk": "low"})
    if status in ("OFFLINE", "UNKNOWN"):
        actions.append({"label": "启动", "action_type": "start", "target_key": target_key, "risk": "high"})
    if any("Agent" in str(x) or "绑定" in str(x) for x in issues):
        actions.append({"label": "绑定 Agent", "href": f"/admin/projects/{row.get('project_id') or ''}/agents", "risk": "low"})
    if any("ops_base_url" in str(x) for x in issues):
        actions.append({"label": "拓扑编排", "href": f"/admin/projects/{row.get('project_id') or ''}/topologies", "risk": "low"})
    return actions

def _build_diagnostics_summary(project_id: str = "", env_key: str = "production") -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _resolve_ops_env_key(env_key)
    onboarding = _build_node_onboarding(project_id=pid)
    checks = onboarding.get("checks") if isinstance(onboarding.get("checks"), list) else []
    targets = {str(t.get("node_id") or ""): t for t in _list_action_targets(pid, env)}
    rows: List[Dict[str, Any]] = []
    for chk in checks:
        if not isinstance(chk, dict):
            continue
        nid = str(chk.get("node_id") or chk.get("id") or "").strip()
        tgt = targets.get(nid) or {}
        row = dict(chk)
        row["project_id"] = pid
        row["agent_id"] = str(tgt.get("agent_id") or "")
        row["probe_status"] = str(tgt.get("probe_status") or "")
        row["target_key"] = str(tgt.get("target_key") or (f"topology:{nid}" if nid else ""))
        row["target_type"] = str(tgt.get("target_type") or "topology")
        if row.get("agent_id") and not row.get("probe_status"):
            row.setdefault("issues", [])
            if isinstance(row["issues"], list):
                row["issues"] = list(row["issues"]) + ["Agent 未探活或 probe 未 PASS"]
        row["fix_actions"] = _diagnostics_fix_actions(row)
        rows.append(row)

    for tgt in _list_action_targets(pid, env):
        nid = str(tgt.get("node_id") or "")
        if not nid or any(str(r.get("node_id") or r.get("id") or "") == nid for r in rows):
            continue
        rows.append({
            "id": nid,
            "node_id": nid,
            "node_name": tgt.get("label"),
            "name": tgt.get("label"),
            "role": tgt.get("role"),
            "status": tgt.get("status") or "UNKNOWN",
            "severity": "warning" if str(tgt.get("probe_status") or "").upper() != "PASS" else "ok",
            "issues": [] if str(tgt.get("probe_status") or "").upper() == "PASS" else ["Agent probe 未 PASS"],
            "message": "",
            "agent_id": tgt.get("agent_id"),
            "probe_status": tgt.get("probe_status"),
            "target_key": tgt.get("target_key"),
            "target_type": tgt.get("target_type"),
            "project_id": pid,
            "env_key": env,
            "fix_actions": _diagnostics_fix_actions({**tgt, "project_id": pid}),
        })

    critical = sum(1 for r in rows if str(r.get("severity") or "") == "critical")
    warning = sum(1 for r in rows if str(r.get("severity") or "") == "warning")
    return {
        "ok": True,
        "summary": {
            "total_nodes": len(rows),
            "critical": critical,
            "warning": warning,
            "ok_nodes": max(0, len(rows) - critical - warning),
        },
        "checks": rows,
    }

def _append_bounded(key: str, item: Dict[str, Any], *, limit: int, description: str) -> None:
    rows = _load_json_config(key, [])
    if not isinstance(rows, list):
        rows = []
    rows.insert(0, item)
    if len(rows) > limit:
        rows = rows[:limit]
    _save_json_config(key, rows, description=description)

def _append_trace(entry: Dict[str, Any]) -> None:
    _append_bounded(OPS_TRACE_LOG_KEY, entry, limit=500, description="Ops 平台执行流水")

def _append_event(entry: Dict[str, Any]) -> None:
    _append_bounded(OPS_EVENT_LOG_KEY, entry, limit=800, description="Ops platform event timeline")

def _find_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    tid = str(trace_id or "").strip()
    if not tid:
        return None
    rows = _load_json_config(OPS_TRACE_LOG_KEY, [])
    if not isinstance(rows, list):
        return None
    for item in rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("trace_id") or "").strip() == tid:
            return item
    return None

def _value_contains_token(value: Any, token: str) -> bool:
    needle = str(token or "").strip().lower()
    if not needle:
        return False
    if isinstance(value, dict):
        for sub_value in value.values():
            if _value_contains_token(sub_value, needle):
                return True
        return False
    if isinstance(value, list):
        for sub_value in value:
            if _value_contains_token(sub_value, needle):
                return True
        return False
    return needle in str(value or "").lower()

def _approval_target_id(node_id: str, action_type: str, target: str) -> str:
    return f"ops:{(node_id or '').strip()}:{(action_type or '').strip()}:{(target or '').strip()}"

def _approved_by_id(approval_id: str) -> Optional[Dict[str, Any]]:
    aid = str(approval_id or "").strip()
    if not aid:
        return None
    for item in approvals_db:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == aid and str(item.get("status") or "") == "approved":
            return item
    return None

def _build_alerts_from_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for n in nodes:
        status = str(n.get("status") or "").upper()
        node_name = str(n.get("name") or n.get("id") or "-")
        if status in ("OFFLINE", "DEGRADED"):
            alerts.append({
                "id": f"alert-{n.get('id')}-{status}",
                "time": _now_iso(),
                "severity": "critical" if status == "OFFLINE" else "warning",
                "title": f"节点状态异常：{node_name}",
                "message": f"状态={status}; serverId={n.get('server_id') or '-'}",
                "status": "open",
                "node_id": n.get("id"),
                "target": n.get("id"),
            })
        p99 = n.get("p99_ms")
        if isinstance(p99, (int, float)) and p99 >= 200:
            alerts.append({
                "id": f"alert-{n.get('id')}-p99",
                "time": _now_iso(),
                "severity": "warning",
                "title": f"延迟偏高：{node_name}",
                "message": f"P99={p99:.1f}ms",
                "status": "open",
                "node_id": n.get("id"),
                "target": n.get("id"),
            })
    return alerts

def _build_overview(project_id: str = "", env_key: str = "production") -> Dict[str, Any]:
    operator = str(session.get("user") or "intranet-ops")
    project = str(project_id or "").strip()
    env = _resolve_ops_env_key(env_key)
    ctx = _resolve_topology_context(project, env, "")
    topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
    topo_map = {}
    for item in topo.get("nodes") or []:
        if isinstance(item, dict):
            nid = str(item.get("id") or "").strip()
            if nid:
                topo_map[nid] = item
    rows = _load_nodes()
    out_nodes: List[Dict[str, Any]] = []
    for item in rows:
        if not item.get("enabled"):
            continue
        if project and str(item.get("project_id") or "") != project:
            continue
        item_env = _normalize_env_key(item.get("env") or "production")
        if item_env != env:
            continue
        try:
            overview = ops_gateway.build_node_overview(item, actor=operator)
        except Exception as exc:
            import logging as _el
            _el.getLogger(__name__).warning("build_node_overview failed for %s: %s", item.get("id"), exc)
            overview = {"id": item.get("id"), "name": item.get("name"), "server_id": str(item.get("server_id") or "").strip(), "project_id": item.get("project_id"), "env": item.get("env"), "channel": item.get("channel"), "owner": item.get("owner") or "", "base_url": item.get("base_url"), "ops_base_url": item.get("ops_base_url"), "status": "OFFLINE", "health_ok": False, "ready_ok": False, "qps": None, "p99_ms": None, "cpu": None, "memory_mb": None, "disk_percent": None}
        meta = topo_map.get(str(item.get("id") or "")) or {}
        overview["role"] = str(meta.get("role") or item.get("role") or "business")
        overview["description"] = str(meta.get("desc") or item.get("description") or "")
        overview["biz_status"] = str(meta.get("bizStatus") or item.get("biz_status") or "normal")
        overview["owner"] = str(meta.get("owner") or overview.get("owner") or "")
        overview["topology_position"] = {"x": meta.get("x"), "y": meta.get("y")}
        daemon = _get_daemon_state(str(item.get("id") or ""))
        if daemon:
            overview["daemon"] = daemon
            state = str(daemon.get("status") or "").upper()
            if state in ("RUNNING", "ONLINE"):
                overview["status"] = "ONLINE"
            elif state in ("STOPPED", "ADDED", "NOT_RUNNING"):
                overview["status"] = "UNKNOWN"
            elif state in ("ERROR", "CRASHED", "FAILED"):
                overview["status"] = "OFFLINE"
        else:
            overview["daemon"] = {"status": "ADDED", "updated_at": _now_iso()}
        out_nodes.append(overview)

    total = len(out_nodes)
    healthy = len([x for x in out_nodes if x.get("status") == "ONLINE"])
    degraded = len([x for x in out_nodes if x.get("status") == "DEGRADED"])
    offline = len([x for x in out_nodes if x.get("status") == "OFFLINE"])
    sla = (healthy / total * 100.0) if total else 0.0
    alerts = _build_alerts_from_nodes(out_nodes)

    snapshot = {"updated_at": _now_iso(), "alerts": alerts}
    _save_json_config(OPS_ALERT_SNAPSHOT_KEY, snapshot, description="Ops 平台告警快照")

    return {
        "ok": True,
        "project_id": project,
        "env_key": env,
        "summary": {
            "total_nodes": total,
            "healthy_nodes": healthy,
            "degraded_nodes": degraded,
            "offline_nodes": offline,
            "alert_count": len(alerts),
            "sla_percent": round(sla, 2),
        },
        "nodes": out_nodes,
        "alerts": alerts,
        "topology": topo,
        "updated_at": _now_iso(),
    }

def _validate_ops_request(payload: Dict[str, Any], node: Dict[str, Any]) -> Dict[str, Any]:
    action_type = str(payload.get("action_type") or "").strip().lower()
    target = str(payload.get("target") or "").strip()
    ticket_id = str(payload.get("ticket_id") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    approver = str(payload.get("approver") or "").strip()
    approval_id = str(payload.get("approval_id") or "").strip()
    dry_run = bool(payload.get("dry_run"))

    risk, require_approval, domain = ops_gateway.inspect_risk(action_type)
    missing: List[str] = []
    if not action_type:
        missing.append("action_type")
    if require_approval:
        if not target:
            missing.append("target")
        if not ticket_id:
            missing.append("ticket_id")
        if not reason:
            missing.append("reason")
        if not approver:
            missing.append("approver")

    approval_target = _approval_target_id(str(node.get("id") or ""), action_type, target)
    approved_ref = get_approved_approval("gm_ops_action", approval_target)
    approved_by_id = _approved_by_id(approval_id)
    approved = bool(approved_ref) or bool(approved_by_id)
    agent_supported_actions = {
        "status",
        "health_check",
        "ready_check",
        "runtime_snapshot",
        "log_tail",
        "start",
        "stop",
        "restart",
        "start_all",
        "stop_all",
        "smoke_test",
        "stress_test",
    }
    unsupported = bool(action_type) and (action_type not in agent_supported_actions)
    if unsupported:
        missing.append("unsupported_action_type")

    return {
        "ok": len(missing) == 0 and (not unsupported),
        "missing": missing,
        "risk": risk,
        "domain": domain,
        "require_approval": require_approval,
        "approved": approved,
        "approved_ref": approved_ref or approved_by_id,
        "approval_target_id": approval_target,
        "dry_run": dry_run,
        "target": target,
        "ticket_id": ticket_id,
        "reason": reason,
        "approver": approver,
        "action_type": action_type,
        "unsupported": unsupported,
        "error_code": ("OPS_ACTION_UNSUPPORTED" if unsupported else ""),
        "agent_supported_actions": sorted(agent_supported_actions),
    }

def _execute_ops_action(payload: Dict[str, Any], node: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical ops action executor for action_center and route handlers."""
    return _execute_validated(payload, node, validation)

def _execute_validated(payload: Dict[str, Any], node: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    action_type = validation.get("action_type")
    target = validation.get("target") or str(node.get("server_id") or "").strip()
    ticket_id = validation.get("ticket_id") or "OPS-N/A"
    reason = validation.get("reason") or "ops execute"
    dry_run = bool(validation.get("dry_run"))
    operator = str(session.get("user") or "intranet-ops")
    body_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}

    run_mode = str(payload.get("run_mode") or body_payload.get("run_mode") or "").strip().lower()
    via_agent = bool(payload.get("via_agent")) or bool(body_payload.get("via_agent")) or (run_mode == "agent")
    if via_agent:
        queued = _enqueue_agent_job(
            node_id=str(node.get("id") or ""),
            action_type=str(action_type or ""),
            target=target,
            payload=body_payload,
            validation=validation,
        )
        trace_id = "agt-" + uuid.uuid4().hex[:16]
        message = f"agent job queued: {queued.get('job_id')}"
        trace_entry = {
            "trace_id": trace_id,
            "time": _now_iso(),
            "node": str(node.get("id") or ""),
            "node_name": str(node.get("name") or ""),
            "action": action_type,
            "target": target,
            "risk": validation.get("risk"),
            "ticket_id": ticket_id,
            "reason": reason,
            "approver": validation.get("approver"),
            "approved": bool(validation.get("approved")),
            "approval_target_id": validation.get("approval_target_id"),
            "dry_run": dry_run,
            "ok": True,
            "message": message,
            "raw": {"queued": True, "job_id": queued.get("job_id"), "status": "PENDING"},
        }
        _append_trace(trace_entry)
        _append_event(
            {
                "id": "evt-" + uuid.uuid4().hex[:12],
                "time": _now_iso(),
                "severity": "info",
                "status": "open",
                "title": f"Agent 任务入队：{action_type}",
                "message": f"node={node.get('id')}; job={queued.get('job_id')}; target={target}",
                "trace_id": trace_id,
                "node_id": node.get("id"),
                "agent_id": str(body_payload.get("desired_agent_id") or payload.get("agent_id") or ""),
                "action_type": action_type,
                "target": target,
                "job_id": queued.get("job_id"),
            }
        )
        log_audit("ops_platform_action_enqueue_agent", f"action={action_type}; node={node.get('id')}; job={queued.get('job_id')}")
        return {
            "ok": True,
            "message": message,
            "trace_id": trace_id,
            "data": {"job_id": queued.get("job_id"), "status": "PENDING"},
            "result": {"success": True, "queued": True, "job_id": queued.get("job_id")},
            "validation": {
                "risk": validation.get("risk"),
                "require_approval": validation.get("require_approval"),
                "approved": validation.get("approved"),
            },
        }

    result = ops_gateway.execute_platform_action(
        node,
        action_type=action_type,
        target=target,
        payload=body_payload,
        actor=operator,
        reason=reason,
        ticket_id=ticket_id,
        dry_run=dry_run,
    )

    trace_id = str(result.get("trace_id") or "").strip() or uuid.uuid4().hex[:16]
    message = str(result.get("message") or "")
    success = bool(result.get("success"))
    degraded = False
    if (not success) and (
        "Ops service unavailable" in message
        or "missing ops_base_url" in message
        or "Failed to establish a new connection" in message
    ):
        degraded = True
        success = True
        message = "下游 Ops 服务不可达，已降级为平台模拟执行（未实际下发服务器）"
        result = {
            **(result if isinstance(result, dict) else {}),
            "success": True,
            "status": 200,
            "degraded": True,
            "result_code": "OPS_DOWNSTREAM_UNAVAILABLE",
            "result_message": message,
        }

    trace_entry = {
        "trace_id": trace_id,
        "time": _now_iso(),
        "node": str(node.get("id") or ""),
        "node_name": str(node.get("name") or ""),
        "action": action_type,
        "target": target,
        "risk": validation.get("risk"),
        "ticket_id": ticket_id,
        "reason": reason,
        "approver": validation.get("approver"),
        "approved": bool(validation.get("approved")),
        "approval_target_id": validation.get("approval_target_id"),
        "dry_run": dry_run,
        "ok": success,
        "message": message,
        "raw": result,
        "degraded": degraded,
    }
    _append_trace(trace_entry)

    _append_event(
        {
            "id": "evt-" + uuid.uuid4().hex[:12],
            "time": _now_iso(),
            "severity": "info" if success else "critical",
            "status": "open" if not success else "resolved",
            "title": f"动作执行{'成功' if success else '失败'}：{action_type}",
            "message": f"node={node.get('id')}; target={target}; traceId={trace_id}; msg={message}",
            "trace_id": trace_id,
            "node_id": node.get("id"),
            "agent_id": str(body_payload.get("desired_agent_id") or payload.get("agent_id") or ""),
            "action_type": action_type,
            "target": target,
        }
    )

    log_audit("ops_platform_action_execute", f"action={action_type}; node={node.get('id')}; target={target}; trace={trace_id}; ok={success}")

    return {
        "ok": success,
        "message": message or ("执行成功" if success else "执行失败"),
        "trace_id": trace_id,
        "data": result.get("data") if isinstance(result.get("data"), dict) else result.get("data"),
        "result": result,
        "degraded": degraded,
        "validation": {
            "risk": validation.get("risk"),
            "require_approval": validation.get("require_approval"),
            "approved": validation.get("approved"),
        },
    }

def _build_node_onboarding(project_id: str = "") -> Dict[str, Any]:
    overview = _build_overview(project_id=project_id)
    nodes = overview.get("nodes") if isinstance(overview.get("nodes"), list) else []
    topo = overview.get("topology") if isinstance(overview.get("topology"), dict) else {"nodes": [], "edges": []}
    edge_rows = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    edges_by_node: Dict[str, int] = {}
    for e in edge_rows:
        if not isinstance(e, dict):
            continue
        frm = str(e.get("from") or "")
        to = str(e.get("to") or "")
        if frm:
            edges_by_node[frm] = edges_by_node.get(frm, 0) + 1
        if to:
            edges_by_node[to] = edges_by_node.get(to, 0) + 1

    checks: List[Dict[str, Any]] = []
    warning_count = 0
    critical_count = 0
    for n in nodes:
        nid = str(n.get("id") or "")
        issues: List[str] = []
        if not str(n.get("server_id") or ""):
            issues.append("缺少 server_id")
        if not str(n.get("ops_base_url") or ""):
            issues.append("缺少 ops_base_url")
        if not str(n.get("owner") or ""):
            issues.append("缺少 owner")
        if not str(n.get("description") or ""):
            issues.append("缺少节点说明")
        if edges_by_node.get(nid, 0) == 0:
            issues.append("No topology edges connected")
        status = str(n.get("status") or "").upper()
        severity = "ok"
        if status == "OFFLINE":
            severity = "critical"
        elif status in ("DEGRADED", "UNKNOWN"):
            severity = "warning"
        if issues and severity == "ok":
            severity = "warning"
        if severity == "critical":
            critical_count += 1
        elif severity == "warning":
            warning_count += 1
        checks.append(
            {
                "id": nid,
                "node_id": nid,
                "node_name": n.get("name"),
                "name": n.get("name"),
                "role": n.get("role"),
                "status": status or "UNKNOWN",
                "severity": severity,
                "issues": issues,
                "message": "；".join(issues) if issues else "",
                "onboarding_check": "；".join(issues) if issues else "通过",
                "edges": edges_by_node.get(nid, 0),
                "last_heartbeat": n.get("last_heartbeat"),
            }
        )
    checks.sort(key=lambda x: ({"critical": 0, "warning": 1, "ok": 2}.get(x.get("severity"), 3), x.get("node_id") or ""))
    return {
        "ok": True,
        "summary": {
            "total_nodes": len(nodes),
            "critical": critical_count,
            "warning": warning_count,
            "ok_nodes": max(0, len(nodes) - critical_count - warning_count),
        },
        "checks": checks,
    }
