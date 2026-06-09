# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
import services.ops.helpers as ops_helpers
from routes.ops import bp

@bp.route("/api/ops-platform/flow-smoke", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_flow_smoke():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    path_nodes = payload.get("path_nodes") if isinstance(payload.get("path_nodes"), list) else []
    if len(path_nodes) < 1:
        return jsonify({"ok": False, "error": "invalid_path", "message": "至少选择一个节点"}), 400
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "production")
    topology_id = str(payload.get("topology_id") or "").strip()
    actor = str(session.get("user") or "admin")
    use_runtime_direct = bool(project_id and ops_helpers._project_uses_runtime_topology(project_id))
    result_steps: List[Dict[str, Any]] = []
    success = True
    trace_ids: List[str] = []
    job_ids: List[str] = []
    seen = set()
    for nid_raw in path_nodes:
        nid = str(nid_raw or "").strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        node = ops_helpers._resolve_flow_test_node(payload, nid)
        if not node:
            result_steps.append({"node_id": nid, "ok": False, "message": "node not found"})
            success = False
            continue
        resolved_id = str(node.get("id") or nid)
        if use_runtime_direct:
            probe = ops_helpers._smoke_probe_topology_node(project_id, env_key, topology_id, node)
            ok = bool(probe.get("ok"))
            msg = str(probe.get("message") or "")
            result_steps.append({"node_id": resolved_id, "ok": ok, "message": msg, "mode": probe.get("mode") or "direct-probe"})
            if not ok:
                success = False
            continue
        req = {
            "node_id": resolved_id,
            "action_type": "smoke_test",
            "target": str(node.get("server_id") or resolved_id),
            "ticket_id": "OPS-SMOKE-" + uuid.uuid4().hex[:8],
            "reason": "flow smoke",
            "approver": actor,
            "run_mode": "agent",
            "via_agent": True,
            "payload": {"flow_smoke": True, "path_nodes": path_nodes},
        }
        validation = ops_helpers._validate_ops_request(req, node)
        if not validation.get("ok"):
            msg = "validation failed"
            if validation.get("unsupported"):
                msg = "smoke_test unsupported by agent"
            result_steps.append({"node_id": resolved_id, "ok": False, "message": msg, "validation": validation})
            success = False
            continue
        validation = ops_helpers._auto_approve_ops_request(req, node, validation, actor, "flow smoke auto approve")
        if not validation.get("ok"):
            result_steps.append({"node_id": resolved_id, "ok": False, "message": "approval failed", "validation": validation})
            success = False
            continue
        executed = ops_helpers._execute_validated(req, node, validation)
        ok = bool(executed.get("ok"))
        msg = str(executed.get("message") or "")
        trace_id = str(executed.get("trace_id") or "")
        job_id = str(((executed.get("data") or {}) if isinstance(executed.get("data"), dict) else {}).get("job_id") or "")
        if trace_id:
            trace_ids.append(trace_id)
        if job_id:
            job_ids.append(job_id)
        result_steps.append({"node_id": resolved_id, "ok": ok, "message": msg, "trace_id": trace_id, "job_id": job_id, "result": executed})
        if not ok:
            success = False
    flow_id = "flow-" + uuid.uuid4().hex[:12]
    ops_helpers._append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": ops_helpers._now_iso(), "severity": ("info" if success else "critical"), "status": ("resolved" if success else "open"), "title": "流程冒烟测试", "message": f"flow={flow_id}; nodes={len(seen)}; success={success}"})
    ops_helpers._append_bounded(OPS_FLOW_EXEC_KEY, {"flow_id": flow_id, "time": ops_helpers._now_iso(), "type": "smoke", "ok": success, "steps": result_steps}, limit=120, description="流程执行记录")
    return jsonify({"ok": success, "flow_id": flow_id, "trace_ids": trace_ids, "job_ids": job_ids, "steps": result_steps}), (200 if success else 502)



@bp.route("/api/ops-platform/stress-test", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_stress_test():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = ops_helpers._node_or_400(payload)
    if err:
        return err
    project_id = str(payload.get("project_id") or node.get("project_id") or "").strip()
    qps = int(payload.get("qps") or 300)
    duration_sec = int(payload.get("duration_sec") or 180)
    reason = str(payload.get("reason") or "stress test").strip()
    actor = str(session.get("user") or "admin")
    ticket_id = "OPS-STRESS-" + uuid.uuid4().hex[:8]
    use_direct = bool(ops_helpers._project_uses_runtime_topology(project_id))
    req = {
        "node_id": str(node.get("id") or ""),
        "action_type": "stress_test",
        "target": str(node.get("server_id") or node.get("id") or ""),
        "ticket_id": ticket_id,
        "reason": reason,
        "approver": actor,
        "run_mode": "direct" if use_direct else "agent",
        "via_agent": not use_direct,
        "payload": {"qps": qps, "duration_sec": duration_sec},
    }
    validation = ops_helpers._validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "error_code": validation.get("error_code") or "",
            "message": "压力测试请求未通过校验",
            "validation": validation,
        }), 400
    validation = ops_helpers._auto_approve_ops_request(req, node, validation, actor, "stress test auto approve")
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "approval_failed", "message": "压力测试自动审批失败", "validation": validation}), 502
    if use_direct:
        result = ops_gateway.execute_platform_action(
            node,
            action_type="stress_test",
            target=str(node.get("server_id") or node.get("id") or ""),
            payload={"qps": qps, "duration_sec": duration_sec},
            actor=actor,
            reason=reason,
            ticket_id=ticket_id,
            dry_run=False,
        )
        ok = bool(result.get("success"))
        msg = str(result.get("message") or "")
        if (not ok) and (
            "Ops service unavailable" in msg
            or "missing ops_base_url" in msg
            or "Failed to establish a new connection" in msg
        ):
            ok = True
            msg = "下游 Ops 不可达，已记录压力测试参数（本地直连模式）"
            result = {**(result if isinstance(result, dict) else {}), "success": True, "degraded": True}
        trace_id = str(result.get("trace_id") or "") or ("str-" + uuid.uuid4().hex[:16])
    else:
        result = ops_helpers._execute_validated(req, node, validation)
        ok = bool(result.get("ok"))
        msg = str(result.get("message") or "")
        trace_id = str(result.get("trace_id") or "")
    ops_helpers._append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": ops_helpers._now_iso(), "severity": ("info" if ok else "warning"), "status": ("resolved" if ok else "open"), "title": "压力测试触发", "message": f"node={node.get('id')}; qps={qps}; duration={duration_sec}s; ok={ok}"})
    return jsonify({
        "ok": ok,
        "message": msg,
        "trace_id": trace_id,
        "job_id": ((result.get("data") or {}) if isinstance(result.get("data"), dict) else {}).get("job_id") if isinstance(result, dict) else None,
        "result": result if isinstance(result, dict) else {},
    }), (200 if ok else 502)















@bp.route("/api/ops-platform/actions/validate", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_actions_validate():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = ops_helpers._action_target_or_400(payload)
    if err:
        return err

    validation = ops_helpers._validate_ops_request(payload, node)
    if not validation.get("ok"):
        if validation.get("unsupported"):
            return jsonify({
                "ok": False,
                "error": "unsupported_action",
                "error_code": validation.get("error_code") or "OPS_ACTION_UNSUPPORTED",
                "message": "该动作未接入 game-server Agent 能力，请更换动作。",
                "action_type": validation.get("action_type"),
                "supported_actions": validation.get("agent_supported_actions") or [],
            }), 400
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "message": "缺少必填字段: " + ", ".join(validation.get("missing") or []),
            "missing": validation.get("missing") or [],
            "risk": validation.get("risk"),
            "require_approval": validation.get("require_approval"),
            "approval_target_id": validation.get("approval_target_id"),
            "approved": validation.get("approved"),
        }), 400

    return jsonify({
        "ok": True,
        "message": "预检通过",
        "risk": validation.get("risk"),
        "domain": validation.get("domain"),
        "require_approval": validation.get("require_approval"),
        "approval_target_id": validation.get("approval_target_id"),
        "approved": validation.get("approved"),
    })



@bp.route("/api/ops-platform/actions/approval", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_actions_approval():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = ops_helpers._action_target_or_400(payload)
    if err:
        return err

    validation = ops_helpers._validate_ops_request(payload, node)
    if not validation.get("require_approval"):
        return jsonify({"ok": False, "error": "approval_not_required", "message": "Approval is not required for this action"}), 400

    reason = validation.get("reason") or "ops action approval"
    aid = create_approval(
        "gm_ops_action",
        str(session.get("user") or "unknown"),
        "ops_action",
        validation.get("approval_target_id") or "",
        reason=reason,
        project_id=str(node.get("project_id") or payload.get("project_id") or ""),
    )
    log_audit("ops_platform_action_approval_create", f"approval={aid}; target={validation.get('approval_target_id')}")

    return jsonify({
        "ok": True,
        "message": "Approval request created. Execute after it is approved.",
        "approval_id": aid,
        "approval_target_id": validation.get("approval_target_id"),
        "approval_center": "/admin/approval",
    })



@bp.route("/api/ops-platform/actions/execute", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_actions_execute():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = ops_helpers._action_target_or_400(payload)
    if err:
        return err

    project_id = str(payload.get("project_id") or node.get("project_id") or "").strip()
    freeze = ops_helpers._change_freeze_for_project(project_id)
    validation = ops_helpers._validate_ops_request(payload, node)
    if not validation.get("ok"):
        if validation.get("unsupported"):
            return jsonify({
                "ok": False,
                "error": "unsupported_action",
                "error_code": validation.get("error_code") or "OPS_ACTION_UNSUPPORTED",
                "message": "该动作未接入 game-server Agent 能力，请更换动作。",
                "action_type": validation.get("action_type"),
                "supported_actions": validation.get("agent_supported_actions") or [],
            }), 400
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "message": "缺少必填字段: " + ", ".join(validation.get("missing") or []),
            "missing": validation.get("missing") or [],
            "risk": validation.get("risk"),
            "require_approval": validation.get("require_approval"),
        }), 400

    if freeze.get("active") and validation.get("require_approval") and not validation.get("dry_run"):
        return jsonify({
            "ok": False,
            "error": "change_freeze_active",
            "message": "项目处于变更冻结窗口，高危动作已禁止执行",
            "freeze_reason": str(freeze.get("reason") or ""),
        }), 423

    if validation.get("require_approval") and (not validation.get("dry_run")) and (not validation.get("approved")):
        return jsonify({
            "ok": False,
            "error": "approval_required",
            "message": "High risk action requires approval before execute.",
            "approval_target_id": validation.get("approval_target_id"),
            "approval_center": "/admin/approval",
        }), 412

    result = ops_helpers._execute_validated(payload, node, validation)
    status = 200 if result.get("ok") else 502
    return jsonify(result), status



@bp.route("/api/ops-platform/actions/<trace_id>")
@admin_required("gm_ops")
def ops_platform_action_detail(trace_id: str):
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    item = ops_helpers._find_trace(trace_id)
    if not item:
        return jsonify({"ok": False, "error": "trace_not_found"}), 404
    return jsonify({"ok": True, "trace": item})






















