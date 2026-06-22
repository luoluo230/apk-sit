# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import create_approval, log_audit
from services.authz import admin_required
import services.ops.helpers as ops_helpers
from routes.ops import bp

@bp.route("/api/ops-platform/runtime/flow-control", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_runtime_flow_control():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    op = str(payload.get("op") or "").strip().lower()
    if op not in ("start", "stop"):
        return jsonify({"ok": False, "error": "invalid_op", "message": "op must be start or stop"}), 400
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    actor = str(session.get("user") or "admin")
    policy = ops_helpers._load_agent_policy()
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    scoped_project_id = str(registry.get("project_id") or project_id or "")
    scoped_env_key = str(registry.get("env_key") or env_key or "production")
    scoped_topology_id = str(registry.get("topology_id") or topology_id or "")
    current_active = ops_helpers._runtime_active_for_scope(scoped_project_id, scoped_env_key, scoped_topology_id)
    freeze = ops_helpers._change_freeze_for_project(scoped_project_id)
    if op == "start" and freeze.get("active"):
        return jsonify({
            "ok": False,
            "error": "change_freeze_active",
            "message": "项目处于变更冻结窗口，禁止启动拓扑运行",
            "freeze_reason": str(freeze.get("reason") or ""),
        }), 423

    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    topo_edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    node_ids: List[str] = [str(n.get("id") or "").strip() for n in topo_nodes if isinstance(n, dict) and str(n.get("id") or "").strip()]
    if not node_ids:
        return jsonify({"ok": False, "error": "empty_topology", "message": "当前项目没有可执行节点"}), 400

    run_id = "run-" + uuid.uuid4().hex[:12]
    if op == "start" and ops_helpers._project_uses_runtime_topology(scoped_project_id):
        ops_helpers._cancel_runtime_start_runs_for_scope(scoped_project_id, scoped_env_key, scoped_topology_id, except_run_id=run_id)
    elif op == "start" and current_active.get("active"):
        return jsonify({"ok": False, "error": "topology_run_active", "message": "当前拓扑已有运行中的流程", "run_id": str(current_active.get("run_id") or "")}), 409

    action_type = "start" if op == "start" else "stop"
    now = ops_helpers._now_iso()
    logs: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    bindings = ops_helpers._load_scope_agent_bindings(scoped_topology_id)
    service_bindings = ops_helpers._load_scope_service_bindings(scoped_topology_id)

    if op == "start" and ops_helpers._project_uses_runtime_topology(scoped_project_id):
        run_obj = {
            "run_id": run_id,
            "project_id": scoped_project_id,
            "env_key": scoped_env_key,
            "topology_id": scoped_topology_id,
            "topology_name": str(registry.get("name") or ""),
            "op": op,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "items": [],
            "logs": [],
        }
        ops_helpers._upsert_runtime_run(run_obj)
        cluster = ops_helpers._spawn_runtime_start_orchestration(
            run_id,
            scoped_project_id,
            scoped_env_key,
            scoped_topology_id,
            topo_nodes,
            topo_edges,
            service_bindings,
            bindings,
            actor,
        )
        items = cluster.get("items") if isinstance(cluster.get("items"), list) else []
        logs = cluster.get("logs") if isinstance(cluster.get("logs"), list) else []
        run_obj["items"] = items
        run_obj["logs"] = logs
        ops_helpers._upsert_runtime_run(run_obj)
        return jsonify({
            "ok": True,
            "run_id": run_id,
            "status": "running",
            "project_id": scoped_project_id,
            "env_key": scoped_env_key,
            "topology_id": scoped_topology_id,
            "items": items,
            "logs": logs,
        })

    if op == "stop" and ops_helpers._project_uses_runtime_topology(scoped_project_id):
        ops_helpers._cancel_runtime_start_runs_for_scope(scoped_project_id, scoped_env_key, scoped_topology_id, except_run_id=run_id)
        run_obj = {
            "run_id": run_id,
            "project_id": scoped_project_id,
            "env_key": scoped_env_key,
            "topology_id": scoped_topology_id,
            "topology_name": str(registry.get("name") or ""),
            "op": op,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "items": [],
            "logs": [],
        }
        ops_helpers._upsert_runtime_run(run_obj)
        cluster = ops_helpers._spawn_runtime_stop_orchestration(
            run_id,
            scoped_project_id,
            scoped_env_key,
            scoped_topology_id,
            topo_nodes,
            topo_edges,
            service_bindings,
            bindings,
            actor,
        )
        items = cluster.get("items") if isinstance(cluster.get("items"), list) else []
        logs = cluster.get("logs") if isinstance(cluster.get("logs"), list) else []
        run_obj["items"] = items
        run_obj["logs"] = logs
        ops_helpers._upsert_runtime_run(run_obj)
        return jsonify({
            "ok": True,
            "run_id": run_id,
            "status": "running",
            "project_id": scoped_project_id,
            "env_key": scoped_env_key,
            "topology_id": scoped_topology_id,
            "items": items,
            "logs": logs,
        })

    reg_v2 = ops_helpers._load_agent_registry_v2()
    fresh_sec = max(20, int(policy.get("agent_online_fresh_sec") or 120))
    cluster_status = ops_helpers._fetch_cluster_runtime_status(
        [x for x in reg_v2.values() if isinstance(x, dict) and str(x.get("project_id") or "") in ("", scoped_project_id)]
    )
    stop_node_ids = list(reversed(node_ids)) if op == "stop" else node_ids

    for nid in stop_node_ids:
        topo_node = next((x for x in topo_nodes if isinstance(x, dict) and str(x.get("id") or "") == nid), None)
        node = ops_helpers._build_runtime_node_from_topology_node(scoped_project_id, scoped_env_key, topo_node or {}, scoped_topology_id) if topo_node else None
        if not node:
            logs.append({"ts": ops_helpers._now_iso(), "level": "error", "node_id": nid, "message": "节点不存在，已跳过"})
            continue
        bound_agent = str(bindings.get(nid) or "")
        bound_desc = reg_v2.get(bound_agent) if bound_agent else None
        online = bool(bound_desc and str(bound_desc.get("status") or "").upper() in ("ONLINE", "READY", "RUNNING"))
        probe_ok = bool(bound_desc and str(bound_desc.get("probe_status") or "").upper() == "PASS")
        fresh = False
        hb_age = -1.0
        if bound_desc and bound_desc.get("last_seen"):
            try:
                hb = datetime.fromisoformat(str(bound_desc.get("last_seen")).replace("Z", ""))
                hb_age = (datetime.utcnow() - hb).total_seconds()
                fresh = hb_age <= fresh_sec
            except Exception:
                fresh = False
                hb_age = -1.0
        online = online and fresh and probe_ok
        use_agent_mode = online
        desired_role = str(node.get("role") or "")
        current_runtime = bound_desc.get("runtime") if isinstance(bound_desc, dict) and isinstance(bound_desc.get("runtime"), dict) else {}
        current_role = str(current_runtime.get("current_role") or current_runtime.get("role") or "")
        current_state = str(current_runtime.get("state") or bound_desc.get("run_state") or "").upper()
        cluster_live = bool(op == "start" and probe_ok and ops_helpers._cluster_state_is_online(cluster_status.get(nid)))
        if op == "start" and use_agent_mode and (
            cluster_live
            or (
                desired_role
                and current_role == desired_role
                and current_state in ("RUNNING", "ONLINE", "READY", "SUCCESS")
            )
            or (
                probe_ok
                and current_state in ("RUNNING", "ONLINE", "READY", "SUCCESS")
                and ops_helpers._is_embedded_cluster_agent(bound_desc or {"node_id": nid})
            )
        ):
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS", "mode": "agent-reuse"})
            msg = f"复用已运行服务: role={desired_role or current_role or '-'}; cluster={'live' if cluster_live else 'runtime'}"
            logs.append({"ts": ops_helpers._now_iso(), "level": "info", "node_id": nid, "message": msg})
            continue
        req = {
            "node_id": nid,
            "action_type": action_type,
            "target": nid,
            "ticket_id": "OPS-RUN-" + run_id[-6:],
            "reason": "拓扑运行模式一键" + ("启动" if op == "start" else "停止"),
            "approver": actor,
            "run_mode": "agent" if use_agent_mode else "direct",
            "via_agent": bool(use_agent_mode),
            "payload": {
                "run_mode": "agent" if use_agent_mode else "direct",
                "desired_role": desired_role,
                "desired_server_id": str(node.get("server_id") or ""),
                "switch_required": bool(op == "start" and use_agent_mode and desired_role and current_role and current_role != desired_role),
                "current_role": current_role,
                "launch_visible_console": bool(op == "start"),
            },
        }
        validation = ops_helpers._validate_ops_request(req, node)
        if not validation.get("ok"):
            logs.append({"ts": ops_helpers._now_iso(), "level": "error", "node_id": nid, "message": "参数校验失败: " + ",".join(validation.get("missing") or [])})
            continue
        if validation.get("require_approval") and not validation.get("approved"):
            aid = create_approval(
                "gm_ops_action",
                actor,
                "ops_action",
                str(validation.get("approval_target_id") or ""),
                reason=str(validation.get("reason") or "runtime run"),
                project_id=str(node.get("project_id") or project_id),
            )
            ok, err = approve_or_reject(aid, actor, "approve", "runtime one-click auto approve")
            if not ok:
                logs.append({"ts": ops_helpers._now_iso(), "level": "error", "node_id": nid, "message": "自动审批失败: " + str(err or "unknown")})
                continue
            req["approval_id"] = aid
            validation = ops_helpers._validate_ops_request(req, node)
        if bool((req.get("payload") or {}).get("switch_required")):
            logs.append(
                {
                    "ts": ops_helpers._now_iso(),
                    "level": "warn",
                    "node_id": nid,
                    "message": f"远端Agent当前类型为 {current_role or '-'}，将先停止后切换到 {desired_role or '-'}",
                }
            )
        result = ops_helpers._execute_validated(req, node, validation)
        if not result.get("ok"):
            logs.append({"ts": ops_helpers._now_iso(), "level": "error", "node_id": nid, "message": str(result.get("message") or result.get("error") or "execute failed")})
            continue
        job_id = str(((result.get("data") or {}).get("job_id")) or "")
        trace_id = str(result.get("trace_id") or "")
        if use_agent_mode and job_id:
            items.append({"node_id": nid, "job_id": job_id, "trace_id": trace_id, "status": "PENDING", "mode": "agent"})
            logs.append({"ts": ops_helpers._now_iso(), "level": "info", "node_id": nid, "job_id": job_id, "message": "已入队: " + job_id})
        else:
            items.append({"node_id": nid, "job_id": "", "trace_id": trace_id, "status": "SUCCESS", "mode": "direct"})
            reason = "agent_missing"
            if bound_agent and not bound_desc:
                reason = "agent_not_registered"
            elif bound_desc and str(bound_desc.get("status") or "").upper() not in ("ONLINE", "READY", "RUNNING"):
                reason = "agent_status_" + str(bound_desc.get("status") or "UNKNOWN")
            elif bound_desc and str(bound_desc.get("probe_status") or "").upper() != "PASS":
                reason = "agent_probe_not_pass"
            elif bound_desc and not fresh:
                reason = "agent_heartbeat_stale"
            detail = f"未命中在线Agent，已走直连执行; reason={reason}; bound_agent={bound_agent or '-'}; hb_age_sec={(round(hb_age,1) if hb_age >= 0 else '-')}; fresh_sec={fresh_sec}"
            logs.append({"ts": ops_helpers._now_iso(), "level": "warn", "node_id": nid, "message": detail})

    run_obj = {
        "run_id": run_id,
        "project_id": scoped_project_id,
        "env_key": scoped_env_key,
        "topology_id": scoped_topology_id,
        "topology_name": str(registry.get("name") or ""),
        "op": op,
        "status": "queued",
        "created_at": now,
        "updated_at": ops_helpers._now_iso(),
        "items": items,
        "logs": logs,
    }
    ops_helpers._upsert_runtime_run(run_obj)
    return jsonify({"ok": True, "run_id": run_id, "status": run_obj.get("status"), "project_id": scoped_project_id, "env_key": scoped_env_key, "topology_id": scoped_topology_id, "items": items, "logs": logs})



@bp.route("/api/ops-platform/runtime/flow-status")
@admin_required("gm_ops")
def ops_platform_runtime_flow_status():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    run_id = str(request.args.get("run_id") or "").strip()
    run_obj = ops_helpers._find_runtime_run(run_id)
    if not run_obj:
        return jsonify({"ok": False, "error": "run_not_found"}), 404

    jobs = ops_helpers._load_agent_jobs()
    job_map = {str(j.get("job_id") or ""): j for j in jobs if isinstance(j, dict) and j.get("job_id")}
    changed_logs: List[Dict[str, Any]] = []
    done = 0
    fail = 0
    items = run_obj.get("items") if isinstance(run_obj.get("items"), list) else []
    created_at = str(run_obj.get("created_at") or "")
    timed_out = False
    try:
        base_dt = datetime.fromisoformat(created_at.replace("Z", ""))
        timed_out = (datetime.utcnow() - base_dt).total_seconds() > 90
    except Exception:
        timed_out = False

    for item in items:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("job_id") or "")
        prev = str(item.get("status") or "PENDING")
        row = job_map.get(job_id) or {}
        cur = str(row.get("status") or prev or "PENDING").upper()
        if timed_out and cur in ("PENDING", "LEASED", "RUNNING"):
            cur = "TIMEOUT"
        item["status"] = cur
        if cur in ("SUCCESS", "FAILED", "TIMEOUT", "CANCELED", "SKIPPED"):
            done += 1
        if cur in ("FAILED", "TIMEOUT", "CANCELED"):
            fail += 1
        if cur != prev:
            msg = f"{item.get('node_id')}: {prev} -> {cur}"
            changed_logs.append({"ts": ops_helpers._now_iso(), "level": "error" if cur in ("FAILED", "TIMEOUT", "CANCELED") else "info", "node_id": item.get("node_id"), "job_id": job_id, "message": msg})

    run_logs = run_obj.get("logs") if isinstance(run_obj.get("logs"), list) else []
    run_logs.extend(changed_logs)
    if len(run_logs) > 400:
        run_logs = run_logs[-400:]
    run_obj["logs"] = run_logs
    total = len([x for x in items if isinstance(x, dict)])
    if total == 0:
        run_obj["status"] = "failed"
    elif done >= total:
        run_obj["status"] = "failed" if fail > 0 else "success"
    else:
        run_obj["status"] = "running"
    run_obj["updated_at"] = ops_helpers._now_iso()
    ops_helpers._upsert_runtime_run(run_obj)
    debug_obj = {
        "server_time": ops_helpers._now_iso(),
        "run_updated_at": run_obj.get("updated_at"),
        "timed_out": bool(timed_out),
        "status_histogram": {
            "PENDING": len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() == "PENDING"]),
            "LEASED": len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() == "LEASED"]),
            "RUNNING": len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() == "RUNNING"]),
            "SUCCESS": len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() == "SUCCESS"]),
            "FAILED": len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() == "FAILED"]),
            "TIMEOUT": len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() == "TIMEOUT"]),
            "CANCELED": len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() == "CANCELED"]),
        },
    }
    return jsonify({
        "ok": True,
        "run_id": run_obj.get("run_id"),
        "project_id": str(run_obj.get("project_id") or ""),
        "env_key": str(run_obj.get("env_key") or ""),
        "topology_id": str(run_obj.get("topology_id") or ""),
        "topology_name": str(run_obj.get("topology_name") or ""),
        "op": run_obj.get("op"),
        "status": run_obj.get("status"),
        "done": done,
        "total": total,
        "failed": fail,
        "items": items,
        "logs": run_logs[-120:],
        "debug": debug_obj,
    })



@bp.route("/api/ops-platform/runtime/active")
@admin_required("gm_ops")
def ops_platform_runtime_active():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    ctx = ops_helpers._resolve_topology_context(project_id, env_key, topology_id)
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    info = ops_helpers._runtime_active_for_scope(str(row.get("project_id") or project_id or ""), str(row.get("env_key") or env_key or ""), str(row.get("topology_id") or topology_id or ""))
    scoped_pid = str(row.get("project_id") or project_id or "")
    scoped_env = str(row.get("env_key") or env_key or "")
    scoped_tid = str(row.get("topology_id") or topology_id or "")
    live_verified = False
    live_count = 0
    live_total = 0
    if scoped_pid and scoped_tid and ops_helpers._project_uses_runtime_topology(scoped_pid):
        try:
            topo = ops_helpers._load_topology_scoped(scoped_pid, scoped_env, scoped_tid)
            topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
            bindings = ops_helpers._load_scope_service_bindings(scoped_tid)
            probe_stat = ops_helpers._refresh_runtime_service_probes_from_topology(scoped_pid, scoped_env, scoped_tid, topo_nodes, bindings)
            live_count = int(probe_stat.get("live_count") or 0)
            live_total = int(probe_stat.get("total") or 0)
            live_verified = bool(live_total > 0 and live_count >= live_total and probe_stat.get("gateway_live"))
        except Exception:
            live_verified = False
    return jsonify({
        "ok": True,
        "project_id": scoped_pid,
        "env_key": scoped_env,
        "topology_id": scoped_tid,
        "active": bool(info.get("active")),
        "run_id": str(info.get("run_id") or ""),
        "status": str(info.get("status") or ""),
        "reason": str(info.get("reason") or ""),
        "live_verified": live_verified,
        "live_count": live_count,
        "live_total": live_total,
    })


