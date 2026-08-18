# -*- coding: utf-8 -*-
"""Agents route submodule."""
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
from routes.ops import deps as ops_helpers
from routes.ops import bp

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

