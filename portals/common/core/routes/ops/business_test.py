# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
from services.business_test_catalog import (
    build_catalog_view,
    delete_custom_plan,
    get_plan,
    list_plans,
    save_custom_plan,
    validate_plan_dict,
)
from routes.ops import deps as ops_helpers
from routes.ops import bp

@bp.route("/api/ops-platform/business-test/catalog", methods=["GET"])
@admin_required("gm_ops")
def ops_platform_business_test_catalog():
    repo = ops_helpers._business_test_repo()
    return jsonify(build_catalog_view(repo))



@bp.route("/api/ops-platform/business-test/plans", methods=["GET", "POST"])
@admin_required("gm_ops")
def ops_platform_business_test_plans():
    repo = ops_helpers._business_test_repo()
    if request.method == "GET":
        category = str(request.args.get("category") or "").strip()
        return jsonify(list_plans(repo, category))
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "invalid_body"}), 400
    result = save_custom_plan(payload, repo)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)



@bp.route("/api/ops-platform/business-test/plans/<plan_id>", methods=["GET", "DELETE"])
@admin_required("gm_ops")
def ops_platform_business_test_plan_detail(plan_id: str):
    repo = ops_helpers._business_test_repo()
    pid = str(plan_id or "").strip()
    if request.method == "GET":
        plan = get_plan(repo, pid)
        if not plan:
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True, "plan": plan})
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    builtin = get_plan(repo, pid)
    if builtin and str(builtin.get("source") or "") == "builtin":
        return jsonify({"ok": False, "error": "builtin_readonly"}), 400
    return jsonify(delete_custom_plan(pid))



@bp.route("/api/ops-platform/business-test/run", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_business_test_run():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    plan_id = str(payload.get("plan_id") or "").strip()
    plan_override = payload.get("plan_override") if isinstance(payload.get("plan_override"), dict) else None
    transport = str(payload.get("transport") or "websocket").strip().lower()
    user_prefix = str(payload.get("user_prefix") or "biztest").strip()
    server_id = str(payload.get("server_id") or "game-cn-1").strip()
    if plan_override:
        issues = validate_plan_dict(plan_override, ops_helpers._business_test_repo())
        if issues:
            return jsonify({"ok": False, "error": "plan_invalid", "issues": issues}), 400
        plan_id = str(plan_override.get("plan_id") or plan_id or "custom-inline")
    elif not plan_id:
        return jsonify({"ok": False, "error": "missing_plan_id"}), 400
    elif not get_plan(ops_helpers._business_test_repo(), plan_id):
        return jsonify({"ok": False, "error": "plan_not_found", "plan_id": plan_id}), 404
    gateway_endpoint = ops_helpers._resolve_business_test_gateway_endpoint(payload)
    preflight = ops_helpers._business_test_preflight(transport, gateway_endpoint)
    if not preflight.get("ok"):
        flow_id = "biz-" + uuid.uuid4().hex[:12]
        fail_result = {
            "ok": False,
            "preflight": preflight,
            "plan_id": plan_id,
            "transport": transport,
            "steps": [],
            "message": preflight.get("message") or "business test preflight failed",
            "summary": preflight.get("message") or "business test preflight failed",
        }
        ops_helpers._append_bounded(
            OPS_FLOW_EXEC_KEY,
            {"flow_id": flow_id, "time": ops_helpers._now_iso(), "type": "business_test", "ok": False, "plan_id": plan_id, "transport": transport, "preflight_failed": True},
            limit=120,
            description="业务测试执行记录",
        )
        return jsonify({"ok": False, "flow_id": flow_id, **fail_result}), 502
    result = ops_helpers._run_business_test_runner(
        plan_id, transport, plan_override, user_prefix, server_id, gateway_endpoint
    )
    result["preflight"] = preflight
    result["gateway_endpoint"] = gateway_endpoint
    flow_id = "biz-" + uuid.uuid4().hex[:12]
    ops_helpers._append_bounded(
        OPS_FLOW_EXEC_KEY,
        {"flow_id": flow_id, "time": ops_helpers._now_iso(), "type": "business_test", "ok": result.get("ok"), "plan_id": plan_id, "transport": transport},
        limit=120,
        description="业务测试执行记录",
    )
    return jsonify({"ok": bool(result.get("ok")), "flow_id": flow_id, **result}), (200 if result.get("ok") else 502)



@bp.route("/api/ops-platform/db-migration", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_db_migration():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = ops_helpers._node_or_400(payload)
    if err:
        return err
    direction = str(payload.get("direction") or "up").strip().lower()
    version = str(payload.get("version") or "").strip()
    reason = str(payload.get("reason") or "db migration").strip()
    if str(node.get("role") or "") not in ("database", "cache"):
        return jsonify({"ok": False, "error": "invalid_role", "message": "Only database/cache nodes support db migration"}), 400
    cmd = str(payload.get("command") or node.get("daemon_start_cmd") or "").strip()

    native = ops_gateway.execute_platform_action(
        node,
        action_type="db_migration",
        target=str(node.get("server_id") or ""),
        payload={"direction": direction, "version": version, "command": cmd},
        actor=str(session.get("user") or "intranet-ops"),
        reason=reason,
        ticket_id="OPS-DB-MIGRATION",
        dry_run=False,
    )
    if native.get("success"):
        trace_id = "mig-" + uuid.uuid4().hex[:16]
        ops_helpers._append_trace({
            "trace_id": trace_id,
            "time": ops_helpers._now_iso(),
            "node": str(node.get("id") or ""),
            "node_name": str(node.get("name") or ""),
            "action": "db_migration",
            "target": str(node.get("server_id") or ""),
            "risk": "high",
            "ticket_id": "OPS-DB-MIGRATION",
            "reason": reason,
            "approver": str(session.get("user") or "intranet-ops"),
            "approved": True,
            "dry_run": False,
            "ok": True,
            "message": str(native.get("message") or "Migration accepted"),
            "raw": native,
        })
        ops_helpers._append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": ops_helpers._now_iso(), "severity": "info", "status": "resolved", "title": "DB Migration", "message": f"node={node.get('id')}; direction={direction}; version={version}; mode=native"})
        log_audit("ops_platform_db_migration", f"node={node.get('id')}; direction={direction}; version={version}; mode=native")
        return jsonify({"ok": True, "message": native.get("message") or "Migration accepted", "trace_id": trace_id, "job_id": None, "result": native})

    if not cmd:
        return jsonify({"ok": False, "error": "native_failed_no_command", "message": f"原生迁移能力失败且未提供本地命令: {native.get('message') or 'unknown'}"}), 502

    code = subprocess.call(cmd, shell=True)
    ok = code == 0
    ops_helpers._set_daemon_state(str(node.get("id") or ""), {"last_action": f"db_migration_{direction}", "last_error": ("" if ok else f"exit_code={code}")})
    trace_id = "mig-" + uuid.uuid4().hex[:16]
    ops_helpers._append_trace({
        "trace_id": trace_id,
        "time": ops_helpers._now_iso(),
        "node": str(node.get("id") or ""),
        "node_name": str(node.get("name") or ""),
        "action": "db_migration",
        "target": str(node.get("server_id") or ""),
        "risk": "high",
        "ticket_id": "OPS-DB-MIGRATION",
        "reason": reason,
        "approver": str(session.get("user") or "intranet-ops"),
        "approved": True,
        "dry_run": False,
        "ok": ok,
        "message": ("Migration success (fallback)" if ok else "Migration failed (fallback)"),
        "raw": {"exit_code": code, "native_error": native.get("message"), "mode": "fallback"},
    })
    ops_helpers._append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": ops_helpers._now_iso(), "severity": ("info" if ok else "critical"), "status": ("resolved" if ok else "open"), "title": "DB Migration", "message": f"node={node.get('id')}; direction={direction}; version={version}; mode=fallback; code={code}"})
    log_audit("ops_platform_db_migration", f"node={node.get('id')}; direction={direction}; version={version}; mode=fallback; code={code}")
    return jsonify({"ok": ok, "message": ("Migration success (fallback)" if ok else "Migration failed (fallback)"), "trace_id": trace_id, "job_id": None, "exit_code": code, "native_error": native.get("message")}), (200 if ok else 502)


