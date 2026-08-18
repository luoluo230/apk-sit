# -*- coding: utf-8 -*-
"""Agents route submodule."""
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
from routes.ops import deps as ops_helpers
from routes.ops import bp



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


