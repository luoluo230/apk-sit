# -*- coding: utf-8 -*-
"""Topology route submodule."""
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import create_approval, get_channels_for_project, log_audit, project_versions_db
from services.authz import admin_required
from services.release.topology_binding_service import (
    build_topology_binding_picker,
    delete_topology_binding,
    delete_topology_binding_for_scope,
    list_topology_bindings,
    resolve_topology_binding,
    upsert_topology_binding,
)
from routes.ops import deps as ops_helpers
from routes.ops import bp

from routes.ops.topology_helpers import project_binding_catalog, project_topology_catalog


@bp.route("/api/ops-platform/topology")
@admin_required("gm_ops")
def ops_platform_topology():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    return jsonify({
        "ok": True,
        "project_id": str(registry.get("project_id") or project_id or ""),
        "env_key": str(registry.get("env_key") or env_key or ""),
        "topology_id": str(registry.get("topology_id") or topology_id or ""),
        "registry": registry,
        "topologies": topo.get("topologies") if isinstance(topo.get("topologies"), list) else [],
        "topology": {"nodes": topo.get("nodes") or [], "edges": topo.get("edges") or [], "meta": topo.get("meta") or {}},
        "node_count": len(topo.get("nodes") or []),
    })



@bp.route("/api/ops-platform/topology/workbench-mode", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_workbench_mode():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    workbench_mode = str(payload.get("workbench_mode") or "").strip().lower()
    locked_mode = str(payload.get("workbench_locked_mode") if payload.get("workbench_locked_mode") is not None else "").strip().lower()
    if workbench_mode and workbench_mode not in ("edit", "run", "test"):
        return jsonify({"ok": False, "error": "invalid_mode", "message": "无效的工作台模式"}), 400
    if locked_mode and locked_mode not in ("edit", "run", "test"):
        return jsonify({"ok": False, "error": "invalid_locked_mode", "message": "无效的锁定模式"}), 400
    scoped = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "").strip()
    pid = str(registry.get("project_id") or project_id or "").strip()
    env = ops_helpers._normalize_env_key(registry.get("env_key") or env_key or "production")
    nodes = scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else []
    if not tid or not nodes:
        return jsonify({"ok": False, "error": "topology_not_found", "message": "未找到拓扑或拓扑为空"}), 404
    meta = scoped.get("meta") if isinstance(scoped.get("meta"), dict) else {}
    if workbench_mode in ("edit", "run", "test"):
        meta["workbench_mode"] = workbench_mode
    if "workbench_locked_mode" in payload:
        meta["workbench_locked_mode"] = locked_mode if locked_mode in ("edit", "run", "test") else ""
        if locked_mode in ("edit", "run", "test"):
            meta["workbench_mode"] = locked_mode
    meta["workbench_mode_updated_at"] = ops_helpers._now_iso()
    saved = ops_helpers._save_topology_scoped(
        pid,
        env,
        tid,
        {
            "nodes": nodes,
            "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
            "meta": meta,
        },
    )
    saved_meta = saved.get("meta") if isinstance(saved.get("meta"), dict) else meta
    log_audit(
        "ops_platform_topology_workbench_mode",
        f"topology={tid}; mode={saved_meta.get('workbench_mode')}; locked={saved_meta.get('workbench_locked_mode') or ''}",
    )
    return jsonify({
        "ok": True,
        "workbench_mode": str(saved_meta.get("workbench_mode") or "edit"),
        "workbench_locked_mode": str(saved_meta.get("workbench_locked_mode") or ""),
        "workbench_mode_updated_at": str(saved_meta.get("workbench_mode_updated_at") or ""),
    })



@bp.route("/api/ops-platform/topology/save", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_save():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    topo = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
    valid, errors = ops_helpers._validate_topology_contract(topo)
    if not valid:
        return jsonify({"ok": False, "error": "topology_contract_invalid", "message": "；".join(errors), "errors": errors}), 400
    ctx = ops_helpers._resolve_topology_context(project_id, env_key, topology_id)
    registry = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    pid = str(registry.get("project_id") or project_id or "")
    tid = str(registry.get("topology_id") or topology_id or "")
    agent_stat = ops_helpers._upsert_agents_from_topology(pid, saved.get("nodes") if isinstance(saved.get("nodes"), list) else [])
    purge_stat = {}
    saved_meta = saved.get("meta") if isinstance(saved.get("meta"), dict) else {}
    if saved_meta.get("runtime_topology") or ops_helpers._project_uses_runtime_topology(pid):
        purge_stat = ops_helpers._purge_design_demo_project_state(pid, tid)
    sync_result = ops_helpers._sync_topology_to_game_server(pid, str(registry.get("env_key") or env_key or ""), tid, str(session.get("user") or "admin"))
    canonical_stat = ops_helpers._consolidate_runtime_agents_to_canonical(pid)
    log_audit("ops_platform_topology_save", f"project={registry.get('project_id') or project_id}; env={registry.get('env_key') or env_key}; topology={registry.get('topology_id') or topology_id}; nodes={len((saved.get('nodes') or []))}; edges={len((saved.get('edges') or []))}")
    return jsonify({
        "ok": True,
        "message": "Topology saved",
        "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}},
        "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry,
        "agents": agent_stat,
        "purge": purge_stat,
        "sync": sync_result,
        "canonical": canonical_stat,
    })



@bp.route("/api/ops-platform/topology/node/update", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_update():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
    if not node_id:
        return jsonify({"ok": False, "error": "missing node_id"}), 400

    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    target = None
    for item in topo.get("nodes") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == node_id:
            target = item
            break
    if not target:
        return jsonify({"ok": False, "error": "node not found"}), 404

    if "role" in patch:
        target["role"] = str(patch.get("role") or "business")
    if "name" in patch:
        target["name"] = str(patch.get("name") or target.get("id") or "")
    if "kind" in patch:
        target["kind"] = ops_helpers._infer_node_kind(str(target.get("role") or "business"), str(patch.get("kind") or ""))
    if "desc" in patch:
        target["desc"] = str(patch.get("desc") or "")
    if "bizStatus" in patch:
        target["bizStatus"] = str(patch.get("bizStatus") or "normal")
    if "owner" in patch:
        target["owner"] = str(patch.get("owner") or "")
    if "x" in patch:
        try:
            target["x"] = float(patch.get("x"))
        except Exception:
            pass
    if "y" in patch:
        try:
            target["y"] = float(patch.get("y"))
        except Exception:
            pass
    if "tags" in patch and isinstance(patch.get("tags"), list):
        target["tags"] = patch.get("tags")
    if "preset_id" in patch:
        target["preset_id"] = str(patch.get("preset_id") or "").strip()
    if "daemon_start_cmd" in patch:
        target["daemon_start_cmd"] = str(patch.get("daemon_start_cmd") or "").strip()
    if "daemon_stop_cmd" in patch:
        target["daemon_stop_cmd"] = str(patch.get("daemon_stop_cmd") or "").strip()
    if "daemon_port" in patch:
        try:
            target["daemon_port"] = int(patch.get("daemon_port") or 0)
        except Exception:
            pass
    if "ui" in patch and isinstance(patch.get("ui"), dict):
        target["ui"] = patch.get("ui")
    if not isinstance(target.get("ui"), dict):
        target["ui"] = {}
    target["kind"] = ops_helpers._infer_node_kind(str(target.get("role") or "business"), str(target.get("kind") or ""))
    target["ui"]["ports"] = ops_helpers._normalize_ports(str(target.get("kind") or "standard"), target["ui"].get("ports"))
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)

    log_audit("ops_platform_topology_node_update", f"node={node_id}")
    return jsonify({"ok": True, "message": "节点属性已更新", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology/node/clone", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_clone():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    src = next((x for x in nodes if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not src:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    clone = copy.deepcopy(src)
    new_id = f"{node_id}-copy-{uuid.uuid4().hex[:4]}"
    clone["id"] = new_id
    clone["name"] = f"{str(src.get('name') or node_id)} 副本"
    clone["server_id"] = str(src.get("server_id") or new_id)
    ui = clone.get("ui") if isinstance(clone.get("ui"), dict) else {}
    try:
        clone["x"] = float(src.get("x") or ui.get("x") or 120) + 48.0
    except Exception:
        clone["x"] = 168.0
    try:
        clone["y"] = float(src.get("y") or ui.get("y") or 120) + 48.0
    except Exception:
        clone["y"] = 168.0
    ui["x"] = clone["x"]
    ui["y"] = clone["y"]
    clone["ui"] = ui
    nodes.append(clone)
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_node_clone", f"node={node_id}; clone={new_id}")
    return jsonify({"ok": True, "message": "节点已复制", "node_id": new_id, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology/node/disable", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_disable():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    disabled = bool(payload.get("disabled", True))
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    target = next((x for x in (topo.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not target:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    ui = target.get("ui") if isinstance(target.get("ui"), dict) else {}
    ui["disabled"] = disabled
    target["ui"] = ui
    target["bizStatus"] = "offline" if disabled else "normal"
    saved = ops_helpers._save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_node_disable", f"node={node_id}; disabled={disabled}")
    return jsonify({"ok": True, "message": "节点状态已更新", "disabled": disabled, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})



@bp.route("/api/ops-platform/topology/node/logs")
@admin_required("gm_ops")
def ops_platform_topology_node_logs():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    node_id = str(request.args.get("node_id") or "").strip()
    limit = max(1, min(200, int(request.args.get("limit") or 40)))
    topo = ops_helpers._load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    node = next((x for x in (topo.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    jobs = [x for x in reversed(ops_helpers._load_agent_jobs()) if isinstance(x, dict) and str(x.get("node_id") or "") == node_id][:limit]
    events = [x for x in ops_helpers._load_json_config(OPS_EVENT_LOG_KEY, []) if isinstance(x, dict) and str(x.get("node_id") or "") == node_id]
    events = list(reversed(events[-limit:]))
    bindings = ops_helpers._load_scope_agent_bindings(str(registry.get("topology_id") or topology_id or ""))
    return jsonify({
        "ok": True,
        "node": node,
        "agent_id": str(bindings.get(node_id) or ""),
        "jobs": jobs,
        "events": events,
    })











