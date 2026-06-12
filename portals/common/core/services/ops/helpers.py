# -*- coding: utf-8 -*-
"""Shared helpers for Ops platform and classic GM."""
from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
import hashlib
import queue as _queue_mod
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from flask import current_app, jsonify, redirect, render_template, render_template_string, request, session

from config import DATA_DIR
from models.data import (
    approvals_db,
    audit_log_db,
    approve_or_reject,
    create_approval,
    get_approved_approval,
    get_system_config,
    log_audit,
    projects_db,
    set_system_config,
)
from services.authz import admin_required, can_access_module, has_scope, is_admin
from services.business_test_catalog import (
    build_catalog_view,
    delete_custom_plan,
    get_plan,
    list_plans,
    resolve_gateway_endpoint,
    resolve_paths,
    save_custom_plan,
    validate_plan_dict,
)
from services.legacy_gm_bridge_client import LegacyGmBridgeClient
import services.ops.constants as _ops_constants
import services.ops.storage as _ops_storage
from services.ops.encoding import repair_legacy_node_text, text_has_mojibake

for _mod in (_ops_constants, _ops_storage):
    for _k, _v in vars(_mod).items():
        if not _k.startswith("__"):
            globals()[_k] = _v
del _mod, _k, _v, _ops_constants, _ops_storage
ops_gateway = ops_gateway  # re-bind after merge

_client = LegacyGmBridgeClient()
NODE_CONFIG_KEY = "GM_LEGACY_NODES"
GM_ACTION_PATHS = {
    "search_player": "/gm/search-player",
    "player_status": "/gm/player-status",
    "adjust_currency": "/gm/adjust-currency",
    "adjust_item": "/gm/adjust-item",
    "hero_edit": "/gm/hero-edit",
    "stage_update": "/gm/stage-update",
    "idle_recompute": "/gm/idle-recompute",
    "send_mail": "/gm/send-mail",
    "send_broadcast": "/gm/send-broadcast",
    "save_template": "/gm/save-template",
    "save_activity": "/gm/save-activity",
    "save_announcement": "/gm/save-announcement",
    "script_task": "/gm/script-task",
}

# Back-compat aliases for classic GM code
_text_has_mojibake = text_has_mojibake
_repair_legacy_node_text = repair_legacy_node_text

from concurrent.futures import ThreadPoolExecutor, as_completed
import time as _time_mod

# --- 全局探活缓存（须在引用它们的函数之前初始化）---
_probe_cache: Dict[str, Dict[str, Any]] = {}
_probe_cache_agents: List[Dict[str, Any]] = []
_probe_cache_ts: float = 0.0
_probe_cache_sync_ts: float = 0.0
_probe_cache_lock = threading.Lock()
_probe_change_seq = 0

# --- SSE 订阅者队列 ---
_sse_subscribers: List[_queue_mod.Queue] = []
_sse_sub_lock = threading.Lock()
_probe_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ops-probe")

PROBE_INTERVAL_SEC = 5.0
PROBE_SYNC_INTERVAL_SEC = 30.0

def _normalize_node(payload: Dict[str, Any]) -> Dict[str, Any]:
    node_id = str(payload.get("id") or uuid.uuid4().hex[:12]).strip()
    fallback_ops_base = str(
        payload.get("ops_base_url")
        or os.getenv("GM_LEGACY_OPS_BASE_URL", "")
        or payload.get("base_url")
        or os.getenv("GM_LEGACY_BASE_URL", "")
        or "http://127.0.0.1:5054"
        or ""
    ).strip()
    return {
        "id": node_id,
        "name": str(payload.get("name") or node_id).strip(),
        "base_url": str(payload.get("base_url") or "").strip(),
        "ops_base_url": fallback_ops_base,
        "ops_read_key": str(payload.get("ops_read_key") or "").strip(),
        "ops_write_key": str(payload.get("ops_write_key") or "").strip(),
        "ops_actor": str(payload.get("ops_actor") or "").strip(),
        "ops_role": str(payload.get("ops_role") or "").strip(),
        "username": str(payload.get("username") or "").strip(),
        "password": str(payload.get("password") or "").strip(),
        "server_id": str(payload.get("server_id") or "").strip(),
        "project_id": str(payload.get("project_id") or "").strip(),
        "owner": str(payload.get("owner") or "").strip(),
        "role": str(payload.get("role") or "business").strip(),
        "node_category": str(payload.get("node_category") or "").strip(),
        "node_type": str(payload.get("node_type") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "biz_status": str(payload.get("biz_status") or "normal").strip(),
        "allowed_upstream_roles": payload.get("allowed_upstream_roles") if isinstance(payload.get("allowed_upstream_roles"), list) else [],
        "allowed_downstream_roles": payload.get("allowed_downstream_roles") if isinstance(payload.get("allowed_downstream_roles"), list) else [],
        "daemon_profile": str(payload.get("daemon_profile") or "").strip(),
        "daemon_start_cmd": str(payload.get("daemon_start_cmd") or "").strip(),
        "daemon_stop_cmd": str(payload.get("daemon_stop_cmd") or "").strip(),
        "env": str(payload.get("env") or "").strip(),
        "channel": str(payload.get("channel") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
        "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else [],
    }


def _default_nodes() -> List[Dict[str, Any]]:
    base_url = str(os.getenv("GM_LEGACY_BASE_URL", "http://127.0.0.1:8080")).strip()
    ops_base_url = str(os.getenv("GM_LEGACY_OPS_BASE_URL", "http://127.0.0.1:5054")).strip()
    ops_read_key = str(os.getenv("GM_LEGACY_OPS_READ_KEY", "2062f00689b2abee75b9bab1bd49f435c57e580d14db436942374d09a5d5468a")).strip()
    ops_write_key = str(os.getenv("GM_LEGACY_OPS_WRITE_KEY", "2062f00689b2abee75b9bab1bd49f435c57e580d14db436942374d09a5d5468a")).strip()
    ops_actor = str(os.getenv("GM_LEGACY_OPS_ACTOR", "intranet-ops")).strip()
    ops_role = str(os.getenv("GM_LEGACY_OPS_ROLE", "SuperAdmin")).strip()
    username = str(os.getenv("GM_LEGACY_USERNAME", "gm")).strip()
    password = str(os.getenv("GM_LEGACY_PASSWORD", "")).strip()
    return [
        _normalize_node(
            {
                "id": "local-gm",
                "name": "本地GM节点",
                "base_url": base_url,
                "ops_base_url": ops_base_url,
                "ops_read_key": ops_read_key,
                "ops_write_key": ops_write_key,
                "ops_actor": ops_actor,
                "ops_role": ops_role,
                "username": username,
                "password": password,
                "server_id": "",
                "role": "business",
                "node_category": "application",
                "node_type": "business_server",
                "description": "默认节点",
                "biz_status": "normal",
                "allowed_upstream_roles": ["gateway", "scheduler", "admin"],
                "allowed_downstream_roles": ["database", "cache", "mq", "search"],
                "daemon_profile": "ops_native",
                "enabled": True,
            }
        )
    ]


def _repair_legacy_node_text(item: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(item or {})
    name = str(row.get("name") or "")
    desc = str(row.get("description") or "")
    if _text_has_mojibake(name):
        if str(row.get("id") or "") == "local-gm":
            row["name"] = "本地GM节点"
        else:
            row["name"] = str(row.get("id") or "节点")
    if _text_has_mojibake(desc):
        row["description"] = "默认节点"
    return row


def _load_nodes() -> List[Dict[str, Any]]:
    raw = get_system_config(NODE_CONFIG_KEY, [])
    if isinstance(raw, list) and raw:
        rows: List[Dict[str, Any]] = []
        changed = False
        for item in raw:
            if isinstance(item, dict):
                repaired = _repair_legacy_node_text(item)
                if repaired != item:
                    changed = True
                rows.append(_normalize_node(repaired))
        if rows:
            if changed:
                _save_nodes(rows)
            return rows
    return _default_nodes()


def _save_nodes(rows: List[Dict[str, Any]]) -> None:
    normalized = [_normalize_node(item if isinstance(item, dict) else {}) for item in (rows or [])]
    set_system_config(
        NODE_CONFIG_KEY,
        normalized,
        value_type="json",
        description="Legacy GM + Ops 节点配置",
        username="system",
    )


def _resolve_node(node_id: str = "", project_id: str = "", env: str = "", channel: str = "") -> Optional[Dict[str, Any]]:
    rows = _load_nodes()
    enabled = [x for x in rows if x.get("enabled")]
    if node_id:
        for item in rows:
            if str(item.get("id") or "") == node_id:
                return item
    if project_id:
        for item in enabled:
            if str(item.get("project_id") or "") == project_id:
                if env and str(item.get("env") or "") not in ("", env):
                    continue
                if channel and str(item.get("channel") or "") not in ("", channel):
                    continue
                return item
    return enabled[0] if enabled else (rows[0] if rows else None)


def _node_or_400(payload: Dict[str, Any]):
    node = _resolve_flow_test_node(payload)
    if not node:
        return None, (jsonify({"ok": False, "error": "no node configured"}), 400)
    return node, None


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
        actions.append({"label": "绑定 Agent", "href": f"/admin/ops-platform/agent-control?project_id={row.get('project_id') or ''}", "risk": "low"})
    if any("ops_base_url" in str(x) for x in issues):
        actions.append({"label": "拓扑编排", "href": f"/admin/ops-platform/topology?project_id={row.get('project_id') or ''}", "risk": "low"})
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


def _allow_ops_view() -> bool:
    return bool(
        is_admin()
        or
        can_access_module("gm_ops")
        or has_scope("ops.platform.view")
        or has_scope("gm.ops.execute")
        or has_scope("gm.audit.view")
    )


def _allow_ops_execute() -> bool:
    return bool(
        is_admin()
        or
        can_access_module("gm_ops")
        or has_scope("ops.platform.execute")
        or has_scope("gm.ops.execute")
    )


def _allow_gm_execute() -> bool:
    return bool(
        can_access_module("gm_ops")
        or has_scope("gm.classic.execute")
        or has_scope("gm.liveops.execute")
        or has_scope("gm.ops.execute")
    )


def _render_ops_page(
    content: str,
    title: str,
    active_page: str = "",
    project_id: str = "",
    env_key: str = "",
    topology_id: str = "",
    extra_css: str = "",
    extra_js: str = "",
):
    """Unified page wrapper — all ops pages use the shared sidebar shell."""
    if not project_id:
        project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
    if project_id:
        session["ops_last_project"] = project_id
    if not env_key:
        env_key = _resolve_ops_env_key(request.args.get("env_key") or "")
    if env_key:
        session["ops_last_env"] = env_key
    if not topology_id:
        topology_id = str(request.args.get("topology_id", ""))
    project_name = project_id
    try:
        row = (projects_db or {}).get(project_id) or {}
        project_name = str(row.get("name") or project_id or "未选择项目").strip() or project_id or "未选择项目"
    except Exception:
        project_name = project_id or "未选择项目"
    env_label = _env_label(env_key) if env_key else ""
    user_name = str(session.get("user") or "").strip() or "运维管理员"
    return render_template(
        "ops_shell.html",
        content=content,
        title=title,
        active_page=active_page,
        project_id=project_id,
        project_name=project_name,
        project_label=f"{project_name}_{env_label}" if project_name and env_label else project_name or "未选择项目",
        env_key=env_key,
        topology_id=topology_id,
        avatar_text=(user_name[:1] or "A").upper(),
        user_name=user_name,
        extra_css=extra_css,
        extra_js=extra_js,
    )


def _render_page(content: str, title: str):
    """Legacy compat — delegates to _render_ops_page."""
    return _render_ops_page(content, title)


def _render_local_template(template_name: str, **kwargs):
    core_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    path = os.path.join(core_dir, "templates", template_name)
    with open(path, "r", encoding="utf-8") as f:
        return render_template_string(f.read(), **kwargs)


def _render_standalone_page(content: str, title: str):
    """Legacy compat — delegates to _render_ops_page."""
    return _render_ops_page(content, title)


def _normalize_env_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    alias = {
        "dev": "development",
        "develop": "development",
        "development": "development",
        "test": "testing",
        "testing": "testing",
        "qa": "testing",
        "staging": "staging",
        "pre": "staging",
        "preprod": "staging",
        "pre-release": "staging",
        "prod": "production",
        "production": "production",
        "online": "production",
    }
    return alias.get(text, text or "production")


def _default_env_options() -> List[Dict[str, str]]:
    return [
        {"env_key": "development", "label": "开发环境"},
        {"env_key": "testing", "label": "测试环境"},
        {"env_key": "staging", "label": "预发环境"},
        {"env_key": "production", "label": "生产环境"},
    ]


def _env_label(env_key: str) -> str:
    key = _normalize_env_key(env_key)
    for item in _default_env_options():
        if str(item.get("env_key") or "") == key:
            return str(item.get("label") or key)
    return key or "生产环境"


def _load_topology_registry() -> List[Dict[str, Any]]:
    raw = _load_json_config(OPS_TOPOLOGY_REGISTRY_KEY, [])
    return raw if isinstance(raw, list) else []


def _save_topology_registry(rows: List[Dict[str, Any]]) -> None:
    items = rows if isinstance(rows, list) else []
    _save_json_config(OPS_TOPOLOGY_REGISTRY_KEY, items, description="Ops 拓扑注册表")


def _load_topology_contents() -> Dict[str, Any]:
    raw = _load_json_config(OPS_TOPOLOGY_CONTENTS_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_topology_contents(data: Dict[str, Any]) -> None:
    payload = data if isinstance(data, dict) else {}
    _save_json_config(OPS_TOPOLOGY_CONTENTS_KEY, payload, description="Ops 拓扑内容分片")


def _scope_binding_key(topology_id: str, node_id: str) -> str:
    return f"{str(topology_id or '').strip()}::{str(node_id or '').strip()}"


def _topology_content_counts(topology_id: str) -> Tuple[int, int]:
    tid = str(topology_id or "").strip()
    if not tid:
        return 0, 0
    contents = _load_topology_contents()
    topo = contents.get(tid) if isinstance(contents.get(tid), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    return len(nodes), len(edges)


def _ensure_design_demo_registry(project_id: str) -> None:
    """设计稿管理弹窗 demo：四环境各一条拓扑注册记录（存在则同步元数据）。"""
    pid = str(project_id or "").strip()
    if not pid:
        return
    if _project_has_cluster_json(pid):
        return
    rows = _load_topology_registry()
    if not isinstance(rows, list):
        rows = []
    demo_specs = [
        {"env_key": "production", "name": "生产环境拓扑", "version_label": "v2.3.1", "owner": "运维管理员", "is_default": True, "status": "running", "updated_at": "2025-05-20T12:34:00+08:00", "design_demo_node_count": 5, "design_demo_edge_count": 6},
        {"env_key": "staging", "name": "预发环境拓扑", "version_label": "v2.1.4", "owner": "张三", "status": "running", "updated_at": "2025-05-19T12:34:00+08:00", "design_demo_node_count": 5, "design_demo_edge_count": 6},
        {"env_key": "testing", "name": "测试环境拓扑", "version_label": "v1.8.7", "owner": "李四", "status": "stopped", "updated_at": "2025-05-16T12:34:00+08:00", "design_demo_node_count": 5, "design_demo_edge_count": 6},
        {"env_key": "development", "name": "开发环境拓扑", "version_label": "v1.5.2", "owner": "王五", "status": "running", "updated_at": "2025-05-12T12:34:00+08:00", "design_demo_node_count": 4, "design_demo_edge_count": 5},
    ]
    changed = False
    contents = _load_topology_contents()
    for spec in demo_specs:
        env = _normalize_env_key(spec.get("env_key"))
        hit_idx = -1
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if str(row.get("project_id") or "") == pid and _normalize_env_key(row.get("env_key")) == env:
                hit_idx = i
                break
        if hit_idx >= 0:
            merged = dict(rows[hit_idx])
            merged["name"] = spec["name"]
            merged["version_label"] = spec["version_label"]
            merged["owner"] = spec["owner"]
            merged["status"] = spec.get("status") or merged.get("status")
            if spec.get("is_default"):
                merged["is_default"] = True
            merged["design_demo_node_count"] = spec.get("design_demo_node_count")
            merged["design_demo_edge_count"] = spec.get("design_demo_edge_count")
            merged["updated_at"] = spec.get("updated_at") or merged.get("updated_at")
            rows[hit_idx] = _normalize_topology_registry_row(merged)
            changed = True
            continue
        row = _normalize_topology_registry_row(
            {
                "topology_id": f"topology-design-{pid.replace('/', '-').replace(' ', '-').lower()}-{env}",
                "project_id": pid,
                "env_key": env,
                "name": spec["name"],
                "version_label": spec["version_label"],
                "owner": spec["owner"],
                "is_default": bool(spec.get("is_default")),
                "status": spec.get("status") or "running",
                "description": "设计稿 demo 拓扑",
                "created_at": spec.get("updated_at") or _now_iso(),
                "updated_at": spec.get("updated_at") or _now_iso(),
                "design_demo_node_count": spec.get("design_demo_node_count"),
                "design_demo_edge_count": spec.get("design_demo_edge_count"),
            }
        )
        rows.append(row)
        contents[row["topology_id"]] = _core_minimal_topology_content(pid, env, runtime_ids=False)
        changed = True
    if changed:
        _save_topology_registry(rows)
        _save_topology_contents(contents)


def _normalize_topology_registry_row(row: Dict[str, Any]) -> Dict[str, Any]:
    item = row if isinstance(row, dict) else {}
    env_key = _normalize_env_key(item.get("env_key"))
    topology_id = str(item.get("topology_id") or "").strip() or ("topology-" + uuid.uuid4().hex[:10])
    out = {
        "topology_id": topology_id,
        "project_id": str(item.get("project_id") or "").strip(),
        "env_key": env_key,
        "env_label": _env_label(env_key),
        "name": str(item.get("name") or topology_id).strip(),
        "version_label": str(item.get("version_label") or "").strip(),
        "owner": str(item.get("owner") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "blueprint_id": str(item.get("blueprint_id") or "").strip(),
        "copied_from_topology_id": str(item.get("copied_from_topology_id") or "").strip(),
        "is_default": bool(item.get("is_default", False)),
        "status": str(item.get("status") or "draft").strip().lower(),
        "created_at": str(item.get("created_at") or _now_iso()),
        "updated_at": str(item.get("updated_at") or item.get("created_at") or _now_iso()),
    }
    nc, ec = _topology_content_counts(topology_id)
    if item.get("design_demo_node_count") is not None:
        out["design_demo_node_count"] = int(item.get("design_demo_node_count") or 0)
        out["design_demo_edge_count"] = int(item.get("design_demo_edge_count") or 0)
        out["node_count"] = out["design_demo_node_count"]
        out["edge_count"] = out["design_demo_edge_count"]
    elif nc or ec:
        out["node_count"] = nc
        out["edge_count"] = ec
    elif item.get("node_count") is not None:
        out["node_count"] = int(item.get("node_count") or 0)
        out["edge_count"] = int(item.get("edge_count") or 0)
    else:
        out["node_count"] = 5
        out["edge_count"] = 6
    return out


def _design_reference_topology_content(project_id: str = "", env_key: str = "production") -> Dict[str, Any]:
    """设计稿标准 6 节点 demo 拓扑：Gateway / Auth / Ops / Game / TCP Transport / Database。"""
    gateway_ports = {
        "in": [],
        "out": [
            {"id": "out-1", "label": "http:80", "kind": "out", "max_links": 1},
            {"id": "out-2", "label": "http:443", "kind": "out", "max_links": 1},
        ],
    }

    def _node(
        node_id: str,
        name: str,
        role: str,
        desc: str,
        x: int,
        y: int,
        color: str,
        kind: str = "",
        tags: Optional[List[str]] = None,
        ports: Optional[Dict[str, Any]] = None,
        owner: str = "",
        group: str = "",
        list_only: bool = False,
        remote_port: int = 0,
        endpoints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        k = kind or _infer_node_kind(role, "")
        ui_ports = ports if isinstance(ports, dict) else _normalize_ports(k, None)
        ui: Dict[str, Any] = {
            "x": x,
            "y": y,
            "w": 220,
            "h": 108,
            "color": color,
            "locked": False,
            "ports": ui_ports,
            "list_only": bool(list_only),
        }
        if remote_port:
            ui["remote"] = {"port": int(remote_port)}
        if endpoints:
            ui["network"] = {"endpoints": list(endpoints)}
        return {
            "id": node_id,
            "name": name,
            "server_id": node_id,
            "project_id": str(project_id or ""),
            "env": _normalize_env_key(env_key) or "production",
            "role": role,
            "kind": k,
            "desc": desc,
            "bizStatus": "normal",
            "owner": str(owner or ""),
            "group": str(group or ""),
            "x": float(x),
            "y": float(y),
            "tags": tags if isinstance(tags, list) else [],
            "ui": ui,
        }

    nodes = [
        _node("gateway-01", "Gateway", "gateway", "网关服务", 72, 48, "#1890ff", "entry", ports=gateway_ports),
        _node("auth-01", "Auth", "auth", "认证服务", 72, 248, "#52c41a"),
        _node("ops-01", "Ops", "admin", "运维服务", 320, 248, "#faad14"),
        _node(
            "game-01", "Game", "business",
            "核心游戏逻辑服务节点。处理玩家会话与游戏逻辑。",
            560, 128, "#722ed1", "game",
            tags=["business", "core"], owner="运维团队", group="游戏服务",
            remote_port=9501, endpoints=["10.0.1.15:9501"],
        ),
        _node("tcp-01", "TCP Transport", "transport", "传输服务", 820, 328, "#f5222d", "terminal"),
        _node("db-01", "Database", "database", "Mongo 主存储", 560, 280, "#13c2c2", tags=["storage"]),
    ]
    edges = [
        {"id": "edge-gw-auth", "from": "gateway-01", "to": "auth-01", "from_port": "out-1", "to_port": "in-1", "type": "http", "note": "http:80"},
        {"id": "edge-gw-ops", "from": "gateway-01", "to": "ops-01", "from_port": "out-2", "to_port": "in-1", "type": "http", "note": "http:443"},
        {"id": "edge-auth-game", "from": "auth-01", "to": "game-01", "from_port": "out-1", "to_port": "in-1", "type": "tcp", "note": "tcp:5501"},
        {"id": "edge-ops-game", "from": "ops-01", "to": "game-01", "from_port": "out-1", "to_port": "in-1", "type": "tcp", "note": "tcp:5512"},
        {"id": "edge-game-tcp", "from": "game-01", "to": "tcp-01", "from_port": "out-1", "to_port": "in-1", "type": "tcp", "note": "tcp:9512"},
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "layout_mode": "structured",
            "layout_locked": False,
            "design_reference": "v4",
            "layout_spacing": {"rank_gap": 268, "row_gap": 128},
            "updated_at": _now_iso(),
        },
    }


_DESIGN_DEMO_NODE_IDS = frozenset({"gateway-01", "auth-01", "game-01", "ops-01", "tcp-01", "db-01"})
_DESIGN_DEMO_AGENT_IDS = frozenset({
    "agent-01",
    "agent-gateway-01",
    "agent-auth-01",
    "agent-game-01",
    "agent-ops-01",
    "agent-tcp-01",
    "agent-db-01",
})
_DEMO_TO_RUNTIME_NODE = {
    "gateway-01": "gateway-cn-1",
    "auth-01": "auth-cn-1",
    "game-01": "game-cn-1",
    "ops-01": "ops-cn-1",
    "tcp-01": "tcp-cn-1",
    "db-01": "mongo-db-cn-1",
}
_RUNTIME_MINIMAL_NODE_IDS = frozenset({"gateway-cn-1", "auth-cn-1", "ops-cn-1", "game-cn-1"})
_RUNTIME_INFRA_NODE_IDS = frozenset({"mongo-db-cn-1", "redis-cache-cn-1"})
_CORE_PRESET_IDS = frozenset({
    "gateway_http",
    "auth_service",
    "business_main",
    "ops_service",
    "tcp_transport",
    "pressure_worker",
    "redis_cache",
    "mongo_db",
    "mq_kafka",
    "scheduler_job",
})


def _project_has_cluster_json(project_id: str = "") -> bool:
    pid = str(project_id or "").strip()
    if pid and pid != "GomeKu":
        return False
    return bool(_load_cluster_json())


def _topology_has_design_demo_nodes(topo: Any) -> bool:
    if not isinstance(topo, dict):
        return False
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
    return bool(ids & _DESIGN_DEMO_NODE_IDS)


def _ensure_runtime_topology_bindings(topology_id: str, node_ids: List[str]) -> None:
    tid = str(topology_id or "").strip()
    if not tid:
        return
    agent_store = _load_node_agent_bindings()
    service_store = _load_node_service_bindings()
    agent_changed = False
    service_changed = False
    for raw_nid in node_ids or []:
        node_id = str(raw_nid or "").strip()
        if not node_id:
            continue
        agent_key = _scope_binding_key(tid, node_id)
        if str(agent_store.get(agent_key) or "").strip() != CANONICAL_LOCAL_AGENT_ID:
            agent_store[agent_key] = CANONICAL_LOCAL_AGENT_ID
            agent_changed = True
        service_key = _scope_binding_key(tid, node_id)
        if str(service_store.get(service_key) or "").strip() != node_id:
            service_store[service_key] = node_id
            service_changed = True
    if agent_changed:
        _save_node_agent_bindings(agent_store)
    if service_changed:
        _save_node_service_bindings(service_store)


def _topology_missing_runtime_infra(topo: Any) -> bool:
    if not isinstance(topo, dict):
        return False
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict) and str(n.get("id") or "")}
    if "game-cn-1" in ids:
        return not _RUNTIME_INFRA_NODE_IDS.issubset(ids)
    if "game-01" in ids:
        return not {"redis-01", "db-01"}.issubset(ids)
    return False


def _build_runtime_infra_topology_node(
    node_id: str,
    preset_id: str,
    name: str,
    role: str,
    desc: str,
    project_id: str,
    env_key: str,
    x: int,
    y: int,
    color: str,
    port: int,
) -> Dict[str, Any]:
    kind = _infer_node_kind(role, "")
    contract = _load_node_contract(preset_id) or {}
    daemon_defaults = _contract_daemon_defaults(preset_id, port)
    ui_ports = _normalize_ports(kind, None)
    return {
        "id": node_id,
        "name": name,
        "server_id": node_id,
        "preset_id": preset_id,
        "node_type": str(contract.get("node_type") or preset_id),
        "project_id": str(project_id or ""),
        "env": _normalize_env_key(env_key) or "production",
        "role": role,
        "kind": kind,
        "desc": desc,
        "bizStatus": "normal",
        "owner": "ops-admin",
        "group": str(contract.get("category") or "infrastructure"),
        "daemon_profile": "external_daemon",
        "daemon_start_cmd": str(daemon_defaults.get("StartCommand") or ""),
        "daemon_stop_cmd": str(daemon_defaults.get("StopCommand") or ""),
        "daemon_port": int(port or 0),
        "x": float(x),
        "y": float(y),
        "tags": [role, preset_id],
        "ui": {
            "x": float(x),
            "y": float(y),
            "w": 220,
            "h": 90,
            "color": color,
            "locked": False,
            "ports": ui_ports,
            "remote": {"port": int(port or 0)} if port > 0 else {},
            "network": {"endpoints": [f"127.0.0.1:{port}"]} if port > 0 else {},
        },
    }


def _append_runtime_infra_stack(topo: Dict[str, Any], project_id: str = "", env_key: str = "production") -> Dict[str, Any]:
    """补齐最小完整栈的数据层：Game → Redis + Mongo。"""
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key) or "production"
    nodes = list(topo.get("nodes") or []) if isinstance(topo.get("nodes"), list) else []
    edges = list(topo.get("edges") or []) if isinstance(topo.get("edges"), list) else []
    node_by_id = {str(n.get("id") or ""): n for n in nodes if isinstance(n, dict) and str(n.get("id") or "")}
    if "game-cn-1" in node_by_id:
        infra_specs = [
            ("redis-cache-cn-1", "redis_cache", "Redis", "cache", "Redis 缓存与会话存储", 820, 48, "#eb2f96", 6379),
            ("mongo-db-cn-1", "mongo_db", "MongoDB", "database", "Mongo 业务主存储", 820, 248, "#13c2c2", 27017),
        ]
        edge_specs = list(_RUNTIME_INFRA_EDGE_SPECS)
    elif "game-01" in node_by_id:
        infra_specs = [
            ("redis-01", "redis_cache", "Redis", "cache", "Redis 缓存与会话存储", 820, 48, "#eb2f96", 6379),
            ("db-01", "mongo_db", "MongoDB", "database", "Mongo 业务主存储", 820, 248, "#13c2c2", 27017),
        ]
        edge_specs = list(_CORE_MINIMAL_DEMO_INFRA_EDGE_SPECS)
    else:
        return topo

    for node_id, preset_id, name, role, desc, x, y, color, port in infra_specs:
        if node_id in node_by_id:
            continue
        node = _build_runtime_infra_topology_node(
            node_id, preset_id, name, role, desc, pid, env, x, y, color, port
        )
        nodes.append(node)
        node_by_id[node_id] = node

    valid_ids = set(node_by_id.keys())
    existing = {(str(e.get("from") or ""), str(e.get("to") or "")) for e in edges if isinstance(e, dict)}
    for frm, to, note in edge_specs:
        if frm not in valid_ids or to not in valid_ids or (frm, to) in existing:
            continue
        edges.append(
            {
                "id": f"edge-{frm}-{to}",
                "from": str(frm),
                "to": str(to),
                "from_port": "out-1",
                "to_port": "in-1",
                "type": "depends_on",
                "note": str(note),
            }
        )
        existing.add((frm, to))

    topo["nodes"] = nodes
    topo["edges"] = edges
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    meta["blueprint_id"] = str(meta.get("blueprint_id") or "minimal_framework")
    meta["framework_profile"] = str(meta.get("framework_profile") or "commercial_game_server")
    topo["meta"] = meta
    return topo


def _apply_runtime_minimal_topology(topology_id: str, project_id: str, env_key: str = "production") -> Dict[str, Any]:
    """将指定拓扑重写为 cluster.json 最小完整栈（应用层 + Redis/Mongo 数据层）。"""
    tid = str(topology_id or "").strip()
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key) or "production"
    if not tid or not pid:
        return {"updated": False, "reason": "missing_scope"}
    cluster_rows = _load_cluster_json() if _project_has_cluster_json(pid) else []
    if cluster_rows:
        topo = _build_cluster_topology_content(cluster_rows, pid)
    else:
        topo = _core_minimal_topology_content(pid, env, runtime_ids=False)
    topo = _append_runtime_infra_stack(topo, pid, env)
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    meta["runtime_topology"] = True
    meta["cluster_source"] = bool(cluster_rows)
    meta["updated_at"] = _now_iso()
    meta.pop("design_reference", None)
    topo["meta"] = meta
    for node in topo.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node["env"] = env
        node["project_id"] = pid
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = _repair_runtime_topology_edges(nodes, edges, meta)
    contents = _load_topology_contents()
    contents[tid] = topo
    _save_topology_contents(contents)
    runtime_node_ids = [
        str(n.get("id") or "")
        for n in nodes
        if isinstance(n, dict) and str(n.get("id") or "").endswith("-cn-1")
    ]
    if runtime_node_ids:
        _ensure_runtime_topology_bindings(tid, runtime_node_ids)
    return {"updated": True, "topology_id": tid, "node_count": len(nodes), "edge_count": len(topo.get("edges") or [])}


def _migrate_gomeku_design_topology_contents(project_id: str = "GomeKu") -> None:
    """一次性升级 GomeKu 各环境仍残留的设计稿 demo 拓扑内容。"""
    pid = str(project_id or "").strip()
    if not _project_has_cluster_json(pid):
        return
    env_by_tid: Dict[str, str] = {}
    for row in _load_topology_registry():
        if not isinstance(row, dict) or str(row.get("project_id") or "") != pid:
            continue
        tid = str(row.get("topology_id") or "").strip()
        if tid:
            env_by_tid[tid] = _normalize_env_key(row.get("env_key"))
    for tid, topo in list(_load_topology_contents().items()):
        if "gomeku" not in str(tid).lower() or not isinstance(topo, dict):
            continue
        meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        node_ids = {
            str(n.get("id") or "")
            for n in (topo.get("nodes") or [])
            if isinstance(n, dict) and str(n.get("id") or "")
        }
        needs_upgrade = (
            _topology_has_design_demo_nodes(topo)
            or str(meta.get("design_reference") or "").startswith("v")
            or bool({"tcp-01"} & node_ids)
            or _topology_missing_runtime_infra(topo)
        )
        if not needs_upgrade:
            continue
        env = env_by_tid.get(tid) or "production"
        _apply_runtime_minimal_topology(tid, pid, env)


def _core_minimal_topology_content(
    project_id: str = "",
    env_key: str = "production",
    *,
    runtime_ids: bool = False,
) -> Dict[str, Any]:
    """最小完整栈：Gateway / Auth / Ops / Game + Redis / Mongo。"""
    env = _normalize_env_key(env_key) or "production"
    pid = str(project_id or "").strip()
    gateway_ports = {
        "in": [],
        "out": [
            {"id": "out-1", "label": "http:80", "kind": "out", "max_links": 1},
            {"id": "out-2", "label": "http:443", "kind": "out", "max_links": 1},
        ],
    }

    def _node(
        node_id: str,
        name: str,
        role: str,
        desc: str,
        x: int,
        y: int,
        color: str,
        kind: str = "",
        ports: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        k = kind or _infer_node_kind(role, "")
        ui_ports = ports if isinstance(ports, dict) else _normalize_ports(k, None)
        return {
            "id": node_id,
            "name": name,
            "server_id": node_id,
            "project_id": pid,
            "env": env,
            "role": role,
            "kind": k,
            "desc": desc,
            "bizStatus": "normal",
            "owner": "",
            "group": "",
            "x": float(x),
            "y": float(y),
            "tags": [],
            "ui": {
                "x": float(x),
                "y": float(y),
                "w": 220,
                "h": 108,
                "color": color,
                "locked": False,
                "ports": ui_ports,
            },
        }

    if runtime_ids:
        node_specs: List[Tuple[Any, ...]] = [
            ("gateway-cn-1", "Gateway", "gateway", "网关服务", 72, 48, "#1890ff", "entry", gateway_ports),
            ("auth-cn-1", "Auth", "auth", "认证服务", 72, 248, "#52c41a"),
            ("ops-cn-1", "Ops", "ops", "运维服务", 320, 248, "#faad14", "admin"),
            ("game-cn-1", "Game", "business", "游戏服务", 560, 128, "#722ed1", "game"),
        ]
        edge_specs = [
            ("gateway-cn-1", "auth-cn-1", "http:80"),
            ("gateway-cn-1", "ops-cn-1", "http:443"),
            ("auth-cn-1", "game-cn-1", "tcp:5512"),
            ("ops-cn-1", "game-cn-1", "tcp:5512"),
        ]
        meta_extra = {"runtime_topology": True, "cluster_source": True}
    else:
        node_specs = [
            ("gateway-01", "Gateway", "gateway", "网关服务", 72, 48, "#1890ff", "entry", gateway_ports),
            ("auth-01", "Auth", "auth", "认证服务", 72, 248, "#52c41a"),
            ("ops-01", "Ops", "admin", "运维服务", 320, 248, "#faad14"),
            ("game-01", "Game", "business", "游戏服务", 560, 128, "#722ed1", "game"),
        ]
        edge_specs = [
            ("gateway-01", "auth-01", "http:80"),
            ("gateway-01", "ops-01", "http:443"),
            ("auth-01", "game-01", "tcp:5501"),
            ("ops-01", "game-01", "tcp:5512"),
        ]
        meta_extra = {"design_reference": "minimal-v1"}

    nodes: List[Dict[str, Any]] = []
    for spec in node_specs:
        nid, name, role, desc, x, y, color = spec[:7]
        kind = str(spec[7] or "") if len(spec) > 7 else ""
        ports = spec[8] if len(spec) > 8 else None
        nodes.append(_node(str(nid), str(name), str(role), str(desc), int(x), int(y), str(color), kind, ports))

    edges: List[Dict[str, Any]] = []
    for frm, to, note in edge_specs:
        edges.append(
            {
                "id": f"edge-{frm}-{to}",
                "from": str(frm),
                "to": str(to),
                "from_port": "out-1",
                "to_port": "in-1",
                "type": "http" if str(note).startswith("http") else "tcp",
                "note": str(note),
            }
        )

    meta: Dict[str, Any] = {
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "layout_mode": "structured",
        "layout_locked": False,
        "layout_spacing": {"rank_gap": 268, "row_gap": 128},
        "updated_at": _now_iso(),
    }
    meta.update(meta_extra)
    topo = {"nodes": nodes, "edges": edges, "meta": meta}
    return _append_runtime_infra_stack(topo, pid, env)


def _project_uses_runtime_topology(project_id: str) -> bool:
    pid = str(project_id or "").strip()
    if not pid:
        return False
    if _project_has_cluster_json(pid):
        return True
    _migrate_topology_storage_if_needed()
    tid = _runtime_default_topology_id(pid, "production")
    contents = _load_topology_contents()
    topo = contents.get(tid) if isinstance(contents.get(tid), dict) else {}
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    has_runtime_nodes = any(isinstance(n, dict) and str(n.get("id") or "").endswith("-cn-1") for n in nodes)
    return has_runtime_nodes and bool(meta.get("runtime_topology") or meta.get("cluster_source"))


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


def _purge_design_demo_project_state(project_id: str, topology_id: str = "") -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid:
        return {"removed_agents": 0, "removed_bindings": 0}
    reg = _load_agent_registry_v2()
    removed_agents = 0
    for aid in list(reg.keys()):
        item = reg.get(aid) if isinstance(reg.get(aid), dict) else {}
        if str(item.get("project_id") or pid).strip() != pid:
            continue
        if _is_design_demo_agent_row(item):
            reg.pop(aid, None)
            removed_agents += 1
    _save_agent_registry_v2(reg)

    bindings = _load_node_agent_bindings()
    removed_bindings = 0
    tid = str(topology_id or "").strip()
    for key in list(bindings.keys()):
        node_part = key.split("::", 1)[-1] if "::" in key else key
        if node_part not in _DESIGN_DEMO_NODE_IDS:
            continue
        if tid and not str(key).startswith(tid + "::"):
            continue
        bindings.pop(key, None)
        removed_bindings += 1
    _save_node_agent_bindings(bindings)
    return {"removed_agents": removed_agents, "removed_bindings": removed_bindings}


def _topology_ops_dispatch_base(project_id: str, env_key: str, topo: Dict[str, Any]) -> str:
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    ops_node = next(
        (
            n for n in nodes
            if isinstance(n, dict) and str(n.get("id") or "") in ("ops-cn-1", "ops-01")
        ),
        None,
    )
    port = 5504
    if isinstance(ops_node, dict):
        ui = ops_node.get("ui") if isinstance(ops_node.get("ui"), dict) else {}
        remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
        try:
            port = int(remote.get("port") or ops_node.get("daemon_port") or 5504)
        except Exception:
            port = 5504
    return f"http://127.0.0.1:{port}"


def _resolve_topology_node_id_for_service(project_id: str, service_id: str, hint_node_id: str = "") -> str:
    """将 service_id / 绑定键 / demo 映射解析为可 dispatch 的拓扑 node_id。"""
    sid = str(service_id or "").strip()
    hint = str(hint_node_id or "").strip()
    candidates: List[str] = []
    if hint:
        candidates.append(hint)
    if sid:
        candidates.append(sid)
        mapped = str(_DEMO_TO_RUNTIME_NODE.get(sid) or "").strip()
        if mapped:
            candidates.append(mapped)
    for key, value in (_load_node_service_bindings() or {}).items():
        if str(value or "").strip() != sid:
            continue
        text = str(key or "").strip()
        node_id = text.split("::", 1)[-1].strip() if "::" in text else text
        if node_id:
            candidates.append(node_id)
    seen: set = set()
    for nid in candidates:
        if not nid or nid in seen:
            continue
        seen.add(nid)
        if _resolve_ops_dispatch_node(project_id, nid):
            return nid
    return hint or sid


def _resolve_ops_dispatch_node(project_id: str, node_id: str, env_key: str = "production") -> Optional[Dict[str, Any]]:
    nid = str(node_id or "").strip()
    if not nid:
        return None
    for item in _load_nodes():
        if isinstance(item, dict) and str(item.get("id") or "").strip() == nid:
            return item

    pid = str(project_id or "").strip()
    ctx = _resolve_topology_context(pid, _normalize_env_key(env_key) or "production", "")
    topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    tid = str(row.get("topology_id") or "")
    lookup_id = _DEMO_TO_RUNTIME_NODE.get(nid, nid)
    topo_node = next(
        (
            n for n in (topo.get("nodes") or [])
            if isinstance(n, dict) and str(n.get("id") or "").strip() == lookup_id
        ),
        None,
    )
    if not isinstance(topo_node, dict):
        return None
    built = _build_runtime_node_from_topology_node(pid, env_key, topo_node, tid)
    built["ops_base_url"] = _topology_ops_dispatch_base(pid, env_key, topo)
    built["enabled"] = True
    return _normalize_node(built)


def _resolve_flow_test_node(payload: Dict[str, Any], node_id: str = "") -> Optional[Dict[str, Any]]:
    project_id = str((payload or {}).get("project_id") or "").strip()
    env_key = _normalize_env_key((payload or {}).get("env_key") or "production")
    nid = str(node_id or (payload or {}).get("node_id") or "").strip()
    if not nid:
        return None
    if project_id:
        hit = _resolve_ops_dispatch_node(project_id, nid, env_key)
        if hit:
            return hit
    return _resolve_node(
        node_id=nid,
        project_id=project_id,
        env=str((payload or {}).get("env") or "").strip(),
        channel=str((payload or {}).get("channel") or "").strip(),
    )


def _smoke_probe_topology_node(project_id: str, env_key: str, topology_id: str, node: Dict[str, Any]) -> Dict[str, Any]:
    contract = _resolve_node_contract_for_topology_node(node)
    port = _resolve_topology_node_port(node, contract, None, None)
    host = "127.0.0.1"
    role = str(node.get("role") or "").strip().lower()
    nid = str(node.get("id") or "")

    if _is_external_daemon_node(node):
        ok = _probe_tcp_open(host, port) if port > 0 else False
        return {"ok": ok, "message": f"daemon tcp {'PASS' if ok else 'FAIL'} ({host}:{port})", "mode": "tcp-probe"}

    if port > 0 and _probe_tcp_open(host, port):
        return {"ok": True, "message": f"tcp PASS ({host}:{port})", "mode": "tcp-probe"}

    if role in ("auth", "game", "business", "admin", "ops"):
        for svc in _services_for_project(project_id):
            if not isinstance(svc, dict):
                continue
            st = str(svc.get("status") or svc.get("run_state") or "").upper()
            p = int(svc.get("remote_game_server_port") or svc.get("service_port") or 0)
            if st in ("RUNNING", "ONLINE", "READY", "STARTING") and p > 0 and _probe_tcp_open(host, p):
                return {
                    "ok": True,
                    "message": f"cluster service live via {svc.get('service_id')}:{p}",
                    "mode": "cluster-probe",
                }
        return {
            "ok": False,
            "message": f"节点 {nid} 未检测到可用端口（请先一键启动全流程）",
            "mode": "cluster-probe",
        }

    ok = _probe_tcp_open(host, port) if port > 0 else False
    return {"ok": ok, "message": f"tcp {'PASS' if ok else 'FAIL'} ({host}:{port or '-'})", "mode": "tcp-probe"}


def _auto_approve_ops_request(req: Dict[str, Any], node: Dict[str, Any], validation: Dict[str, Any], actor: str, note: str) -> Dict[str, Any]:
    if not validation.get("require_approval") or validation.get("approved"):
        return validation
    aid = create_approval(
        "gm_ops_action",
        actor,
        "ops_action",
        str(validation.get("approval_target_id") or ""),
        reason=str(validation.get("reason") or note),
        project_id=str(node.get("project_id") or ""),
    )
    ok, err = approve_or_reject(aid, actor, "approve", note)
    if not ok:
        validation = dict(validation)
        validation["ok"] = False
        validation["missing"] = list(validation.get("missing") or []) + ["approval_failed"]
        validation["approval_error"] = str(err or "approval failed")
        return validation
    req["approval_id"] = aid
    return _validate_ops_request(req, node)


def _needs_design_reference_upgrade(topo: Any) -> bool:
    if not isinstance(topo, dict):
        return True
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    if meta.get("runtime_topology") or meta.get("cluster_source"):
        if any(isinstance(n, dict) and str(n.get("id") or "").endswith("-cn-1") for n in nodes):
            return False
    if str(meta.get("design_reference") or "") == "v4":
        for item in nodes:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "")
            if nid == "game-01" and "核心游戏逻辑" not in str(item.get("desc") or ""):
                return True
            if nid == "game-01" and str(item.get("owner") or "") != "运维团队":
                return True
            if nid == "db-01":
                ui = item.get("ui") if isinstance(item.get("ui"), dict) else {}
                if ui.get("list_only"):
                    return True
        edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
        notes = {str(e.get("note") or "") for e in edges if isinstance(e, dict)}
        if "http:80" not in notes or "tcp:9512" not in notes:
            return True
        if "db-01" not in {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}:
            return True
        return False
    if str(meta.get("design_reference") or "") in ("v1", "v2", "v3", ""):
        return True
    if len(nodes) >= 5:
        ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
        if {"gateway-01", "auth-01", "game-01", "tcp-01", "db-01"}.issubset(ids):
            return False
    if len(nodes) <= 1:
        return True
    ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
    if ids <= {"local-gm", ""}:
        return True
    for item in nodes:
        if not isinstance(item, dict):
            continue
        if _text_has_mojibake(str(item.get("desc") or "")):
            return True
    return False


def _ensure_design_reference_bindings(topology_id: str) -> None:
    tid = str(topology_id or "").strip()
    if not tid:
        return
    store = _load_node_agent_bindings()
    if not isinstance(store, dict):
        store = {}
    key = _scope_binding_key(tid, "game-01")
    if not str(store.get(key) or "").strip():
        store[key] = "agent-01"
        _save_node_agent_bindings(store)


def _ensure_design_reference_agents(project_id: str) -> None:
    """设计稿 demo：保证 game-01 可绑定 agent-01 并在 Inspector/节点卡展示。"""
    pid = str(project_id or "").strip()
    if not pid:
        return
    registry = _load_agent_registry_v2()
    if not isinstance(registry, dict):
        registry = {}
    aid = "agent-01"
    existing = registry.get(aid) if isinstance(registry.get(aid), dict) else {}
    if str(existing.get("project_id") or "").strip() and str(existing.get("project_id") or "").strip() != pid:
        return
    if existing.get("agent_id") == aid and str(existing.get("probe_status") or "").upper() == "PASS":
        return
    now = _now_iso()
    registry[aid] = {
        "agent_id": aid,
        "device_id": "device-game-01",
        "display_name": aid,
        "project_id": pid,
        "node_id": "game-01",
        "host_name": "10.0.1.15",
        "host_ip": "10.0.1.15",
        "port": 9501,
        "remote_game_server_port": 9501,
        "status": "ONLINE",
        "probe_status": "PASS",
        "probe_at": now,
        "last_seen": now,
        "version": "v2.3.1",
        "services": [
            {
                "service_id": "svc-game-01-a",
                "agent_id": aid,
                "node_id": "game-01",
                "service_port": 9501,
                "status": "ONLINE",
                "probe_status": "PASS",
            },
            {
                "service_id": "svc-game-01-b",
                "agent_id": aid,
                "node_id": "game-01",
                "service_port": 9502,
                "status": "ONLINE",
                "probe_status": "PASS",
            },
            {
                "service_id": "svc-game-01-c",
                "agent_id": aid,
                "node_id": "game-01",
                "service_port": 9503,
                "status": "ONLINE",
                "probe_status": "PASS",
            },
        ],
    }
    _save_agent_registry_v2(registry)


def _default_topology_content_from_nodes(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = _load_topology(rows)
    if not isinstance(base.get("meta"), dict):
        base["meta"] = {}
    base["meta"]["layout_mode"] = "structured"
    return base


def _topology_seed_content(project_id: str, env_key: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key) or "production"
    cluster_rows = _load_cluster_json() if _project_has_cluster_json(pid) else []
    if cluster_rows:
        return _build_cluster_topology_content(cluster_rows, pid)
    return _core_minimal_topology_content(pid, env, runtime_ids=False)


def _migrate_topology_storage_if_needed() -> None:
    rows = _load_topology_registry()
    contents = _load_topology_contents()
    if rows and contents:
        return

    all_nodes = _load_nodes()
    project_ids = sorted({str(x.get("project_id") or "").strip() for x in all_nodes if isinstance(x, dict) and str(x.get("project_id") or "").strip()})
    if not project_ids:
        project_ids = [""]

    registry_rows: List[Dict[str, Any]] = rows if isinstance(rows, list) else []
    content_map: Dict[str, Any] = contents if isinstance(contents, dict) else {}
    topology_by_scope: Dict[str, str] = {}
    now = _now_iso()
    for project_id in project_ids:
        scoped_nodes = [x for x in all_nodes if isinstance(x, dict) and str(x.get("project_id") or "").strip() == project_id] if project_id else list(all_nodes)
        scoped_envs = sorted({_normalize_env_key(x.get("env") or "") for x in scoped_nodes if isinstance(x, dict)}) or ["production"]
        for env_key in scoped_envs:
            env_nodes = []
            for item in scoped_nodes:
                if not isinstance(item, dict):
                    continue
                item_env = _normalize_env_key(item.get("env") or "")
                if item_env and item_env != env_key:
                    continue
                env_nodes.append(item)
            topology_id = f"topology-{(project_id or 'default').replace('/', '-').replace(' ', '-').lower() or 'default'}-{env_key}-default"
            topology_by_scope[f"{project_id}::{env_key}"] = topology_id
            if not any(str((x or {}).get("topology_id") or "") == topology_id for x in registry_rows if isinstance(x, dict)):
                registry_rows.append(
                    _normalize_topology_registry_row(
                        {
                            "topology_id": topology_id,
                            "project_id": project_id,
                            "env_key": env_key,
                            "name": _env_label(env_key) + "主拓扑",
                            "version_label": "v1.0.0",
                            "owner": "system",
                            "description": "从历史单拓扑配置迁移",
                            "is_default": True,
                            "status": "running" if env_key == "production" else "draft",
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
                )
            content_map[topology_id] = _default_topology_content_from_nodes(env_nodes)

    if registry_rows:
        _save_topology_registry(registry_rows)
    if content_map:
        _save_topology_contents(content_map)

    binding_store = _load_node_agent_bindings()
    if isinstance(binding_store, dict) and binding_store and not any("::" in str(k or "") for k in binding_store.keys()):
        converted: Dict[str, Any] = {}
        for node_id, agent_id in binding_store.items():
            node_text = str(node_id or "").strip()
            if not node_text:
                continue
            raw_node = next((x for x in all_nodes if isinstance(x, dict) and str(x.get("id") or "").strip() == node_text), None)
            project_id = str((raw_node or {}).get("project_id") or "").strip()
            env_key = _normalize_env_key((raw_node or {}).get("env") or "")
            topology_id = topology_by_scope.get(f"{project_id}::{env_key}") or topology_by_scope.get(f"{project_id}::production") or next(iter(content_map.keys()), "")
            converted[_scope_binding_key(topology_id, node_text)] = agent_id
        if converted:
            _save_node_agent_bindings(converted)

    service_binding_store = _load_node_service_bindings()
    if isinstance(service_binding_store, dict) and service_binding_store and not any("::" in str(k or "") for k in service_binding_store.keys()):
        converted_services: Dict[str, Any] = {}
        for node_id, service_id in service_binding_store.items():
            node_text = str(node_id or "").strip()
            if not node_text:
                continue
            raw_node = next((x for x in all_nodes if isinstance(x, dict) and str(x.get("id") or "").strip() == node_text), None)
            project_id = str((raw_node or {}).get("project_id") or "").strip()
            env_key = _normalize_env_key((raw_node or {}).get("env") or "")
            topology_id = topology_by_scope.get(f"{project_id}::{env_key}") or topology_by_scope.get(f"{project_id}::production") or next(iter(content_map.keys()), "")
            converted_services[_scope_binding_key(topology_id, node_text)] = service_id
        if converted_services:
            _save_node_service_bindings(converted_services)

    runtime_rows = _load_runtime_runs()
    runtime_changed = False
    for row in runtime_rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("topology_id") or "").strip():
            continue
        project_id = str(row.get("project_id") or "").strip()
        env_key = _normalize_env_key(row.get("env_key") or "")
        topology_id = topology_by_scope.get(f"{project_id}::{env_key}") or topology_by_scope.get(f"{project_id}::production") or next(iter(content_map.keys()), "")
        row["env_key"] = env_key or "production"
        row["topology_id"] = topology_id
        runtime_changed = True
    if runtime_changed:
        _save_runtime_runs(runtime_rows)


def _list_topologies(project_id: str = "", env_key: Optional[str] = None) -> List[Dict[str, Any]]:
    _migrate_topology_storage_if_needed()
    pid = str(project_id or "").strip()
    if pid == "GomeKu" and _project_has_cluster_json(pid):
        _migrate_gomeku_design_topology_contents(pid)
    env_filter = _normalize_env_key(env_key) if (env_key is not None and str(env_key).strip()) else None
    if pid:
        _ensure_design_demo_registry(pid)
    out: List[Dict[str, Any]] = []
    for item in _load_topology_registry():
        if not isinstance(item, dict):
            continue
        row = _normalize_topology_registry_row(item)
        if pid and row.get("project_id") != pid:
            continue
        if env_filter and row.get("env_key") != env_filter:
            continue
        out.append(row)
    out.sort(key=lambda x: (x.get("project_id") or "", x.get("env_key") or "", 0 if x.get("is_default") else 1, x.get("updated_at") or ""), reverse=False)
    return out


def _ensure_topology_for_scope(project_id: str, env_key: str) -> Dict[str, Any]:
    _migrate_topology_storage_if_needed()
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    rows = _load_topology_registry()
    for item in rows:
        if not isinstance(item, dict):
            continue
        row = _normalize_topology_registry_row(item)
        if row.get("project_id") == pid and row.get("env_key") == env and row.get("is_default"):
            return row
    row = _normalize_topology_registry_row(
        {
            "topology_id": "topology-" + uuid.uuid4().hex[:10],
            "project_id": pid,
            "env_key": env,
            "name": _env_label(env) + "主拓扑",
            "version_label": "v1.0.0",
            "owner": str(session.get("user") or "system"),
            "description": "自动创建的默认拓扑",
            "is_default": True,
            "status": "running" if env == "production" else "draft",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
    )
    rows.append(row)
    _save_topology_registry(rows)
    contents = _load_topology_contents()
    contents[row["topology_id"]] = _topology_seed_content(pid, env)
    _save_topology_contents(contents)
    return row


def _resolve_ops_project_id(raw: str = "") -> str:
    pid = str(raw or "").strip()
    if pid:
        return pid
    pid = str(session.get("ops_last_project") or "").strip()
    if pid:
        return pid
    return "GomeKu"


def _resolve_ops_env_key(raw: str = "") -> str:
    env = str(raw or "").strip()
    if env:
        return _normalize_env_key(env)
    env = str(session.get("ops_last_env") or "").strip()
    if env:
        return _normalize_env_key(env)
    return "production"


def _agent_matches_env(item: Dict[str, Any], env_key: str = "") -> bool:
    if not env_key:
        return True
    env = _normalize_env_key(env_key)
    agent_env = _normalize_env_key(str((item or {}).get("env_key") or (item or {}).get("env") or "production"))
    return agent_env == env


def _resolve_ops_topology_id(project_id: str, env_key: str, raw: str = "") -> str:
    tid = str(raw or "").strip()
    if tid:
        return tid
    ctx = _resolve_topology_context(project_id, env_key, "")
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    return str(row.get("topology_id") or "")


def _ops_platform_redirect_to_runtime_project():
    """Redirect to default project/env if scope params are missing."""
    raw_pid = str(request.args.get("project_id") or "").strip()
    raw_env = str(request.args.get("env_key") or "").strip()
    if raw_pid and raw_env:
        return None
    args = request.args.to_dict(flat=True)
    if not raw_pid:
        args["project_id"] = _resolve_ops_project_id("")
    if not raw_env:
        args["env_key"] = _resolve_ops_env_key("")
    if request.path.rstrip("/").endswith("/topology"):
        if not str(args.get("topology_id") or "").strip():
            args["topology_id"] = _runtime_default_topology_id(
                args.get("project_id", ""),
                args.get("env_key", "production"),
            )
    return redirect(request.path + "?" + urlencode(args))


def _resolve_topology_context(project_id: str = "", env_key: str = "", topology_id: str = "") -> Dict[str, Any]:
    _migrate_topology_storage_if_needed()
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    rows = _list_topologies(pid, env)
    target = None
    if tid:
        for item in rows:
            if str(item.get("topology_id") or "") == tid:
                target = item
                break
    if target is None:
        preferred_tid = _runtime_default_topology_id(pid, env or "production")
        for item in rows:
            if str(item.get("topology_id") or "") == preferred_tid:
                target = item
                break
    if target is None:
        for item in rows:
            if item.get("is_default"):
                target = item
                break
    if target is None and rows:
        target = rows[0]
    if target is None:
        target = _ensure_topology_for_scope(pid, env or "production")
        rows = _list_topologies(pid, env or "production")
    tid_str = str(target.get("topology_id") or "")
    project_for_topo = str(target.get("project_id") or pid or "")
    env_for_topo = str(target.get("env_key") or env or "production")
    contents = _load_topology_contents()
    topo = contents.get(tid_str) if isinstance(contents.get(tid_str), dict) else {}
    if not topo:
        topo = _topology_seed_content(project_for_topo, env_for_topo)
        contents[tid_str] = topo
        _save_topology_contents(contents)
    elif _project_has_cluster_json(project_for_topo):
        topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        node_ids = {
            str(n.get("id") or "")
            for n in (topo.get("nodes") or [])
            if isinstance(n, dict) and str(n.get("id") or "")
        }
        needs_cluster_sync = (
            _topology_has_design_demo_nodes(topo)
            or not (topo_meta.get("runtime_topology") or topo_meta.get("cluster_source"))
            or _topology_missing_runtime_infra(topo)
            or bool({"tcp-01"} & node_ids)
        )
        if needs_cluster_sync:
            _sync_cluster_to_agents(project_for_topo)
            _apply_runtime_minimal_topology(tid_str, project_for_topo, env_for_topo)
            _purge_design_demo_project_state(project_for_topo, tid_str)
            contents = _load_topology_contents()
            topo = contents.get(tid_str) if isinstance(contents.get(tid_str), dict) else topo
    elif _needs_design_reference_upgrade(topo):
        meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        if not meta.get("cluster_source") and not meta.get("runtime_topology"):
            topo = _core_minimal_topology_content(project_for_topo, env_for_topo, runtime_ids=False)
            contents[tid_str] = topo
            _save_topology_contents(contents)
    topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    runtime_node_ids = [
        str(n.get("id") or "")
        for n in (topo.get("nodes") or [])
        if isinstance(n, dict) and str(n.get("id") or "").endswith("-cn-1")
    ]
    if runtime_node_ids and (topo_meta.get("runtime_topology") or topo_meta.get("cluster_source")):
        _ensure_runtime_topology_bindings(tid_str, runtime_node_ids)
    elif not topo_meta.get("cluster_source") and not topo_meta.get("runtime_topology"):
        _ensure_design_reference_bindings(tid_str)
        _ensure_design_reference_agents(project_for_topo or pid or "")
    return {
        "topology": topo,
        "row": target,
        "topologies": rows,
    }


def _normalize_layout_spacing(raw: Any) -> Dict[str, int]:
    row = raw if isinstance(raw, dict) else {}
    try:
        rank_gap = int(row.get("rank_gap") or 268)
    except Exception:
        rank_gap = 268
    try:
        row_gap = int(row.get("row_gap") or 128)
    except Exception:
        row_gap = 128
    return {
        "rank_gap": max(160, min(480, rank_gap)),
        "row_gap": max(80, min(240, row_gap)),
    }


def _load_topology_scoped(project_id: str = "", env_key: str = "", topology_id: str = "") -> Dict[str, Any]:
    ctx = _resolve_topology_context(project_id, env_key, topology_id)
    topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    viewport = meta.get("viewport") if isinstance(meta.get("viewport"), dict) else {}
    normalized_nodes: List[Dict[str, Any]] = []
    seen = set()
    for item in nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        role = str(item.get("role") or "business")
        kind = _infer_node_kind(role, str(item.get("kind") or ""))
        ui = item.get("ui") if isinstance(item.get("ui"), dict) else {}
        ui = _strip_default_node_ui_color(ui)
        if ui.get("list_only"):
            ui = dict(ui)
            ui.pop("list_only", None)
        ui["ports"] = _normalize_ports(kind, ui.get("ports"))
        normalized_nodes.append(
            {
                "id": nid,
                "name": str(item.get("name") or nid),
                "server_id": str(item.get("server_id") or nid),
                "project_id": str(item.get("project_id") or ctx.get("row", {}).get("project_id") or ""),
                "env": str(item.get("env") or ctx.get("row", {}).get("env_key") or "production"),
                "role": role,
                "kind": kind,
                "desc": str(item.get("desc") or ""),
                "bizStatus": str(item.get("bizStatus") or "normal"),
                "owner": str(item.get("owner") or ""),
                "group": str(item.get("group") or ""),
                "node_category": str(item.get("node_category") or ""),
                "node_type": str(item.get("node_type") or ""),
                "preset_id": str(item.get("preset_id") or ""),
                "daemon_profile": str(item.get("daemon_profile") or ""),
                "daemon_start_cmd": str(item.get("daemon_start_cmd") or ""),
                "daemon_stop_cmd": str(item.get("daemon_stop_cmd") or ""),
                "daemon_port": int(item.get("daemon_port") or 0) if item.get("daemon_port") is not None else 0,
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "ui": ui,
                "x": float(item.get("x") or ui.get("x") or 0),
                "y": float(item.get("y") or ui.get("y") or 0),
            }
        )
    valid_ids = {str(x.get("id") or "") for x in normalized_nodes if isinstance(x, dict)}
    normalized_edges: List[Dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to or frm not in valid_ids or to not in valid_ids:
            continue
        normalized_edges.append(
            {
                "id": str(edge.get("id") or f"edge-{uuid.uuid4().hex[:10]}"),
                "from": frm,
                "to": to,
                "from_port": str(edge.get("from_port") or "out-1"),
                "to_port": str(edge.get("to_port") or "in-1"),
                "type": str(edge.get("type") or "depends_on"),
                "note": str(edge.get("note") or ""),
                "ui": edge.get("ui") if isinstance(edge.get("ui"), dict) else {},
            }
        )
    normalized_edges = _repair_runtime_topology_edges(normalized_nodes, normalized_edges, meta)
    out_meta: Dict[str, Any] = {
            "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
            "version": int(meta.get("version") or 1),
            "updated_at": str(meta.get("updated_at") or ""),
            "layout_mode": str(meta.get("layout_mode") or "structured"),
            "layout_locked": bool(meta.get("layout_locked")),
            "design_reference": str(meta.get("design_reference") or ""),
        "runtime_topology": bool(meta.get("runtime_topology")),
        "cluster_source": bool(meta.get("cluster_source")),
        "workbench_mode": str(meta.get("workbench_mode") or "edit"),
        "workbench_locked_mode": str(meta.get("workbench_locked_mode") or ""),
        "workbench_mode_updated_at": str(meta.get("workbench_mode_updated_at") or ""),
        "description": str(meta.get("description") or ""),
    }
    if isinstance(meta.get("layout_spacing"), dict) or meta.get("layout_spacing_customized"):
        out_meta["layout_spacing"] = _normalize_layout_spacing(meta.get("layout_spacing"))
        out_meta["layout_spacing_customized"] = bool(meta.get("layout_spacing_customized"))
    return {
        "nodes": normalized_nodes,
        "edges": normalized_edges,
        "meta": out_meta,
        "registry": ctx.get("row"),
        "topologies": ctx.get("topologies") if isinstance(ctx.get("topologies"), list) else [],
    }


def _save_topology_scoped(project_id: str, env_key: str, topology_id: str, topology: Dict[str, Any]) -> Dict[str, Any]:
    ctx = _resolve_topology_context(project_id, env_key, topology_id)
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    tid = str(row.get("topology_id") or topology_id or "").strip()
    normalized = _load_topology_scoped(str(row.get("project_id") or project_id or ""), str(row.get("env_key") or env_key or ""), tid)
    incoming_nodes = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
    incoming_edges = topology.get("edges") if isinstance(topology.get("edges"), list) else []
    incoming_meta = topology.get("meta") if isinstance(topology.get("meta"), dict) else {}
    replace_all = bool(incoming_meta.get("runtime_topology") or incoming_meta.get("replace_all"))

    node_index: Dict[str, Any] = {}
    if not replace_all:
        node_index = {str(x.get("id") or ""): x for x in (normalized.get("nodes") or []) if isinstance(x, dict)}
    for item in incoming_nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid:
            continue
        src = node_index.get(nid) or {
            "id": nid,
            "name": str(item.get("name") or nid),
            "server_id": str(item.get("server_id") or nid),
            "project_id": str(row.get("project_id") or project_id or ""),
            "env": str(row.get("env_key") or env_key or "production"),
            "role": "business",
            "kind": "standard",
            "desc": "",
            "bizStatus": "normal",
            "owner": "",
            "tags": [],
            "ui": {},
            "x": 0.0,
            "y": 0.0,
        }
        src["name"] = str(item.get("name") or src.get("name") or nid)
        src["server_id"] = str(item.get("server_id") or src.get("server_id") or nid)
        src["role"] = str(item.get("role") or src.get("role") or "business")
        src["kind"] = _infer_node_kind(str(src.get("role") or "business"), str(item.get("kind") or src.get("kind") or ""))
        src["desc"] = str(item.get("desc") or src.get("desc") or "")
        src["bizStatus"] = str(item.get("bizStatus") or src.get("bizStatus") or "normal")
        src["owner"] = str(item.get("owner") or src.get("owner") or "")
        src["node_category"] = str(item.get("node_category") or src.get("node_category") or "")
        src["node_type"] = str(item.get("node_type") or src.get("node_type") or "")
        src["tags"] = item.get("tags") if isinstance(item.get("tags"), list) else (src.get("tags") if isinstance(src.get("tags"), list) else [])
        for field in (
            "preset_id", "daemon_profile", "daemon_start_cmd", "daemon_stop_cmd", "group", "notes",
        ):
            if field in item:
                src[field] = item.get(field)
        if "daemon_port" in item:
            try:
                src["daemon_port"] = int(item.get("daemon_port") or 0)
            except Exception:
                pass
        src["ui"] = item.get("ui") if isinstance(item.get("ui"), dict) else (src.get("ui") if isinstance(src.get("ui"), dict) else {})
        src["ui"]["ports"] = _normalize_ports(str(src.get("kind") or "standard"), src["ui"].get("ports"))
        try:
            src["x"] = float(item.get("x"))
        except Exception:
            pass
        try:
            src["y"] = float(item.get("y"))
        except Exception:
            pass
        src["project_id"] = str(row.get("project_id") or project_id or "")
        src["env"] = str(row.get("env_key") or env_key or "production")
        node_index[nid] = src

    valid_ids = set(node_index.keys())
    merged_edges: List[Dict[str, Any]] = []
    for edge in incoming_edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to or frm == to or frm not in valid_ids or to not in valid_ids:
            continue
        merged_edges.append(
            {
                "id": str(edge.get("id") or f"edge-{uuid.uuid4().hex[:10]}"),
                "from": frm,
                "to": to,
                "from_port": str(edge.get("from_port") or "out-1"),
                "to_port": str(edge.get("to_port") or "in-1"),
                "type": str(edge.get("type") or "depends_on"),
                "note": str(edge.get("note") or ""),
                "ui": edge.get("ui") if isinstance(edge.get("ui"), dict) else {},
            }
        )
    viewport = incoming_meta.get("viewport") if isinstance(incoming_meta.get("viewport"), dict) else {}
    prev_meta = normalized.get("meta") if isinstance(normalized.get("meta"), dict) else {}
    spacing = incoming_meta.get("layout_spacing") if isinstance(incoming_meta.get("layout_spacing"), dict) else prev_meta.get("layout_spacing")
    spacing_customized = bool(
        incoming_meta.get("layout_spacing_customized")
        if "layout_spacing_customized" in incoming_meta
        else prev_meta.get("layout_spacing_customized")
    )
    if isinstance(incoming_meta.get("layout_spacing"), dict):
        spacing_customized = True
    meta_out: Dict[str, Any] = {
        "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
        "version": int(incoming_meta.get("version") or prev_meta.get("version") or 1),
        "updated_at": _now_iso(),
        "layout_mode": str(incoming_meta.get("layout_mode") or prev_meta.get("layout_mode") or "structured"),
        "layout_locked": bool(incoming_meta.get("layout_locked") if "layout_locked" in incoming_meta else prev_meta.get("layout_locked")),
        "design_reference": str(incoming_meta.get("design_reference") or prev_meta.get("design_reference") or ""),
        "runtime_topology": bool(incoming_meta.get("runtime_topology") or prev_meta.get("runtime_topology")),
        "cluster_source": bool(incoming_meta.get("cluster_source") or prev_meta.get("cluster_source")),
        "description": str(incoming_meta.get("description") or prev_meta.get("description") or ""),
    }
    if spacing_customized:
        meta_out["layout_spacing"] = _normalize_layout_spacing(spacing)
        meta_out["layout_spacing_customized"] = True
    payload = {
        "nodes": list(node_index.values()),
        "edges": merged_edges,
        "meta": meta_out,
        "updated_at": _now_iso(),
    }
    contents = _load_topology_contents()
    contents[tid] = payload
    _save_topology_contents(contents)

    rows = _load_topology_registry()
    for idx, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        if str(item.get("topology_id") or "") != tid:
            continue
        merged = _normalize_topology_registry_row(item)
        merged["updated_at"] = _now_iso()
        rows[idx] = merged
        break
    _save_topology_registry(rows)
    saved = dict(payload)
    saved["registry"] = _resolve_topology_context(str(row.get("project_id") or ""), str(row.get("env_key") or ""), tid).get("row")
    return saved


def _topology_gateway_node(project_id: str = "", env_key: str = "") -> Dict[str, Any]:
    return (
        _resolve_node(project_id=str(project_id or "").strip(), env=_normalize_env_key(env_key))
        or _resolve_node(project_id=str(project_id or "").strip())
        or _resolve_node()
        or {}
    )


def _build_runtime_node_from_topology_node(project_id: str, env_key: str, topo_node: Dict[str, Any], topology_id: str = "") -> Dict[str, Any]:
    base = dict(_topology_gateway_node(project_id, env_key))
    node = topo_node if isinstance(topo_node, dict) else {}
    node_id = str(node.get("id") or "").strip()
    base["id"] = node_id
    base["name"] = str(node.get("name") or node_id or base.get("name") or "")
    base["project_id"] = str(project_id or base.get("project_id") or "")
    base["env"] = _normalize_env_key(env_key or node.get("env") or base.get("env") or "")
    base["server_id"] = str(node.get("server_id") or node_id or base.get("server_id") or "")
    base["owner"] = str(node.get("owner") or base.get("owner") or "")
    base["role"] = str(node.get("role") or base.get("role") or "business")
    base["description"] = str(node.get("desc") or node.get("description") or base.get("description") or "")
    base["topology_id"] = str(topology_id or "")
    base["preset_id"] = str(node.get("preset_id") or "").strip()
    base["daemon_profile"] = str(node.get("daemon_profile") or "").strip()
    base["daemon_start_cmd"] = str(node.get("daemon_start_cmd") or "").strip()
    base["daemon_stop_cmd"] = str(node.get("daemon_stop_cmd") or "").strip()
    if node.get("daemon_port") is not None:
        base["daemon_port"] = int(node.get("daemon_port") or 0)
    contract = _resolve_node_contract_for_topology_node(node)
    port = _resolve_topology_node_port(node, contract, None, None)
    if port > 0:
        base["port"] = port
    preset_id = str(node.get("preset_id") or contract.get("preset_id") or "").strip()
    if preset_id and (not base.get("daemon_start_cmd") or not base.get("daemon_stop_cmd")):
        daemon_defaults = _contract_daemon_defaults(preset_id, port)
        if not base.get("daemon_start_cmd"):
            base["daemon_start_cmd"] = _format_contract_command(str(daemon_defaults.get("StartCommand") or ""), port)
        if not base.get("daemon_stop_cmd"):
            base["daemon_stop_cmd"] = _format_contract_command(str(daemon_defaults.get("StopCommand") or ""), port)
    if preset_id == "mongo_db" and base.get("daemon_start_cmd"):
        mongo_dbpath = _gomeku_mongo_dbpath()
        os.makedirs(mongo_dbpath, exist_ok=True)
    return base


def _node_contract_registry_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    return os.path.join(repo_root, "docs", "ops_alignment", "node_contract_registry.json")


def _load_node_contract_registry() -> Dict[str, Any]:
    global _NODE_CONTRACT_REGISTRY_CACHE
    if isinstance(_NODE_CONTRACT_REGISTRY_CACHE, dict) and _NODE_CONTRACT_REGISTRY_CACHE.get("contracts"):
        return _NODE_CONTRACT_REGISTRY_CACHE
    path = _node_contract_registry_path()
    data: Dict[str, Any] = {"contracts": [], "env_profiles": {}}
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                data = raw
    except Exception:
        pass
    _NODE_CONTRACT_REGISTRY_CACHE = data
    return data


def _load_node_contract(preset_id: str) -> Optional[Dict[str, Any]]:
    pid = str(preset_id or "").strip()
    if not pid:
        return None
    for item in _load_node_contract_registry().get("contracts") or []:
        if isinstance(item, dict) and str(item.get("preset_id") or "") == pid:
            return item
    return None


def _resolve_env_profile_name() -> str:
    if os.name == "nt":
        return "local_windows"
    if os.name == "posix":
        try:
            if os.uname().sysname == "Darwin":
                return "local_macos"
        except Exception:
            pass
        return "local_linux"
    return "local_macos"


def _format_contract_command(template: str, port: int, extras: Optional[Dict[str, Any]] = None) -> str:
    text = str(template or "").strip()
    if not text:
        return ""
    merged = {
        "port": int(port or 0),
        "qps": 300,
        "duration_sec": 180,
        "data_dir": _gomeku_mongo_dbpath(),
    }
    if isinstance(extras, dict):
        merged.update(extras)
    try:
        return text.format(**merged)
    except Exception:
        out = text.replace("{port}", str(int(port or 0)))
        return out.replace("{data_dir}", str(merged.get("data_dir") or _gomeku_mongo_dbpath()))


def _resolve_node_contract_for_topology_node(node: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    preset_id = str(node.get("preset_id") or "").strip()
    if preset_id:
        hit = _load_node_contract(preset_id)
        if hit:
            return hit
    nid = str(node.get("id") or "").strip()
    for preset in _load_node_presets():
        if not isinstance(preset, dict):
            continue
        pid = str(preset.get("preset_id") or "").strip()
        if pid and (nid == pid or nid.startswith(pid + "-")):
            hit = _load_node_contract(pid)
            if hit:
                return hit
    role = str(node.get("role") or "").strip().lower()
    if role == "admin":
        role = "ops"
    for item in _load_node_contract_registry().get("contracts") or []:
        if isinstance(item, dict) and str(item.get("role") or "").strip().lower() == role:
            return item
    return {}


def _contract_daemon_defaults(preset_id: str, port: int) -> Dict[str, str]:
    reg = _load_node_contract_registry()
    profiles = reg.get("env_profiles") if isinstance(reg.get("env_profiles"), dict) else {}
    profile_name = _resolve_env_profile_name()
    profile = profiles.get(profile_name) if isinstance(profiles.get(profile_name), dict) else {}
    raw = profile.get(preset_id) if isinstance(profile.get(preset_id), dict) else {}
    out: Dict[str, str] = {}
    for key in ("StartCommand", "StopCommand", "HealthCheckCommand", "StressCommand", "ScheduleCommand"):
        val = _format_contract_command(str(raw.get(key) or ""), port)
        if val:
            out[key] = val
    return out


def _cluster_type_for_contract(contract: Dict[str, Any], role: str) -> str:
    if isinstance(contract, dict) and str(contract.get("cluster_type") or "").strip():
        return str(contract.get("cluster_type") or "").strip()
    return _cluster_type_for_role(role)


def _cluster_type_for_role(role: str) -> str:
    mapping = {
        "gateway": "Gateway",
        "auth": "Auth",
        "business": "Game",
        "pressure": "Daemon",
        "database": "Daemon",
        "cache": "Daemon",
        "mq": "Daemon",
        "search": "Search",
        "scheduler": "Daemon",
        "admin": "Ops",
        "edge": "Gateway",
        "analytics": "Analytics",
        "ops": "Ops",
        "transport": "Tcp",
    }
    key = str(role or "").strip().lower()
    if key == "admin":
        key = "ops"
    return mapping.get(key, key.title() or "Game")


def _cluster_category_for_role(role: str) -> str:
    key = str(role or "").strip().lower()
    if key in ("database", "cache", "mq", "search"):
        return "middleware"
    if key in ("pressure",):
        return "test"
    if key in ("gateway", "edge", "transport"):
        return "network"
    return "application"


def _resolve_topology_node_port(
    node: Dict[str, Any],
    contract: Dict[str, Any],
    service: Optional[Dict[str, Any]],
    agent: Optional[Dict[str, Any]],
) -> int:
    ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
    remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
    for candidate in (
        int(node.get("daemon_port") or 0),
        int(remote.get("port") or 0),
        int((contract or {}).get("default_port") or 0),
        int((service or {}).get("service_port") or 0),
        int((service or {}).get("remote_game_server_port") or 0),
        int((agent or {}).get("remote_game_server_port") or 0) if isinstance(agent, dict) else 0,
        int((agent or {}).get("port") or 0) if isinstance(agent, dict) else 0,
    ):
        if candidate > 0:
            return candidate
    return 0


def _cluster_relay_port_for_type(cluster_type: str, role: str) -> int:
    t = str(cluster_type or "").strip().lower()
    r = str(role or "").strip().lower()
    if t == "auth" or r == "auth":
        return 15501
    if t in ("game", "cross") or r in ("game", "business"):
        return 15502 if t != "cross" else 15503
    return 0


def _enrich_cluster_relay_metadata(
    metadata: Dict[str, Any],
    cluster_type: str,
    role: str,
) -> Dict[str, Any]:
    meta = dict(metadata or {})
    relay_port = _cluster_relay_port_for_type(cluster_type, role)
    if relay_port > 0:
        meta.setdefault("ClusterRelayPort", str(relay_port))
    meta.setdefault("ClusterRelayToken", _CLUSTER_RELAY_TOKEN_DEFAULT)
    return meta


def _build_daemon_metadata(
    node: Dict[str, Any],
    contract: Dict[str, Any],
    port: int,
    base_meta: Dict[str, Any],
) -> Dict[str, Any]:
    meta = dict(base_meta or {})
    preset_id = str(node.get("preset_id") or contract.get("preset_id") or "").strip()
    execution_model = str(contract.get("execution_model") or "").strip().lower()
    if execution_model not in ("daemon", "worker"):
        return meta
    start_cmd = str(node.get("daemon_start_cmd") or "").strip()
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    defaults = _contract_daemon_defaults(preset_id, port) if preset_id else {}
    if not start_cmd:
        start_cmd = str(defaults.get("StartCommand") or "").strip()
    if not stop_cmd:
        stop_cmd = str(defaults.get("StopCommand") or "").strip()
    if start_cmd:
        meta["StartCommand"] = start_cmd
    if stop_cmd:
        meta["StopCommand"] = stop_cmd
    for key in ("HealthCheckCommand", "StressCommand", "ScheduleCommand"):
        node_val = str(node.get(key.lower()) or node.get(key) or "").strip()
        if not node_val:
            node_val = str(defaults.get(key) or "").strip()
        if node_val:
            meta[key] = node_val
    if preset_id:
        meta["PresetId"] = preset_id
    meta["ExecutionModel"] = execution_model
    return meta


def _validate_topology_contract(topo: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("disabled") or str(node.get("bizStatus") or "").lower() == "disabled":
            continue
        contract = _resolve_node_contract_for_topology_node(node)
        execution_model = str(contract.get("execution_model") or "").strip().lower()
        if execution_model not in ("daemon", "worker"):
            continue
        node_id = str(node.get("id") or node.get("server_id") or "").strip() or "unknown"
        port = _resolve_topology_node_port(node, contract, None, None)
        preset_id = str(node.get("preset_id") or contract.get("preset_id") or "").strip()
        start_cmd = str(node.get("daemon_start_cmd") or "").strip()
        if not start_cmd and preset_id:
            start_cmd = str(_contract_daemon_defaults(preset_id, port).get("StartCommand") or "").strip()
        if port <= 0:
            errors.append(f"节点 {node_id} 缺少有效端口（daemon/worker 类型需要 default_port 或 ui.remote.port）")
        if not start_cmd:
            errors.append(f"节点 {node_id} 缺少 StartCommand（请在检查器填写 daemon 启动命令）")
    return (len(errors) == 0, errors)


def _topology_to_cluster_payload(project_id: str, env_key: str, topology_id: str) -> Dict[str, Any]:
    scoped = _load_topology_scoped(project_id, env_key, topology_id)
    topo = {
        "nodes": scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else [],
        "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
        "meta": scoped.get("meta") if isinstance(scoped.get("meta"), dict) else {},
    }
    row = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    agent_bindings = _load_scope_agent_bindings(topology_id)
    service_bindings = _load_scope_service_bindings(topology_id)
    services = _services_for_project(project_id)
    services_map = {str(x.get("service_id") or "").strip(): x for x in services if isinstance(x, dict)}
    agents_map = {str(x.get("agent_id") or "").strip(): x for x in _agents_v2_for_project(project_id) if isinstance(x, dict)}
    edge_in: Dict[str, List[str]] = {}
    edge_out: Dict[str, List[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to:
            continue
        edge_out.setdefault(frm, []).append(to)
        edge_in.setdefault(to, []).append(frm)

    def _resolve_server_id(target_node: Optional[Dict[str, Any]]) -> str:
        if not isinstance(target_node, dict):
            return ""
        return str(target_node.get("server_id") or target_node.get("id") or "").strip()

    cluster_servers: List[Dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        contract = _resolve_node_contract_for_topology_node(node)
        role = str(node.get("role") or contract.get("role") or "business").strip().lower()
        if role == "admin":
            role = "ops"
        service_id = str(service_bindings.get(node_id) or "").strip()
        service = services_map.get(service_id) if service_id else None
        agent_id = str(agent_bindings.get(node_id) or (service or {}).get("agent_id") or "").strip()
        agent = agents_map.get(agent_id) if agent_id else None
        endpoints = []
        if isinstance(service, dict) and isinstance(service.get("endpoints"), list):
            endpoints = service.get("endpoints") or []
        elif isinstance(agent, dict) and isinstance(((agent.get("network") or {}).get("endpoints")), list):
            endpoints = ((agent.get("network") or {}).get("endpoints")) or []
        endpoint = str(endpoints[0] or "").strip() if endpoints else ""
        endpoint_host = endpoint.split(":")[0].strip() if endpoint and ":" in endpoint else endpoint
        service_port = _resolve_topology_node_port(node, contract, service, agent)
        remote_port = service_port
        runtime_status = str((service or {}).get("status") or (service or {}).get("run_state") or (agent or {}).get("status") or (agent or {}).get("run_state") or "UNKNOWN").upper()
        cluster_type = _cluster_type_for_contract(contract, role)
        probe_host = _resolve_agent_probe_host(agent, service, node)
        if probe_host in ("0.0.0.0", "*", ""):
            probe_host = endpoint_host or DEFAULT_LOOPBACK
        bind_host = endpoint_host or ("0.0.0.0" if role in ("gateway", "transport", "edge") else "127.0.0.1")
        relay_port = _cluster_relay_port_for_type(cluster_type, role)
        base_meta = {
            "ProjectId": str(project_id or ""),
            "EnvKey": _normalize_env_key(env_key),
            "TopologyId": str(topology_id or ""),
            "TopologyName": str(row.get("name") or ""),
            "VersionLabel": str(row.get("version_label") or ""),
            "NodeId": node_id,
            "AgentId": agent_id,
            "ServiceId": str((service or {}).get("service_id") or ""),
            "AgentWs": str(endpoint or ""),
            "RemoteGameServerPort": str(remote_port or ""),
            "ProbeHost": probe_host,
            "PresetId": str(node.get("preset_id") or contract.get("preset_id") or ""),
            "ProbeStrategy": str(contract.get("probe_strategy") or "tcp"),
        }
        if relay_port > 0:
            base_meta["ClusterRelayPort"] = str(relay_port)
        base_meta["ClusterRelayToken"] = _CLUSTER_RELAY_TOKEN_DEFAULT
        metadata = _enrich_cluster_relay_metadata(
            _build_daemon_metadata(node, contract, service_port, base_meta),
            cluster_type,
            role,
        )
        cluster_servers.append(
            {
                "ServerId": str(node.get("server_id") or node_id),
                "DisplayName": str(node.get("name") or node_id),
                "Type": cluster_type,
                "Role": role,
                "Category": _cluster_category_for_role(role),
                "Description": str(node.get("desc") or ""),
                "UpstreamServerIds": [
                    sid for sid in [
                        _resolve_server_id(next((x for x in nodes if isinstance(x, dict) and str(x.get("id") or "") == upstream_id), None))
                        for upstream_id in (edge_in.get(node_id) or [])
                    ] if sid
                ],
                "DownstreamServerIds": [
                    sid for sid in [
                        _resolve_server_id(next((x for x in nodes if isinstance(x, dict) and str(x.get("id") or "") == downstream_id), None))
                        for downstream_id in (edge_out.get(node_id) or [])
                    ] if sid
                ],
                "Host": bind_host,
                "ProbeHost": probe_host,
                "Port": service_port,
                "State": "Online" if runtime_status in ("ONLINE", "READY", "RUNNING", "SUCCESS") else "Offline",
                "Metadata": metadata,
            }
        )
    return {
        "project_id": str(project_id or ""),
        "env_key": _normalize_env_key(env_key),
        "topology_id": str(topology_id or ""),
        "topology_name": str(row.get("name") or ""),
        "version_label": str(row.get("version_label") or ""),
        "cluster": {
            "MaintenanceMessage": "Managed by Ops topology workbench.",
            "EnableHotReload": True,
            "Servers": cluster_servers,
        },
    }


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


def _sync_topology_to_game_server(project_id: str, env_key: str, topology_id: str, actor: str) -> Dict[str, Any]:
    gateway_node = _topology_gateway_node(project_id, env_key)
    if not gateway_node:
        return {"ok": False, "error": "missingops_gateway_node", "message": "未找到可用的 Ops 网关节点"}
    payload = _topology_to_cluster_payload(project_id, env_key, topology_id)
    result = ops_gateway.apply_topology(
        gateway_node,
        payload=payload,
        actor=actor,
        reason="topology save sync",
        ticket_id="OPS-TOPO-" + uuid.uuid4().hex[:8],
    )
    return {
        "ok": bool(result.get("success")),
        "message": str(result.get("message") or ""),
        "status": int(result.get("status") or 0),
        "data": result.get("data") if isinstance(result.get("data"), dict) else {},
        "payload": payload,
    }


def _runtime_default_topology_id(project_id: str = "", env_key: str = "") -> str:
    pid = str(project_id or "").strip() or "GomeKu"
    env = _normalize_env_key(env_key or "production")
    safe = pid.replace("/", "-").replace(" ", "-").lower() or "default"
    return f"topology-{safe}-{env}-default"


def _binding_fallback_topology_ids(project_id: str = "", env_key: str = "", topology_id: str = "") -> List[str]:
    tid = str(topology_id or "").strip()
    out: List[str] = []
    for candidate in (
        tid,
        _runtime_default_topology_id(project_id, env_key),
        "topology-gomeku-production-default",
        "topology-design-gomeku-production",
    ):
        c = str(candidate or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def _load_scope_agent_bindings(topology_id: str) -> Dict[str, str]:
    data = _load_node_agent_bindings()
    out: Dict[str, str] = {}
    tid = str(topology_id or "").strip()
    for key, value in (data.items() if isinstance(data, dict) else []):
        text = str(key or "").strip()
        if not text or not str(value or "").strip():
            continue
        if "::" in text:
            scope_id, node_id = text.split("::", 1)
            if scope_id != tid:
                continue
            out[node_id] = str(value or "").strip()
        elif not tid:
            out[text] = str(value or "").strip()
    return out


def _resolve_scope_agent_bindings_for_scope(
    topology_id: str,
    project_id: str = "",
    env_key: str = "",
    valid_nodes: Optional[set] = None,
) -> Dict[str, str]:
    best: Dict[str, str] = {}
    nodes = valid_nodes if isinstance(valid_nodes, set) else None
    for tid in _binding_fallback_topology_ids(project_id, env_key, topology_id):
        cur = _load_scope_agent_bindings(tid)
        if not cur:
            continue
        if nodes:
            filtered = {k: v for k, v in cur.items() if k in nodes}
            if len(filtered) > len(best):
                best = filtered
        elif len(cur) > len(best):
            best = cur
    return best


def _resolve_scope_service_bindings_for_scope(
    topology_id: str,
    project_id: str = "",
    env_key: str = "",
    valid_nodes: Optional[set] = None,
) -> Dict[str, str]:
    best: Dict[str, str] = {}
    nodes = valid_nodes if isinstance(valid_nodes, set) else None
    for tid in _binding_fallback_topology_ids(project_id, env_key, topology_id):
        cur = _load_scope_service_bindings(tid)
        if not cur:
            continue
        if nodes:
            filtered = {k: v for k, v in cur.items() if k in nodes}
            if len(filtered) > len(best):
                best = filtered
        elif len(cur) > len(best):
            best = cur
    return best


def _save_scope_agent_binding(topology_id: str, node_id: str, agent_id: str) -> Dict[str, Any]:
    data = _load_node_agent_bindings()
    if not isinstance(data, dict):
        data = {}
    key = _scope_binding_key(topology_id, node_id)
    if agent_id:
        data[key] = agent_id
    else:
        data.pop(key, None)
    _save_node_agent_bindings(data)
    return data


def _load_scope_service_bindings(topology_id: str) -> Dict[str, str]:
    data = _load_node_service_bindings()
    out: Dict[str, str] = {}
    tid = str(topology_id or "").strip()
    for key, value in (data.items() if isinstance(data, dict) else []):
        text = str(key or "").strip()
        if not text or not str(value or "").strip():
            continue
        if "::" in text:
            scope_id, node_id = text.split("::", 1)
            if scope_id != tid:
                continue
            out[node_id] = str(value or "").strip()
        elif not tid:
            out[text] = str(value or "").strip()
    return out


def _save_scope_service_binding(topology_id: str, node_id: str, service_id: str) -> Dict[str, Any]:
    data = _load_node_service_bindings()
    if not isinstance(data, dict):
        data = {}
    key = _scope_binding_key(topology_id, node_id)
    if service_id:
        data[key] = service_id
    else:
        data.pop(key, None)
    _save_node_service_bindings(data)
    return data


def _runtime_active_for_scope(project_id: str, env_key: str, topology_id: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    rows = _load_runtime_runs()
    latest_start = None
    latest_stop = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if pid and str(row.get("project_id") or "") != pid:
            continue
        if env and _normalize_env_key(row.get("env_key") or "") != env:
            continue
        if tid and str(row.get("topology_id") or "") != tid:
            continue
        op = str(row.get("op") or "").lower()
        ts = str(row.get("updated_at") or row.get("created_at") or "")
        if op == "start":
            prev_ts = str((latest_start or {}).get("updated_at") or (latest_start or {}).get("created_at") or "")
            if latest_start is None or ts >= prev_ts:
                latest_start = row
        if op == "stop":
            prev_ts = str((latest_stop or {}).get("updated_at") or (latest_stop or {}).get("created_at") or "")
            if latest_stop is None or ts >= prev_ts:
                latest_stop = row
    if not latest_start:
        return {"active": False, "run_id": "", "status": "", "reason": "no_start_run"}
    start_ts = str(latest_start.get("updated_at") or latest_start.get("created_at") or "")
    stop_ts = str((latest_stop or {}).get("updated_at") or (latest_stop or {}).get("created_at") or "")
    stop_st = str((latest_stop or {}).get("status") or "").lower()
    if latest_stop and stop_ts and start_ts and stop_ts >= start_ts:
        if stop_st in ("success", "running", "queued"):
            return {
                "active": False,
                "run_id": str(latest_stop.get("run_id") or latest_start.get("run_id") or ""),
                "status": stop_st,
                "reason": "stopped_after_start" if stop_st == "success" else "stop_in_progress",
            }
        if stop_st in ("failed", "timeout", "canceled"):
            return {
                "active": True,
                "run_id": str(latest_start.get("run_id") or ""),
                "status": str(latest_start.get("status") or ""),
                "reason": "stop_failed",
            }
    start_st = str(latest_start.get("status") or "").lower()
    if start_st in ("failed", "success", "timeout", "canceled"):
        return {"active": False, "run_id": str(latest_start.get("run_id") or ""), "status": start_st, "reason": "start_finished"}
    return {"active": True, "run_id": str(latest_start.get("run_id") or ""), "status": start_st, "reason": "start_alive"}


def _default_agent_policy() -> Dict[str, Any]:
    return {
        "mtls_required": False,
        "lease_timeout_sec": 60,
        "max_retries": 2,
        "default_node_concurrency": 1,
        "agent_online_fresh_sec": 120,
        "rollout": {
            "enabled": False,
            "desired_version": "",
            "channel": "stable",
            "percent": 0,
            "allow_ids": [],
        },
    }


def _load_agent_policy() -> Dict[str, Any]:
    raw = _load_json_config(OPS_AGENT_POLICY_KEY, {})
    out = _default_agent_policy()
    if isinstance(raw, dict):
        for k in ("mtls_required", "lease_timeout_sec", "max_retries", "default_node_concurrency", "agent_online_fresh_sec"):
            if k in raw:
                out[k] = raw[k]
        if isinstance(raw.get("rollout"), dict):
            merged_rollout = out["rollout"]
            merged_rollout.update(raw.get("rollout"))
            out["rollout"] = merged_rollout
    return out


# ──────────────────────────────────────────────────────────────────────
#  Cluster → Agent 同步：从 game-server 的 cluster.json /ops/cluster 自动同步拓扑
# ──────────────────────────────────────────────────────────────────────

def _gomeku_mongo_dbpath() -> str:
    """Mongo 数据目录：全平台统一使用项目 DATA_DIR。"""
    return os.path.join(DATA_DIR, "gomeku-mongo")


def _gameserver_repo_has_executable(repo: str) -> bool:
    root = str(repo or "").strip()
    if not root or not os.path.isdir(root):
        return False
    names = ("GameServer.GameServerApp.exe", "GameServer.GameServerApp")
    for config in ("Debug", "Release"):
        cfg_dir = os.path.join(root, "game-server", "bin", config)
        for name in names:
            if os.path.isfile(os.path.join(cfg_dir, name)):
                return True
        if os.path.isfile(os.path.join(cfg_dir, "GameServer.GameServerApp.dll")):
            return True
    return False


def _resolve_game_server_repo() -> str:
    env = str(os.getenv("GAME_SERVER_REPO") or "").strip()
    if env and os.path.isdir(env):
        return env
    candidates: List[str] = [os.path.join(os.path.expanduser("~"), "game-server")]
    if os.name == "nt":
        candidates.extend([r"E:\maclient\game-server", r"D:\maclient\game-server"])
    else:
        candidates.append(os.path.join(os.path.expanduser("~"), "GameClient", "game-server"))
    seen: set = set()
    ordered: List[str] = []
    for path in candidates:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        ordered.append(path)
    for path in ordered:
        if _gameserver_repo_has_executable(path):
            return path
    for path in ordered:
        if os.path.isdir(path):
            return path
    return env or ordered[0]


CLUSTER_JSON_PATH = os.path.join(_resolve_game_server_repo(), "config", "cluster.json")


def _load_cluster_json() -> List[Dict[str, Any]]:
    """从 game-server 的 cluster.json 读取集群拓扑定义。"""
    path = CLUSTER_JSON_PATH
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        servers = data.get("Servers") if isinstance(data, dict) else []
        return servers if isinstance(servers, list) else []
    except Exception:
        return []


def _cluster_node_category(server_type: str) -> str:
    """将 game-server 节点类型映射为 agent 管理中心的分类。"""
    t = str(server_type or "").strip().lower()
    app_types = {"gateway", "auth", "game", "cross", "ops"}
    transport_types = {"tcp", "kcp", "httptransport"}
    daemon_types = {"daemon"}
    gm_types = {"gm"}
    if t in app_types:
        return "application"
    if t in transport_types:
        return "transport"
    if t in daemon_types:
        return "infrastructure"
    if t in gm_types:
        return "management"
    return "other"


def _cluster_node_capabilities(server: Dict[str, Any]) -> List[str]:
    """根据节点类型推断支持的操作。"""
    t = str(server.get("Type") or "").strip().lower()
    cat = _cluster_node_category(t)
    base = ["health_check", "status"]
    if cat == "application" or cat == "transport":
        base += ["start", "stop", "restart", "smoke_test"]
    if cat == "infrastructure":
        base += ["start", "stop", "restart"]
    if t == "ops":
        base += ["stress_test"]
    supported = server.get("SupportedActions")
    if isinstance(supported, list) and supported:
        return [str(x) for x in supported if str(x).strip()]
    return base


def _sync_cluster_to_nodes(servers: List[Dict[str, Any]], project_id: str = "GomeKu") -> None:
    """
    从 cluster.json 同步拓扑到 nodes 配置（OpsPlatformGateway 需要用 ops_base_url 连 game-server）。
    每个 cluster.json 里的 Ops 类型节点会生成一个 node 条目，ops_base_url 指向其 Ops 端口。
    如果 cluster.json 里有 Ops 节点，用它的 host:port 作为所有 node 的 ops_base_url。
    """
    if not servers:
        return
    # 找到 Ops 节点的地址作为 ops_base_url
    ops_host = "127.0.0.1"
    ops_port = 5504
    for srv in servers:
        srv_type = str(srv.get("Type") or "").strip().lower()
        if srv_type == "ops":
            ops_host = str(srv.get("ProbeHost") or srv.get("Host") or "127.0.0.1").strip()
            ops_port = int(srv.get("Port") or 5504)
            break
    ops_base_url = f"http://{ops_host}:{ops_port}"

    # 生成新的 nodes 列表
    new_nodes: List[Dict[str, Any]] = []
    for srv in servers:
        srv_id = str(srv.get("ServerId") or "").strip()
        if not srv_id:
            continue
        srv_type = str(srv.get("Type") or "").strip()
        role = str(srv.get("Role") or srv_type.lower()).strip()
        host = str(srv.get("ProbeHost") or srv.get("Host") or "127.0.0.1").strip()
        port = int(srv.get("Port") or 0)
        new_nodes.append(_normalize_node({
            "id": srv_id,
            "name": str(srv.get("DisplayName") or srv_id),
            "base_url": f"http://{host}:{port}" if port else ops_base_url,
            "ops_base_url": ops_base_url,
            "ops_read_key": "ops-read-key-2026",
            "ops_write_key": "ops-write-key-2026",
            "ops_actor": "local-ops",
            "ops_role": "SuperAdmin",
            "server_id": srv_id,
            "project_id": project_id,
            "owner": "ops-admin",
            "role": role,
            "description": str(srv.get("Description") or ""),
            "enabled": True,
            "env": "prod",
            "channel": "1001",
        }))
    if new_nodes:
        _save_nodes(new_nodes)


def _sync_cluster_to_agents(project_id: str = "GomeKu") -> Dict[str, Any]:
    """
    从 game-server cluster.json 同步拓扑到 agent registry v2。
    以 cluster.json 为唯一 Source of Truth：
    - cluster.json 里有但 registry 没有的 → 自动创建
    - cluster.json 里有的 → 更新 host/port/capabilities 等字段
    - cluster.json 里没有的老节点 → 标记 stale=True
    返回同步统计。
    """
    servers = _load_cluster_json()
    if not servers:
        return {"synced": 0, "added": 0, "updated": 0, "stale": 0, "error": "no cluster.json data"}

    pid = str(project_id or "GomeKu").strip()
    if _project_uses_runtime_topology(pid):
        services: List[Dict[str, Any]] = []
        active_node_ids: set = set()
        host = "127.0.0.1"
        ops_port = 5504
        now = _now_iso()
        for srv in servers:
            srv_id = str(srv.get("ServerId") or "").strip()
            if not srv_id:
                continue
            active_node_ids.add(srv_id)
            probe_host = str(srv.get("ProbeHost") or srv.get("Host") or host).strip()
            host = probe_host or host
            port = int(srv.get("Port") or 0)
            role = str(srv.get("Role") or srv.get("Type") or "").strip().lower()
            if srv_id == "ops-cn-1":
                ops_port = port or ops_port
            services.append(
                {
                    "service_id": srv_id,
                    "node_id": srv_id,
                    "agent_id": CANONICAL_LOCAL_AGENT_ID,
                    "device_id": CANONICAL_LOCAL_DEVICE_ID,
                    "project_id": pid,
                    "display_name": str(srv.get("DisplayName") or srv_id),
                    "service_type": role,
                    "service_port": port,
                    "remote_game_server_port": port,
                    "status": "UNKNOWN",
                    "run_state": "UNKNOWN",
                    "probe_status": "",
                    "probe_rtt_ms": 0.0,
                    "metrics": {},
                    "updated_at": now,
                    "registration_origin": "cluster.sync",
                }
            )
        try:
            ctx = _resolve_topology_context(pid, "production", "")
            topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
            topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
            if topo_meta.get("runtime_topology") or topo_meta.get("cluster_source"):
                for node in topo.get("nodes") if isinstance(topo.get("nodes"), list) else []:
                    if not isinstance(node, dict):
                        continue
                    nid = str(node.get("server_id") or node.get("id") or "").strip()
                    role = str(node.get("role") or "").strip().lower()
                    if nid and role in ("database", "cache", "mongo", "redis", "search", "mq"):
                        active_node_ids.add(nid)
                        if not any(str(s.get("node_id") or "") == nid for s in services):
                            services.append(_service_dict_from_topology_node(pid, node, now))
        except Exception:
            pass
        _ensure_canonical_local_agent(pid, services, host=host, ops_port=ops_port)
        reg = _load_agent_registry_v2()
        stale_count = 0
        for aid, item in reg.items():
            if not isinstance(item, dict) or aid == CANONICAL_LOCAL_AGENT_ID:
                continue
            if str(item.get("project_id") or "") not in ("", pid):
                continue
            nid = str(item.get("node_id") or "").strip()
            if (nid and nid in active_node_ids) or str(aid).endswith("-cn-1"):
                item["stale"] = True
                item["stale_reason"] = "consolidated_to_canonical"
                item["superseded_by"] = CANONICAL_LOCAL_AGENT_ID
                item["updated_at"] = now
                stale_count += 1
        _save_agent_registry_v2(reg)
        _sync_cluster_to_nodes(servers, pid)
        topo_stat = _sync_cluster_to_topology(pid, servers)
        return {
            "synced": len(servers),
            "added": 0,
            "updated": len(services),
            "stale": stale_count,
            "topology": topo_stat,
            "canonical": True,
        }

    reg = _load_agent_registry_v2()
    now = _now_iso()

    # 建立 node_id → agent_id 的现有映射
    existing_by_node: Dict[str, str] = {}
    for aid, entry in reg.items():
        if isinstance(entry, dict):
            nid = str(entry.get("node_id") or "").strip()
            if nid:
                existing_by_node[nid] = aid

    # cluster.json 中的有效 node_id 集合
    active_node_ids: set = set()
    added = 0
    updated = 0

    for srv in servers:
        srv_id = str(srv.get("ServerId") or "").strip()
        if not srv_id:
            continue
        active_node_ids.add(srv_id)

        host = str(srv.get("Host") or "127.0.0.1").strip()
        # ProbeHost: 探活地址，分布式部署时填实际可达 IP；不填则用 Host
        # 0.0.0.0 绑定是合法的（监听所有网卡），但探活需要具体 IP
        probe_host = str(srv.get("ProbeHost") or host).strip()
        port = int(srv.get("Port") or 0)
        srv_type = str(srv.get("Type") or "").strip()
        display_name = str(srv.get("DisplayName") or srv_id).strip()
        desc = str(srv.get("Description") or "").strip()
        category = str(srv.get("Category") or _cluster_node_category(srv_type)).strip()
        capabilities = _cluster_node_capabilities(srv)
        role = str(srv.get("Role") or srv_type.lower()).strip()
        state_config = str(srv.get("State") or "").strip().upper()

        agent_id = f"agent-{srv_id}"
        hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None

        if hit:
            # 更新已有 agent 的关键字段（以 cluster.json 为准）
            changed = False
            for k, v in [("host_name", host), ("probe_host", probe_host),
                         ("port", port),
                         ("remote_game_server_port", port),
                         ("display_name", display_name),
                         ("desc", desc),
                         ("node_id", srv_id),
                         ("project_id", project_id),
                         ("category", category),
                         ("role", role),
                         ("server_type", srv_type),
                         ("capabilities", capabilities)]:
                if hit.get(k) != v:
                    hit[k] = v
                    changed = True
            hit["registration_origin"] = "cluster.sync"
            hit.pop("stale_reason", None)
            hit.pop("superseded_by", None)
            # 同步配置状态
            if state_config:
                hit["config_state"] = state_config
            # KCP 用 UDP 探活
            if srv_type.upper() == "KCP":
                hit["probe_proto"] = "udp"
            if changed:
                hit["updated_at"] = now
                updated += 1
        else:
            # 新建 agent
            reg[agent_id] = _normalize_agent_descriptor_v2({
                "agent_id": agent_id,
                "device_id": "local-game-server",
                "host_name": host,
                "probe_host": probe_host,
                "node_id": srv_id,
                "project_id": project_id,
                "status": "UNKNOWN",
                "version": "game-server-cluster-v1",
                "last_seen": now,
                "display_name": display_name,
                "port": port,
                "remote_game_server_port": port,
                "desc": desc,
                "run_state": "UNKNOWN",
                "probe_status": "",
                "probe_at": "",
                "probe_rtt_ms": 0.0,
                "capabilities": capabilities,
                "metrics": {},
                "network": {"endpoints": [f"{host}:{port}"] if port else []},
                "transport": {"mode": "remote", "local_bus": {"enabled": True, "endpoint": f"pipe://local-game-server/{agent_id}", "auth_mode": "token"}},
                "config_state": state_config,
                "category": category,
                "role": role,
                "server_type": srv_type,
                "probe_proto": "udp" if srv_type.upper() == "KCP" else "tcp",
                "registration_origin": "cluster.sync",
                "updated_at": now,
            })
            added += 1

    # runtime 拓扑中的基础设施节点（Mongo/Redis 等）不在 cluster.json，但仍应视为有效 Agent
    try:
        ctx = _resolve_topology_context(project_id, "production", "")
        topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
        topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        if topo_meta.get("runtime_topology") or topo_meta.get("cluster_source"):
            for node in topo.get("nodes") if isinstance(topo.get("nodes"), list) else []:
                if not isinstance(node, dict):
                    continue
                nid = str(node.get("server_id") or node.get("id") or "").strip()
                role = str(node.get("role") or "").strip().lower()
                if nid and role in ("database", "cache", "mongo", "redis", "search", "mq"):
                    active_node_ids.add(nid)
    except Exception:
        pass

    # 标记不在 cluster.json 中的老节点为 stale
    # 同一 project_id 下，cluster.json 里的 node_id 是唯一有效集合
    # 老节点（如 gateway_http 等）不在 cluster.json 中 → stale
    stale_count = 0
    for aid, entry in reg.items():
        if not isinstance(entry, dict):
            continue
        entry_project = str(entry.get("project_id") or "").strip()
        # 只处理同一 project 的节点
        if entry_project and entry_project != project_id:
            continue
        nid = str(entry.get("node_id") or "").strip()
        if not nid:
            # 没有 node_id 的老条目也标记 stale
            entry["stale"] = True
            entry["updated_at"] = now
            stale_count += 1
            continue
        if nid not in active_node_ids:
            entry["stale"] = True
            entry["updated_at"] = now
            stale_count += 1
        else:
            entry.pop("stale", None)

    # 合并 Agent 心跳上报的 metrics 到 cluster.json 同步的 agent
    # Agent 注册的 agent_id 可能跟 cluster.json 同步的 agent_id 不同，但 node_id 相同
    for aid, entry in reg.items():
        if not isinstance(entry, dict) or entry.get("stale"):
            continue
        entry_nid = str(entry.get("node_id") or "").strip()
        if not entry_nid or entry_nid in active_node_ids:
            continue
        # 这个 agent 的 node_id 不在 cluster.json active set — 可能是 Agent 自己注册的
        cluster_aid = f"agent-{entry_nid}"
        cluster_entry = reg.get(cluster_aid) if isinstance(reg.get(cluster_aid), dict) else None
        if cluster_entry and not cluster_entry.get("stale"):
            # 合并 metrics、last_seen、run_state
            for mk in ["cpu_percent", "mem_percent", "qps", "rtt_ms", "updated_at"]:
                if entry.get("metrics", {}).get(mk) is not None:
                    cluster_entry.setdefault("metrics", {})[mk] = entry["metrics"][mk]
            if entry.get("last_seen"):
                cluster_entry["last_seen"] = entry["last_seen"]
            if entry.get("run_state") and entry.get("run_state") != "UNKNOWN":
                cluster_entry["run_state"] = entry["run_state"]
            if entry.get("status") and entry.get("status") != "UNKNOWN":
                cluster_entry["status"] = entry["status"]
            # 标记 Agent 自身条目为 stale（数据已合并）
            entry["stale"] = True
            entry["updated_at"] = now
            stale_count += 1

    _save_agent_registry_v2(reg)

    # 同步 nodes 配置（OpsPlatformGateway 用 ops_base_url 连 game-server）
    _sync_cluster_to_nodes(servers, project_id)
    topo_stat = _sync_cluster_to_topology(project_id, servers)
    canonical_stat = _consolidate_runtime_agents_to_canonical(project_id)

    return {"synced": len(servers), "added": added, "updated": updated, "stale": stale_count, "topology": topo_stat, "canonical": canonical_stat}


_CLUSTER_TOPOLOGY_LAYOUT = {
    "gateway": (72, 48),
    "auth": (72, 248),
    "ops": (320, 248),
    "game": (560, 128),
    "cache": (820, 48),
    "redis": (820, 48),
    "database": (820, 248),
    "mongo": (820, 248),
    "tcp": (820, 328),
    "transport": (820, 328),
}


def _cluster_topology_role_kind(srv: Dict[str, Any]) -> Tuple[str, str]:
    srv_type = str(srv.get("Type") or "").strip().lower()
    role = str(srv.get("Role") or srv_type or "business").strip().lower()
    if srv_type == "gateway":
        return "gateway", "gateway"
    if srv_type == "auth":
        return "auth", "auth"
    if srv_type == "ops":
        return "ops", "admin"
    if srv_type in ("tcp", "kcp", "httptransport"):
        return "transport", "terminal"
    if srv_type == "game":
        return "business", "game"
    kind = _infer_node_kind(role, "")
    return role, kind


_RUNTIME_TOPOLOGY_EDGE_SPECS = [
    ("gateway-cn-1", "auth-cn-1", "http:80"),
    ("gateway-cn-1", "ops-cn-1", "http:443"),
    ("auth-cn-1", "game-cn-1", "tcp:5512"),
    ("ops-cn-1", "game-cn-1", "tcp:5512"),
]
_RUNTIME_INFRA_EDGE_SPECS = [
    ("game-cn-1", "redis-cache-cn-1", "structured-auto"),
    ("game-cn-1", "mongo-db-cn-1", "structured-auto"),
]
_CORE_MINIMAL_DEMO_INFRA_EDGE_SPECS = [
    ("game-01", "redis-01", "structured-auto"),
    ("game-01", "db-01", "structured-auto"),
]


def _strip_default_node_ui_color(ui: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ui or {})
    if str(out.get("color") or "").strip().lower() == "#0f172a":
        out.pop("color", None)
    return out


def _repair_runtime_topology_edges(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    meta: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    meta = meta if isinstance(meta, dict) else {}
    if not meta.get("runtime_topology"):
        return edges
    valid_ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict) and str(n.get("id") or "")}
    if not {"gateway-cn-1", "ops-cn-1", "game-cn-1"}.issubset(valid_ids):
        return edges
    existing = {(str(e.get("from") or ""), str(e.get("to") or "")) for e in edges if isinstance(e, dict)}
    out = list(edges)
    for frm, to, note in _RUNTIME_TOPOLOGY_EDGE_SPECS:
        if frm not in valid_ids or to not in valid_ids or (frm, to) in existing:
            continue
        out.append({
            "id": f"edge-{frm}-{to}",
            "from": frm,
            "to": to,
            "from_port": "out-1",
            "to_port": "in-1",
            "type": "depends_on",
            "note": note,
        })
        existing.add((frm, to))
    for frm, to, note in _RUNTIME_INFRA_EDGE_SPECS:
        if frm not in valid_ids or to not in valid_ids or (frm, to) in existing:
            continue
        out.append({
            "id": f"edge-{frm}-{to}",
            "from": frm,
            "to": to,
            "from_port": "out-1",
            "to_port": "in-1",
            "type": "depends_on",
            "note": note,
        })
        existing.add((frm, to))
    return out


def _build_cluster_topology_content(servers: List[Dict[str, Any]], project_id: str = "") -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    nodes: List[Dict[str, Any]] = []
    valid_ids: set = set()
    for idx, srv in enumerate(servers):
        if not isinstance(srv, dict):
            continue
        sid = str(srv.get("ServerId") or "").strip()
        if not sid:
            continue
        valid_ids.add(sid)
        role, kind = _cluster_topology_role_kind(srv)
        srv_type = str(srv.get("Type") or "").strip().lower()
        layout_key = srv_type if srv_type in _CLUSTER_TOPOLOGY_LAYOUT else role
        x, y = _CLUSTER_TOPOLOGY_LAYOUT.get(layout_key, (72 + (idx % 3) * 260, 48 + (idx // 3) * 180))
        port = int(srv.get("Port") or 0)
        display = str(srv.get("DisplayName") or sid).strip()
        desc = str(srv.get("Description") or display).strip()
        ui_ports = _normalize_ports(kind, None)
        nodes.append({
            "id": sid,
            "name": display,
            "server_id": sid,
            "project_id": pid,
            "env": "production",
            "role": role,
            "kind": kind,
            "desc": desc,
            "bizStatus": "normal",
            "owner": "cluster.sync",
            "group": str(srv.get("Category") or "application"),
            "x": float(x),
            "y": float(y),
            "tags": [srv_type] if srv_type else [],
            "ui": {
                "x": float(x),
                "y": float(y),
                "w": 220,
                "h": 90,
                "locked": False,
                "ports": ui_ports,
                "remote": {"port": port} if port > 0 else {},
                "network": {"endpoints": [f"127.0.0.1:{port}"]} if port > 0 else {},
            },
        })

    edges: List[Dict[str, Any]] = []
    seen_edges: set = set()

    def _append_cluster_edge(from_id: str, to_id: str, note: str = "") -> None:
        frm = str(from_id or "").strip()
        to = str(to_id or "").strip()
        if not frm or not to or frm not in valid_ids or to not in valid_ids or frm == to:
            return
        edge_id = f"edge-{frm}-{to}"
        if edge_id in seen_edges:
            return
        seen_edges.add(edge_id)
        edges.append({
            "id": edge_id,
            "from": frm,
            "to": to,
            "from_port": "out-1",
            "to_port": "in-1",
            "type": "depends_on",
            "note": str(note or ""),
        })

    for srv in servers:
        if not isinstance(srv, dict):
            continue
        sid = str(srv.get("ServerId") or "").strip()
        if not sid:
            continue
        port = int(srv.get("Port") or 0)
        downstream = srv.get("DownstreamServerIds") if isinstance(srv.get("DownstreamServerIds"), list) else []
        for target in downstream:
            to_id = str(target or "").strip()
            _append_cluster_edge(sid, to_id, f"tcp:{port}" if port else "")
        upstream = srv.get("UpstreamServerIds") if isinstance(srv.get("UpstreamServerIds"), list) else []
        for source in upstream:
            from_id = str(source or "").strip()
            _append_cluster_edge(from_id, sid, f"tcp:{port}" if port else "")

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "layout_mode": "structured",
            "layout_locked": False,
            "cluster_source": True,
            "cluster_sync_at": _now_iso(),
            "layout_spacing": {"rank_gap": 268, "row_gap": 128},
            "updated_at": _now_iso(),
        },
    }


def _sync_cluster_to_topology(project_id: str, servers: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """将 cluster.json ServerId merge 到项目默认拓扑（保留用户添加的非 cluster 节点）。"""
    pid = str(project_id or "").strip()
    rows = servers if isinstance(servers, list) else _load_cluster_json()
    if not pid or not rows:
        return {"updated": False, "reason": "missing_project_or_cluster"}

    _migrate_topology_storage_if_needed()
    registry_rows = _load_topology_registry()
    target = None
    for item in registry_rows:
        if not isinstance(item, dict):
            continue
        row = _normalize_topology_registry_row(item)
        if row.get("project_id") == pid and row.get("is_default"):
            target = row
            break
    if target is None:
        target = _normalize_topology_registry_row({
            "topology_id": f"topology-{pid.replace('/', '-').replace(' ', '-').lower()}-production",
            "project_id": pid,
            "env_key": "production",
            "name": "生产主拓扑",
            "version_label": "cluster-v1",
            "owner": "cluster.sync",
            "description": "由 cluster.json 自动同步",
            "is_default": True,
            "status": "running",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })
        registry_rows.append(target)
        _save_topology_registry(registry_rows)

    tid = str(target.get("topology_id") or "").strip()
    if not tid:
        return {"updated": False, "reason": "missing_topology_id"}

    contents = _load_topology_contents()
    existing = contents.get(tid) if isinstance(contents.get(tid), dict) else {}
    existing_meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else {}
    existing_nodes = existing.get("nodes") if isinstance(existing.get("nodes"), list) else []
    existing_edges = existing.get("edges") if isinstance(existing.get("edges"), list) else []

    cluster_topo = _build_cluster_topology_content(rows, pid)
    cluster_nodes = cluster_topo.get("nodes") if isinstance(cluster_topo.get("nodes"), list) else []
    cluster_edges = cluster_topo.get("edges") if isinstance(cluster_topo.get("edges"), list) else []
    cluster_ids = {str(n.get("id") or "").strip() for n in cluster_nodes if isinstance(n, dict) and str(n.get("id") or "").strip()}
    minimal_default = (
        pid == "GomeKu"
        and bool(target.get("is_default"))
        and _normalize_env_key(str(target.get("env_key") or "")) == "production"
    )

    merged_nodes: List[Dict[str, Any]] = []
    merged_by_id: Dict[str, Dict[str, Any]] = {}

    if minimal_default:
        pos_by_id = {}
        for item in existing_nodes:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "").strip()
            if not nid:
                continue
            ui = item.get("ui") if isinstance(item.get("ui"), dict) else {}
            pos_by_id[nid] = (
                float(item.get("x") if item.get("x") is not None else ui.get("x") or 0),
                float(item.get("y") if item.get("y") is not None else ui.get("y") or 0),
            )
        for node in cluster_nodes:
            if not isinstance(node, dict):
                continue
            nid = str(node.get("id") or "").strip()
            if not nid:
                continue
            if nid in pos_by_id:
                x, y = pos_by_id[nid]
                node["x"] = x
                node["y"] = y
                ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
                ui["x"] = x
                ui["y"] = y
                node["ui"] = ui
            node_meta = node.get("meta") if isinstance(node.get("meta"), dict) else {}
            node_meta["cluster_source"] = True
            node["meta"] = node_meta
            merged_nodes.append(node)
            merged_by_id[nid] = node
        merged_edges = list(cluster_edges)
        merged_edge_ids = {str(e.get("id") or "") for e in merged_edges if isinstance(e, dict)}
    else:
        for item in existing_nodes:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "").strip()
            if not nid:
                continue
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
            is_cluster = bool(meta.get("cluster_source")) or nid in cluster_ids
            if is_cluster and nid in cluster_ids:
                continue
            if not is_cluster:
                merged_nodes.append(item)
                merged_by_id[nid] = item

        pos_by_id = {}
        for item in existing_nodes:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "").strip()
            if not nid:
                continue
            ui = item.get("ui") if isinstance(item.get("ui"), dict) else {}
            pos_by_id[nid] = (
                float(item.get("x") if item.get("x") is not None else ui.get("x") or 0),
                float(item.get("y") if item.get("y") is not None else ui.get("y") or 0),
            )

        for node in cluster_nodes:
            if not isinstance(node, dict):
                continue
            nid = str(node.get("id") or "").strip()
            if not nid:
                continue
            if nid in pos_by_id:
                x, y = pos_by_id[nid]
                node["x"] = x
                node["y"] = y
                ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
                ui["x"] = x
                ui["y"] = y
                node["ui"] = ui
            node_meta = node.get("meta") if isinstance(node.get("meta"), dict) else {}
            node_meta["cluster_source"] = True
            node["meta"] = node_meta
            merged_nodes.append(node)
            merged_by_id[nid] = node

        merged_edge_ids = set()
        merged_edges = []
        valid_ids = set(merged_by_id.keys())

        for edge in existing_edges:
            if not isinstance(edge, dict):
                continue
            frm = str(edge.get("from") or "").strip()
            to = str(edge.get("to") or "").strip()
            eid = str(edge.get("id") or f"edge-{frm}-{to}")
            if frm in cluster_ids and to in cluster_ids:
                continue
            if frm in valid_ids and to in valid_ids and eid not in merged_edge_ids:
                merged_edges.append(edge)
                merged_edge_ids.add(eid)

        for edge in cluster_edges:
            if not isinstance(edge, dict):
                continue
            eid = str(edge.get("id") or "")
            if eid and eid not in merged_edge_ids:
                merged_edges.append(edge)
                merged_edge_ids.add(eid)

    meta = cluster_topo.get("meta") if isinstance(cluster_topo.get("meta"), dict) else {}
    if existing_meta.get("viewport"):
        meta["viewport"] = existing_meta.get("viewport")
    if existing_meta.get("layout_spacing"):
        meta["layout_spacing"] = existing_meta.get("layout_spacing")
    if existing_meta.get("layout_spacing_customized"):
        meta["layout_spacing_customized"] = existing_meta.get("layout_spacing_customized")
    meta["cluster_sync_at"] = _now_iso()
    meta["updated_at"] = _now_iso()
    meta["runtime_topology"] = True
    meta["cluster_source"] = True
    if existing_meta.get("description"):
        meta["description"] = str(existing_meta.get("description") or "")

    merged_edges = _repair_runtime_topology_edges(merged_nodes, merged_edges, meta)
    topo = {"nodes": merged_nodes, "edges": merged_edges, "meta": meta}
    if pid == "GomeKu":
        env_for_topo = _normalize_env_key(str(target.get("env_key") or "production"))
        topo = _append_runtime_infra_stack(topo, pid, env_for_topo)
        merged_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else merged_nodes
        merged_edges = _repair_runtime_topology_edges(merged_nodes, topo.get("edges") or merged_edges, meta)
        meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else meta
        topo = {"nodes": merged_nodes, "edges": merged_edges, "meta": meta}
    contents[tid] = topo
    _save_topology_contents(contents)
    target["updated_at"] = _now_iso()
    _save_topology_registry(registry_rows)
    return {
        "updated": True,
        "topology_id": tid,
        "node_count": len(merged_nodes),
        "edge_count": len(merged_edges),
        "merged_user_nodes": len([n for n in existing_nodes if isinstance(n, dict) and str(n.get("id") or "") not in cluster_ids]),
    }


# ──────────────────────────────────────────────────────────────────────
#  实时探活：TCP connect 检测端口 + game-server /ops/cluster 联动
# ──────────────────────────────────────────────────────────────────────

def _tcp_probe(host: str, port: int, timeout: float = 1.5) -> Dict[str, Any]:
    """TCP connect 探活，返回 {ok, rtt_ms, error}。"""
    if not host or port <= 0:
        return {"ok": False, "rtt_ms": 0.0, "error": "invalid host/port"}
    start = datetime.utcnow()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        rtt = max(0.0, (datetime.utcnow() - start).total_seconds() * 1000.0)
        return {"ok": True, "rtt_ms": round(rtt, 1), "error": ""}
    except Exception as ex:
        return {"ok": False, "rtt_ms": 0.0, "error": str(ex)}


def _udp_probe(host: str, port: int, timeout: float = 1.5) -> Dict[str, Any]:
    """UDP 探活：发送空包检测端口是否可达（KCP 等协议）。"""
    if not host or port <= 0:
        return {"ok": False, "rtt_ms": 0.0, "error": "invalid host/port"}
    start = datetime.utcnow()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        # 发送一个空 UDP 包，如果端口没监听会收到 ICMP Port Unreachable
        # 如果端口在监听，包会被静默丢弃（KCP 等协议不响应空包）
        # 所以只要没收到 ICMP unreachable 就认为端口可达
        sock.sendto(b"", (host, port))
        # 尝试接收（KCP 可能回握手包）
        try:
            sock.recvfrom(64)
        except socket.timeout:
            # 超时 = 端口可达但无响应，算作在线
            pass
        rtt = max(0.0, (datetime.utcnow() - start).total_seconds() * 1000.0)
        sock.close()
        return {"ok": True, "rtt_ms": round(rtt, 1), "error": ""}
    except OSError as ex:
        # ICMP Port Unreachable → 端口未监听
        try:
            sock.close()
        except Exception:
            pass
        return {"ok": False, "rtt_ms": 0.0, "error": str(ex)}
    except Exception as ex:
        try:
            sock.close()
        except Exception:
            pass
        return {"ok": False, "rtt_ms": 0.0, "error": str(ex)}


def _redis_cli_candidates() -> List[str]:
    if os.name == "nt":
        return ["memurai-cli", "redis-cli"]
    return ["redis-cli"]


def _redis_ping_probe(host: str, port: int, timeout: float = 1.5) -> Dict[str, Any]:
    if not host or port <= 0:
        return {"ok": False, "rtt_ms": 0.0, "error": "invalid host/port"}
    tcp_fast = _tcp_probe(host, port, min(0.45, float(timeout)))
    if not tcp_fast.get("ok"):
        return tcp_fast
    start = datetime.utcnow()
    for cli in _redis_cli_candidates():
        try:
            proc = subprocess.run(
                [cli, "-h", host, "-p", str(port), "ping"],
                capture_output=True,
                text=True,
                timeout=max(0.6, min(1.0, float(timeout))),
            )
            ok = proc.returncode == 0 and "PONG" in (proc.stdout or "").upper()
            rtt = max(0.0, (datetime.utcnow() - start).total_seconds() * 1000.0)
            if ok:
                return {"ok": True, "rtt_ms": round(rtt, 1), "error": "", "method": cli}
        except FileNotFoundError:
            continue
        except Exception:
            break
    return {"ok": True, "rtt_ms": round(float(tcp_fast.get("rtt_ms") or 0.0), 1), "error": "", "method": "tcp-fallback"}


def _probe_by_protocol(host: str, port: int, proto: str = "tcp", timeout: float = 1.5) -> Dict[str, Any]:
    """根据协议类型选择探活方式。"""
    key = str(proto or "tcp").strip().lower()
    if key in ("udp",):
        return _udp_probe(host, port, timeout)
    if key in ("redis_ping", "redis"):
        return _redis_ping_probe(host, port, timeout)
    if key in ("mongo_ping", "mongo_tcp", "mongo"):
        return _tcp_probe(host, port, timeout)
    if key in ("kafka_tcp",):
        return _tcp_probe(host, port, timeout)
    if key in ("cluster_embedded",):
        return {"ok": False, "rtt_ms": 0.0, "error": "cluster_embedded probe deferred"}
    return _tcp_probe(host, port, timeout)


_EMBEDDED_CLUSTER_SERVER_TYPES = {"auth", "game"}
_GAMESERVER_PROCESS_SERVICE_IDS = frozenset(
    {"gateway-cn-1", "auth-cn-1", "game-cn-1", "ops-cn-1"}
)
_GAMESERVER_DEFAULT_PORTS: Dict[str, int] = {
    "gateway-cn-1": 15050,
    "ops-cn-1": 5504,
}
_GAMESERVER_TCP_PROBE_PORTS: Dict[str, int] = {
    "gateway-cn-1": 15050,
    "ops-cn-1": 5504,
}
_CLUSTER_RELAY_PROBE_PORTS: Dict[str, int] = {
    "auth-cn-1": 15501,
    "game-cn-1": 15502,
}
_CLUSTER_RELAY_TOKEN_DEFAULT = "ma-cluster-relay-dev"
_GAMESERVER_START_ORDER: Tuple[str, ...] = ("auth-cn-1", "game-cn-1", "ops-cn-1", "gateway-cn-1")


def _cluster_state_is_online(state: Any) -> bool:
    text = str(state or "").strip().upper()
    return text in ("RUNNING", "READY", "ONLINE", "ACTIVE", "0") or str(state or "").strip() == "0"


def _is_daemon_infra_service(service: Dict[str, Any]) -> bool:
    if not isinstance(service, dict):
        return False
    sid = str(service.get("service_id") or service.get("node_id") or "").strip().lower()
    stype = str(service.get("service_type") or service.get("role") or "").strip().lower()
    return sid in ("mongo-db-cn-1", "redis-cache-cn-1") or stype in ("database", "cache", "mongo", "redis")


def _default_probe_host() -> str:
    return str(os.getenv("OPS_DEFAULT_PROBE_HOST") or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK


def _is_local_runtime_agent(agent_id: str = "", device_id: str = "") -> bool:
    aid = str(agent_id or "").strip()
    did = str(device_id or "").strip()
    return aid == CANONICAL_LOCAL_AGENT_ID or did == CANONICAL_LOCAL_DEVICE_ID


def _resolve_bound_agent(
    agent_bindings: Optional[Dict[str, str]],
    node_id: str,
    reg: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    nid = str(node_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else {}
    agent_id = str(bindings.get(nid) or "").strip()
    if not agent_id:
        return None
    registry = reg if isinstance(reg, dict) else _load_agent_registry_v2()
    hit = registry.get(agent_id) if isinstance(registry.get(agent_id), dict) else None
    return dict(hit) if isinstance(hit, dict) else None


def _resolve_agent_probe_host(
    agent: Optional[Dict[str, Any]] = None,
    service: Optional[Dict[str, Any]] = None,
    topo_node: Optional[Dict[str, Any]] = None,
) -> str:
    """统一服务探活地址：probe_host 优先；本机 runtime / 守护进程固定 loopback。"""
    agent_obj = agent if isinstance(agent, dict) else {}
    service_obj = service if isinstance(service, dict) else {}
    node_obj = topo_node if isinstance(topo_node, dict) else {}
    ui = node_obj.get("ui") if isinstance(node_obj.get("ui"), dict) else {}
    remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
    network = ui.get("network") if isinstance(ui.get("network"), dict) else {}
    for candidate in (
        str(service_obj.get("probe_host") or "").strip(),
        str(agent_obj.get("probe_host") or "").strip(),
        str(remote.get("host") or remote.get("probe_host") or "").strip(),
        str(network.get("probe_host") or "").strip(),
    ):
        if candidate and candidate not in ("0.0.0.0", "*"):
            return candidate
    if _is_daemon_infra_service(service_obj) and _is_local_runtime_agent(
        str(agent_obj.get("agent_id") or ""),
        str(agent_obj.get("device_id") or ""),
    ):
        return DEFAULT_LOOPBACK
    if _is_local_runtime_agent(str(agent_obj.get("agent_id") or ""), str(agent_obj.get("device_id") or "")):
        return DEFAULT_LOOPBACK
    fallback = str(agent_obj.get("host_ip") or agent_obj.get("host_name") or "").strip()
    if fallback and fallback not in ("0.0.0.0", "*"):
        return fallback
    return _default_probe_host()


def _resolve_runtime_probe_host(
    agent: Optional[Dict[str, Any]] = None,
    service: Optional[Dict[str, Any]] = None,
    topo_node: Optional[Dict[str, Any]] = None,
) -> str:
    return _resolve_agent_probe_host(agent, service, topo_node)


def _is_embedded_topology_node(node: Dict[str, Any], contract: Optional[Dict[str, Any]] = None) -> bool:
    if not isinstance(node, dict):
        return False
    contract_obj = contract if isinstance(contract, dict) else _resolve_node_contract_for_topology_node(node)
    execution_model = str(contract_obj.get("execution_model") or "").strip().lower()
    probe_strategy = str(contract_obj.get("probe_strategy") or "").strip().lower()
    if execution_model == "embedded" or probe_strategy == "cluster_embedded":
        return True
    nid = str(node.get("id") or node.get("node_id") or "").strip().lower()
    if nid in ("auth-cn-1", "game-cn-1"):
        return True
    role = str(node.get("role") or contract_obj.get("role") or "").strip().lower()
    if role in ("auth", "business", "game") and (nid.startswith("auth-") or nid.startswith("game-")):
        return True
    return False


def _resolve_topology_probe_port(
    node: Dict[str, Any],
    contract: Dict[str, Any],
    service: Optional[Dict[str, Any]] = None,
    agent: Optional[Dict[str, Any]] = None,
) -> int:
    if _is_embedded_topology_node(node, contract):
        return 0
    return _resolve_topology_node_port(node, contract, service, agent)


def _resolve_runtime_probe_ports(contract: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    return {
        "gateway": _RUNTIME_GATEWAY_PROBE_PORT,
        "ops": _RUNTIME_OPS_PROBE_PORT,
    }


def _resolve_orchestration_probe_host(
    project_id: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    agent_bindings: Optional[Dict[str, str]] = None,
    reg: Optional[Dict[str, Any]] = None,
) -> str:
    nid = str(topo_node.get("id") or "").strip()
    agent = _resolve_bound_agent(agent_bindings, nid, reg)
    if agent:
        return _resolve_runtime_probe_host(agent, None, topo_node)
    if _project_uses_runtime_topology(project_id):
        return DEFAULT_LOOPBACK
    return _default_probe_host()


def _resolve_orchestration_scope(
    project_id: str,
    topology_id: str,
    agent_bindings: Optional[Dict[str, str]] = None,
    reg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bindings = agent_bindings if isinstance(agent_bindings, dict) else {}
    registry = reg if isinstance(reg, dict) else _load_agent_registry_v2()
    hosts: List[str] = []
    has_remote = False
    for _nid, aid in bindings.items():
        agent_id = str(aid or "").strip()
        if not agent_id:
            continue
        if not _is_local_runtime_agent(agent_id):
            has_remote = True
        agent = registry.get(agent_id) if isinstance(registry.get(agent_id), dict) else {}
        hosts.append(_resolve_runtime_probe_host(agent, None, None))
    default_host = DEFAULT_LOOPBACK
    if has_remote and hosts:
        default_host = hosts[0]
    elif hosts:
        default_host = hosts[0]
    return {
        "default_probe_host": default_host,
        "has_remote_agents": has_remote,
        "probe_hosts": hosts,
    }


def _is_embedded_cluster_agent(agent: Dict[str, Any]) -> bool:
    srv_type = str(agent.get("server_type") or "").strip().lower()
    if srv_type in _EMBEDDED_CLUSTER_SERVER_TYPES:
        return True
    nid = str(agent.get("node_id") or "").strip().lower()
    return nid.startswith("auth-") or nid.startswith("game-")


def _is_embedded_cluster_service(service: Dict[str, Any]) -> bool:
    if not isinstance(service, dict):
        return False
    sid = str(service.get("service_id") or service.get("node_id") or "").strip().lower()
    stype = str(service.get("service_type") or service.get("type") or "").strip().lower()
    role = str(service.get("role") or "").strip().lower()
    if sid in ("auth-cn-1", "game-cn-1"):
        return True
    if stype in _EMBEDDED_CLUSTER_SERVER_TYPES:
        return True
    if sid.startswith("auth-") or sid.startswith("game-"):
        return True
    return role in ("auth", "business") and ("auth" in sid or "game" in sid)


def _resolve_service_runtime_state(
    service: Dict[str, Any],
    host: str = "127.0.0.1",
    cluster_status: Optional[Dict[str, str]] = None,
    probe_timeout: float = 0.8,
    fast_probe: bool = False,
) -> Dict[str, Any]:
    """统一服务级运行态：embedded 模块走 cluster 状态，其余走 TCP + cluster 兜底。"""
    svc = dict(service) if isinstance(service, dict) else {}
    sid = str(svc.get("service_id") or svc.get("node_id") or "").strip()
    prior_run = str(svc.get("run_state") or svc.get("status") or "").strip().upper()
    port = int(svc.get("service_port") or svc.get("remote_game_server_port") or 0)
    timeout = max(0.08, min(float(probe_timeout or 0.8), 2.0)) if fast_probe else max(0.2, min(float(probe_timeout or 0.8), 2.0))

    if _service_starting_grace_active(svc):
        if port > 0 and _probe_tcp_open(host, port, timeout=0.12 if fast_probe else 0.25):
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
            svc["probe_method"] = "grace-fast-tcp"
            svc["probe_host"] = str(host or "127.0.0.1").strip()
            return svc
        svc["probe_status"] = "FAIL"
        svc["status"] = "STARTING"
        svc["run_state"] = "STARTING"
        svc["probe_method"] = "starting-grace"
        svc["probe_host"] = str(host or "127.0.0.1").strip()
        return svc
    sid_lower = sid.lower()
    cs_map = cluster_status if isinstance(cluster_status, dict) else {}
    cs = str(cs_map.get(sid) or "").strip().upper()
    embedded = _is_embedded_cluster_service(svc)
    probe_method = "tcp"
    open_ok = False

    if embedded:
        probe_method = "cluster-embedded"
        gw_ops_up = _embedded_process_gateway_up(host, timeout=timeout)
        if cs and _cluster_state_is_online(cs):
            open_ok = True
        elif cs and not _cluster_state_is_online(cs):
            if gw_ops_up:
                open_ok = True
                probe_method = "cluster-embedded-process-up"
            else:
                open_ok = False
                probe_method = "cluster-embedded-offline"
        elif gw_ops_up:
            open_ok = True
            probe_method = "cluster-process-up-fast" if fast_probe else "cluster-process-up"
        else:
            open_ok = False
            probe_method = "cluster-embedded-offline"
        if open_ok:
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
        else:
            svc["probe_status"] = "FAIL"
            if prior_run == "STARTING":
                svc["status"] = "STARTING"
                svc["run_state"] = "STARTING"
            else:
                svc["status"] = "STOPPED"
                svc["run_state"] = "STOPPED"
        svc["probe_method"] = probe_method
        svc["probe_host"] = str(host or "127.0.0.1").strip()
        if cs:
            svc["cluster_state"] = cs
        return svc
    elif sid_lower in _GAMESERVER_PROCESS_SERVICE_IDS:
        tcp_port = _gameserver_tcp_probe_port(sid_lower)
        if tcp_port > 0:
            open_ok = _gameserver_service_live(sid_lower, fast=fast_probe)
            probe_method = "gameserver-tcp-fast" if fast_probe else "gameserver-tcp"
        elif fast_probe:
            gw_live = _probe_tcp_open(host, 15050, timeout=timeout)
            ops_live = _probe_tcp_open(host, 5504, timeout=timeout)
            open_ok = bool(gw_live or ops_live)
            probe_method = "gameserver-process-fast"
        else:
            open_ok = _is_gameserver_process_alive(sid_lower)
            probe_method = "gameserver-process"
        if open_ok:
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
        else:
            svc["probe_status"] = "FAIL"
            if prior_run == "STARTING":
                svc["status"] = "STARTING"
                svc["run_state"] = "STARTING"
            else:
                svc["status"] = "STOPPED"
                svc["run_state"] = "STOPPED"
        svc["probe_method"] = probe_method
        svc["probe_host"] = str(host or "127.0.0.1").strip()
        return svc
    elif _is_daemon_infra_service(svc):
        probe_method = "redis_ping" if "redis" in sid or str(svc.get("service_type") or "").lower() == "cache" else "mongo_ping"
        if port > 0:
            probe = _probe_by_protocol(host, port, probe_method, timeout=timeout)
            open_ok = bool(probe.get("ok"))
        else:
            open_ok = False
    else:
        open_ok = _probe_tcp_open(host, port, timeout=timeout) if port > 0 else False
        if not open_ok and cs and _cluster_state_is_online(cs):
            open_ok = True
            probe_method = "cluster-fallback"

    if open_ok:
        svc["probe_status"] = "PASS"
        svc["status"] = "RUNNING"
        svc["run_state"] = "RUNNING"
    elif embedded and not cs:
        # GameServer 进程内模块：Gateway/Ops 均不可达时与 Gateway 行一致显示已停止
        gw_live = _probe_tcp_open(host, 15050, timeout=timeout)
        ops_live = _probe_tcp_open(host, 5504, timeout=timeout)
        if not gw_live and not ops_live:
            svc["probe_status"] = "FAIL"
            svc["status"] = "STOPPED"
            svc["run_state"] = "STOPPED"
            probe_method = "cluster-embedded-offline"
        elif gw_live or ops_live:
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
            probe_method = "cluster-process-up"
        else:
            svc["probe_status"] = "FAIL"
            svc["status"] = "STOPPED"
            svc["run_state"] = "STOPPED"
            probe_method = "cluster-embedded-deferred"
    else:
        svc["probe_status"] = "FAIL"
        if prior_run == "STARTING" or _service_starting_grace_active(svc):
            svc["status"] = "STARTING"
            svc["run_state"] = "STARTING"
        else:
            svc["status"] = "STOPPED"
            svc["run_state"] = "STOPPED"
    svc["probe_method"] = probe_method
    svc["probe_host"] = str(host or "127.0.0.1").strip()
    if cs:
        svc["cluster_state"] = cs
    return svc


_cluster_runtime_cache: Dict[str, Any] = {"ts": 0.0, "map": {}}
_CLUSTER_RUNTIME_CACHE_TTL_SEC = 5.0


def _fetch_cluster_runtime_status(agents: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    cluster_status: Dict[str, str] = {}
    if not _probe_tcp_open("127.0.0.1", 5504, timeout=0.25):
        return cluster_status
    try:
        gw = OpsPlatformGateway()
        ops_node = _resolve_node(node_id="ops-cn-1")
        if not ops_node:
            for a in agents or []:
                nid = str(a.get("node_id") or "").strip()
                node_candidate = _resolve_node(node_id=nid)
                if node_candidate and node_candidate.get("ops_base_url"):
                    ops_node = node_candidate
                    break
        if not ops_node:
            ops_node = _resolve_ops_dispatch_node("", "ops-cn-1")
        if not ops_node:
            return cluster_status
        cluster_resp = gw.cluster(ops_node, actor="probe", reason="cluster-status", ticket_id="OPS-PROBE")
        if cluster_resp and cluster_resp.get("success"):
            cluster_data = cluster_resp.get("data") or {}
            servers = cluster_data.get("Servers") or cluster_data.get("servers") or []
            for srv in servers:
                if not isinstance(srv, dict):
                    continue
                sid = str(srv.get("ServerId") or srv.get("serverId") or "").strip()
                st = srv.get("State") if srv.get("State") is not None else srv.get("state")
                if sid and st is not None:
                    cluster_status[sid] = str(st).strip().upper()
    except Exception:
        pass
    return cluster_status


def _invalidate_runtime_probe_state() -> None:
    """停止/刷新后立即使探活与 cluster 缓存失效，避免 UI 长时间显示旧 PASS。"""
    global _probe_cache, _probe_cache_ts, _cluster_runtime_cache
    with _probe_cache_lock:
        _probe_cache = {}
        _probe_cache_ts = 0.0
        _cluster_runtime_cache["ts"] = 0.0
        _cluster_runtime_cache["map"] = {}


def _seed_probe_cache_from_registry() -> None:
    """将 registry 中最新 probe/status 写入探活缓存，供 agents 列表立即读取。"""
    global _probe_cache, _probe_cache_ts
    reg = _load_agent_registry_v2()
    seeded: Dict[str, Dict[str, Any]] = {}
    for aid, item in (reg.items() if isinstance(reg, dict) else []):
        if not isinstance(item, dict) or item.get("stale"):
            continue
        agent_id = str(aid or "").strip()
        if not agent_id:
            continue
        probe = str(item.get("probe_status") or "").upper()
        effective = str(item.get("effective_status") or item.get("status") or "UNKNOWN").upper()
        seeded[agent_id] = {
            "ok": probe == "PASS",
            "effective_status": effective,
            "rtt_ms": float(item.get("probe_rtt_ms") or 0.0),
            "probe_at": str(item.get("updated_at") or _now_iso()),
            "metrics": item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
        }
    with _probe_cache_lock:
        _probe_cache = seeded
        _probe_cache_ts = _time_mod.time()


def _derive_agent_probe_from_services(services: List[Dict[str, Any]]) -> Tuple[str, str]:
    rows = [s for s in (services or []) if isinstance(s, dict)]
    if not rows:
        return "UNKNOWN", "FAIL"
    any_pass = any(str(s.get("probe_status") or "").upper() == "PASS" for s in rows)
    any_starting = any(str(s.get("run_state") or s.get("status") or "").upper() == "STARTING" for s in rows)
    if any_pass:
        return "ONLINE", "PASS"
    if any_starting:
        return "STARTING", "FAIL"
    return "OFFLINE", "FAIL"


def _fetch_cluster_runtime_status_cached(agents: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    now = _time_mod.time()
    with _probe_cache_lock:
        cached_ts = float(_cluster_runtime_cache.get("ts") or 0.0)
        cached_map = _cluster_runtime_cache.get("map") if isinstance(_cluster_runtime_cache.get("map"), dict) else {}
        if now - cached_ts < _CLUSTER_RUNTIME_CACHE_TTL_SEC and cached_map:
            return dict(cached_map)
    fresh = _fetch_cluster_runtime_status(agents)
    with _probe_cache_lock:
        _cluster_runtime_cache["ts"] = now
        _cluster_runtime_cache["map"] = dict(fresh)
    return fresh


def _service_starting_grace_active(service: Dict[str, Any], grace_sec: float = 120.0) -> bool:
    if not isinstance(service, dict):
        return False
    run = str(service.get("run_state") or service.get("status") or "").strip().upper()
    if run != "STARTING":
        return False
    ts = _parse_iso_ts(service.get("updated_at"))
    if ts <= 0:
        return True
    return (_time_mod.time() - ts) <= max(10.0, float(grace_sec))


def _merge_probe_with_cluster_status(
    probe_info: Dict[str, Any],
    agent: Dict[str, Any],
    cluster_status: Dict[str, str],
) -> None:
    """Auth/Game 等业务模块不绑独立端口，TCP 失败时用 /ops/cluster 状态判定。"""
    nid = str(agent.get("node_id") or "").strip()
    config_state = str(agent.get("config_state") or "").strip().upper()
    cat = str(agent.get("category") or "").strip().lower()
    cs = cluster_status.get(nid, "")
    if nid and cs:
        if _cluster_state_is_online(cs):
            probe_info["effective_status"] = "ONLINE"
        elif cs in ("MAINTENANCE", "1"):
            probe_info["effective_status"] = "MAINTENANCE"
        elif cs in ("STOPPED", "OFFLINE", "DOWN", "2") and not probe_info.get("ok"):
            if cat in ("application", "service") and _is_embedded_cluster_agent(agent):
                probe_info["effective_status"] = "ONLINE"
            else:
                probe_info["effective_status"] = "OFFLINE"
    if config_state == "MAINTENANCE":
        probe_info["effective_status"] = "MAINTENANCE"
    if (
        not probe_info.get("ok")
        and probe_info.get("effective_status") == "ONLINE"
        and _is_embedded_cluster_agent(agent)
        and (not cs or _cluster_state_is_online(cs) or config_state in ("ONLINE", "0"))
    ):
        probe_info["ok"] = True
        probe_info["error"] = ""
        probe_info["probe_method"] = "cluster-embedded"


def _probe_agents_batch(agents: List[Dict[str, Any]], timeout: float = 2.0) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    if not agents:
        return results
    lock = threading.Lock()

    def _probe_one(agent: Dict[str, Any]) -> None:
        aid = str(agent.get("agent_id") or "")
        host = str(agent.get("probe_host") or agent.get("host_name") or "").strip()
        if host in ("0.0.0.0", "*"):
            host = "127.0.0.1"
        port = int(agent.get("port") or agent.get("remote_game_server_port") or 0)
        proto = str(agent.get("probe_strategy") or agent.get("probe_proto") or "tcp").strip().lower()
        probe = _probe_by_protocol(host, port, proto=proto, timeout=timeout)
        probe["probe_at"] = _now_iso()
        probe["effective_status"] = "ONLINE" if probe.get("ok") else "OFFLINE"
        with lock:
            results[aid] = probe

    threads = []
    for agent in agents:
        t = threading.Thread(target=_probe_one, args=(agent,))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=max(3.0, timeout + 1.0))

    cluster_status = _fetch_cluster_runtime_status(agents)
    for agent in agents:
        aid = str(agent.get("agent_id") or "")
        probe_info = results.get(aid)
        if isinstance(probe_info, dict):
            _merge_probe_with_cluster_status(probe_info, agent, cluster_status)
    return results


def _probe_agents_realtime(agents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    批量实时探活：对每个 agent 执行 TCP connect 检测。
    返回 {agent_id: {ok, rtt_ms, error, effective_status}} 字典。
    同时尝试从 game-server /ops/cluster 拉取集群实际状态。
    """
    results: Dict[str, Dict[str, Any]] = {}
    if not agents:
        return results

    # 并行 TCP 探活
    lock = threading.Lock()
    def _probe_one(agent: Dict[str, Any]) -> None:
        aid = str(agent.get("agent_id") or "")
        # 探活地址优先用 probe_host（分布式部署时填可达 IP），fallback 用 host_name
        host = str(agent.get("probe_host") or agent.get("host_name") or "").strip()
        port = int(agent.get("port") or agent.get("remote_game_server_port") or 0)
        proto = str(agent.get("probe_strategy") or agent.get("probe_proto") or "tcp").strip().lower()
        probe = _probe_by_protocol(host, port, proto=proto)
        # 根据探活结果确定 effective_status
        if probe["ok"]:
            probe["effective_status"] = "ONLINE"
        else:
            probe["effective_status"] = "OFFLINE"
        with lock:
            results[aid] = probe

    threads = []
    for a in agents:
        t = threading.Thread(target=_probe_one, args=(a,))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=3.0)

    # 合并 cluster 状态：如果 cluster.json 里配了 Maintenance 但端口通，标记为 MAINTENANCE
    cluster_status = _fetch_cluster_runtime_status(agents)
    for aid, probe_info in results.items():
        for a in agents:
            if str(a.get("agent_id") or "") == aid:
                _merge_probe_with_cluster_status(probe_info, a, cluster_status)
                break

    return results


# ──────────────────────────────────────────────────────────────────────
#  后台探活引擎 + SSE 推送：定时探活缓存结果，状态变化时推送前端
# ──────────────────────────────────────────────────────────────────────


def _probe_background_tick() -> None:
    """后台探活一轮：线程池并发探测所有 agent，结果写入缓存，变化时通知 SSE。"""
    global _probe_cache, _probe_cache_agents, _probe_cache_ts, _probe_cache_sync_ts, _probe_change_seq

    # --- 1. 定期同步 cluster.json → agent registry ---
    now = _time_mod.time()
    if now - _probe_cache_sync_ts >= PROBE_SYNC_INTERVAL_SEC:
        try:
            _sync_cluster_to_agents()
            _probe_cache_sync_ts = now
        except Exception:
            pass

    # --- 2. 加载 agent 列表 ---
    reg = _load_agent_registry_v2()
    agents = [_normalize_agent_descriptor_v2(x) for x in reg.values() if isinstance(x, dict)]
    agents = [a for a in agents if not a.get("stale")]

    # --- 3. 线程池并发探活 ---
    probe_results: Dict[str, Dict[str, Any]] = {}
    futures = {}
    for a in agents:
        aid = str(a.get("agent_id") or "")
        host = str(a.get("probe_host") or a.get("host_name") or "").strip()
        port = int(a.get("port") or a.get("remote_game_server_port") or 0)
        proto = str(a.get("probe_strategy") or a.get("probe_proto") or "tcp").strip().lower()
        future = _probe_pool.submit(_probe_by_protocol, host, port, proto)
        futures[future] = aid

    # 尝试从 game-server /ops/health + /ops/cluster 拉取集群运行状态和指标
    # 所有 game-server 节点共享同一个 Ops API，只需调一次
    cluster_status: Dict[str, str] = {}
    cluster_metrics: Dict[str, Dict[str, Any]] = {}  # node_id -> metrics
    try:
        gw = OpsPlatformGateway()
        # 找到任一有 ops_base_url 的 node
        ops_node = None
        for a in agents:
            nid = str(a.get("node_id") or "").strip()
            node_candidate = _resolve_node(node_id=nid)
            if node_candidate and node_candidate.get("ops_base_url"):
                ops_node = node_candidate
                break
        if not ops_node:
            ops_node = _resolve_node(node_id="ops-cn-1")
        if ops_node:
            # /ops/health
            try:
                health_resp = gw.health(ops_node, actor="probe", reason="bg-metrics", ticket_id="OPS-BG")
                if health_resp and health_resp.get("success"):
                    h_data = health_resp.get("data") or {}
                    tel = h_data.get("Telemetry") or {}
                    if isinstance(tel, dict):
                        # health 返回的是 ops-cn-1 的指标
                        ops_nid = str(h_data.get("ServerId") or "ops-cn-1").strip()
                        cluster_metrics[ops_nid] = {
                            "cpu_percent": None,
                            "mem_percent": None,
                            "qps": tel.get("Qps"),
                            "rtt_ms": tel.get("P99Ms"),
                            "total_requests": tel.get("TotalRequests"),
                            "total_responses": tel.get("TotalResponses"),
                            "queue_depth": tel.get("QueueDepth"),
                            "reconnect_success_rate": tel.get("ReconnectSuccessRate"),
                            "source": "runtime.sample",
                        }
            except Exception:
                pass
            # /ops/cluster — 拉取所有节点状态
            try:
                cluster_resp = gw.cluster(ops_node, actor="probe", reason="bg-health", ticket_id="OPS-BG")
                if cluster_resp and cluster_resp.get("success"):
                    cluster_data = cluster_resp.get("data") or {}
                    c_servers = cluster_data.get("Servers") or cluster_data.get("servers") or []
                    for srv in c_servers:
                        sid = str(srv.get("ServerId") or srv.get("serverId") or "").strip()
                        st = str(srv.get("State") or srv.get("state") or "").strip().upper()
                        if sid and st:
                            cluster_status[sid] = st
                        # 从 cluster 响应提取各节点指标
                        srv_metrics = srv.get("Metrics") or srv.get("metrics") or {}
                        if isinstance(srv_metrics, dict) and any(v is not None for v in srv_metrics.values()):
                            cluster_metrics[sid] = {
                                "cpu_percent": srv_metrics.get("CpuPercent"),
                                "mem_percent": srv_metrics.get("MemPercent"),
                                "qps": srv_metrics.get("Qps"),
                                "rtt_ms": srv_metrics.get("P99Ms"),
                                "total_requests": srv_metrics.get("TotalRequests"),
                                "total_responses": srv_metrics.get("TotalResponses"),
                                "queue_depth": srv_metrics.get("QueueDepth"),
                                "reconnect_success_rate": srv_metrics.get("ReconnectSuccessRate"),
                                "source": "runtime.sample",
                            }
            except Exception:
                pass
    except Exception:
        pass

    # 采集本机指标（Redis/MongoDB/Daemon 等非 game-server 节点）
    try:
        import psutil
        disk_pct = None
        try:
            disk_pct = round(float(psutil.disk_usage("/").percent), 1)
        except Exception:
            try:
                disk_pct = round(float(psutil.disk_usage("C:\\").percent), 1)
            except Exception:
                disk_pct = None
        proc_metrics = {
            "cpu_percent": round(psutil.cpu_percent(interval=0.1), 1),
            "mem_percent": round(psutil.virtual_memory().percent, 1),
            "disk_percent": disk_pct,
            "source": "runtime.sample",
            "updated_at": _now_iso(),
        }
    except ImportError:
        proc_metrics = _fallback_local_control_metrics()
    except Exception:
        proc_metrics = _fallback_local_control_metrics()
    if not any(proc_metrics.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent")):
        proc_metrics = _fallback_local_control_metrics()

    # 收集探活结果
    for future in as_completed(futures, timeout=PROBE_INTERVAL_SEC):
        aid = futures[future]
        probe = future.result()
        probe["probe_at"] = _now_iso()
        if probe["ok"]:
            probe["effective_status"] = "ONLINE"
        else:
            probe["effective_status"] = "OFFLINE"
        probe["metrics"] = {}
        probe_results[aid] = probe

    # 合并 cluster 状态 + 指标
    for aid, probe_info in probe_results.items():
        for a in agents:
            if str(a.get("agent_id") or "") == aid:
                _merge_probe_with_cluster_status(probe_info, a, cluster_status)
                nid = str(a.get("node_id") or "").strip()
                config_state = str(a.get("config_state") or "").strip().upper()
                if config_state == "MAINTENANCE":
                    probe_info["effective_status"] = "MAINTENANCE"
                # 指标：优先 game-server 上报的，fallback 本机
                if nid and nid in cluster_metrics:
                    probe_info["metrics"] = cluster_metrics[nid]
                    probe_info["metrics"]["source"] = "real"
                else:
                    # 非集群节点或集群没上报指标的，用本机指标
                    if probe_info.get("effective_status") == "ONLINE" and proc_metrics:
                        probe_info["metrics"] = dict(proc_metrics)
                        probe_info["metrics"]["source"] = "local"
                break

    # --- 4. 检测变化，更新缓存 ---
    changed = False
    with _probe_cache_lock:
        for aid, new_pr in probe_results.items():
            old_pr = _probe_cache.get(aid)
            # 状态变化 或 指标变化 都算 changed
            if old_pr is None:
                changed = True
            elif old_pr.get("effective_status") != new_pr.get("effective_status"):
                changed = True
            elif old_pr.get("metrics") != new_pr.get("metrics"):
                changed = True
        _probe_cache = probe_results
        _probe_cache_agents = agents
        _probe_cache_ts = _time_mod.time()
        if changed:
            _probe_change_seq += 1

    # --- 4b. 更新 canonical agent 的服务级探活与指标采样 ---
    try:
        _reconcile_all_gameserver_daemon_states()
        tick_now = _now_iso()
        reg = _load_agent_registry_v2()
        canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else {}
        if canonical and not canonical.get("stale"):
            host = str(canonical.get("probe_host") or canonical.get("host_name") or "127.0.0.1").strip()
            services = canonical.get("services") if isinstance(canonical.get("services"), list) else []
            svc_changed = False
            refreshed_services: List[Dict[str, Any]] = []
            for svc in services:
                if not isinstance(svc, dict):
                    continue
                resolved = _resolve_service_runtime_state(svc, host=host, cluster_status=cluster_status)
                nid = str(resolved.get("node_id") or resolved.get("service_id") or "").strip()
                if nid and nid in cluster_metrics:
                    resolved["metrics"] = dict(cluster_metrics[nid])
                    resolved["metrics"]["source"] = "runtime.sample"
                elif resolved.get("probe_status") == "PASS" and proc_metrics:
                    resolved["metrics"] = dict(proc_metrics)
                    resolved["metrics"]["source"] = "runtime.sample"
                resolved["updated_at"] = tick_now
                refreshed_services.append(resolved)
                svc_changed = True
            services = refreshed_services
            merged_control: Dict[str, Any] = _sample_local_control_metrics()
            if proc_metrics:
                for key, val in proc_metrics.items():
                    if val is not None:
                        merged_control[key] = val
            for nid, cm in cluster_metrics.items():
                if isinstance(cm, dict):
                    for key in ("cpu_percent", "mem_percent", "qps", "rtt_ms", "queue_depth"):
                        if cm.get(key) is not None:
                            merged_control[key] = cm.get(key)
            if merged_control:
                merged_control["updated_at"] = tick_now
                merged_control["source"] = "runtime.sample"
                canonical["metrics"] = {"control": merged_control, **merged_control}
                canonical["metrics_live"] = True
            canonical["services"] = services
            canonical["last_seen"] = tick_now
            canonical["updated_at"] = tick_now
            pr_main = probe_results.get(CANONICAL_LOCAL_AGENT_ID) or {}
            if pr_main:
                canonical["probe_status"] = "PASS" if pr_main.get("ok") else "FAIL"
                canonical["probe_rtt_ms"] = float(pr_main.get("rtt_ms") or 0.0)
            _append_realtime_agent_sample(canonical)
            reg[CANONICAL_LOCAL_AGENT_ID] = canonical
            _save_agent_registry_v2(reg)
            if svc_changed:
                with _probe_cache_lock:
                    _probe_change_seq += 1
    except Exception:
        pass

    # --- 5. 每轮都推送（参数实时滚动） ---
    payload = _build_sse_payload(agents, probe_results)
    _sse_broadcast(payload)


def _build_sse_payload(agents: List[Dict[str, Any]], probe_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """构造推送给前端的完整 payload。"""
    now_iso = _now_iso()
    jobs = _load_agent_jobs()
    queue: Dict[str, int] = {"PENDING": 0, "RUNNING": 0, "SUCCESS": 0, "FAILED": 0, "CANCELED": 0, "TIMEOUT": 0}
    for item in jobs:
        if not isinstance(item, dict):
            continue
        st = str(item.get("status") or "").upper()
        if st in queue:
            queue[st] += 1
    online = 0
    out_agents: List[Dict[str, Any]] = []
    bindings = _load_node_agent_bindings()
    bound_agent_ids = set(str(v or "") for v in bindings.values() if str(v or "").strip())
    for a in agents:
        obj = dict(a)
        aid = str(obj.get("agent_id") or "")
        pr = probe_results.get(aid) or {}
        obj["effective_status"] = pr.get("effective_status", "UNKNOWN")
        obj["probe_status"] = "PASS" if pr.get("ok") else "FAIL"
        obj["probe_rtt_ms"] = pr.get("rtt_ms", 0.0)
        obj["probe_source"] = "bg-engine"
        obj["probe_at"] = str(pr.get("probe_at") or now_iso)
        obj["is_bound"] = aid in bound_agent_ids
        # Heartbeat metrics are the source of truth. Probe metrics may be stale or
        # synthetic, so only fill fields that the agent did not report.
        pr_metrics = pr.get("metrics") or {}
        base_m = obj.get("metrics") if isinstance(obj.get("metrics"), dict) else {}
        merged_metrics = dict(base_m)
        if pr_metrics:
            for key in (
                "cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms",
                "service_cpu_percent", "service_memory_mb", "total_requests",
                "total_responses", "queue_depth", "reconnect_success_rate",
            ):
                if merged_metrics.get(key) is None and pr_metrics.get(key) is not None:
                    merged_metrics[key] = pr_metrics.get(key)
            if not merged_metrics.get("updated_at"):
                merged_metrics["updated_at"] = str(pr_metrics.get("updated_at") or now_iso)
            if not merged_metrics.get("source"):
                merged_metrics["source"] = str(pr_metrics.get("source") or "probe")
        if merged_metrics:
            control_metrics = {
                "cpu_percent": merged_metrics.get("cpu_percent"),
                "mem_percent": merged_metrics.get("mem_percent"),
                "disk_percent": merged_metrics.get("disk_percent"),
                "qps": merged_metrics.get("qps"),
                "rtt_ms": merged_metrics.get("rtt_ms"),
                "service_cpu_percent": merged_metrics.get("service_cpu_percent"),
                "service_memory_mb": merged_metrics.get("service_memory_mb"),
                "total_requests": merged_metrics.get("total_requests"),
                "total_responses": merged_metrics.get("total_responses"),
                "queue_depth": merged_metrics.get("queue_depth"),
                "reconnect_success_rate": merged_metrics.get("reconnect_success_rate"),
                "updated_at": str(merged_metrics.get("updated_at") or now_iso),
                "source": str(merged_metrics.get("source") or "agent"),
            }
            business_metrics = (base_m.get("business") if isinstance(base_m.get("business"), dict) else {})
            obj["metrics"] = {**control_metrics, "control": control_metrics, "business": business_metrics}
            obj["metrics_missing"] = {
                "control": not any(control_metrics.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")),
                "business": not any(business_metrics.get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn")),
            }
        else:
            obj["metrics_missing"] = {"control": True, "business": True}
        if str(obj.get("effective_status") or "").upper() in ("ONLINE", "READY", "RUNNING"):
            online += 1
        out_agents.append(obj)
    device_snaps: Dict[str, Dict[str, Any]] = {}
    for item in out_agents:
        did = str(item.get("device_id") or "unknown-device")
        m = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        mc = m.get("control") if isinstance(m.get("control"), dict) else m
        mb = m.get("business") if isinstance(m.get("business"), dict) else {}
        snap = device_snaps.get(did) if isinstance(device_snaps.get(did), dict) else {
            "control": {"cpu_percent": None, "mem_percent": None, "disk_percent": None, "qps": None, "rtt_ms": None, "service_cpu_percent": None, "service_memory_mb": None, "updated_at": "", "source": "missing"},
            "business": {"qps": None, "rtt_p95_ms": None, "rtt_p99_ms": None, "error_rate": None, "conn": None, "updated_at": "", "source": "missing"},
            "updated_at": "", "source": "missing",
        }
        for key in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms", "service_cpu_percent", "service_memory_mb"):
            if mc.get(key) is not None:
                snap["control"][key] = mc.get(key)
        for key in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"):
            if mb.get(key) is not None:
                snap["business"][key] = mb.get(key)
        if mc.get("updated_at"):
            snap["control"]["updated_at"] = str(mc.get("updated_at"))
            snap["updated_at"] = str(mc.get("updated_at"))
        if mc.get("source"):
            snap["control"]["source"] = str(mc.get("source"))
            snap["source"] = str(mc.get("source"))
        device_snaps[did] = snap
    for item in out_agents:
        snap = device_snaps.get(str(item.get("device_id") or "unknown-device")) or {}
        item["device_metrics_snapshot"] = snap
        item["metrics"] = {**(snap.get("control") or {}), "control": (snap.get("control") or {}), "business": (snap.get("business") or {})}
        item["metrics_missing"] = {"control": not any((snap.get("control") or {}).get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")), "business": not any((snap.get("business") or {}).get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"))}
    return {
        "ok": True,
        "metrics": {
            "agents_total": len(agents),
            "agents_online": online,
            "jobs_pending": queue.get("PENDING", 0),
            "jobs_running": queue.get("RUNNING", 0),
        },
        "queue": queue,
        "agents": out_agents,
        "bindings": bindings,
        "policy": _load_agent_policy(),
        "probe_seq": _probe_change_seq,
        "pushed_at": now_iso,
    }


def _sse_broadcast(payload: Dict[str, Any]) -> None:
    """向所有 SSE 订阅者广播 payload。"""
    msg = json.dumps(payload, ensure_ascii=False)
    dead: List[_queue_mod.Queue] = []
    with _sse_sub_lock:
        for q in _sse_subscribers:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                _sse_subscribers.remove(q)
            except ValueError:
                pass


def _probe_bg_loop(app_ref) -> None:
    """后台探活主循环，daemon 线程。"""
    while True:
        with app_ref.app_context():
            try:
                _probe_background_tick()
            except Exception as exc:
                import logging
                logging.getLogger("ops.probe").warning("probe tick failed: %s", exc, exc_info=True)
        _time_mod.sleep(PROBE_INTERVAL_SEC)


# --- 延迟启动后台探活线程（首次请求时触发，避免 import 时 app 未初始化）
_probe_bg_started = False


def _ensure_probe_bg_started() -> None:
    """确保后台探活线程已启动。在首次 API 请求时调用。"""
    global _probe_bg_started
    if _probe_bg_started:
        return
    _probe_bg_started = True
    from flask import current_app
    app_ref = current_app._get_current_object()
    t = threading.Thread(target=_probe_bg_loop, args=(app_ref,), name="ops-probe-bg", daemon=True)
    t.start()

# --- consolidated from routes/ops ---

def _business_test_repo() -> str:
    return _resolve_game_server_repo()

def _biz_key_variants(key: str) -> List[str]:
    k = str(key or "").strip()
    if not k:
        return []
    variants = [k]
    if "_" in k:
        variants.append("".join(part[:1].upper() + part[1:] for part in k.split("_") if part))
    else:
        variants.append(k[:1].upper() + k[1:])
    return variants

def _biz_step_get(step: Dict[str, Any], *keys: str) -> Any:
    if not isinstance(step, dict):
        return None
    for key in keys:
        for variant in _biz_key_variants(key):
            if variant in step:
                return step.get(variant)
    return None

def _biz_run_get(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    if not isinstance(data, dict):
        return default
    for variant in _biz_key_variants(key):
        if variant in data:
            return data.get(variant)
    return default

def _normalize_business_steps(steps: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(steps, list):
        return out
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        server_raw = _biz_step_get(raw, "server") or {}
        client_raw = _biz_step_get(raw, "client") or {}
        out.append({
            "step_id": _biz_step_get(raw, "step_id", "id"),
            "protocol": _biz_step_get(raw, "protocol"),
            "message_id": _biz_step_get(raw, "message_id"),
            "result": _biz_step_get(raw, "result"),
            "blocked_reason": _biz_step_get(raw, "blocked_reason"),
            "client": {
                "request_json": _biz_step_get(client_raw, "request_json") if isinstance(client_raw, dict) else None,
                "transport": _biz_step_get(client_raw, "transport") if isinstance(client_raw, dict) else None,
                "seq": _biz_step_get(client_raw, "seq") if isinstance(client_raw, dict) else None,
            },
            "server": {
                "response_json": _biz_step_get(server_raw, "response_json") if isinstance(server_raw, dict) else None,
                "error_code": _biz_step_get(server_raw, "error_code") if isinstance(server_raw, dict) else None,
                "latency_ms": _biz_step_get(server_raw, "latency_ms") if isinstance(server_raw, dict) else None,
                "data_type": _biz_step_get(server_raw, "data_type") if isinstance(server_raw, dict) else None,
            },
        })
    return out

def _count_gameserver_processes() -> int:
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq GameServer.GameServerApp.exe", "/NH"],
                text=True,
                errors="replace",
            )
            return sum(1 for line in out.splitlines() if "GameServer.GameServerApp" in line)
    except Exception:
        pass
    return -1

def _ws_handshake_probe(host: str = "127.0.0.1", port: int = 15050, path: str = "/ws/", timeout_sec: float = 3.0) -> Tuple[bool, str]:
    import base64
    import secrets

    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")
    try:
        with socket.create_connection((host, port), timeout=timeout_sec) as sock:
            sock.settimeout(timeout_sec)
            sock.sendall(req)
            resp = b""
            while b"\r\n\r\n" not in resp and len(resp) < 8192:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp += chunk
            ok = b"101" in resp.split(b"\r\n", 1)[0] if resp else False
            return ok, ("ws_open" if ok else "ws_handshake_failed")
    except OSError as ex:
        return False, "ws_connect_failed:" + str(ex)

def _resolve_business_test_gateway_endpoint(
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    explicit = body.get("gateway_endpoint") if isinstance(body.get("gateway_endpoint"), dict) else {}
    if explicit.get("ws_url") or explicit.get("host"):
        return dict(explicit)
    project_id = str(body.get("project_id") or "").strip()
    env_key = _normalize_env_key(body.get("env_key") or "production")
    topology_id = str(body.get("topology_id") or "").strip()
    if not topology_id and project_id:
        topology_id = _runtime_default_topology_id(project_id, env_key)
    if topology_id:
        scoped = _load_topology_scoped(project_id, env_key, topology_id)
        topo = {
            "nodes": scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else [],
            "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
        }
        bindings = _load_scope_agent_bindings(topology_id)
        return resolve_gateway_endpoint(topo, bindings, str(body.get("transport") or "websocket"))
    return resolve_gateway_endpoint(None, None, str(body.get("transport") or "websocket"))

def _business_test_login_probe(
    gateway_host: str,
    gateway_port: int = 15050,
    relay_host: str = "",
    relay_port: int = 15501,
) -> Tuple[bool, str]:
    host = str(gateway_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    ws_ok, detail = _ws_handshake_probe(host, int(gateway_port or 15050))
    if not ws_ok:
        return False, "gateway_ws_failed:" + detail
    rh = str(relay_host or host).strip() or host
    rp = int(relay_port or 0)
    if rp > 0 and not _probe_tcp_open(rh, rp, timeout=0.6):
        return False, f"auth_cluster_relay_unreachable:{rh}:{rp}"
    return True, "gateway_ws_and_auth_relay_ok"

def _business_test_preflight(
    transport: str,
    gateway_endpoint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    transport = str(transport or "websocket").strip().lower()
    endpoint = gateway_endpoint if isinstance(gateway_endpoint, dict) else {}
    host = str(endpoint.get("host") or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    port = int(endpoint.get("port") or 15050)
    ws_url = str(endpoint.get("ws_url") or f"ws://{host}:{port}/ws/")
    gs_count = _count_gameserver_processes()
    issues: List[str] = []
    warnings: List[str] = []
    transport_ok = False
    login_probe_ok = False
    login_detail = ""
    if transport == "websocket":
        transport_ok, detail = _ws_handshake_probe(host, port)
        if not transport_ok:
            issues.append(f"WebSocket 握手失败: {ws_url} ({detail})")
        else:
            login_probe_ok, login_detail = _business_test_login_probe(host, port, host, 15501)
            if not login_probe_ok:
                issues.append(
                    "Login 前置探针失败: " + login_detail
                    + "；请检查 Gateway 集群转发与 Auth ClusterRelay 端口 (15501)"
                )
    elif transport == "tcp":
        tcp_host = str(endpoint.get("tcp_host") or host).strip() or host
        tcp_port = int(endpoint.get("tcp_port") or 5601)
        try:
            with socket.create_connection((tcp_host, tcp_port), timeout=2):
                transport_ok = True
        except OSError as ex:
            issues.append(f"TCP {tcp_host}:{tcp_port} 不可达: {ex}")
    else:
        transport_ok = True
        login_probe_ok = True
    if gs_count == 0 and not transport_ok:
        issues.append("未检测到 GameServer 进程且传输探针失败，请先「一键启动全流程」启动分布式拓扑")
    elif gs_count == 0 and transport_ok:
        warnings.append("未从 tasklist 解析到 GameServer 进程名，但传输探针已通过（可能为进程名截断）")
    elif gs_count > 1 and transport_ok and login_probe_ok:
        warnings.append(f"检测到 {gs_count} 个 GameServer 进程（分布式多进程模式）")
    return {
        "ok": len(issues) == 0,
        "transport": transport,
        "transport_ok": transport_ok,
        "login_probe_ok": login_probe_ok,
        "login_probe_detail": login_detail,
        "gateway_endpoint": endpoint,
        "gateway_ws_url": ws_url,
        "gameserver_process_count": gs_count,
        "issues": issues,
        "warnings": warnings,
        "message": "; ".join(issues) if issues else ("; ".join(warnings) if warnings else "preflight passed"),
    }

def _summarize_business_test_failure(result: Dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return "business test failed"
    parts: List[str] = []
    err = str(result.get("error") or "").strip()
    if err:
        parts.append(err)
    exit_code = result.get("exit_code")
    if exit_code not in (None, 0):
        parts.append("exit_code=" + str(exit_code))
    biz = result.get("business_run") if isinstance(result.get("business_run"), dict) else {}
    biz_err = str((biz or {}).get("error") or "").strip()
    if biz_err:
        parts.append("runner_error=" + biz_err)
    steps = _normalize_business_steps(result.get("steps"))
    result["steps"] = steps
    failed_steps = [s for s in steps if str(s.get("result") or "") == "failed"]
    if failed_steps:
        s0 = failed_steps[0]
        proto = str(s0.get("protocol") or "-")
        reason = str(s0.get("blocked_reason") or s0.get("step_id") or "unknown")
        server = s0.get("server") if isinstance(s0.get("server"), dict) else {}
        latency = server.get("latency_ms")
        parts.append("failed_step=" + proto + " reason=" + reason + (f" latency_ms={latency}" if latency is not None else ""))
        if proto == "Login_c2s" and reason == "timeout":
            parts.append(
                "hint=Login 超时无响应：请检查 Gateway 集群转发、Auth ClusterRelay(15501) 与 Mongo/Redis 可达；"
                "确认业务测试连接的 Gateway 端点来自拓扑 probe_host"
            )
    preflight = result.get("preflight") if isinstance(result.get("preflight"), dict) else {}
    for issue in (preflight.get("issues") or []) if isinstance(preflight.get("issues"), list) else []:
        parts.append("preflight=" + str(issue))
    stderr = str(result.get("stderr") or "").strip()
    if stderr:
        tail = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
        if tail:
            parts.append("stderr_tail=" + tail[-1][:240])
    stdout = str(result.get("stdout") or "").strip()
    if stdout and not failed_steps:
        tail = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        if tail:
            parts.append("stdout_tail=" + tail[-1][:240])
    if not parts:
        return "business test failed (no detail; check stderr/stdout in response JSON)"
    return "; ".join(parts)

def _run_business_test_runner(
    plan_id: str,
    transport: str,
    plan_override: Optional[Dict[str, Any]] = None,
    user_prefix: str = "biztest",
    server_id: str = "game-cn-1",
    gateway_endpoint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    repo = _business_test_repo()
    paths = resolve_paths(repo)
    runner_py = paths.get("runner_py") or ""
    if not os.path.isfile(runner_py):
        return {"ok": False, "error": "runner_missing", "message": "run-business-test.py not found", "path": runner_py}
    out_dir = os.path.join(DATA_DIR, "business_test_runs", plan_id + "-" + uuid.uuid4().hex[:8])
    os.makedirs(out_dir, exist_ok=True)
    endpoint = gateway_endpoint if isinstance(gateway_endpoint, dict) else {}
    ws_url = str(endpoint.get("ws_url") or "").strip()
    tcp_host = str(endpoint.get("tcp_host") or endpoint.get("host") or "").strip()
    tcp_port = int(endpoint.get("tcp_port") or 0)
    py_cmds = [
        "py", "-3", runner_py, "--transport", transport, "--output", out_dir,
        "--user-prefix", user_prefix, "--server-id", server_id, "--timeout-ms", "15000",
    ]
    if ws_url and transport == "websocket":
        py_cmds.extend(["--ws", ws_url])
    if tcp_host and transport == "tcp":
        py_cmds.extend(["--tcp-host", tcp_host])
        if tcp_port > 0:
            py_cmds.extend(["--tcp-port", str(tcp_port)])
    if plan_override and isinstance(plan_override, dict):
        plan_copy = dict(plan_override)
        if ws_url and transport == "websocket":
            plan_copy["endpoint"] = dict(plan_copy.get("endpoint") or {})
            plan_copy["endpoint"]["ws"] = ws_url
        inline_path = os.path.join(out_dir, "plan-inline.json")
        with open(inline_path, "w", encoding="utf-8") as f:
            json.dump(plan_copy, f, ensure_ascii=False, indent=2)
        py_cmds.extend(["--plan-path", inline_path])
    elif plan_id:
        py_cmds.extend(["--plan", plan_id])
    else:
        return {"ok": False, "error": "missing_plan", "message": "plan_id or plan_override required"}
    started = time.time()
    try:
        proc = subprocess.run(py_cmds, cwd=os.path.dirname(runner_py), capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "message": "business test timed out", "artifact_dir": out_dir}
    except FileNotFoundError:
        py_cmds[0] = "python"
        proc = subprocess.run(py_cmds, cwd=os.path.dirname(runner_py), capture_output=True, text=True, timeout=600)
    elapsed = round(time.time() - started, 3)
    run_json_path = os.path.join(out_dir, "business-run.json")
    report_json_path = os.path.join(out_dir, "business-report.json")
    run_data: Dict[str, Any] = {}
    if os.path.isfile(run_json_path):
        try:
            with open(run_json_path, "r", encoding="utf-8") as f:
                run_data = json.load(f)
        except Exception:
            run_data = {}
    ok = proc.returncode == 0 and bool(_biz_run_get(run_data, "passed", proc.returncode == 0))
    server_log_tail = ""
    try:
        log_dir = os.path.join(repo, "game-server", "bin", "Debug", "logs")
        if os.path.isdir(log_dir):
            logs = sorted(
                [os.path.join(log_dir, n) for n in os.listdir(log_dir) if n.startswith("cluster-") and n.endswith(".log")],
                key=os.path.getmtime,
                reverse=True,
            )
            if logs:
                with open(logs[0], "r", encoding="utf-8", errors="replace") as lf:
                    lines = lf.readlines()
                server_log_tail = "".join(lines[-40:])
    except Exception:
        server_log_tail = ""
    raw_steps = _biz_run_get(run_data, "steps") or []
    if not isinstance(raw_steps, list):
        raw_steps = []
    norm_steps = _normalize_business_steps(raw_steps)
    result: Dict[str, Any] = {
        "ok": ok,
        "exit_code": proc.returncode,
        "seconds": elapsed,
        "plan_id": plan_id,
        "transport": transport,
        "artifact_dir": out_dir,
        "business_run": run_data,
        "steps": norm_steps,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
        "server_log_tail": server_log_tail,
        "report_json": report_json_path if os.path.isfile(report_json_path) else "",
        "run_json": run_json_path if os.path.isfile(run_json_path) else "",
    }
    if not ok:
        result["summary"] = _summarize_business_test_failure(result)
        result["message"] = result["summary"]
    return result

def _cancel_runtime_start_runs_for_scope(
    project_id: str,
    env_key: str,
    topology_id: str,
    except_run_id: str = "",
) -> int:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    skip = str(except_run_id or "").strip()
    rows = _load_runtime_runs()
    changed = 0
    now = _now_iso()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if pid and str(row.get("project_id") or "") != pid:
            continue
        if env and _normalize_env_key(row.get("env_key") or "") != env:
            continue
        if tid and str(row.get("topology_id") or "") != tid:
            continue
        if str(row.get("op") or "").lower() != "start":
            continue
        if str(row.get("status") or "").lower() not in ("running", "queued"):
            continue
        if skip and str(row.get("run_id") or "") == skip:
            continue
        row["status"] = "canceled"
        row["updated_at"] = now
        changed += 1
    if changed:
        _save_runtime_runs(rows)
    return changed

def _mark_project_runtime_services_stopped(project_id: str) -> None:
    pid = str(project_id or "").strip()
    for svc in _services_for_project(pid):
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or "").strip()
        if sid:
            _update_canonical_service_runtime(sid, status="STOPPED", run_state="STOPPED", probe_status="FAIL")
    reg = _load_agent_registry_v2()
    canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else None
    if isinstance(canonical, dict):
        canonical["status"] = "OFFLINE"
        canonical["effective_status"] = "OFFLINE"
        canonical["run_state"] = "STOPPED"
        canonical["probe_status"] = "FAIL"
        canonical["updated_at"] = _now_iso()
        reg[CANONICAL_LOCAL_AGENT_ID] = canonical
        _save_agent_registry_v2(reg)
    _invalidate_runtime_probe_state()
    _seed_probe_cache_from_registry()

def _runtime_cluster_stop_all(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    actor: str,
    run_id: str,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    ticket_id = "OPS-RUN-" + str(run_id or "")[-6:]
    reason = "拓扑运行模式一键停止"
    logs: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    ordered = [n for n in (topo_nodes or []) if isinstance(n, dict)]
    ordered.reverse()

    for topo_node in ordered:
        nid = str(topo_node.get("id") or "").strip()
        if not nid:
            continue
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        if not node:
            logs.append({"ts": _now_iso(), "level": "error", "node_id": nid, "message": "节点不存在，已跳过"})
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "FAILED", "mode": "direct"})
            continue
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        if _is_external_daemon_node(node):
            result = _ops_platform_daemon_action(node, "stop", reason, ticket_id, actor)
            ok = bool(result.get("success"))
            if service_id:
                st = "STOPPED" if ok else "FAILED"
                _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="FAIL")
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS" if ok else "FAILED", "mode": "daemon"})
            logs.append(
                {
                    "ts": _now_iso(),
                    "level": "info" if ok else "error",
                    "node_id": nid,
                    "message": str(result.get("message") or ("daemon stop ok" if ok else "daemon stop failed")),
                }
            )
            continue
        result = _execute_canonical_service_action(
            pid,
            nid,
            service_id,
            "stop",
            actor,
            reason,
            ticket_id,
            {"run_mode": "direct", "via_agent": False},
        )
        ok = bool(result.get("ok"))
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS" if ok else "FAILED", "mode": "direct"})
        logs.append(
            {
                "ts": _now_iso(),
                "level": "info" if ok else "error",
                "node_id": nid,
                "message": str(result.get("message") or ("stop ok" if ok else "stop failed")),
            }
        )

    gs_stop = _stop_local_game_server()
    logs.append(
        {
            "ts": _now_iso(),
            "level": "info" if gs_stop.get("success") else "warn",
            "node_id": "cluster",
            "message": str(gs_stop.get("message") or "GameServer stop signal sent"),
        }
    )
    _mark_project_runtime_services_stopped(pid)
    fail = len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() != "SUCCESS"])
    logs.append(
        {
            "ts": _now_iso(),
            "level": "info" if fail == 0 else "warn",
            "node_id": "cluster",
            "message": f"集群级停止完成: success={len(items) - fail}, failed={fail}",
        }
    )
    return {"items": items, "logs": logs, "failed": fail}

def _topo_order_node_ids(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], reverse: bool = False) -> List[str]:
    ids = [str(n.get("id") or "").strip() for n in (nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()]
    if not ids:
        return []
    indeg = {i: 0 for i in ids}
    adj = {i: [] for i in ids}
    for edge in edges or []:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if frm in indeg and to in indeg:
            adj[frm].append(to)
            indeg[to] += 1
    q = [i for i in ids if indeg[i] == 0]
    out: List[str] = []
    while q:
        cur = q.pop(0)
        out.append(cur)
        for nx in adj.get(cur, []):
            indeg[nx] -= 1
            if indeg[nx] == 0:
                q.append(nx)
    if len(out) != len(ids):
        out = ids
    if reverse:
        out.reverse()
    return out

def _refresh_runtime_service_probes_from_topology(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    scope = _resolve_orchestration_scope(pid, tid, bindings)
    default_host = str(scope.get("default_probe_host") or DEFAULT_LOOPBACK)
    gateway_live = _probe_tcp_open(default_host, _RUNTIME_GATEWAY_PROBE_PORT)
    ops_live = _probe_tcp_open(default_host, _RUNTIME_OPS_PROBE_PORT)
    live_count = 0
    total = 0
    for topo_node in topo_nodes or []:
        if not isinstance(topo_node, dict):
            continue
        nid = str(topo_node.get("id") or "").strip()
        if not nid:
            continue
        total += 1
        node = _build_runtime_node_from_topology_node(pid, env_key, topo_node, topology_id)
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        if _is_embedded_topology_node(topo_node, contract):
            live = gateway_live or ops_live
        elif probe_port > 0:
            live = _probe_tcp_open(host, probe_port)
        else:
            role = str(node.get("role") or "").strip().lower()
            live = (gateway_live or ops_live) if role in ("auth", "game", "business", "admin", "ops") else False
        if live:
            live_count += 1
        st = "RUNNING" if live else "STOPPED"
        if service_id:
            _update_canonical_service_runtime(
                service_id,
                status=st,
                run_state=st,
                probe_status="PASS" if live else "FAIL",
                metrics=_sample_local_control_metrics() if live else {},
            )
    reg = _load_agent_registry_v2()
    canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else None
    if isinstance(canonical, dict):
        any_live = live_count > 0 and (gateway_live or ops_live)
        canonical["status"] = "ONLINE" if any_live else "OFFLINE"
        canonical["effective_status"] = canonical["status"]
        canonical["run_state"] = canonical["status"]
        canonical["probe_status"] = "PASS" if gateway_live else ("WARN" if ops_live else "FAIL")
        canonical["updated_at"] = _now_iso()
        canonical["metrics"] = _sample_local_control_metrics()
        reg[CANONICAL_LOCAL_AGENT_ID] = canonical
        _save_agent_registry_v2(reg)
        _append_realtime_agent_sample(canonical)
    return {"live_count": live_count, "total": total, "gateway_live": gateway_live, "ops_live": ops_live}

def _ensure_runtime_infra_ports(
    timeout_sec: float = 45.0,
    project_id: str = "",
    env_key: str = "",
    topology_id: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    """确保 Mongo/Redis 基础设施端口可用；Windows 走本机守护进程启动逻辑。"""

    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    mongo_host = _resolve_orchestration_probe_host(
        str(project_id or ""), tid, {"id": "mongo-db-cn-1"}, bindings
    )
    redis_host = _resolve_orchestration_probe_host(
        str(project_id or ""), tid, {"id": "redis-cache-cn-1"}, bindings
    )

    def _ports_snapshot() -> Tuple[bool, str]:
        mongo_ok = _probe_tcp_open(mongo_host, 27017, timeout=0.15)
        redis_ok = _probe_tcp_open(redis_host, 6379, timeout=0.15)
        msg = (
            f"mongo:{mongo_host}:27017={'PASS' if mongo_ok else 'FAIL'} "
            f"redis:{redis_host}:6379={'PASS' if redis_ok else 'FAIL'}"
        )
        return bool(mongo_ok and redis_ok), msg

    ok, msg = _ports_snapshot()
    if ok:
        return True, msg

    pid = str(project_id or "GomeKu").strip()
    env = _normalize_env_key(env_key or "production")
    tid = str(topology_id or "").strip()
    scoped_nodes: List[Dict[str, Any]] = []
    try:
        scoped = _load_topology_scoped(pid, env, tid) if tid else {}
        scoped_nodes = [n for n in (scoped.get("nodes") or []) if isinstance(n, dict)]
    except Exception:
        scoped_nodes = []

    def _infra_node(nid: str, role: str, port: int) -> Dict[str, Any]:
        hit = next((n for n in scoped_nodes if str(n.get("id") or "") == nid), None)
        if isinstance(hit, dict):
            return _build_runtime_node_from_topology_node(pid, env, hit, tid)
        return {
            "id": nid,
            "role": role,
            "port": port,
            "daemon_profile": "external_daemon",
        }

    for nid, role, port in (
        ("mongo-db-cn-1", "database", 27017),
        ("redis-cache-cn-1", "cache", 6379),
    ):
        infra_host = mongo_host if role == "database" else redis_host
        if _probe_tcp_open(infra_host, port, timeout=0.12):
            continue
        node = _infra_node(nid, role, port)
        if os.name == "nt":
            _start_external_daemon_node(node, "start")
        else:
            if role == "database":
                db_dir = _gomeku_mongo_dbpath()
                os.makedirs(db_dir, exist_ok=True)
                for cmd in (
                    ["mongod", "--dbpath", db_dir, "--port", "27017", "--bind_ip", "127.0.0.1", "--fork", "--logpath", f"{db_dir}/mongod.log"],
                    ["/opt/homebrew/bin/mongod", "--dbpath", db_dir, "--port", "27017", "--bind_ip", "127.0.0.1", "--fork", "--logpath", f"{db_dir}/mongod.log"],
                    ["/usr/local/bin/mongod", "--dbpath", db_dir, "--port", "27017", "--bind_ip", "127.0.0.1", "--fork", "--logpath", f"{db_dir}/mongod.log"],
                ):
                    try:
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                    except Exception:
                        pass
                    if _probe_tcp_open(mongo_host, 27017, timeout=0.15):
                        break
            else:
                for cmd in (
                    ["redis-server", "--daemonize", "yes", "--port", "6379", "--bind", "127.0.0.1"],
                    ["/opt/homebrew/bin/redis-server", "--daemonize", "yes", "--port", "6379", "--bind", "127.0.0.1"],
                ):
                    try:
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                    except Exception:
                        pass
                    if _probe_tcp_open(redis_host, 6379, timeout=0.15):
                        break

    deadline = time.time() + max(5.0, float(timeout_sec))
    last = msg
    while time.time() < deadline:
        ok, last = _ports_snapshot()
        if ok:
            return True, last
        time.sleep(0.5)
    return False, last


_runtime_orchestrator_lock = threading.Lock()

def _runtime_run_patch(
    run_id: str,
    *,
    items: Optional[List[Dict[str, Any]]] = None,
    logs_append: Optional[List[Dict[str, Any]]] = None,
    status: Optional[str] = None,
) -> None:
    rid = str(run_id or "").strip()
    if not rid:
        return
    with _runtime_orchestrator_lock:
        run = _find_runtime_run(rid)
        if not isinstance(run, dict):
            return
        if items is not None:
            run["items"] = items
        if logs_append:
            run_logs = run.get("logs") if isinstance(run.get("logs"), list) else []
            run_logs.extend(logs_append)
            if len(run_logs) > 400:
                run_logs = run_logs[-400:]
            run["logs"] = run_logs
        if status:
            run["status"] = status
        run["updated_at"] = _now_iso()
        _upsert_runtime_run(run)

def _runtime_orchestrator_log(run_id: str, node_id: str, level: str, message: str) -> None:
    _runtime_run_patch(
        run_id,
        logs_append=[{"ts": _now_iso(), "level": level, "node_id": node_id, "message": message}],
    )

def _runtime_orchestrator_set_item(items: List[Dict[str, Any]], node_id: str, status: str, **extra: Any) -> None:
    nid = str(node_id or "").strip()
    for item in items:
        if isinstance(item, dict) and str(item.get("node_id") or "") == nid:
            item["status"] = status
            for k, v in extra.items():
                item[k] = v
            return

def _wait_agent_job_terminal(job_id: str, timeout_sec: float = 120.0) -> Tuple[bool, Dict[str, Any]]:
    jid = str(job_id or "").strip()
    if not jid:
        return False, {"status": "FAILED", "message": "missing job_id"}
    deadline = time.time() + max(5.0, float(timeout_sec))
    while time.time() < deadline:
        jobs = _load_agent_jobs()
        hit = next((j for j in jobs if isinstance(j, dict) and str(j.get("job_id") or "") == jid), None)
        if isinstance(hit, dict):
            st = str(hit.get("status") or "").upper()
            if _agent_status_terminal(st):
                return st == "SUCCESS", hit
        time.sleep(1.0)
    return False, {"status": "TIMEOUT", "job_id": jid}

def _orchestrate_remote_node_action(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    action: str,
    actor: str,
    reason: str,
    ticket_id: str,
) -> Tuple[bool, str, str]:
    act = str(action or "start").strip().lower()
    nid = str(topo_node.get("id") or "").strip()
    node = _build_runtime_node_from_topology_node(project_id, env_key, topo_node, topology_id)
    service_id = str((service_bindings or {}).get(nid) or nid).strip()
    req = {
        "node_id": nid,
        "action_type": act,
        "target": nid,
        "ticket_id": ticket_id,
        "reason": reason,
        "approver": actor,
        "run_mode": "agent",
        "via_agent": True,
        "payload": {
            "run_mode": "agent",
            "desired_role": str(node.get("role") or ""),
            "desired_server_id": str(node.get("server_id") or nid),
            "desired_service_id": service_id,
            "switch_required": act in ("start", "restart"),
            "launch_visible_console": False,
        },
    }
    validation = _validate_ops_request(req, node)
    if not validation.get("ok"):
        return False, "validation_failed: " + str(validation.get("missing") or ""), ""
    if validation.get("require_approval") and not validation.get("approved"):
        validation = dict(validation)
        validation["approved"] = True
    result = _execute_validated(req, node, validation)
    if not result.get("ok"):
        return False, str(result.get("message") or result.get("error") or "remote action failed"), ""
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    job_id = str(data.get("job_id") or "")
    if job_id:
        ok, job = _wait_agent_job_terminal(job_id, timeout_sec=180.0 if act == "start" else 90.0)
        job_result = job.get("result") if isinstance(job.get("result"), dict) else {}
        msg = str(job_result.get("message") or job.get("status") or result.get("message") or "")
        return ok, msg, job_id
    return True, str(result.get("message") or "ok"), job_id

def _probe_topology_node_live(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    *,
    gateway_live: bool = False,
    ops_live: bool = False,
    probe_host: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
    contract = _resolve_node_contract_for_topology_node(topo_node)
    host = str(probe_host or "").strip() or _resolve_orchestration_probe_host(pid, tid, topo_node, agent_bindings)
    probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
    if _is_embedded_topology_node(topo_node, contract):
        live = bool(gateway_live or ops_live)
        return (
            live,
            f"gateway:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if gateway_live else 'FAIL'} "
            f"ops:{_RUNTIME_OPS_PROBE_PORT}={'PASS' if ops_live else 'FAIL'} @{host}",
        )
    if probe_port > 0:
        live = _probe_tcp_open(host, probe_port)
        return live, f"tcp:{host}:{probe_port}={'PASS' if live else 'FAIL'}"
    role = str(node.get("role") or "").strip().lower()
    if role in ("auth", "game", "business", "admin", "ops", "gateway", "edge"):
        live = bool(gateway_live or ops_live)
        return (
            live,
            f"gateway:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if gateway_live else 'FAIL'} "
            f"ops:{_RUNTIME_OPS_PROBE_PORT}={'PASS' if ops_live else 'FAIL'} @{host}",
        )
    return False, "no probe target"

def _orchestration_post_launch_wait(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    contract: Dict[str, Any],
    service_id: str,
    launch_detail: str,
    *,
    probe_host: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
    timeout_sec: float = 25.0,
) -> Tuple[bool, str]:
    """编排逐步启动后的就绪等待：embedded 以进程存活为准，不依赖 5501/5502。"""
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    sid = str(service_id or topo_node.get("id") or "").strip().lower()
    detail = str(launch_detail or "").strip()
    role = str(topo_node.get("role") or contract.get("role") or "").strip().lower()
    cluster_type = _cluster_type_for_contract(contract, role)
    relay_port = int(_CLUSTER_RELAY_PROBE_PORTS.get(sid) or _cluster_relay_port_for_type(cluster_type, role) or 0)
    if role in ("gateway", "edge") or cluster_type.lower() == "gateway":
        ws_ok, ws_detail = _ws_handshake_probe(host, _RUNTIME_GATEWAY_PROBE_PORT)
        tcp_ok = _probe_tcp_open(host, _RUNTIME_GATEWAY_PROBE_PORT, timeout=0.35)
        if ws_ok and tcp_ok:
            return True, detail or f"gateway ws/tcp PASS @{host}:{_RUNTIME_GATEWAY_PROBE_PORT}"
        return False, (
            f"{detail}; gateway ws={'PASS' if ws_ok else 'FAIL'} ({ws_detail}) "
            f"tcp:{host}:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if tcp_ok else 'FAIL'}"
        )
    if relay_port > 0 and role in ("auth", "game", "business"):
        relay_ok = _probe_tcp_open(host, relay_port, timeout=0.5)
        if relay_ok:
            return True, detail or f"cluster-relay:{host}:{relay_port}=PASS"
        pid = _find_gameserver_pid_by_service(sid)
        if pid > 0 and _is_process_running(pid):
            return True, detail or f"{sid} pid {pid} alive (relay pending)"
        return False, f"{detail}; cluster-relay:{host}:{relay_port}=FAIL"
    if _is_embedded_topology_node(topo_node, contract):
        if _gameserver_service_live(sid, probe_host=host):
            return True, detail or f"{sid} process live"
        pid = _find_gameserver_pid_by_service(sid)
        if pid > 0 and _is_process_running(pid):
            return True, detail or f"{sid} pid {pid} alive"
        if "alive" in detail.lower() and "pid" in detail.lower():
            return True, detail
        gw = _probe_tcp_open(host, _RUNTIME_GATEWAY_PROBE_PORT, timeout=0.2)
        ops = _probe_tcp_open(host, _RUNTIME_OPS_PROBE_PORT, timeout=0.2)
        if gw or ops:
            return True, (
                f"gateway:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if gw else 'FAIL'} "
                f"ops:{_RUNTIME_OPS_PROBE_PORT}={'PASS' if ops else 'FAIL'} @{host}"
            )
        return False, (
            f"{detail}; embedded {sid} not live; "
            f"gateway:{_RUNTIME_GATEWAY_PROBE_PORT}={'PASS' if gw else 'FAIL'} "
            f"ops:{_RUNTIME_OPS_PROBE_PORT}={'PASS' if ops else 'FAIL'} @{host}"
        )
    return _wait_topology_node_live(
        project_id,
        env_key,
        topology_id,
        topo_node,
        timeout_sec=timeout_sec,
        probe_host=host,
        agent_bindings=agent_bindings,
    )

def _wait_topology_node_live(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_node: Dict[str, Any],
    *,
    timeout_sec: float = 35.0,
    gateway_live: bool = False,
    ops_live: bool = False,
    probe_host: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str]:
    host = str(probe_host or "").strip() or _resolve_orchestration_probe_host(
        project_id, topology_id, topo_node, agent_bindings
    )
    deadline = time.time() + max(3.0, float(timeout_sec))
    last = ""
    while time.time() < deadline:
        gw = gateway_live or _probe_tcp_open(host, _RUNTIME_GATEWAY_PROBE_PORT)
        ops = ops_live or _probe_tcp_open(host, _RUNTIME_OPS_PROBE_PORT)
        ok, msg = _probe_topology_node_live(
            project_id,
            env_key,
            topology_id,
            topo_node,
            gateway_live=gw,
            ops_live=ops,
            probe_host=host,
            agent_bindings=agent_bindings,
        )
        last = msg
        if ok:
            return True, msg
        time.sleep(1.0)
    return False, last or "probe timeout"

def _wait_topology_node_down(
    port: int,
    timeout_sec: float = 15.0,
    probe_host: str = DEFAULT_LOOPBACK,
) -> Tuple[bool, str]:
    if port <= 0:
        return True, "no port"
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    deadline = time.time() + max(2.0, float(timeout_sec))
    while time.time() < deadline:
        if not _probe_tcp_open(host, port):
            return True, f"port {port} closed on {host}"
        time.sleep(0.8)
    return False, f"port {port} still open on {host}"

def _runtime_orchestrate_start_worker(
    run_id: str,
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
) -> None:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    ticket_id = "OPS-RUN-" + str(run_id or "")[-6:]
    reason = "拓扑运行模式一键启动"
    run = _find_runtime_run(run_id)
    items = run.get("items") if isinstance(run, dict) and isinstance(run.get("items"), list) else []
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    ordered_ids = [str(x.get("node_id") or "") for x in items if isinstance(x, dict) and str(x.get("node_id") or "")]
    if not ordered_ids:
        ordered_ids = _topo_order_node_ids(topo_nodes, topo_edges, reverse=False)
        items = []
        for seq, nid in enumerate(ordered_ids, start=1):
            topo_node = id_to_node.get(nid) or {}
            node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid) if topo_node else {}
            mode = "daemon" if topo_node and _is_external_daemon_node(node) else "direct"
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "PENDING", "mode": mode, "seq": seq, "step_total": len(ordered_ids)})
        _runtime_run_patch(run_id, items=items)
    total = len(ordered_ids)
    fail = 0

    _runtime_orchestrator_log(run_id, "cluster", "info", "Step 0/{}: 清理旧 GameServer 进程".format(total))
    _stop_local_game_server()
    time.sleep(1.2)

    _runtime_orchestrator_log(run_id, "cluster", "info", "Step 0/{}: 检查并启动 Mongo/Redis 基础设施".format(total))
    infra_ok, infra_msg = _ensure_runtime_infra_ports(
        timeout_sec=45.0, project_id=pid, env_key=env, topology_id=tid, agent_bindings=bindings
    )
    _runtime_orchestrator_log(
        run_id,
        "cluster",
        "info" if infra_ok else "error",
        "基础设施探活: " + infra_msg,
    )
    if not infra_ok:
        for nid in ordered_ids:
            _runtime_orchestrator_set_item(items, nid, "FAILED")
        _runtime_run_patch(run_id, items=items, status="failed")
        return

    for seq, nid in enumerate(ordered_ids, start=1):
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            _runtime_orchestrator_set_item(items, nid, "FAILED")
            _runtime_orchestrator_log(run_id, nid, "error", f"Step {seq}/{total}: 节点配置缺失")
            fail += 1
            break

        _runtime_orchestrator_set_item(items, nid, "RUNNING", step=seq, step_total=total)
        _runtime_run_patch(run_id, items=items)
        _runtime_orchestrator_log(run_id, nid, "info", f"Step {seq}/{total}: 开始启动节点 {nid}")

        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        bound_agent_id = str((bindings or {}).get(nid) or CANONICAL_LOCAL_AGENT_ID).strip()
        ok = False
        detail = ""
        job_id = ""

        if _is_external_daemon_node(node):
            result = _ops_platform_daemon_action(node, "start", reason, ticket_id, actor)
            ok = bool(result.get("success"))
            detail = str(result.get("message") or "")
            if not ok and probe_port > 0 and _probe_tcp_open(probe_host, probe_port):
                ok = True
                detail = f"daemon 端口已监听 ({probe_host}:{probe_port})"
            if ok:
                wait_ok, wait_msg = _wait_topology_node_live(
                    pid, env, tid, topo_node, timeout_sec=20.0, probe_host=probe_host, agent_bindings=bindings
                )
                ok = wait_ok
                detail = wait_msg if wait_ok else (detail + "; " + wait_msg)
        elif not _is_local_runtime_agent(bound_agent_id):
            _runtime_orchestrator_log(run_id, "cluster", "info", f"Step {seq}/{total}: 远端 Agent 启动 {nid}")
            ok, detail, job_id = _orchestrate_remote_node_action(
                pid, env, tid, topo_node, service_bindings, bindings, "start", actor, reason, ticket_id
            )
            if ok:
                wait_ok, wait_msg = _wait_topology_node_live(
                    pid, env, tid, topo_node, timeout_sec=25.0, probe_host=probe_host, agent_bindings=bindings
                )
                ok = wait_ok
                detail = wait_msg if wait_ok else (detail + "; " + wait_msg)
        else:
            service_id = str((service_bindings or {}).get(nid) or nid).strip()
            _runtime_orchestrator_log(run_id, "cluster", "info", f"Step {seq}/{total}: 启动独立进程 {service_id}")
            launch = _launch_gameserver_service(
                service_id, reason, wait_ready=True, timeout_sec=120, node=node, probe_host=probe_host
            )
            ok = bool(launch.get("success"))
            detail = str(launch.get("message") or "")
            if ok:
                wait_ok, wait_msg = _orchestration_post_launch_wait(
                    pid,
                    env,
                    tid,
                    topo_node,
                    contract,
                    service_id,
                    detail,
                    probe_host=probe_host,
                    agent_bindings=bindings,
                    timeout_sec=25.0,
                )
                ok = wait_ok
                detail = wait_msg if wait_ok else (detail + "; " + wait_msg)

        if ok:
            _runtime_orchestrator_set_item(items, nid, "SUCCESS", step=seq, step_total=total, job_id=job_id)
            _runtime_orchestrator_log(run_id, nid, "info", f"Step {seq}/{total}: 节点 {nid} 启动成功 — {detail}")
            _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
        else:
            _runtime_orchestrator_set_item(items, nid, "FAILED", step=seq, step_total=total, detail=detail)
            _runtime_orchestrator_log(run_id, nid, "error", f"Step {seq}/{total}: 节点 {nid} 启动失败 — {detail}")
            fail += 1
            for rest in ordered_ids[seq:]:
                if str(rest) != nid:
                    _runtime_orchestrator_set_item(items, rest, "SKIPPED")
            break

        _runtime_run_patch(run_id, items=items)
        time.sleep(0.35)

    probe_stat = _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
    gateway_live = bool(probe_stat.get("gateway_live"))
    game_ok = bool(fail == 0 and gateway_live)
    _consolidate_runtime_agents_to_canonical(pid)
    if fail > 0 and gateway_live and int(probe_stat.get("live_count") or 0) >= max(1, int(probe_stat.get("total") or 0) - 1):
        final_status = "success"
        _runtime_orchestrator_log(
            run_id,
            "cluster",
            "info",
            f"启动编排降级成功: gateway_live={gateway_live}, live={probe_stat.get('live_count')}/{probe_stat.get('total')}, step_fail={fail}",
        )
    else:
        final_status = "success" if fail == 0 else "failed"
    _runtime_orchestrator_log(
        run_id,
        "cluster",
        "info" if fail == 0 else "error",
        f"启动编排结束: status={final_status}, gateway_live={gateway_live}, live={probe_stat.get('live_count')}/{probe_stat.get('total')}, failed={fail}",
    )
    _runtime_run_patch(run_id, items=items, status=final_status)

def _spawn_runtime_start_orchestration(
    run_id: str,
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    ordered_ids = _topo_order_node_ids(topo_nodes, topo_edges, reverse=False)
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    items: List[Dict[str, Any]] = []
    for seq, nid in enumerate(ordered_ids, start=1):
        topo_node = id_to_node.get(nid) or {}
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid) if topo_node else {}
        mode = "daemon" if topo_node and _is_external_daemon_node(node) else "direct"
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "PENDING", "mode": mode, "seq": seq, "step_total": len(ordered_ids)})
    logs = [
        {
            "ts": _now_iso(),
            "level": "info",
            "node_id": "cluster",
            "message": f"启动编排已入队，共 {len(ordered_ids)} 个节点，将按拓扑序逐节点启动",
        }
    ]
    _runtime_run_patch(run_id, items=items, logs_append=logs, status="running")
    threading.Thread(
        target=_runtime_orchestrate_start_worker,
        args=(run_id, pid, env, tid, topo_nodes, topo_edges, service_bindings, agent_bindings, actor),
        daemon=True,
    ).start()
    return {"items": items, "logs": logs, "failed": 0, "status": "running", "async": True}

def _runtime_orchestrate_stop_worker(
    run_id: str,
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
) -> None:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    ticket_id = "OPS-RUN-" + str(run_id or "")[-6:]
    reason = "拓扑运行模式一键停止"
    run = _find_runtime_run(run_id)
    items = run.get("items") if isinstance(run, dict) and isinstance(run.get("items"), list) else []
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    ordered_ids = [str(x.get("node_id") or "") for x in items if isinstance(x, dict) and str(x.get("node_id") or "")]
    if not ordered_ids:
        ordered_ids = list(reversed(_topo_order_node_ids(topo_nodes, topo_edges, reverse=False)))
        items = []
        for seq, nid in enumerate(ordered_ids, start=1):
            topo_node = id_to_node.get(nid) or {}
            node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid) if topo_node else {}
            mode = "daemon" if topo_node and _is_external_daemon_node(node) else "direct"
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "PENDING", "mode": mode, "seq": seq, "step_total": len(ordered_ids)})
        _runtime_run_patch(run_id, items=items)
    total = len(ordered_ids)
    fail = 0
    for seq, nid in enumerate(ordered_ids, start=1):
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            _runtime_orchestrator_set_item(items, nid, "FAILED")
            fail += 1
            continue

        _runtime_orchestrator_set_item(items, nid, "RUNNING", step=seq, step_total=total)
        _runtime_run_patch(run_id, items=items)
        _runtime_orchestrator_log(run_id, nid, "info", f"Step {seq}/{total}: 开始停止节点 {nid}")

        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        bound_agent_id = str((bindings or {}).get(nid) or CANONICAL_LOCAL_AGENT_ID).strip()
        ok = False
        detail = ""

        if _is_external_daemon_node(node):
            result = _ops_platform_daemon_action(node, "stop", reason, ticket_id, actor)
            ok = bool(result.get("success"))
            detail = str(result.get("message") or "")
            if probe_port > 0:
                down_ok, down_msg = _wait_topology_node_down(probe_port, timeout_sec=12.0, probe_host=probe_host)
                ok = ok and down_ok
                detail = detail + "; " + down_msg
            if service_id:
                st = "STOPPED" if ok else "FAILED"
                _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="FAIL")
        elif not _is_local_runtime_agent(bound_agent_id):
            ok, detail, _job_id = _orchestrate_remote_node_action(
                pid, env, tid, topo_node, service_bindings, bindings, "stop", actor, reason, ticket_id
            )
            if service_id:
                st = "STOPPED" if ok else "FAILED"
                _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="FAIL")
        else:
            stop_res = _stop_gameserver_service(service_id, node, probe_host=probe_host)
            ok = bool(stop_res.get("success"))
            detail = str(stop_res.get("message") or "")
            if probe_port > 0:
                down_ok, down_msg = _wait_topology_node_down(probe_port, timeout_sec=12.0, probe_host=probe_host)
                ok = ok and down_ok
                detail = detail + "; " + down_msg
            if service_id:
                st = "STOPPED" if ok else "FAILED"
                _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="FAIL")

        if ok:
            _runtime_orchestrator_set_item(items, nid, "SUCCESS", step=seq, step_total=total)
            _runtime_orchestrator_log(run_id, nid, "info", f"Step {seq}/{total}: 节点 {nid} 已停止 — {detail}")
        else:
            _runtime_orchestrator_set_item(items, nid, "FAILED", step=seq, step_total=total, detail=detail)
            _runtime_orchestrator_log(run_id, nid, "error", f"Step {seq}/{total}: 节点 {nid} 停止失败 — {detail}")
            fail += 1

        _runtime_run_patch(run_id, items=items)
        time.sleep(0.35)

    _mark_project_runtime_services_stopped(pid)
    _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
    final_status = "success" if fail == 0 else "failed"
    _runtime_orchestrator_log(
        run_id,
        "cluster",
        "info" if fail == 0 else "warn",
        f"停止编排结束: status={final_status}, failed={fail}",
    )
    _runtime_run_patch(run_id, items=items, status=final_status)

def _spawn_runtime_stop_orchestration(
    run_id: str,
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    ordered_ids = list(reversed(_topo_order_node_ids(topo_nodes, topo_edges, reverse=False)))
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    items: List[Dict[str, Any]] = []
    for seq, nid in enumerate(ordered_ids, start=1):
        topo_node = id_to_node.get(nid) or {}
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid) if topo_node else {}
        mode = "daemon" if topo_node and _is_external_daemon_node(node) else "direct"
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "PENDING", "mode": mode, "seq": seq, "step_total": len(ordered_ids)})
    logs = [
        {
            "ts": _now_iso(),
            "level": "info",
            "node_id": "cluster",
            "message": f"停止编排已入队，共 {len(ordered_ids)} 个节点，将按逆拓扑序逐节点停止",
        }
    ]
    _runtime_run_patch(run_id, items=items, logs_append=logs, status="running")
    threading.Thread(
        target=_runtime_orchestrate_stop_worker,
        args=(run_id, pid, env, tid, topo_nodes, topo_edges, service_bindings, agent_bindings, actor),
        daemon=True,
    ).start()
    return {"items": items, "logs": logs, "failed": 0, "status": "running", "async": True}

def _runtime_cluster_start_all(
    project_id: str,
    env_key: str,
    topology_id: str,
    topo_nodes: List[Dict[str, Any]],
    topo_edges: List[Dict[str, Any]],
    service_bindings: Dict[str, str],
    agent_bindings: Dict[str, str],
    actor: str,
    run_id: str,
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    bindings = agent_bindings if isinstance(agent_bindings, dict) else _load_scope_agent_bindings(tid)
    ticket_id = "OPS-RUN-" + str(run_id or "")[-6:]
    reason = "拓扑运行模式一键启动"
    logs: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    id_to_node = {str(n.get("id") or "").strip(): n for n in (topo_nodes or []) if isinstance(n, dict) and str(n.get("id") or "").strip()}
    ordered_ids = _topo_order_node_ids(topo_nodes, topo_edges, reverse=False)
    daemon_ids = [nid for nid in ordered_ids if isinstance(id_to_node.get(nid), dict) and _is_external_daemon_node(_build_runtime_node_from_topology_node(pid, env, id_to_node[nid], tid))]
    app_ids = [nid for nid in ordered_ids if nid not in daemon_ids]

    logs.append({"ts": _now_iso(), "level": "info", "node_id": "cluster", "message": "清理旧 GameServer 进程，准备全新启动"})
    _stop_local_game_server()
    time.sleep(1.5)

    infra_ok, infra_msg = _ensure_runtime_infra_ports(
        timeout_sec=45.0, project_id=pid, env_key=env, topology_id=tid, agent_bindings=bindings
    )
    logs.append(
        {
            "ts": _now_iso(),
            "level": "info" if infra_ok else "error",
            "node_id": "cluster",
            "message": "基础设施探活: " + infra_msg,
        }
    )
    if not infra_ok:
        for nid in daemon_ids + app_ids:
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "FAILED", "mode": "direct"})
        logs.append({"ts": _now_iso(), "level": "error", "node_id": "cluster", "message": "Mongo/Redis 未就绪，已中止 GameServer 启动"})
        _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
        return {"items": items, "logs": logs, "failed": max(1, len(items)), "gateway_live": False}

    unified_launch: Optional[Dict[str, Any]] = None
    unified_ok = False
    if _should_use_unified_gameserver_all(app_ids, service_bindings):
        logs.append({"ts": _now_iso(), "level": "info", "node_id": "cluster", "message": "Windows 本地：使用 GameServer --all 单进程启动（业务测试/E2E 需要）"})
        unified_launch = _launch_gameserver_unified_all(reason, wait_ready=True, timeout_sec=120)
        unified_ok = bool(unified_launch.get("success"))
        logs.append(
            {
                "ts": _now_iso(),
                "level": "info" if unified_ok else "error",
                "node_id": "cluster",
                "message": str(unified_launch.get("message") or "unified-all launch"),
            }
        )

    for nid in daemon_ids:
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            continue
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        result = _ops_platform_daemon_action(node, "start", reason, ticket_id, actor)
        ok = bool(result.get("success"))
        if not ok and probe_port > 0 and _probe_tcp_open(probe_host, probe_port):
            ok = True
            result = {"success": True, "message": f"daemon 端口已监听 ({probe_host}:{probe_port})"}
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS" if ok else "FAILED", "mode": "daemon"})
        logs.append(
            {
                "ts": _now_iso(),
                "level": "info" if ok else "warn",
                "node_id": nid,
                "message": str(result.get("message") or ("daemon start ok" if ok else "daemon start failed")),
            }
        )

    for nid in app_ids:
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            continue
        node = _build_runtime_node_from_topology_node(pid, env, topo_node, tid)
        service_id = str((service_bindings or {}).get(nid) or nid).strip()
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        if unified_launch is not None and service_id.strip().lower() in _GAMESERVER_PROCESS_SERVICE_IDS:
            ok = unified_ok
            launch = {
                "success": ok,
                "message": str((unified_launch or {}).get("message") or "unified-all"),
                "data": {"live": ok, "mode": "unified-all"},
            }
        else:
            launch = _launch_gameserver_service(
                service_id, reason, wait_ready=True, timeout_sec=120, node=node, probe_host=probe_host
            )
        ok = bool(launch.get("success"))
        launch_msg = str(launch.get("message") or "")
        unified_node = unified_launch is not None and service_id.strip().lower() in _GAMESERVER_PROCESS_SERVICE_IDS
        if ok and not unified_node:
            wait_ok, wait_msg = _orchestration_post_launch_wait(
                pid,
                env,
                tid,
                topo_node,
                contract,
                service_id,
                launch_msg,
                probe_host=probe_host,
                agent_bindings=bindings,
                timeout_sec=25.0,
            )
            ok = wait_ok
            launch = {"success": ok, "message": wait_msg, "data": launch.get("data")}
        elif unified_node and unified_ok:
            ok = True
            launch = {"success": True, "message": launch_msg, "data": {"live": True, "mode": "unified-all"}}
        live = bool((launch.get("data") or {}).get("live")) or _gameserver_service_live(service_id, node, probe_host=probe_host)
        if unified_node and unified_ok:
            live = _ws_handshake_probe()[0]
        ok = ok and live
        items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS" if ok else "FAILED", "mode": "direct"})
        logs.append(
            {
                "ts": _now_iso(),
                "level": "info" if ok else "error",
                "node_id": nid,
                "message": str(launch.get("message") or (f"{'live' if live else 'down'} port={probe_port or '-'}")),
            }
        )

    probe_stat = _refresh_runtime_service_probes_from_topology(pid, env, tid, topo_nodes, service_bindings, bindings)
    gateway_live = bool(probe_stat.get("gateway_live"))

    for nid in daemon_ids:
        if any(str(x.get("node_id") or "") == nid and str(x.get("status") or "").upper() == "FAILED" for x in items if isinstance(x, dict)):
            continue
        topo_node = id_to_node.get(nid)
        if not isinstance(topo_node, dict):
            continue
        contract = _resolve_node_contract_for_topology_node(topo_node)
        probe_port = _resolve_topology_probe_port(topo_node, contract, None, None)
        probe_host = _resolve_orchestration_probe_host(pid, tid, topo_node, bindings)
        live = _probe_tcp_open(probe_host, probe_port) if probe_port > 0 else False
        for item in items:
            if isinstance(item, dict) and str(item.get("node_id") or "") == nid:
                item["status"] = "SUCCESS" if live else str(item.get("status") or "FAILED")

    _consolidate_runtime_agents_to_canonical(pid)
    item_fail = len([x for x in items if isinstance(x, dict) and str(x.get("status") or "").upper() != "SUCCESS"])
    game_ok = bool(gateway_live and item_fail == 0)
    fail = item_fail
    logs.append(
        {
            "ts": _now_iso(),
            "level": "info" if fail == 0 else "error",
            "node_id": "cluster",
            "message": f"集群级启动完成: game_ok={game_ok}, gateway_live={gateway_live}, live={probe_stat.get('live_count')}/{probe_stat.get('total')}, failed={fail}",
        }
    )
    return {"items": items, "logs": logs, "failed": fail, "gateway_live": gateway_live and game_ok}

def _save_agent_policy(policy: Dict[str, Any]) -> None:
    out = _default_agent_policy()
    if isinstance(policy, dict):
        for k in ("mtls_required", "lease_timeout_sec", "max_retries", "default_node_concurrency", "agent_online_fresh_sec"):
            if k in policy:
                out[k] = policy.get(k)
        if isinstance(policy.get("rollout"), dict):
            merged_rollout = out["rollout"]
            merged_rollout.update(policy.get("rollout"))
            out["rollout"] = merged_rollout
    _save_json_config(OPS_AGENT_POLICY_KEY, out, description="Ops Agent 策略配置")

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
    now = datetime.utcnow()
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
        age = (now - leased_at.replace(tzinfo=None)).total_seconds()
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
    probe = str(probe_status or "").strip().upper()
    if probe == "FAIL":
        return "OFFLINE"
    run = str(run_state or "").strip().upper()
    if run in ("RUNNING", "READY") and probe == "PASS":
        return "RUNNING"
    if run in ("STARTING", "STOPPING", "RESTARTING"):
        return run
    if run in ("STOPPED", "STOP"):
        return "STOPPED"
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
        "_ts": _parse_iso_ts(sample_time) or datetime.utcnow().timestamp(),
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
    cutoff = datetime.utcnow().timestamp() - max(60, int(window_sec or OPS_AGENT_METRIC_WINDOW_SEC))
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

def _enrich_preset_from_contract(preset: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(preset, dict):
        return preset
    pid = str(preset.get("preset_id") or "").strip()
    contract = _load_node_contract(pid) if pid else None
    out = dict(preset)
    if isinstance(contract, dict):
        if not out.get("default_port") and contract.get("default_port"):
            out["default_port"] = int(contract.get("default_port") or 0)
        if not out.get("probe_strategy") and contract.get("probe_strategy"):
            out["probe_strategy"] = str(contract.get("probe_strategy") or "")
        if contract.get("role") and str(out.get("role") or "") == "admin":
            out["role"] = str(contract.get("role") or out.get("role") or "")
        if contract.get("execution_model") in ("daemon", "worker"):
            out["daemon_profile"] = "external_daemon"
    return out

def _default_node_presets() -> List[Dict[str, Any]]:
    raw = [
        {
            "preset_id": "gateway_http",
            "name": "网关服务",
            "category": "application",
            "role": "gateway",
            "node_type": "gateway_server",
            "default_desc": "入口网关，承接流量并转发业务服务",
            "fixed_upstream_roles": ["edge", "lb", "admin", "ops"],
            "fixed_downstream_roles": ["business", "pressure", "auth"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "auth_service",
            "name": "认证服务",
            "category": "application",
            "role": "auth",
            "node_type": "auth_server",
            "default_desc": "用户认证与会话校验服务",
            "fixed_upstream_roles": ["gateway", "edge"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "business_main",
            "name": "游戏服务",
            "category": "application",
            "role": "business",
            "node_type": "business_server",
            "default_desc": "核心业务处理节点",
            "fixed_upstream_roles": ["gateway", "scheduler", "admin", "ops", "auth"],
            "fixed_downstream_roles": ["database", "cache", "mq", "search", "transport"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "ops_service",
            "name": "运维服务",
            "category": "application",
            "role": "ops",
            "node_type": "ops_server",
            "default_desc": "运维控制与诊断服务",
            "fixed_upstream_roles": ["gateway", "edge"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "tcp_transport",
            "name": "传输服务",
            "category": "network",
            "role": "transport",
            "node_type": "tcp_transport",
            "default_desc": "TCP 长连接传输节点",
            "fixed_upstream_roles": ["business", "gateway"],
            "fixed_downstream_roles": [],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "pressure_worker",
            "name": "压测服务",
            "category": "test",
            "role": "pressure",
            "node_type": "pressure_server",
            "default_desc": "压测流量与性能回归节点",
            "fixed_upstream_roles": ["gateway", "admin", "ops"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "redis_cache",
            "name": "Redis 缓存",
            "category": "infrastructure",
            "role": "cache",
            "node_type": "redis_cache",
            "default_desc": "缓存与会话存储节点",
            "fixed_upstream_roles": ["business", "gateway", "scheduler"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mongo_db",
            "name": "Mongo Database",
            "category": "database",
            "role": "database",
            "node_type": "mongo_database",
            "default_desc": "业务主存储数据库",
            "fixed_upstream_roles": ["business", "scheduler", "admin", "ops"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mq_kafka",
            "name": "消息队列",
            "category": "infrastructure",
            "role": "mq",
            "node_type": "mq_kafka",
            "default_desc": "异步事件队列",
            "fixed_upstream_roles": ["business", "gateway", "scheduler"],
            "fixed_downstream_roles": ["business", "analytics"],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "scheduler_job",
            "name": "调度服务",
            "category": "application",
            "role": "scheduler",
            "node_type": "scheduler_server",
            "default_desc": "定时任务与批处理节点",
            "fixed_upstream_roles": ["admin", "ops"],
            "fixed_downstream_roles": ["business", "database", "cache", "mq"],
            "daemon_profile": "external_daemon",
        },
    ]
    return [_enrich_preset_from_contract(x) for x in raw]

def _load_node_presets() -> List[Dict[str, Any]]:
    defaults = _default_node_presets()
    default_by_id = {str(p.get("preset_id") or "").strip(): p for p in defaults if str(p.get("preset_id") or "").strip()}
    raw = get_system_config(OPS_NODE_PRESETS_KEY, [])
    if isinstance(raw, list) and raw:
        out: List[Dict[str, Any]] = []
        seen: set = set()
        for item in raw:
            if isinstance(item, dict) and str(item.get("preset_id") or "").strip():
                pid = str(item.get("preset_id") or "").strip()
                if pid == "mysql_db":
                    continue
                seen.add(pid)
                out.append(_enrich_preset_from_contract(item))
        if out:
            if any(_text_has_mojibake(str(x.get("name") or "") + str(x.get("default_desc") or "")) for x in out):
                _save_json_config(OPS_NODE_PRESETS_KEY, defaults, description="Ops node preset catalog")
                return defaults
            missing_core = [pid for pid in _CORE_PRESET_IDS if pid not in seen]
            if missing_core:
                merged = list(out)
                for pid in missing_core:
                    preset = default_by_id.get(pid)
                    if preset:
                        merged.append(preset)
                _save_json_config(OPS_NODE_PRESETS_KEY, merged, description="Ops node preset catalog")
                return merged
            return out
    presets = _default_node_presets()
    _save_json_config(OPS_NODE_PRESETS_KEY, presets, description="Ops node preset catalog")
    return presets

def _load_daemon_state() -> Dict[str, Any]:
    raw = get_system_config(OPS_DAEMON_STATE_KEY, {})
    return raw if isinstance(raw, dict) else {}

def _save_daemon_state(state: Dict[str, Any]) -> None:
    _save_json_config(OPS_DAEMON_STATE_KEY, state if isinstance(state, dict) else {}, description="Ops daemon process state")

def _set_daemon_state(node_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    data = _load_daemon_state()
    nid = str(node_id or "").strip()
    cur = data.get(nid) if isinstance(data.get(nid), dict) else {}
    merged = dict(cur)
    merged.update(patch or {})
    merged["updated_at"] = _now_iso()
    data[nid] = merged
    _save_daemon_state(data)
    return merged

def _get_daemon_state(node_id: str) -> Dict[str, Any]:
    data = _load_daemon_state()
    nid = str(node_id or "").strip()
    return data.get(nid) if isinstance(data.get(nid), dict) else {}

def _is_process_running(pid: int) -> bool:
    value = int(pid or 0)
    if value <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, value)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return int(exit_code.value) == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(value, 0)
        return True
    except Exception:
        return False

def _preset_role_rules(role: str) -> Dict[str, List[str]]:
    r = str(role or "").strip().lower()
    up: set = set()
    down: set = set()
    for preset in _load_node_presets():
        if str(preset.get("role") or "").strip().lower() != r:
            continue
        for item in (preset.get("fixed_upstream_roles") or []):
            up.add(str(item))
        for item in (preset.get("fixed_downstream_roles") or []):
            down.add(str(item))
    return {"allowed_upstream_roles": sorted(up), "allowed_downstream_roles": sorted(down)}

def _connect_rule_meta(node: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(node or {})
    role = str(row.get("role") or "business").strip().lower()
    preset_rules = _preset_role_rules(role)
    row["role"] = role
    row["allowed_upstream_roles"] = list(preset_rules["allowed_upstream_roles"])
    row["allowed_downstream_roles"] = list(preset_rules["allowed_downstream_roles"])
    return row

def _link_role_block_reason(from_node: Dict[str, Any], to_node: Dict[str, Any]) -> str:
    frm = _connect_rule_meta(from_node or {})
    to = _connect_rule_meta(to_node or {})
    from_role = str(frm.get("role") or "").strip().lower()
    to_role = str(to.get("role") or "").strip().lower()
    allow_down = [str(x).strip().lower() for x in (frm.get("allowed_downstream_roles") or []) if str(x).strip()]
    allow_up = [str(x).strip().lower() for x in (to.get("allowed_upstream_roles") or []) if str(x).strip()]
    if allow_down and to_role and to_role not in allow_down:
        return f"「{from_role}」不允许连接「{to_role}」（可连下游：{', '.join(allow_down)}）"
    if allow_up and from_role and from_role not in allow_up:
        return f"「{to_role}」不接受来自「{from_role}」（可接受上游：{', '.join(allow_up)}）"
    return ""

def _can_link_nodes(from_node: Dict[str, Any], to_node: Dict[str, Any]) -> bool:
    return not _link_role_block_reason(from_node, to_node)

def _infer_node_kind(role: str, explicit_kind: str = "") -> str:
    ek = str(explicit_kind or "").strip().lower()
    if ek in ("entry", "standard", "terminal"):
        return ek
    r = str(role or "").strip().lower()
    if r in ("gateway", "edge"):
        return "entry"
    if r in ("database", "cache", "mq", "search", "transport", "tcp"):
        return "terminal"
    return "standard"

def _default_ports_for_kind(kind: str) -> Dict[str, List[Dict[str, Any]]]:
    k = _infer_node_kind("", kind)
    if k == "entry":
        return {"in": [], "out": [{"id": "out-1", "label": "out-1", "kind": "out", "max_links": 1}]}
    if k == "terminal":
        return {"in": [{"id": "in-1", "label": "in-1", "kind": "in", "max_links": 1}], "out": []}
    return {
        "in": [{"id": "in-1", "label": "in-1", "kind": "in", "max_links": 1}],
        "out": [{"id": "out-1", "label": "out-1", "kind": "out", "max_links": 1}],
    }

def _normalize_ports(kind: str, ports: Any) -> Dict[str, List[Dict[str, Any]]]:
    defaults = _default_ports_for_kind(kind)
    if not isinstance(ports, dict):
        return defaults

    out: Dict[str, List[Dict[str, Any]]] = {"in": [], "out": []}
    for side in ("in", "out"):
        rows = ports.get(side) if isinstance(ports.get(side), list) else []
        for idx, p in enumerate(rows):
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or f"{side}-{idx+1}").strip()
            if not pid:
                pid = f"{side}-{idx+1}"
            out[side].append(
                {
                    "id": pid,
                    "label": str(p.get("label") or pid),
                    "kind": side,
                    "max_links": 1,
                    "required": bool(p.get("required", False)),
                }
            )
    if kind == "entry":
        out["in"] = []
        if not out["out"]:
            out["out"] = defaults["out"]
    elif kind == "terminal":
        out["out"] = []
        if not out["in"]:
            out["in"] = defaults["in"]
    else:
        if not out["in"]:
            out["in"] = defaults["in"]
        if not out["out"]:
            out["out"] = defaults["out"]
    return out

def _default_topology_for_nodes(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    out_nodes: List[Dict[str, Any]] = []
    out_edges: List[Dict[str, Any]] = []
    total = max(1, len(nodes))
    cols = max(3, min(5, int((total ** 0.5) + 0.8)))
    for idx, n in enumerate(nodes):
        row = idx // cols
        col = idx % cols
        kind = _infer_node_kind(str(n.get("role") or ""), str(n.get("kind") or ""))
        out_nodes.append(
            {
                "id": str(n.get("id") or ""),
                "role": str(n.get("role") or "business"),
                "kind": kind,
                "desc": str(n.get("description") or ""),
                "bizStatus": str(n.get("biz_status") or "normal"),
                "owner": str(n.get("owner") or ""),
                "x": int(26 + col * 185),
                "y": int(26 + row * 132),
                "tags": n.get("tags") if isinstance(n.get("tags"), list) else [],
                "ui": {
                    "x": int(26 + col * 185),
                    "y": int(26 + row * 132),
                    "w": 220,
                    "h": 90,
                    "color": "#0f172a",
                    "locked": False,
                    "ports": _normalize_ports(kind, None),
                },
            }
        )
    for i in range(max(0, len(out_nodes) - 1)):
        frm = out_nodes[i].get("id")
        to = out_nodes[i + 1].get("id")
        if frm and to:
            out_edges.append(
                {
                    "id": f"edge-{uuid.uuid4().hex[:10]}",
                    "from": frm,
                    "to": to,
                    "from_port": "out-1",
                    "to_port": "in-1",
                    "type": "depends_on",
                    "note": "",
                }
            )
    return {"nodes": out_nodes, "edges": out_edges, "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}}}

def _load_topology(current_nodes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = current_nodes if isinstance(current_nodes, list) else _load_nodes()
    raw = get_system_config(OPS_TOPOLOGY_KEY, {})
    if isinstance(raw, dict):
        nodes = raw.get("nodes") if isinstance(raw.get("nodes"), list) else []
        edges = raw.get("edges") if isinstance(raw.get("edges"), list) else []
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    else:
        nodes, edges, meta = [], [], {}

    valid_ids = set([str(x.get("id") or "") for x in rows if isinstance(x, dict)])
    merged_nodes: List[Dict[str, Any]] = []
    seen = set()
    for item in nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid or nid not in valid_ids or nid in seen:
            continue
        seen.add(nid)
        merged_nodes.append(
            {
                "id": nid,
                "role": str(item.get("role") or "business"),
                "kind": _infer_node_kind(str(item.get("role") or "business"), str(item.get("kind") or "")),
                "desc": str(item.get("desc") or ""),
                "bizStatus": str(item.get("bizStatus") or "normal"),
                "owner": str(item.get("owner") or ""),
                "x": float(item.get("x") or 0),
                "y": float(item.get("y") or 0),
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "ui": item.get("ui") if isinstance(item.get("ui"), dict) else {},
            }
        )
    if len(merged_nodes) < len(valid_ids):
        default_topo = _default_topology_for_nodes(rows)
        for item in default_topo.get("nodes") or []:
            nid = str(item.get("id") or "")
            if nid and nid not in seen:
                merged_nodes.append(item)
                seen.add(nid)

    merged_edges: List[Dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to or frm not in valid_ids or to not in valid_ids:
            continue
        merged_edges.append(
            {
                "id": str(edge.get("id") or f"edge-{uuid.uuid4().hex[:10]}"),
                "from": frm,
                "to": to,
                "from_port": str(edge.get("from_port") or "out-1"),
                "to_port": str(edge.get("to_port") or "in-1"),
                "type": str(edge.get("type") or "depends_on"),
                "note": str(edge.get("note") or ""),
                "ui": edge.get("ui") if isinstance(edge.get("ui"), dict) else {},
            }
        )
    for n in merged_nodes:
        if not isinstance(n, dict):
            continue
        kind = _infer_node_kind(str(n.get("role") or ""), str(n.get("kind") or ""))
        n["kind"] = kind
        ui = n.get("ui") if isinstance(n.get("ui"), dict) else {}
        ui["ports"] = _normalize_ports(kind, ui.get("ports"))
        if "w" not in ui:
            ui["w"] = 220
        if "h" not in ui:
            ui["h"] = 90
        n["ui"] = ui
    viewport = meta.get("viewport") if isinstance(meta.get("viewport"), dict) else {}
    out_meta = {
        "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
        "version": int(meta.get("version") or 1),
        "updated_at": str(meta.get("updated_at") or ""),
    }
    return {"nodes": merged_nodes, "edges": merged_edges, "meta": out_meta}

def _save_topology(topology: Dict[str, Any]) -> Dict[str, Any]:
    nodes = topology.get("nodes") if isinstance(topology, dict) and isinstance(topology.get("nodes"), list) else []
    edges = topology.get("edges") if isinstance(topology, dict) and isinstance(topology.get("edges"), list) else []
    meta = topology.get("meta") if isinstance(topology, dict) and isinstance(topology.get("meta"), dict) else {}
    viewport = meta.get("viewport") if isinstance(meta.get("viewport"), dict) else {}
    payload = {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
            "version": int(meta.get("version") or 1),
            "updated_at": _now_iso(),
        },
        "updated_at": _now_iso(),
    }
    _save_json_config(OPS_TOPOLOGY_KEY, payload, description="Ops 平台拓扑配置")
    return payload

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


_AGENT_DETAIL_SERVICE_CACHE_MAX_AGE_SEC = 12.0

def _parse_agent_detail_include(raw: str) -> set:
    text = str(raw or "all").strip().lower()
    if not text or text == "all":
        return {"all"}
    return {part.strip() for part in text.split(",") if part.strip()}

def _agent_detail_include_wants(include_set: set, section: str) -> bool:
    return "all" in include_set or str(section or "").strip().lower() in include_set

def _service_runtime_cache_fresh(services: List[Dict[str, Any]], max_age_sec: float = _AGENT_DETAIL_SERVICE_CACHE_MAX_AGE_SEC) -> bool:
    if not services:
        return False
    now = _time_mod.time()
    for svc in services:
        if not isinstance(svc, dict):
            return False
        run = str(svc.get("run_state") or svc.get("status") or "").strip().upper()
        if run in ("STARTING", "STOPPING", "RESTARTING"):
            return False
        ts = _parse_iso_ts(svc.get("updated_at"))
        if ts <= 0 or (now - ts) > max(4.0, float(max_age_sec)):
            return False
    return True

def _probe_service_cache_fresh(max_age_sec: float = PROBE_INTERVAL_SEC * 3) -> bool:
    with _probe_cache_lock:
        cache_ts = float(_probe_cache_ts or 0.0)
    if cache_ts <= 0:
        return False
    return (_time_mod.time() - cache_ts) <= max(6.0, float(max_age_sec))

def _should_use_cached_service_state(services: List[Dict[str, Any]], force_live: bool = False) -> bool:
    if force_live:
        return False
    if any(_is_embedded_cluster_service(s) for s in (services or []) if isinstance(s, dict)):
        return False
    if _probe_service_cache_fresh():
        return True
    return _service_runtime_cache_fresh(services)

def _embedded_process_gateway_up(host: str = DEFAULT_LOOPBACK, timeout: float = 0.15) -> bool:
    probe_host = str(host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    return bool(
        _probe_tcp_open(probe_host, _RUNTIME_GATEWAY_PROBE_PORT, timeout=timeout)
        or _probe_tcp_open(probe_host, _RUNTIME_OPS_PROBE_PORT, timeout=timeout)
    )

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
    service_summary = {
        "total": len(services),
        "online": len([s for s in services if _effective_runtime_status(s.get("status"), s.get("run_state"), s.get("probe_status")) in ("ONLINE", "RUNNING", "READY")]),
        "abnormal": len([s for s in services if _effective_runtime_status(s.get("status"), s.get("run_state"), s.get("probe_status")) in ("DEGRADED", "ERROR", "FAILED", "OFFLINE", "STOPPED")]),
    }
    service_summary["stopped"] = max(0, service_summary["total"] - service_summary["online"] - service_summary["abnormal"])

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

def _gateway_blueprint_ports() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "in": [],
        "out": [
            {"id": "out-1", "label": "http:80", "kind": "out", "max_links": 8, "required": False},
            {"id": "out-2", "label": "http:443", "kind": "out", "max_links": 8, "required": False},
        ],
    }

def _commercial_framework_core_edges() -> List[Dict[str, Any]]:
    """各规模模板共享的控制面与数据层连线（preset 级，应用时按实例展开）。"""
    return [
        {"from": "gateway_http", "to": "auth_service", "from_port": "out-1", "note": "http:80", "mode": "each_to_all"},
        {"from": "gateway_http", "to": "ops_service", "from_port": "out-2", "note": "http:443", "mode": "each_to_all"},
        {"from": "auth_service", "to": "business_main", "note": "tcp:session", "mode": "each_to_all"},
        {"from": "ops_service", "to": "business_main", "note": "tcp:control", "mode": "each_to_all"},
        {"from": "business_main", "to": "redis_cache", "note": "structured-auto", "mode": "each_to_all"},
        {"from": "business_main", "to": "mongo_db", "note": "structured-auto", "mode": "each_to_all"},
    ]

def _normalize_blueprint_edge_rel(rel: Any) -> Optional[Dict[str, Any]]:
    if isinstance(rel, list) and len(rel) >= 2:
        mode = "round_robin"
        if len(rel) > 2 and isinstance(rel[2], str):
            mode = str(rel[2] or "round_robin").strip().lower()
        return {
            "from": str(rel[0] or "").strip(),
            "to": str(rel[1] or "").strip(),
            "mode": mode,
            "from_port": "out-1",
            "to_port": "in-1",
            "note": "blueprint-auto",
            "type": "depends_on",
        }
    if isinstance(rel, dict):
        frm = str(rel.get("from") or rel.get("from_preset") or "").strip()
        to = str(rel.get("to") or rel.get("to_preset") or "").strip()
        if not frm or not to:
            return None
        return {
            "from": frm,
            "to": to,
            "mode": str(rel.get("mode") or "round_robin").strip().lower(),
            "from_port": str(rel.get("from_port") or "out-1").strip(),
            "to_port": str(rel.get("to_port") or "in-1").strip(),
            "note": str(rel.get("note") or "blueprint-auto").strip(),
            "type": str(rel.get("type") or "depends_on").strip(),
        }
    return None

def _blueprint_edge_instance_pairs(source_ids: List[str], target_ids: List[str], mode: str) -> List[Tuple[str, str]]:
    if not source_ids or not target_ids:
        return []
    m = str(mode or "round_robin").strip().lower()
    pairs: List[Tuple[str, str]] = []
    if m == "each_to_all":
        for sid in source_ids:
            for tid in target_ids:
                pairs.append((sid, tid))
    elif m == "each_to_first":
        tid = target_ids[0]
        for sid in source_ids:
            pairs.append((sid, tid))
    elif m == "indexed":
        for idx, sid in enumerate(source_ids):
            if idx < len(target_ids):
                pairs.append((sid, target_ids[idx]))
    else:
        for idx, sid in enumerate(source_ids):
            pairs.append((sid, target_ids[idx % len(target_ids)]))
    return pairs

def _apply_topology_blueprint_edges(
    topo: Dict[str, Any],
    created_by_preset: Dict[str, List[str]],
    plan_edges: List[Any],
) -> None:
    if not isinstance(topo.get("edges"), list):
        topo["edges"] = []
    existing = topo["edges"]
    for rel in plan_edges or []:
        spec = _normalize_blueprint_edge_rel(rel)
        if not spec:
            continue
        s_nodes = created_by_preset.get(str(spec.get("from") or "")) or []
        t_nodes = created_by_preset.get(str(spec.get("to") or "")) or []
        if not s_nodes or not t_nodes:
            continue
        for sid, tid in _blueprint_edge_instance_pairs(s_nodes, t_nodes, str(spec.get("mode") or "round_robin")):
            dup = False
            for edge in existing:
                if not isinstance(edge, dict):
                    continue
                if (
                    str(edge.get("from") or "") == sid
                    and str(edge.get("to") or "") == tid
                    and str(edge.get("from_port") or "out-1") == str(spec.get("from_port") or "out-1")
                ):
                    dup = True
                    break
            if dup:
                continue
            existing.append(
                {
                    "id": f"edge-{uuid.uuid4().hex[:10]}",
                    "from": sid,
                    "to": tid,
                    "from_port": str(spec.get("from_port") or "out-1"),
                    "to_port": str(spec.get("to_port") or "in-1"),
                    "type": str(spec.get("type") or "depends_on"),
                    "note": str(spec.get("note") or "blueprint-auto"),
                }
            )


# 通用游戏服商业分层：入口 → 控制面 → 业务 → 传输(可选) → 异步/数据
_BLUEPRINT_LAYER_BY_PRESET: Dict[str, int] = {
    "gateway_http": 0,
    "auth_service": 1,
    "ops_service": 1,
    "business_main": 2,
    "tcp_transport": 3,
    "scheduler_job": 4,
    "mq_kafka": 4,
    "pressure_worker": 4,
    "redis_cache": 5,
    "mongo_db": 5,
}


def _layout_blueprint_nodes_by_layer(topo: Dict[str, Any], created_node_ids: List[str]) -> None:
    created_set = set(created_node_ids)
    created_nodes = [n for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "") in created_set]
    if not created_nodes:
        return
    layer_buckets: Dict[int, List[Dict[str, Any]]] = {}
    for node in created_nodes:
        preset_id = str(node.get("preset_id") or "").strip()
        layer = int(_BLUEPRINT_LAYER_BY_PRESET.get(preset_id, 2))
        layer_buckets.setdefault(layer, []).append(node)
    rank_gap = 268.0
    row_gap = 128.0
    base_x = 72.0
    base_y = 48.0
    for layer in sorted(layer_buckets.keys()):
        rows = layer_buckets[layer]
        x = base_x + float(layer) * rank_gap
        for idx, node in enumerate(rows):
            y = base_y + float(idx) * row_gap
            node["x"] = x
            node["y"] = y
            ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
            ui["x"] = x
            ui["y"] = y
            if "w" not in ui:
                ui["w"] = 220
            if "h" not in ui:
                ui["h"] = 90
            node["ui"] = ui

def _default_topology_blueprints() -> List[Dict[str, Any]]:
    core_edges = _commercial_framework_core_edges()
    return [
        {
            "blueprint_id": "minimal_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "最小框架",
            "desc": "通用游戏服最小栈：入口网关、认证、运维控制、业务逻辑、缓存与主库；适合单机/开发/小规模上线",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
            ],
            "edges": list(core_edges),
        },
        {
            "blueprint_id": "medium_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "中型框架",
            "desc": "通用中型架构：最小栈 + 业务水平扩展、异步消息与定时调度；适合常规商业服与多实例部署",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 2},
                {"preset_id": "scheduler_job", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": list(core_edges)
            + [
                {"from": "business_main", "to": "mq_kafka", "note": "async-events", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "business_main", "note": "batch-jobs", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "mongo_db", "note": "batch-read", "mode": "each_to_first"},
            ],
        },
        {
            "blueprint_id": "full_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "全量框架",
            "desc": "通用大型架构：多入口、控制面、多业务实例、实时传输、消息与调度；适合完整运维链路与生产扩展",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 2},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 3},
                {"preset_id": "tcp_transport", "count": 1},
                {"preset_id": "scheduler_job", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": list(core_edges)
            + [
                {"from": "business_main", "to": "tcp_transport", "note": "tcp:realtime", "mode": "each_to_all"},
                {"from": "business_main", "to": "mq_kafka", "note": "async-events", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "business_main", "note": "batch-jobs", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "mongo_db", "note": "batch-read", "mode": "each_to_first"},
            ],
        },
        {
            "blueprint_id": "pressure_test_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "压测框架",
            "desc": "压测专用（非生产）：入口网关 + 业务节点 + 压测 Worker；不含 Auth/Ops/缓存/数据库，与商业生产模板隔离",
            "framework_profile": "pressure_test",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "business_main", "count": 1},
                {"preset_id": "pressure_worker", "count": 1},
            ],
            "edges": [
                {"from": "gateway_http", "to": "business_main", "from_port": "out-1", "note": "http:load-entry", "mode": "each_to_all"},
                {"from": "pressure_worker", "to": "business_main", "note": "stress:qps", "mode": "each_to_all"},
            ],
        },
    ]

def _merge_topology_blueprints_with_defaults(stored: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    defaults = _default_topology_blueprints()
    default_by_id = {str(d.get("blueprint_id") or ""): d for d in defaults}
    stored_by_id = {
        str(x.get("blueprint_id") or ""): x
        for x in stored
        if isinstance(x, dict) and str(x.get("blueprint_id") or "").strip()
    }
    merged: List[Dict[str, Any]] = []
    changed = False
    for default_row in defaults:
        bid = str(default_row.get("blueprint_id") or "")
        old = stored_by_id.get(bid)
        old_ver = int(old.get("blueprint_version") or 0) if isinstance(old, dict) else 0
        new_ver = int(default_row.get("blueprint_version") or 0)
        if isinstance(old, dict) and old_ver >= new_ver:
            merged.append(old)
        else:
            merged.append(default_row)
            changed = True
    for bid, row in stored_by_id.items():
        if bid not in default_by_id:
            merged.append(row)
    if not stored:
        changed = True
    return merged, changed

def _load_topology_blueprints() -> List[Dict[str, Any]]:
    raw = get_system_config(OPS_TOPOLOGY_BLUEPRINTS_KEY, [])
    stored: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and str(item.get("blueprint_id") or "").strip():
                stored.append(item)
    merged, changed = _merge_topology_blueprints_with_defaults(stored)
    if changed or not stored:
        _save_json_config(OPS_TOPOLOGY_BLUEPRINTS_KEY, merged, description="Ops topology blueprints")
    return merged

def _is_external_daemon_node(node: Dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        return False
    profile = str(node.get("daemon_profile") or "").strip().lower()
    role = str(node.get("role") or "").strip().lower()
    return profile == "external_daemon" or role in ("database", "cache", "mongo", "redis")

def _probe_tcp_open(host: str, port: int, timeout: float = 0.8) -> bool:
    host_name = str(host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port_val = int(port or 0)
    except Exception:
        return False
    if port_val <= 0:
        return False
    try:
        with socket.create_connection((host_name, port_val), timeout=max(0.05, float(timeout))):
            return True
    except Exception:
        return False


_GS_LOG_LINE_RE = re.compile(
    r"^\[(?P<time>[^\]]+)\]\[(?P<level>INFO|WARN|WARNING|ERROR|DEBUG|TRACE|FATAL)\]\[(?P<category>[^\]]*)\]\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_GS_LOG_ERROR_HINT = re.compile(
    r"(?i)(\bfailed\b|\bfailure\b|\bexception\b|\berror\b|\bfatal\b|\bcrash\b|\bunable to\b|\bcannot access\b|\bcreateindexes failed\b)",
)
_GS_LOG_WARN_HINT = re.compile(
    r"(?i)(\bwarning\b|\bwarn\b|partial start|degraded|timeout|skipping protocol)",
)
_GS_LOG_SESSION_START = re.compile(
    r"(游戏服务器框架启动中|框架启动中|GameServer framework starting)",
    re.IGNORECASE,
)
_GS_LOG_LIFECYCLE_HIDE = re.compile(
    r"(注销协议|业务模块停止|已注销所有脚本|正在停止所有服务器|集群已安全退出|检测到配置变更，已重新加载)",
)
_SERVICE_LOG_HINTS: Dict[str, List[str]] = {
    "gateway-cn-1": ["gateway", "websocket"],
    "auth-cn-1": ["auth"],
    "game-cn-1": ["game", "router"],
    "ops-cn-1": ["ops", "http", "daemon", "cluster"],
    "mongo-db-cn-1": ["mongo", "mongosession", "mongod"],
    "redis-cache-cn-1": ["redis", "memurai"],
    "db-01": ["mongo", "mongod", "mongosession"],
}

def _daemon_log_path(node_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(node_id or "daemon").strip()) or "daemon"
    log_dir = os.path.join(DATA_DIR, "logs", "daemons")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"{safe}.log")

def _gameserver_log_artifact_paths() -> Tuple[str, str]:
    repo = _resolve_game_server_repo()
    log_dir = os.path.join(repo, "tools", "SmokeTest", "artifacts")
    return (
        os.path.join(log_dir, "server-live.out.log"),
        os.path.join(log_dir, "server-live.err.log"),
    )

def _is_gameserver_process_service_id(service_id: str) -> bool:
    return str(service_id or "").strip().lower() in _GAMESERVER_PROCESS_SERVICE_IDS

def _gameserver_service_port(service_id: str, node: Optional[Dict[str, Any]] = None) -> int:
    if isinstance(node, dict):
        port = int(node.get("port") or node.get("remote_game_server_port") or 0)
        if port > 0:
            return port
    return int(_GAMESERVER_DEFAULT_PORTS.get(str(service_id or "").strip().lower(), 0))

def _gameserver_tcp_probe_port(service_id: str, node: Optional[Dict[str, Any]] = None) -> int:
    sid = str(service_id or "").strip().lower()
    if sid in _GAMESERVER_TCP_PROBE_PORTS:
        return int(_GAMESERVER_TCP_PROBE_PORTS.get(sid) or 0)
    return 0


_gameserver_pid_cache: Dict[str, Tuple[float, int]] = {}
_GAMESERVER_PID_CACHE_TTL_SEC = 5.0

def _find_gameserver_pid_by_service(service_id: str) -> int:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return 0
    now = _time_mod.time()
    cached = _gameserver_pid_cache.get(sid)
    if cached and (now - float(cached[0] or 0.0)) < _GAMESERVER_PID_CACHE_TTL_SEC:
        return int(cached[1] or 0)
    needle = f"--servers={sid}"
    if os.name == "nt":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='GameServer.GameServerApp.exe'\" | "
                    "Select-Object ProcessId,CommandLine | ForEach-Object { "
                    f"if ($_.CommandLine -like '*{needle}*') {{ $_.ProcessId }} }}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            pid = 0
            for line in reversed((proc.stdout or "").splitlines()):
                text = line.strip()
                if text.isdigit():
                    pid = int(text)
                    break
            _gameserver_pid_cache[sid] = (now, pid)
            return pid
        except Exception:
            pass
        _gameserver_pid_cache[sid] = (now, 0)
        return 0
    try:
        proc = subprocess.run(
            ["bash", "-lc", "ps -eo pid=,args= | grep GameServer.GameServerApp | grep -F -- " + sid],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.strip().split(None, 1)
            if parts and parts[0].isdigit() and needle in (parts[1] if len(parts) > 1 else ""):
                pid = int(parts[0])
                _gameserver_pid_cache[sid] = (now, pid)
                return pid
    except Exception:
        pass
    _gameserver_pid_cache[sid] = (now, 0)
    return 0

def _is_gameserver_process_alive(service_id: str) -> bool:
    sid = str(service_id or "").strip().lower()
    state = _get_daemon_state(sid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    if pid > 0 and _is_process_running(pid):
        return True
    found = _find_gameserver_pid_by_service(sid)
    if found > 0 and _is_process_running(found):
        _set_daemon_state(sid, {"pid": found, "status": "RUNNING"})
        return True
    if found > 0:
        _set_daemon_state(sid, {"pid": 0, "status": "STOPPED"})
    return False

def _gameserver_service_live(
    service_id: str,
    node: Optional[Dict[str, Any]] = None,
    pid: int = 0,
    fast: bool = False,
    probe_host: str = "",
) -> bool:
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    port = _gameserver_tcp_probe_port(service_id, node)
    probe_timeout = 0.12 if fast else 0.35
    if port > 0:
        if not _probe_tcp_open(host, port, timeout=probe_timeout):
            return False
        if fast:
            return True
        active_pid = pid if pid > 0 and _is_process_running(pid) else _find_gameserver_pid_by_service(service_id)
        return bool(active_pid > 0 and _is_process_running(active_pid))
    if fast:
        state = _get_daemon_state(str(service_id or "").strip().lower())
        cached_pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
        return bool(cached_pid > 0 and _is_process_running(cached_pid))
    return _is_gameserver_process_alive(service_id)

def _reconcile_gameserver_daemon_state(service_id: str) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {}
    live = _gameserver_service_live(sid)
    state = _get_daemon_state(sid)
    cur_status = str(state.get("status") or "").strip().upper()
    pid = _find_gameserver_pid_by_service(sid) if live else 0
    if live:
        patch = {"status": "RUNNING", "pid": int(pid or state.get("pid") or 0), "last_error": ""}
    elif cur_status in ("STARTING", "STOPPING"):
        patch = {"status": "STOPPED", "pid": 0, "last_error": ""}
    else:
        patch = {"status": "STOPPED", "pid": 0}
    merged = _set_daemon_state(sid, patch)
    return merged

def _reconcile_all_gameserver_daemon_states() -> None:
    for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
        try:
            _reconcile_gameserver_daemon_state(sid)
        except Exception:
            pass

def _gameserver_service_log_path(repo: str, service_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "gameserver").strip()) or "gameserver"
    return os.path.join(repo, "tools", "SmokeTest", "artifacts", f"apk-site-service-{safe}.log")

def _gameserver_session_marker_path(repo: str = "", service_id: str = "") -> str:
    root = str(repo or _resolve_game_server_repo() or "").strip()
    sid = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "cluster").strip()) or "cluster"
    return os.path.join(root, "tools", "SmokeTest", "artifacts", f"gameserver-session-{sid}.json")

def _write_gameserver_session_marker(repo: str, pid: int, service_id: str = "") -> None:
    path = _gameserver_session_marker_path(repo, service_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(
            {"started_at": _now_iso(), "pid": int(pid), "epoch": time.time(), "service_id": str(service_id or "").strip()},
            fp,
        )

def _clear_gameserver_session_marker(repo: str = "", service_id: str = "") -> None:
    path = _gameserver_session_marker_path(repo, service_id)
    try:
        os.remove(path)
    except OSError:
        pass

def _read_gameserver_session_marker(repo: str = "", service_id: str = "") -> Dict[str, Any]:
    path = _gameserver_session_marker_path(repo, service_id)
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _find_pid_listening_on_port(port: int, host: str = "127.0.0.1") -> int:
    if port <= 0:
        return 0
    if os.name == "nt":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"$c = Get-NetTCPConnection -LocalAddress '{host}' -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | "
                    "Select-Object -First 1 -ExpandProperty OwningProcess; if ($c) { Write-Output $c }",
                ],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            for line in reversed((proc.stdout or "").splitlines()):
                text = line.strip()
                if text.isdigit():
                    return int(text)
        except Exception:
            pass
        try:
            proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=12, check=False)
            needle = f":{int(port)}"
            for line in (proc.stdout or "").splitlines():
                upper = line.upper()
                if "LISTENING" not in upper or needle not in line:
                    continue
                parts = line.split()
                if parts and parts[-1].isdigit():
                    return int(parts[-1])
        except Exception:
            pass
        return 0
    try:
        proc = subprocess.run(
            ["bash", "-lc", f"lsof -nP -iTCP:{int(port)} -sTCP:LISTEN -t 2>/dev/null | head -1"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        text = (proc.stdout or "").strip().splitlines()
        if text and text[0].strip().isdigit():
            return int(text[0].strip())
    except Exception:
        pass
    return 0

def _apply_service_runtime_after_action(
    service_id: str,
    *,
    status: str,
    live: bool,
    metrics: Optional[Dict[str, Any]] = None,
) -> None:
    st = str(status or "STOPPED").strip().upper()
    probe = "PASS" if live and st == "RUNNING" else ("FAIL" if st == "STOPPED" else "")
    fields: Dict[str, Any] = {"status": st, "run_state": st, "probe_status": probe}
    if metrics is not None:
        fields["metrics"] = metrics
    _update_canonical_service_runtime(service_id, **fields)

def _is_daemon_log_source(paths: List[str]) -> bool:
    if not paths:
        return False
    norm = [str(p or "").replace("\\", "/").lower() for p in paths]
    return all("/logs/daemons/" in p for p in norm)

def _gameserver_log_source_paths(current_session_only: bool = False, service_id: str = "") -> List[str]:
    """优先 UTF-8 结构化日志（ServerLogger 写入），再合并 nohup 控制台输出。"""
    repo = _resolve_game_server_repo()
    paths: List[str] = []
    sid = str(service_id or "").strip().lower()
    if sid in ("mongo-db-cn-1", "redis-cache-cn-1", "db-01"):
        daemon_path = _daemon_log_path(sid if sid != "db-01" else "mongo-db-cn-1")
        return [daemon_path] if os.path.isfile(daemon_path) else []
    def _cluster_log_sort_key(path: str) -> Tuple[float, str]:
        try:
            return (float(os.path.getmtime(path)), os.path.basename(path))
        except OSError:
            return (0.0, os.path.basename(path))

    all_cluster: List[str] = []
    if _is_gameserver_process_service_id(sid):
        inst_logs = os.path.join(_gameserver_instance_dir(repo, sid), "logs")
        if os.path.isdir(inst_logs):
            all_cluster.extend(
                os.path.join(inst_logs, name)
                for name in os.listdir(inst_logs)
                if name.startswith("cluster-") and name.endswith(".log")
            )
        cluster_paths = sorted(set(all_cluster), key=_cluster_log_sort_key, reverse=True)[:1]
        paths.extend(cluster_paths)
        launcher_log = _gameserver_service_log_path(repo, sid)
        if os.path.isfile(launcher_log):
            paths.append(launcher_log)
        return paths
    for sub in (
        os.path.join(repo, "game-server", "bin", "Debug", "logs"),
        os.path.join(repo, "game-server", "bin", "Release", "logs"),
    ):
        if not os.path.isdir(sub):
            continue
        all_cluster.extend(
            os.path.join(sub, name)
            for name in os.listdir(sub)
            if name.startswith("cluster-") and name.endswith(".log")
        )
    cluster_paths = sorted(set(all_cluster), key=_cluster_log_sort_key, reverse=True)[:1]
    if cluster_paths:
        paths.extend(cluster_paths)
        return paths
    out_path, err_path = _gameserver_log_artifact_paths()
    for p in (out_path, err_path):
        if os.path.isfile(p):
            paths.append(p)
    return paths

def _normalize_log_level(level: str) -> str:
    lv = str(level or "").strip().upper()
    if lv in ("WARN", "WARNING"):
        return "warn"
    if lv in ("ERROR", "FATAL"):
        return "error"
    if lv in ("DEBUG", "TRACE"):
        return "debug"
    return "info"

def _infer_log_level_from_text(level: str, raw_line: str, source_path: str = "") -> str:
    normalized = _normalize_log_level(level)
    if normalized in ("warn", "error", "debug"):
        return normalized
    text = str(raw_line or "")
    if _GS_LOG_ERROR_HINT.search(text):
        return "error"
    if _GS_LOG_WARN_HINT.search(text):
        return "warn"
    if str(source_path or "").endswith(".err.log"):
        return "error"
    return "info"

def _log_dedupe_key(raw_line: str) -> str:
    text = str(raw_line or "").strip()
    if not text:
        return ""
    stripped = re.sub(r"^\[[^\]]+\]", "", text, count=1).strip()
    stripped = re.sub(r"^\[(INFO|WARN|WARNING|ERROR|DEBUG|TRACE|FATAL)\]", "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"^\[[^\]]+\]", "", stripped, count=1).strip()
    return stripped.lower()

def _parse_gameserver_log_line(line: str, source_path: str = "") -> Dict[str, Any]:
    raw = str(line or "").rstrip("\n\r")
    if not raw.strip():
        return {"time": "", "level": "info", "category": "", "message": "", "raw": raw}
    match = _GS_LOG_LINE_RE.match(raw.strip())
    if not match:
        level = _infer_log_level_from_text("", raw, source_path)
        category = ""
        bracket = re.match(r"^\[(?P<cat>[^\]]+)\]", raw.strip())
        if bracket:
            category = bracket.group("cat")
        return {
            "time": "",
            "level": level,
            "category": category,
            "message": raw,
            "raw": raw,
        }
    level = _infer_log_level_from_text(match.group("level"), raw, source_path)
    return {
        "time": match.group("time"),
        "level": level,
        "category": match.group("category"),
        "message": match.group("message"),
        "raw": raw,
    }

def _service_log_line_matches(service_id: str, parsed: Dict[str, Any], raw_line: str) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return True
    hints = _SERVICE_LOG_HINTS.get(sid) or []
    if not hints:
        token = sid.split("-")[0]
        hints = [token] if token else []
    hay = f"{parsed.get('category') or ''} {parsed.get('message') or ''} {raw_line}".lower()
    if sid in hay:
        return True
    return any(h in hay for h in hints)

def _log_line_epoch(raw_line: str) -> float:
    text = str(raw_line or "")
    match = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", text)
    if not match:
        return 0.0
    token = match.group(1).replace(" ", "T")
    tail = text[match.end(): match.end() + 2]
    if tail.startswith("Z") or text[match.start(): match.end()].endswith("Z"):
        token += "Z"
    try:
        if token.endswith("Z"):
            return datetime.fromisoformat(token.replace("Z", "+00:00")).timestamp()
        return datetime.fromisoformat(token).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0

def _extract_line_iso_time(raw_line: str) -> str:
    text = str(raw_line or "")
    match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)", text)
    if match:
        return match.group(1)
    epoch = _log_line_epoch(text)
    if epoch > 0:
        return datetime.utcfromtimestamp(epoch).isoformat() + "Z"
    return ""


_DAEMON_SESSION_MARK = re.compile(
    r"daemon\s+(?:start|restart)(?:\s+begin|:?\s+skipped)",
    re.IGNORECASE,
)

def _slice_merged_from_daemon_session(merged: List[Tuple[int, str, str]]) -> Tuple[List[Tuple[int, str, str]], str]:
    start_idx = 0
    started_at = ""
    for idx, (_, line, _) in enumerate(merged):
        if _DAEMON_SESSION_MARK.search(line):
            start_idx = idx
            started_at = _extract_line_iso_time(line)
    if start_idx <= 0:
        return merged, started_at
    return merged[start_idx:], started_at

def _filter_merged_from_session_epoch(
    merged: List[Tuple[int, str, str]],
    epoch: float,
    *,
    grace_sec: float = 8.0,
) -> Tuple[List[Tuple[int, str, str]], str]:
    if epoch <= 0 or not merged:
        return merged, ""
    cutoff = float(epoch) - max(0.0, float(grace_sec))
    kept: List[Tuple[int, str, str]] = []
    trailing_blank = 0
    for item in merged:
        ts = _log_line_epoch(item[1])
        if ts >= cutoff:
            kept.append(item)
            trailing_blank = 0
        elif ts <= 0 and kept and trailing_blank < 2:
            kept.append(item)
            trailing_blank += 1
    if kept:
        return kept, datetime.utcfromtimestamp(float(epoch)).isoformat() + "Z"
    return merged, ""

def _slice_merged_from_current_session(merged: List[Tuple[int, str, str]]) -> Tuple[List[Tuple[int, str, str]], str]:
    start_idx = 0
    started_at = ""
    for idx, (_, line, _) in enumerate(merged):
        if _GS_LOG_SESSION_START.search(line):
            start_idx = idx
            match = _GS_LOG_LINE_RE.match(line.strip())
            if match:
                started_at = match.group("time")
    if start_idx <= 0:
        return merged, started_at
    return merged[start_idx:], started_at

def _should_hide_lifecycle_log_line(raw_line: str) -> bool:
    text = str(raw_line or "")
    if not text.strip():
        return True
    return bool(_GS_LOG_LIFECYCLE_HIDE.search(text))

def _read_text_file_lines(path: str) -> List[str]:
    if not path or not os.path.isfile(path):
        return []
    raw = b""
    try:
        with open(path, "rb") as fp:
            raw = fp.read()
    except Exception:
        return []
    if not raw:
        return []
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(encoding)
        except Exception:
            continue
        if encoding.startswith("utf") and text.count("\ufffd") > max(3, len(text) // 200):
            continue
        return text.splitlines(keepends=True)
    return raw.decode("utf-8", errors="replace").splitlines(keepends=True)

def _read_gameserver_service_logs(
    service_id: str = "",
    *,
    level: str = "all",
    query: str = "",
    tail: int = 400,
    since_offset: int = 0,
    current_session_only: bool = False,
    hide_lifecycle: bool = False,
) -> Dict[str, Any]:
    paths = _gameserver_log_source_paths(current_session_only=current_session_only, service_id=service_id)
    if not paths:
        return {
            "lines": [],
            "total": 0,
            "next_offset": 0,
            "sources": [],
            "message": "未找到 GameServer 日志文件，请先启动 GameServer",
        }

    merged: List[Tuple[int, str, str]] = []
    offset = 0
    seen_keys: set = set()
    daemon_source = _is_daemon_log_source(paths)
    has_cluster_logs = any("cluster-" in os.path.basename(p) for p in paths)
    for path in paths:
        try:
            for line in _read_text_file_lines(path):
                if has_cluster_logs and line.count("\ufffd") >= 4:
                    continue
                if not daemon_source and not current_session_only and not has_cluster_logs:
                    key = _log_dedupe_key(line)
                    if key and key in seen_keys:
                        continue
                    if key:
                        seen_keys.add(key)
                merged.append((offset, line, path))
                offset += len(line.encode("utf-8", errors="replace"))
        except Exception:
            continue

    session_started_at = ""
    if current_session_only and merged:
        if daemon_source:
            merged, session_started_at = _slice_merged_from_daemon_session(merged)
        else:
            marker = _read_gameserver_session_marker(service_id=service_id)
            marker_epoch = float(marker.get("epoch") or 0) if isinstance(marker, dict) else 0.0
            if marker_epoch > 0:
                merged, session_started_at = _filter_merged_from_session_epoch(merged, marker_epoch)
                if marker.get("started_at"):
                    session_started_at = str(marker.get("started_at") or session_started_at)
            else:
                merged, session_started_at = _slice_merged_from_current_session(merged)

    lv_filter = str(level or "all").strip().lower()
    q = str(query or "").strip().lower()
    repo = _resolve_game_server_repo()
    sid_lower = str(service_id or "").strip().lower()
    instance_root = _gameserver_instance_dir(repo, sid_lower).replace("\\", "/").lower() if sid_lower else ""
    skip_service_filter = bool(
        instance_root
        and _is_gameserver_process_service_id(sid_lower)
        and any(instance_root in str(p or "").replace("\\", "/").lower() for p in paths)
    )
    parsed_rows: List[Dict[str, Any]] = []
    for byte_offset, line, path in merged:
        if since_offset > 0 and byte_offset < since_offset:
            continue
        if hide_lifecycle and _should_hide_lifecycle_log_line(line):
            continue
        parsed = _parse_gameserver_log_line(line, path)
        if lv_filter not in ("", "all") and parsed.get("level") != lv_filter:
            continue
        if service_id and not daemon_source and not skip_service_filter and not _service_log_line_matches(service_id, parsed, line):
            continue
        hay = f"{parsed.get('raw') or ''} {parsed.get('category') or ''} {parsed.get('message') or ''}".lower()
        if q and q not in hay:
            continue
        parsed_rows.append({
            **parsed,
            "offset": byte_offset,
            "source": os.path.basename(path),
        })

    def _log_row_epoch(row: Dict[str, Any]) -> float:
        text = str(row.get("time") or row.get("raw") or "")
        match = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", text)
        if not match:
            return 0.0
        try:
            return datetime.fromisoformat(match.group(1).replace(" ", "T")).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return 0.0

    if parsed_rows:
        parsed_rows.sort(key=_log_row_epoch)
    if tail > 0 and len(parsed_rows) > tail:
        parsed_rows = parsed_rows[-tail:]

    next_offset = merged[-1][0] + len(merged[-1][1].encode("utf-8", errors="replace")) if merged else 0
    counts = {"info": 0, "warn": 0, "error": 0, "debug": 0}
    for row in parsed_rows:
        key = str(row.get("level") or "info")
        if key in counts:
            counts[key] += 1

    return {
        "lines": parsed_rows,
        "total": len(parsed_rows),
        "next_offset": next_offset,
        "sources": [os.path.basename(p) for p in paths],
        "counts": counts,
        "service_id": service_id,
        "session_started_at": session_started_at,
        "filters": {
            "current_session_only": bool(current_session_only),
            "hide_lifecycle": bool(hide_lifecycle),
        },
    }

def _local_service_status_snapshot(project_id: str, topology_node_id: str, service_id: str) -> Dict[str, Any]:
    node = _resolve_ops_dispatch_node(project_id, topology_node_id)
    if not node:
        return {"ok": False, "message": "topology node not found"}
    port = int(node.get("port") or node.get("remote_game_server_port") or 0)
    cs_map = _fetch_cluster_runtime_status()
    raw_svc = {
        "service_id": service_id,
        "node_id": topology_node_id,
        "service_port": port,
        "remote_game_server_port": port,
        "service_type": node.get("role") or node.get("service_type") or "",
    }
    resolved = _resolve_service_runtime_state(raw_svc, host="127.0.0.1", cluster_status=cs_map)
    metrics = _sample_local_control_metrics()
    st = str(resolved.get("run_state") or resolved.get("status") or "UNKNOWN").upper()
    labels = {
        "RUNNING": "运行中",
        "ONLINE": "运行中",
        "READY": "运行中",
        "STARTING": "启动中",
        "STOPPED": "已停止",
        "OFFLINE": "离线",
        "UNKNOWN": "未知",
    }
    return {
        "ok": True,
        "message": f"{service_id} 当前状态：{labels.get(st, st)}",
        "data": {
            "service_id": service_id,
            "node_id": topology_node_id,
            "status": resolved.get("status"),
            "run_state": resolved.get("run_state"),
            "status_label": labels.get(st, st),
            "probe_status": resolved.get("probe_status"),
            "probe_method": resolved.get("probe_method"),
            "cluster_state": resolved.get("cluster_state"),
            "port": port,
            "host": "127.0.0.1",
            "metrics": metrics,
            "sampled_at": _now_iso(),
        },
        "mode": "direct-local",
    }


_GAMESERVER_LAUNCH_GUARD = threading.Lock()
_GAMESERVER_LAUNCH_SLOTS: Dict[str, Dict[str, Any]] = {}
_GAMESERVER_LAUNCH_LOCK_TTL_SEC = 180.0

def _clear_gameserver_launch_slot(service_id: str) -> None:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return
    with _GAMESERVER_LAUNCH_GUARD:
        _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)

def _gameserver_launch_slot_active(service_id: str) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return False
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if not isinstance(slot, dict):
            return False
        if float(slot.get("until") or 0.0) <= time.monotonic():
            _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)
            return False
        return True

def _try_acquire_gameserver_launch_slot(service_id: str, ttl_sec: float = _GAMESERVER_LAUNCH_LOCK_TTL_SEC) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return False
    now = time.monotonic()
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if isinstance(slot, dict) and float(slot.get("until") or 0.0) > now:
            return False
        _GAMESERVER_LAUNCH_SLOTS[sid] = {
            "until": now + max(30.0, float(ttl_sec)),
            "thread": threading.current_thread().ident,
        }
        return True

def _release_gameserver_launch_slot(service_id: str) -> None:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return
    ident = threading.current_thread().ident
    with _GAMESERVER_LAUNCH_GUARD:
        slot = _GAMESERVER_LAUNCH_SLOTS.get(sid)
        if isinstance(slot, dict) and slot.get("thread") not in (None, ident):
            return
        _GAMESERVER_LAUNCH_SLOTS.pop(sid, None)

def _launch_gameserver_service(
    service_id: str,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    _reconcile_gameserver_daemon_state(sid)
    if _gameserver_service_live(sid, node, probe_host=host):
        live_pid = _find_gameserver_pid_by_service(sid) or int((_get_daemon_state(sid).get("pid") or 0))
        tcp_port = _gameserver_tcp_probe_port(sid, node)
        repo = _resolve_game_server_repo()
        log_path = _gameserver_service_log_path(repo, sid)
        try:
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(
                    f"[{_now_iso()}] daemon start skipped: {sid} already running "
                    f"pid={live_pid or 0}{', port ' + str(tcp_port) if tcp_port > 0 else ''}\n"
                )
        except Exception:
            pass
        return {
            "success": True,
            "message": f"{sid} 已在运行 (pid {live_pid or '-'}{', port ' + str(tcp_port) if tcp_port > 0 else ''})",
            "data": {"service_id": sid, "pid": live_pid, "already_running": True, "live": True, "log": log_path},
        }
    if _gameserver_launch_slot_active(sid) and not _gameserver_service_live(sid, node, probe_host=host):
        _clear_gameserver_launch_slot(sid)
    if not _try_acquire_gameserver_launch_slot(sid, ttl_sec=max(60.0, float(timeout_sec) + 30.0)):
        return {"success": False, "message": f"{sid} 启动正在进行中，请稍候再试"}
    try:
        return _launch_gameserver_service_impl(sid, reason, wait_ready, timeout_sec, node, probe_host=host)
    finally:
        _release_gameserver_launch_slot(sid)

def _launch_all_gameserver_services_in_order(
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    last: Dict[str, Any] = {"success": False, "message": "no services"}
    for sid in _GAMESERVER_START_ORDER:
        last = _launch_gameserver_service(sid, reason, wait_ready, timeout_sec)
        if not last.get("success"):
            return last
        time.sleep(0.8)
    return last

def _launch_local_game_server(
    service_id: str = "",
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 180,
    node: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    if sid:
        return _launch_gameserver_service(sid, reason, wait_ready, timeout_sec, node)
    return _launch_all_gameserver_services_in_order(reason, wait_ready, timeout_sec)

def _sync_gameserver_runtime_config(repo: str, cfg_dir: str) -> None:
    import shutil

    src_cfg = os.path.join(repo, "config")
    os.makedirs(cfg_dir, exist_ok=True)
    os.makedirs(os.path.join(cfg_dir, "config"), exist_ok=True)
    for name in ("cluster.json", "appsettings.json"):
        src = os.path.join(src_cfg, name)
        if not os.path.isfile(src):
            continue
        for dst in (os.path.join(cfg_dir, name), os.path.join(cfg_dir, "config", name)):
            try:
                if os.path.isfile(dst):
                    with open(src, "rb") as sfp, open(dst, "rb") as dfp:
                        if sfp.read() == dfp.read():
                            continue
                shutil.copy2(src, dst)
            except Exception:
                pass

def _gameserver_instance_dir(repo: str, service_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(service_id or "gameserver").strip()) or "gameserver"
    return os.path.join(repo, "tools", "SmokeTest", "artifacts", "instances", safe)

def _prepare_gameserver_instance(repo: str, service_id: str) -> Tuple[str, str]:
    """为每个服务准备独立运行目录，避免多进程争用同一份 cluster 日志。"""
    import shutil

    src_exe, src_dir = _resolve_gameserver_executable(repo)
    if not src_exe:
        return "", ""
    inst_dir = _gameserver_instance_dir(repo, service_id)
    inst_exe = os.path.join(inst_dir, os.path.basename(src_exe))
    src_stamp = str(int(os.path.getmtime(src_exe)))
    stamp_file = os.path.join(inst_dir, ".build_stamp")
    need_copy = not os.path.isfile(inst_exe)
    if os.path.isfile(stamp_file):
        try:
            with open(stamp_file, "r", encoding="utf-8") as fp:
                need_copy = need_copy or fp.read().strip() != src_stamp
        except Exception:
            need_copy = True
    else:
        need_copy = True
    if need_copy:
        if os.path.isdir(inst_dir):
            shutil.rmtree(inst_dir, ignore_errors=True)
        shutil.copytree(src_dir, inst_dir)
        os.makedirs(os.path.join(inst_dir, "logs"), exist_ok=True)
        with open(stamp_file, "w", encoding="utf-8") as fp:
            fp.write(src_stamp)
    _sync_gameserver_runtime_config(repo, inst_dir)
    return inst_exe, inst_dir

def _resolve_gameserver_executable(repo: str) -> Tuple[str, str]:
    names = ("GameServer.GameServerApp.exe", "GameServer.GameServerApp") if os.name == "nt" else (
        "GameServer.GameServerApp",
        "GameServer.GameServerApp.exe",
    )
    for config in ("Debug", "Release"):
        cfg_dir = os.path.join(repo, "game-server", "bin", config)
        for name in names:
            exe = os.path.join(cfg_dir, name)
            if os.path.isfile(exe):
                return exe, cfg_dir
        dll = os.path.join(cfg_dir, "GameServer.GameServerApp.dll")
        if os.path.isfile(dll):
            return dll, cfg_dir
    return "", ""

def _launch_gameserver_unified_all(
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    """Windows 本地 E2E/业务测试：单进程 --all 启动，避免 Partial 多实例无法 WS 登录路由。"""
    repo = _resolve_game_server_repo()
    exe, cfg_dir = _resolve_gameserver_executable(repo)
    if not exe:
        return {"success": False, "message": "未找到 GameServer.GameServerApp.exe，请先编译 game-server Debug/Release"}
    if _probe_tcp_open("127.0.0.1", 15050, timeout=0.35) and _ws_handshake_probe()[0]:
        gs_count = _count_gameserver_processes()
        if gs_count == 1:
            return {
                "success": True,
                "message": "GameServer --all 已在运行 (ws://127.0.0.1:15050/ws/)",
                "data": {"mode": "unified-all", "already_running": True, "live": True},
            }
    _stop_local_game_server()
    time.sleep(1.2)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "unified-all"
    log_path = os.path.join(repo, "game-server", "bin", "Debug", "logs", "ops-unified-all.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cmd = [exe, "--all", "--headless", "--headless-seconds=86400"]
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(f"\n[{_now_iso()}] unified-all launch reason={reason_note} cmd={' '.join(cmd)}\n")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cfg_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except Exception as ex:
        return {"success": False, "message": f"GameServer --all 启动失败: {ex}"}
    if not wait_ready:
        return {
            "success": True,
            "message": f"GameServer --all 已在后台启动 (pid {proc.pid})",
            "data": {"pid": int(proc.pid), "mode": "unified-all", "starting": True},
        }
    deadline = time.time() + max(25, int(timeout_sec))
    exit_code: Optional[int] = None
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        ws_ok, _ = _ws_handshake_probe()
        if ws_ok and _probe_tcp_open("127.0.0.1", 5504, timeout=0.35):
            for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
                _set_daemon_state(sid, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            return {
                "success": True,
                "message": f"GameServer --all 已就绪 (pid {proc.pid}, ws 15050, ops 5504)",
                "data": {"pid": int(proc.pid), "mode": "unified-all", "live": True, "log": log_path},
            }
        time.sleep(1.0)
    if exit_code is not None:
        return {"success": False, "message": f"GameServer --all 进程退出 code={exit_code}", "data": {"returncode": exit_code}}
    return {"success": False, "message": "GameServer --all 启动超时：15050/5504 未就绪", "data": {"pid": int(proc.pid)}}

def _should_use_unified_gameserver_all(app_ids: List[str], service_bindings: Dict[str, str]) -> bool:
    """Dev-only escape hatch; distributed multi-process is the default orchestration path."""
    if str(os.getenv("OPS_DEV_UNIFIED_GAMESERVER_ALL") or "").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    if os.name != "nt":
        return False
    gs_nodes = {
        str((service_bindings or {}).get(nid) or nid).strip().lower()
        for nid in (app_ids or [])
    }
    return bool(gs_nodes & set(_GAMESERVER_PROCESS_SERVICE_IDS))

def _wait_gameserver_tcp_port_free(
    port: int,
    timeout_sec: float = 20.0,
    probe_host: str = DEFAULT_LOOPBACK,
) -> bool:
    if port <= 0:
        return True
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    deadline = time.time() + max(1.0, float(timeout_sec))
    while time.time() < deadline:
        if not _probe_tcp_open(host, port, timeout=0.25):
            return True
        time.sleep(0.4)
    return not _probe_tcp_open(host, port, timeout=0.25)

def _latest_instance_cluster_log_path(repo: str, service_id: str) -> str:
    inst_logs = os.path.join(_gameserver_instance_dir(repo, service_id), "logs")
    if not os.path.isdir(inst_logs):
        return ""
    candidates = [
        os.path.join(inst_logs, name)
        for name in os.listdir(inst_logs)
        if name.startswith("cluster-") and name.endswith(".log")
    ]
    if not candidates:
        return ""
    try:
        return max(candidates, key=lambda p: os.path.getmtime(p))
    except Exception:
        return candidates[0]

def _sanitize_user_facing_text(text: str, max_len: int = 200) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\uFFFD]", "", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    noise = ("可用命令", "cluster>", "--servers=", "--all", "--gm", "windows-native launch")
    if any(token in cleaned for token in noise):
        return ""
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned

def _extract_cluster_error_hint(cluster_log_path: str, since_pos: int = 0) -> str:
    if not cluster_log_path or not os.path.isfile(cluster_log_path):
        return ""
    try:
        lines = _read_text_file_lines(cluster_log_path)
        chunk = "".join(lines)
        if since_pos > 0 and since_pos < len(chunk.encode("utf-8", errors="replace")):
            chunk = chunk[max(0, since_pos // 2):]
    except Exception:
        return ""
    hints: List[str] = []
    for line in chunk.splitlines():
        text = line.strip()
        if not text:
            continue
        upper = text.upper()
        if not any(token in text for token in ("[ERROR]", "异常", "失败", "FATAL", "IOException", "冲突")) and \
                not any(token in upper for token in ("[ERROR]", "[FATAL]", "FAIL")):
            continue
        parsed = _sanitize_user_facing_text(text, max_len=180)
        if parsed:
            hints.append(parsed)
    return hints[-1] if hints else ""

def _gameserver_service_launch_args(service_id: str) -> List[str]:
    sid = str(service_id or "").strip()
    # 当前 Windows 构建仅识别 --headless-seconds；裸 --headless 需重编译后才常驻。
    return [f"--servers={sid}", "--headless", "--headless-seconds=86400"]

def _format_gameserver_launch_failure(
    service_id: str,
    *,
    exit_code: Optional[int],
    live: bool,
    tcp_port: int,
    repo: str,
    log_path: str,
    cluster_log_pos: int = 0,
) -> str:
    sid = str(service_id or "").strip()
    parts: List[str] = []
    if exit_code is not None and int(exit_code) != 0:
        unsigned = int(exit_code) & 0xFFFFFFFF
        if unsigned in (3221225794, 3221225477):
            parts.append("进程初始化失败，常见原因是端口残留或实例文件损坏")
        else:
            parts.append(f"进程退出码 {exit_code}")
    if tcp_port > 0 and not live:
        parts.append(f"端口 {tcp_port} 未就绪")
    cluster_hint = _extract_cluster_error_hint(_latest_instance_cluster_log_path(repo, sid), cluster_log_pos)
    if cluster_hint:
        parts.append(cluster_hint)
    if not parts:
        parts.append("请打开「查看日志」查看本次启动详情")
    return f"{sid} 启动失败：{'；'.join(parts)}"

def _launch_gameserver_service_impl(
    service_id: str,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {"success": False, "message": f"不支持的 GameServer 服务: {service_id}"}
    port = _gameserver_service_port(sid, node)
    tcp_port = _gameserver_tcp_probe_port(sid, node)
    if _gameserver_service_live(sid, node, probe_host=host):
        live_pid = _find_gameserver_pid_by_service(sid) or int((_get_daemon_state(sid).get("pid") or 0))
        return {
            "success": True,
            "message": f"{sid} 已在运行 (pid {live_pid or '-'}{', port ' + str(tcp_port) if tcp_port > 0 else ''})",
            "data": {"service_id": sid, "port": port, "pid": live_pid, "already_running": True, "live": True},
        }
    stale_pid = _find_gameserver_pid_by_service(sid)
    if stale_pid > 0:
        _kill_tracked_pid(stale_pid)
        time.sleep(0.8)
    if tcp_port > 0:
        if _find_gameserver_pid_by_service(sid) > 0 or _gameserver_service_live(sid, node, probe_host=host):
            _stop_gameserver_service(sid, node, probe_host=host)
        if _probe_tcp_open(host, tcp_port, timeout=0.25) and not _wait_gameserver_tcp_port_free(
            tcp_port, timeout_sec=20.0, probe_host=host
        ):
            return {
                "success": False,
                "message": f"{sid} 启动失败：端口 {tcp_port} 仍被占用，请稍后重试",
                "data": {"service_id": sid, "port": port, "live": False},
            }

    repo = _resolve_game_server_repo()
    log_path = _gameserver_service_log_path(repo, sid)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    if os.name == "nt":
        try:
            return _launch_gameserver_service_windows(
                repo, sid, port, reason, wait_ready, timeout_sec, log_path, probe_host=host
            )
        except Exception as ex:
            return {"success": False, "message": f"启动 {sid} 失败: {ex}"}

    exe, cfg_dir = _resolve_gameserver_executable(repo)
    if not exe:
        script = os.path.join(repo, "scripts", "Start-GameServer.sh")
        return {"success": False, "message": f"未找到 GameServer 可执行文件或脚本: {script}"}
    return _launch_gameserver_service_posix(
        repo, sid, port, reason, wait_ready, timeout_sec, log_path, exe, cfg_dir, probe_host=host
    )

def _launch_gameserver_service_posix(
    repo: str,
    service_id: str,
    port: int,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    log_path: str = "",
    exe: str = "",
    cfg_dir: str = "",
    probe_host: str = DEFAULT_LOOPBACK,
) -> Dict[str, Any]:
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    server_args = _gameserver_service_launch_args(service_id)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "service-action"
    launch_exe = str(exe or "").strip()
    launch_cwd = str(cfg_dir or repo).strip()
    cmd: List[str]
    if launch_exe.endswith(".dll"):
        cmd = ["dotnet", launch_exe, *server_args]
    else:
        cmd = [launch_exe, *server_args]
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(
            f"\n[{_now_iso()}] posix launch service={service_id} reason={reason_note} "
            f"cmd={' '.join(cmd)}\n"
        )
        log_fp.flush()
    proc = subprocess.Popen(cmd, cwd=launch_cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _set_daemon_state(service_id, {"status": "STARTING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    if not wait_ready:
        return {
            "success": True,
            "message": f"{service_id} 已在后台启动",
            "data": {"pid": int(proc.pid), "service_id": service_id, "log": log_path, "exe": launch_exe, "starting": True},
        }
    tcp_port = _gameserver_tcp_probe_port(service_id)
    deadline = time.time() + max(20, int(timeout_sec))
    exit_code: Optional[int] = None
    ready_after = time.time() + 4.0
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            if tcp_port > 0:
                live = _probe_tcp_open(host, tcp_port, timeout=0.35)
            else:
                live = time.time() >= ready_after
        else:
            live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
        if live and (tcp_port > 0 or time.time() >= ready_after):
            _write_gameserver_session_marker(repo, int(proc.pid), service_id)
            _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
            return {
                "success": True,
                "message": f"{service_id} 已就绪 ({ready_msg})",
                "data": {"pid": int(proc.pid), "service_id": service_id, "port": port, "live": True, "log": log_path, "exe": launch_exe},
            }
        time.sleep(0.8)
    if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
        live = _probe_tcp_open(host, tcp_port, timeout=0.5) if tcp_port > 0 else True
    else:
        live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
    ok = bool(live and exit_code is None)
    if ok:
        _write_gameserver_session_marker(repo, int(proc.pid), service_id)
        _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    else:
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            _kill_tracked_pid(int(proc.pid))
        _set_daemon_state(service_id, {"status": "ERROR", "pid": 0, "last_action": "start", "last_error": "launch failed"})
    ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
    msg = f"{service_id} 已就绪 ({ready_msg})" if ok else f"{service_id} 启动失败"
    return {"success": ok, "message": msg, "data": {"returncode": exit_code, "service_id": service_id, "port": port, "live": live, "log": log_path, "exe": launch_exe}}

def _launch_gameserver_service_windows(
    repo: str,
    service_id: str,
    port: int,
    reason: str = "",
    wait_ready: bool = True,
    timeout_sec: int = 120,
    log_path: str = "",
    probe_host: str = DEFAULT_LOOPBACK,
) -> Dict[str, Any]:
    """Windows 原生启动单个 GameServer 节点，禁止走 bash/WSL。"""
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    exe, cfg_dir = _prepare_gameserver_instance(repo, service_id)
    if not exe:
        return {"success": False, "message": "未找到 GameServer.GameServerApp.exe，请先在 game-server 目录编译 Debug/Release"}
    server_args = _gameserver_service_launch_args(service_id)
    reason_note = re.sub(r"[^\x20-\x7E\u4e00-\u9fff]", "", str(reason or "")).strip() or "service-action"
    cluster_log_path = _latest_instance_cluster_log_path(repo, service_id)
    cluster_log_pos = 0
    try:
        if cluster_log_path and os.path.isfile(cluster_log_path):
            cluster_log_pos = os.path.getsize(cluster_log_path)
    except Exception:
        cluster_log_pos = 0
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(
            f"\n[{_now_iso()}] windows-native launch service={service_id} reason={reason_note} "
            f"exe={exe} args={' '.join(server_args)}\n"
        )
        log_fp.flush()
    proc = subprocess.Popen(
        [exe, *server_args],
        cwd=cfg_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    _set_daemon_state(service_id, {"status": "STARTING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    if not wait_ready:
        return {
            "success": True,
            "message": f"{service_id} 已在后台启动",
            "data": {"pid": int(proc.pid), "service_id": service_id, "log": log_path, "exe": exe, "starting": True},
        }
    tcp_port = _gameserver_tcp_probe_port(service_id)
    deadline = time.time() + max(20, int(timeout_sec))
    exit_code: Optional[int] = None
    ready_after = time.time() + 4.0
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            if tcp_port > 0:
                live = _probe_tcp_open(host, tcp_port, timeout=0.35)
            else:
                live = time.time() >= ready_after
        else:
            live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
        if live and (tcp_port > 0 or time.time() >= ready_after):
            _write_gameserver_session_marker(repo, int(proc.pid), service_id)
            _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
            ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
            return {
                "success": True,
                "message": f"{service_id} 已就绪 ({ready_msg})",
                "data": {"pid": int(proc.pid), "service_id": service_id, "port": port, "live": True, "log": log_path, "exe": exe},
            }
        time.sleep(0.8)
    if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
        live = _probe_tcp_open(host, tcp_port, timeout=0.5) if tcp_port > 0 else True
    else:
        live = _gameserver_service_live(service_id, pid=int(proc.pid), probe_host=host)
    ok = bool(live and exit_code is None)
    if ok:
        _write_gameserver_session_marker(repo, int(proc.pid), service_id)
        _set_daemon_state(service_id, {"status": "RUNNING", "pid": int(proc.pid), "last_action": "start", "log_path": log_path})
    else:
        if int(proc.pid) > 0 and _is_process_running(int(proc.pid)):
            _kill_tracked_pid(int(proc.pid))
        _set_daemon_state(service_id, {"status": "ERROR", "pid": 0, "last_action": "start", "last_error": "launch failed"})
    ready_msg = f"port {tcp_port}=PASS" if tcp_port > 0 else f"pid {int(proc.pid)} alive"
    msg = (
        f"{service_id} 已就绪 ({ready_msg})"
        if ok
        else _format_gameserver_launch_failure(
            service_id,
            exit_code=exit_code,
            live=live,
            tcp_port=tcp_port,
            repo=repo,
            log_path=log_path,
            cluster_log_pos=cluster_log_pos,
        )
    )
    return {
        "success": ok,
        "message": msg,
        "data": {
            "returncode": exit_code,
            "service_id": service_id,
            "port": port,
            "live": live,
            "log": log_path,
            "exe": exe,
        },
    }

def _stop_gameserver_service(
    service_id: str,
    node: Optional[Dict[str, Any]] = None,
    probe_host: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    host = str(probe_host or DEFAULT_LOOPBACK).strip() or DEFAULT_LOOPBACK
    if sid not in _GAMESERVER_PROCESS_SERVICE_IDS:
        return {"success": False, "message": f"不支持的 GameServer 服务: {service_id}"}
    _clear_gameserver_launch_slot(sid)
    port = _gameserver_service_port(sid, node)
    tcp_port = _gameserver_tcp_probe_port(sid, node)
    state = _get_daemon_state(sid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    if pid <= 0 or not _is_process_running(pid):
        pid = _find_gameserver_pid_by_service(sid)
    for _ in range(4):
        if pid > 0:
            _kill_tracked_pid(pid)
        pid = _find_gameserver_pid_by_service(sid)
        if pid <= 0 and tcp_port > 0:
            port_pid = _find_pid_listening_on_port(tcp_port)
            if port_pid > 4:
                pid = port_pid
        if pid <= 0:
            break
        time.sleep(0.4)
    deadline = time.time() + 15.0
    while time.time() < deadline:
        if not _gameserver_service_live(sid, node, probe_host=host):
            _set_daemon_state(sid, {"status": "STOPPED", "pid": 0, "last_action": "stop", "last_error": ""})
            _clear_gameserver_session_marker(service_id=sid)
            detail = f"port {tcp_port}" if tcp_port > 0 else "process"
            return {"success": True, "message": f"已停止 {sid} 独立进程 ({detail})"}
        time.sleep(0.4)
    return {"success": False, "message": f"{sid} 仍在运行，停止未完成"}

def _stop_all_gameserver_services() -> Dict[str, Any]:
    try:
        for sid in reversed(_GAMESERVER_START_ORDER):
            _stop_gameserver_service(sid)
        if os.name == "nt":
            for cmd in (
                ["taskkill", "/F", "/IM", "GameServer.GameServerApp.exe"],
                ["taskkill", "/F", "/T", "/FI", "IMAGENAME eq GameServer.GameServerApp.exe"],
            ):
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
        else:
            subprocess.call(["pkill", "-f", "GameServer.GameServerApp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for sid in _GAMESERVER_PROCESS_SERVICE_IDS:
            _clear_gameserver_session_marker(service_id=sid)
        open_ports = [p for p in _GAMESERVER_DEFAULT_PORTS.values() if _probe_tcp_open("127.0.0.1", p, timeout=0.25)]
        if open_ports:
            return {"success": False, "message": f"仍有 GameServer 端口在监听: {open_ports}"}
        return {"success": True, "message": "已停止全部 GameServer 独立进程"}
    except Exception as ex:
        return {"success": False, "message": f"停止 GameServer 失败: {ex}"}

def _stop_local_game_server() -> Dict[str, Any]:
    return _stop_all_gameserver_services()

def _daemon_probe_proto(node: Dict[str, Any]) -> str:
    role = str(node.get("role") or "").strip().lower()
    return "redis_ping" if role in ("cache", "redis") else "mongo_ping"

def _daemon_node_port(node: Dict[str, Any]) -> int:
    if not isinstance(node, dict):
        return 0
    port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or node.get("port") or 0)
    if port > 0:
        return port
    try:
        contract = _resolve_node_contract_for_topology_node(node)
        port = int(_resolve_topology_node_port(node, contract, None, None) or 0)
        if port > 0:
            return port
    except Exception:
        pass
    nid = str(node.get("id") or "").strip().lower()
    role = str(node.get("role") or "").strip().lower()
    if role in ("cache", "redis") or "redis" in nid:
        return 6379
    if role in ("database", "mongo") or "mongo" in nid:
        return 27017
    return 0

def _resolve_mongod_executable() -> str:
    if os.name != "nt":
        return ""
    try:
        import glob

        hits = sorted(glob.glob(r"C:\Program Files\MongoDB\Server\*\bin\mongod.exe"), reverse=True)
        if hits:
            return str(hits[0])
    except Exception:
        pass
    return ""

def _wait_daemon_port_open(node: Dict[str, Any], timeout_sec: float = 30.0) -> bool:
    port = _daemon_node_port(node)
    if port <= 0:
        return False
    proto = _daemon_probe_proto(node)
    deadline = time.time() + max(2.0, float(timeout_sec))
    while time.time() < deadline:
        if _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            return True
        time.sleep(0.5)
    return False

def _start_external_daemon_node(node: Dict[str, Any], act: str = "start") -> Dict[str, Any]:
    """本机守护进程启动：Windows 走服务/可执行文件，避免 Test-NetConnection 拖慢与误报成功。"""
    nid = str(node.get("id") or "")
    port = _daemon_node_port(node)
    role = str(node.get("role") or "").strip().lower()
    log_path = _daemon_log_path(nid)
    lines: List[str] = [f"[{_now_iso()}] daemon {act} begin port={port} role={role}"]

    if port > 0 and _probe_by_protocol("127.0.0.1", port, _daemon_probe_proto(node)).get("ok"):
        try:
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(f"[{_now_iso()}] daemon {act} skipped: port {port} already listening\n")
        except Exception:
            pass
        state = _set_daemon_state(nid, {"status": "RUNNING", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path})
        return {
            "success": True,
            "message": f"daemon already running on port {port}",
            "data": {"node_id": nid, "status": "RUNNING", "pid": 0, "state": state, "log_path": log_path},
        }

    if os.name == "nt":
        if role in ("database", "mongo") or port == 27017:
            db_dir = _gomeku_mongo_dbpath()
            os.makedirs(db_dir, exist_ok=True)
            svc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Start-Service MongoDB -ErrorAction SilentlyContinue; "
                    "if ((Get-Service MongoDB -ErrorAction SilentlyContinue).Status -eq 'Running') { exit 0 } else { exit 1 }",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            lines.append(f"Start-Service MongoDB rc={svc.returncode} out={(svc.stdout or '').strip()} err={(svc.stderr or '').strip()}")
            if svc.returncode != 0:
                mongod = _resolve_mongod_executable()
                if mongod:
                    subprocess.Popen(
                        [mongod, "--dbpath", db_dir, "--port", str(port or 27017), "--bind_ip", "127.0.0.1"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
                    lines.append(f"fallback mongod={mongod}")
        elif role in ("cache", "redis") or port == 6379:
            svc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$s = Get-Service Memurai,MemuraiDeveloper,Redis -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.Status -eq 'Stopped' } | Select-Object -First 1; "
                    "if ($s) { Start-Service $s.Name -ErrorAction SilentlyContinue }; "
                    "if ((Get-Service Memurai,MemuraiDeveloper -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.Status -eq 'Running' } | Select-Object -First 1)) { exit 0 } else { exit 1 }",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            lines.append(f"Start-Service redis/memurai rc={svc.returncode} out={(svc.stdout or '').strip()} err={(svc.stderr or '').strip()}")
    else:
        start_cmd = str(node.get("daemon_start_cmd") or "").strip()
        if start_cmd:
            subprocess.Popen(start_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            lines.append(f"shell cmd={start_cmd[:200]}")

    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write("\n".join(lines) + "\n")

    live = _wait_daemon_port_open(node, timeout_sec=30.0)
    if live:
        state = _set_daemon_state(
            nid,
            {"status": "RUNNING", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path},
        )
        return {
            "success": True,
            "message": f"daemon {act} ok, port {port} listening",
            "data": {"node_id": nid, "status": "RUNNING", "pid": 0, "state": state, "log_path": log_path},
        }

    state = _set_daemon_state(
        nid,
        {"status": "ERROR", "pid": 0, "last_error": f"port {port} not listening", "last_action": act, "log_path": log_path},
    )
    return {
        "success": False,
        "message": f"daemon {act} failed: port {port} not listening (请检查 MongoDB/Memurai 服务是否已安装并可启动)",
        "data": {"node_id": nid, "status": "ERROR", "state": state, "log_path": log_path},
    }

def _wait_daemon_port_closed(node: Dict[str, Any], timeout_sec: float = 12.0) -> bool:
    port = _daemon_node_port(node)
    if port <= 0:
        return True
    proto = _daemon_probe_proto(node)
    deadline = time.time() + max(1.0, float(timeout_sec))
    while time.time() < deadline:
        if not _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            return True
        time.sleep(0.5)
    return False

def _kill_tracked_pid(pid: int) -> bool:
    if pid <= 0 or not _is_process_running(pid):
        return False
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return proc.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False

def _daemon_cmd_looks_unix_only(cmd: str) -> bool:
    """Windows 上跳过明显只能在 Unix/macOS 执行的守护进程命令。"""
    text = str(cmd or "").strip().lower()
    if not text:
        return False
    unix_markers = (
        "/tmp/",
        "/opt/homebrew/",
        "/usr/local/",
        "mongosh ",
        "redis-cli -p",
        " --fork",
        " --daemonize",
        "bash -lc",
        "pkill ",
    )
    if any(marker in text for marker in unix_markers):
        return True
    if text.startswith("mongod ") and "--dbpath /tmp" in text:
        return True
    return False

def _stop_external_daemon_node(node: Dict[str, Any], act: str = "stop") -> Dict[str, Any]:
    """停止本机 Mongo/Redis 等守护节点：优先 stop_cmd，再杀残留 PID，以端口关闭为准。"""
    nid = str(node.get("id") or "")
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    state = _get_daemon_state(nid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    log_path = _daemon_log_path(nid)
    with open(log_path, "a", encoding="utf-8") as log_fp:
        log_fp.write(f"[{_now_iso()}] daemon {act} stop pid={pid} cmd={stop_cmd}\n")

    if stop_cmd and not (os.name == "nt" and _daemon_cmd_looks_unix_only(stop_cmd)):
        subprocess.call(stop_cmd, shell=True)

    _kill_tracked_pid(pid)

    port = _daemon_node_port(node)
    closed = _wait_daemon_port_closed(node, timeout_sec=12.0)
    if not closed and stop_cmd and not (os.name == "nt" and _daemon_cmd_looks_unix_only(stop_cmd)):
        subprocess.call(stop_cmd, shell=True)
        closed = _wait_daemon_port_closed(node, timeout_sec=8.0)

    if not closed and os.name == "nt":
        role = str(node.get("role") or "").strip().lower()
        kill_images: List[str] = []
        if role in ("database", "mongo") or port == 27017:
            kill_images = ["mongod.exe"]
        elif role in ("cache", "redis") or port == 6379:
            kill_images = ["memurai.exe", "redis-server.exe"]
        for image in kill_images:
            subprocess.run(
                ["taskkill", "/F", "/IM", image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        closed = _wait_daemon_port_closed(node, timeout_sec=8.0)

    if closed or port <= 0:
        state = _set_daemon_state(nid, {"status": "STOPPED", "pid": 0, "last_error": "", "last_action": act, "log_path": log_path})
        return {
            "success": True,
            "message": "daemon stopped",
            "data": {"node_id": nid, "status": "STOPPED", "pid": 0, "state": state, "log_path": log_path},
        }

    state = _set_daemon_state(
        nid,
        {"status": "ERROR", "pid": 0, "last_error": f"port {port} still listening", "last_action": act, "log_path": log_path},
    )
    return {
        "success": False,
        "message": f"daemon stop failed: port {port} still listening",
        "data": {"node_id": nid, "status": "ERROR", "state": state, "log_path": log_path},
    }

def _update_canonical_service_runtime(service_id: str, **fields: Any) -> None:
    sid = str(service_id or "").strip()
    if not sid:
        return
    reg = _load_agent_registry_v2()
    canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else None
    if not canonical:
        return
    services = canonical.get("services") if isinstance(canonical.get("services"), list) else []
    now = _now_iso()
    changed = False
    for svc in services:
        if not isinstance(svc, dict):
            continue
        if str(svc.get("service_id") or svc.get("node_id") or "").strip() != sid:
            continue
        for key, value in fields.items():
            if value is not None:
                svc[key] = value
        svc["updated_at"] = now
        changed = True
        break
    if changed:
        canonical["services"] = services
        canonical["updated_at"] = now
        reg[CANONICAL_LOCAL_AGENT_ID] = canonical
        _save_agent_registry_v2(reg)

def _windows_control_metrics() -> Dict[str, Any]:
    now = _now_iso()
    if os.name != "nt":
        return {"source": "runtime.sample", "updated_at": now}
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
                "$disk = Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\"; "
                "$mem = if ($os.TotalVisibleMemorySize -gt 0) { "
                "(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize) * 100 } else { 0 }; "
                "$dsk = if ($disk -and $disk.Size -gt 0) { (($disk.Size - $disk.FreeSpace) / $disk.Size) * 100 } else { 0 }; "
                "[pscustomobject]@{cpu=[double]$cpu; mem=[double]$mem; disk=[double]$dsk} | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            return {"source": "runtime.sample", "updated_at": now}
        payload = json.loads(raw)
        return {
            "cpu_percent": round(float(payload.get("cpu") or 0.0), 1),
            "mem_percent": round(float(payload.get("mem") or 0.0), 1),
            "disk_percent": round(float(payload.get("disk") or 0.0), 1),
            "source": "runtime.sample",
            "updated_at": now,
        }
    except Exception:
        return {"source": "runtime.sample", "updated_at": now}

def _fallback_local_control_metrics() -> Dict[str, Any]:
    """psutil 不可用时的轻量采样。"""
    now = _now_iso()
    if os.name == "nt":
        sample = _windows_control_metrics()
        if any(sample.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent")):
            return sample
    out: Dict[str, Any] = {"source": "runtime.sample", "updated_at": now}
    try:
        if sys.platform == "darwin":
            load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
            cores = max(1, os.cpu_count() or 1)
            out["cpu_percent"] = round(min(100.0, (float(load) / float(cores)) * 100.0), 1)
        proc = subprocess.run(["df", "-k", "/"], capture_output=True, text=True, timeout=2)
        if proc.returncode == 0:
            lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
            if len(lines) >= 2:
                parts = lines[-1].split()
                if len(parts) >= 5 and parts[-2].endswith("%"):
                    out["disk_percent"] = round(float(parts[-2].rstrip("%")), 1)
    except Exception:
        pass
    return out

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

def _refresh_services_live_state(
    services: List[Dict[str, Any]],
    host: str = "127.0.0.1",
    project_id: str = "",
    cluster_status: Optional[Dict[str, str]] = None,
    agent: Optional[Dict[str, Any]] = None,
    fast_probe: bool = False,
    probe_timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    sample = {} if fast_probe else _sample_local_control_metrics()
    cs_map = cluster_status if isinstance(cluster_status, dict) else {}
    if not cs_map and project_id and not fast_probe:
        try:
            cs_map = _fetch_cluster_runtime_status_cached(_agents_v2_for_project(project_id))
        except Exception:
            cs_map = {}
    pt = float(probe_timeout) if probe_timeout is not None else (0.12 if fast_probe else 0.35)
    rows = [raw for raw in (services or []) if isinstance(raw, dict)]

    def _probe_one(raw: Dict[str, Any]) -> Dict[str, Any]:
        svc_host = _resolve_agent_probe_host(agent, raw) if agent else host
        svc = _resolve_service_runtime_state(
            raw,
            host=svc_host,
            cluster_status=cs_map,
            probe_timeout=pt,
            fast_probe=fast_probe,
        )
        if not fast_probe:
            metrics = svc.get("metrics") if isinstance(svc.get("metrics"), dict) else {}
            merged = dict(metrics)
            if str(svc.get("probe_status") or "").upper() == "PASS":
                for key in ("cpu_percent", "mem_percent", "disk_percent", "source", "updated_at"):
                    if sample.get(key) is not None and merged.get(key) is None:
                        merged[key] = sample.get(key)
            if merged:
                svc["metrics"] = merged
            svc["updated_at"] = str(svc.get("updated_at") or sample.get("updated_at") or _now_iso())
        return svc

    if len(rows) <= 1:
        return [_probe_one(raw) for raw in rows]
    out: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(rows))) as pool:
        for svc in pool.map(_probe_one, rows):
            out.append(svc)
    return out

def _execute_canonical_service_action(
    project_id: str,
    topology_node_id: str,
    service_id: str,
    action: str,
    operator: str,
    reason: str,
    ticket_id: str,
    body_payload: Dict[str, Any],
) -> Dict[str, Any]:
    act = str(action or "").strip().lower()
    node = _resolve_ops_dispatch_node(project_id, topology_node_id)
    if not node:
        return {"ok": False, "message": "topology node not found", "mode": "direct"}

    if _is_external_daemon_node(node):
        result = _ops_platform_daemon_action(node, act, reason, ticket_id, operator)
        ok = bool(result.get("success"))
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if not ok:
            return {
                "ok": False,
                "message": str(result.get("message") or "daemon action failed"),
                "data": data,
                "mode": "daemon",
            }
        if ok:
            contract = _resolve_node_contract_for_topology_node(node if isinstance(node, dict) else {})
            port = _resolve_topology_node_port(node if isinstance(node, dict) else {}, contract, None, None)
            role = str(node.get("role") or contract.get("role") or "").strip().lower()
            probe_proto = str(contract.get("probe_strategy") or "tcp").strip().lower()
            if role in ("cache", "redis"):
                probe_proto = "redis_ping"
            elif role in ("database", "mongo"):
                probe_proto = "mongo_ping"
            live = False
            if port > 0:
                for attempt in range(24 if act in ("start", "restart") else 1):
                    probe = _probe_by_protocol("127.0.0.1", port, probe_proto)
                    live = bool(probe.get("ok"))
                    if live or act not in ("start", "restart"):
                        break
                    time.sleep(0.5)
            if act == "stop":
                st = "STOPPED"
            elif live:
                st = "RUNNING"
            elif act in ("start", "restart"):
                st = "STARTING"
            else:
                st = "STOPPED"
            _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="PASS" if live else "FAIL")
        return {"ok": ok, "message": str(result.get("message") or ""), "data": result.get("data") or {}, "mode": "daemon"}

    if act == "status":
        return _local_service_status_snapshot(project_id, topology_node_id, service_id)

    if act == "logs":
        log_payload = _read_gameserver_service_logs(service_id, tail=500)
        return {
            "ok": True,
            "message": f"已读取 GameServer 日志（{log_payload.get('total', 0)} 条）",
            "data": log_payload,
            "mode": "direct-local",
        }

    if _is_gameserver_process_service_id(service_id) and act in ("start", "stop", "restart"):
        _reconcile_gameserver_daemon_state(service_id)
        port = _gameserver_service_port(service_id, node)
        if act == "restart":
            stop_res = _stop_gameserver_service(service_id, node)
            if not stop_res.get("success"):
                return {
                    "ok": False,
                    "message": str(stop_res.get("message") or "restart stop failed"),
                    "data": {},
                    "mode": "direct-local-process",
                }
            act = "start"
        if act == "stop":
            stop_res = _stop_gameserver_service(service_id, node)
            ok = bool(stop_res.get("success"))
            metrics = _sample_local_control_metrics()
            if ok:
                _apply_service_runtime_after_action(service_id, status="STOPPED", live=False, metrics=metrics)
            else:
                _update_canonical_service_runtime(
                    service_id,
                    status="ERROR",
                    run_state="ERROR",
                    probe_status="FAIL",
                    last_action="stop",
                    metrics=metrics,
                )
            canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
            if isinstance(canonical, dict):
                _append_realtime_agent_sample(canonical)
            return {
                "ok": ok,
                "message": str(stop_res.get("message") or ("已停止" if ok else "停止失败")),
                "data": {"service_id": service_id, "port": port, "status": "STOPPED" if ok else "ERROR", "last_action": "stop"},
                "mode": "direct-local-process",
            }
        launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
        ok = bool(launch.get("success"))
        live = bool((launch.get("data") or {}).get("live")) or _gameserver_service_live(service_id, node)
        metrics = _sample_local_control_metrics()
        if ok:
            st = "RUNNING" if live else "STARTING"
            _apply_service_runtime_after_action(service_id, status=st, live=live, metrics=metrics)
            _update_canonical_service_runtime(service_id, last_action="start")
        else:
            _update_canonical_service_runtime(
                service_id,
                status="ERROR",
                run_state="ERROR",
                probe_status="FAIL",
                last_action="start",
                metrics=metrics,
            )
        canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
        if isinstance(canonical, dict):
            _append_realtime_agent_sample(canonical)
        return {
            "ok": ok,
            "message": str(launch.get("message") or ("启动成功" if ok else "启动失败")),
            "data": {
                **(launch.get("data") if isinstance(launch.get("data"), dict) else {}),
                "status": "RUNNING" if ok and live else ("STARTING" if ok else "ERROR"),
                "last_action": "start",
            },
            "mode": "direct-local-process",
        }

    ops_node = _resolve_ops_dispatch_node(project_id, "ops-cn-1") or node
    map_action = {"start": "start", "stop": "stop", "restart": "restart", "status": "status", "probe": "health_check", "logs": "log_tail"}.get(act, act)
    result = ops_gateway.execute_platform_action(
        ops_node,
        action_type=map_action,
        target=service_id,
        payload=body_payload,
        actor=operator,
        reason=reason,
        ticket_id=ticket_id,
        dry_run=False,
    )
    ok = bool(result.get("success"))

    if not ok and act == "start" and _is_gameserver_process_service_id(service_id):
        launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
        if launch.get("success"):
            live = bool((launch.get("data") or {}).get("live")) or _gameserver_service_live(service_id, node)
            ok = True
            result = {
                "success": True,
                "message": str(launch.get("message") or ("服务已在运行" if live else "服务启动中")),
                "data": dict(launch.get("data") or {}, starting=not live),
            }
        else:
            result = launch

    if not ok and act in ("stop", "restart") and _is_gameserver_process_service_id(service_id):
        stop_res = _stop_gameserver_service(service_id, node)
        if stop_res.get("success"):
            ok = act == "stop"
            result = stop_res
            if act == "restart":
                launch = _launch_gameserver_service(service_id, reason, wait_ready=True, timeout_sec=120, node=node)
                ok = bool(launch.get("success"))
                result = launch
        else:
            result = stop_res

    if not ok and act == "stop":
        port = int(node.get("port") or node.get("remote_game_server_port") or 0)
        if port > 0:
            time.sleep(1.2)
            if not _probe_tcp_open("127.0.0.1", port):
                ok = True
                result = {"success": True, "message": "服务端口已释放", "data": {"status": "STOPPED"}}

    if ok:
        live = _gameserver_service_live(service_id, node) if _is_gameserver_process_service_id(service_id) else (
            _probe_tcp_open("127.0.0.1", int(node.get("port") or node.get("remote_game_server_port") or 0))
            if int(node.get("port") or node.get("remote_game_server_port") or 0) > 0
            else bool((result.get("data") or {}).get("starting"))
        )
        st = "STARTING" if (result.get("data") or {}).get("starting") else ("RUNNING" if act != "stop" and live else ("STOPPED" if act == "stop" else "RUNNING"))
        metrics = _sample_local_control_metrics()
        _apply_service_runtime_after_action(service_id, status=st, live=live, metrics=metrics)
        canonical = _load_agent_registry_v2().get(CANONICAL_LOCAL_AGENT_ID)
        if isinstance(canonical, dict):
            _append_realtime_agent_sample(canonical)

    return {
        "ok": ok,
        "message": str(result.get("message") or ("success" if ok else "service action failed")),
        "data": result.get("data") if isinstance(result.get("data"), dict) else {},
        "mode": "direct",
    }

def _ops_platform_daemon_action(node: Dict[str, Any], action: str, reason: str, ticket_id: str, operator: str) -> Dict[str, Any]:
    nid = str(node.get("id") or "")
    act = str(action or "").strip().lower()
    server_id = str(node.get("server_id") or "").strip()
    role = str(node.get("role") or "").strip()
    start_cmd = str(node.get("daemon_start_cmd") or "").strip()
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    state = _get_daemon_state(nid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0
    local_daemon = _is_external_daemon_node(node)

    # Prefer native Ops API path in distributed deployment.
    if server_id and act in ("start", "stop", "restart", "status") and not local_daemon:
        map_action = {"start": "start", "stop": "stop", "restart": "restart", "status": "status"}.get(act, "status")
        result = ops_gateway.execute_platform_action(
            node,
            action_type=map_action,
            target=server_id,
            payload={},
            actor=operator,
            reason=reason,
            ticket_id=ticket_id,
            dry_run=False,
        )
        ok = bool(result.get("success"))
        if ok:
            new_status = "RUNNING" if act in ("start", "restart", "status") else "STOPPED"
            _set_daemon_state(nid, {"status": new_status, "last_error": "", "last_action": act})
        else:
            _set_daemon_state(nid, {"status": "ERROR", "last_error": str(result.get("message") or ""), "last_action": act})
        return result

    if act == "status":
        port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or 0)
        probe_role = str(node.get("role") or role or "").strip().lower()
        proto = "redis_ping" if probe_role in ("cache", "redis") else "mongo_ping"
        port_live = bool(_probe_by_protocol("127.0.0.1", port, proto).get("ok")) if port > 0 else False
        proc_live = _is_process_running(pid) if pid > 0 else False
        if port_live:
            now_status = "RUNNING"
            state = _set_daemon_state(nid, {"status": now_status, "last_error": "", "last_action": "status", "pid": pid if proc_live else 0})
        elif proc_live:
            now_status = "RUNNING"
        elif pid > 0:
            now_status = "CRASHED"
            state = _set_daemon_state(nid, {"status": now_status, "last_error": "process not alive", "pid": 0, "last_action": "status"})
        else:
            now_status = str(state.get("status") or "ADDED")
        return {"success": True, "message": "daemon status (local fallback)", "data": {"node_id": nid, "status": now_status, "pid": pid, "state": state}}

    port = int(node.get("daemon_port") or (node.get("ui") or {}).get("remote", {}).get("port") or 0)
    if act in ("start", "restart") and port > 0:
        role = str(node.get("role") or "").strip().lower()
        proto = "redis_ping" if role in ("cache", "redis") else "mongo_ping"
        if _probe_by_protocol("127.0.0.1", port, proto).get("ok"):
            log_path = _daemon_log_path(nid)
            with open(log_path, "a", encoding="utf-8") as log_fp:
                log_fp.write(f"[{_now_iso()}] daemon {act} skipped: port {port} already listening\n")
            state = _set_daemon_state(nid, {"status": "RUNNING", "pid": pid or 0, "last_error": "", "last_action": act, "log_path": log_path})
            return {
                "success": True,
                "message": f"daemon already running on port {port}",
                "data": {"node_id": nid, "status": "RUNNING", "pid": pid, "state": state, "log_path": log_path},
            }

    if act == "restart":
        stop_res = _stop_external_daemon_node(node, "restart")
        if not stop_res.get("success"):
            return stop_res
        act = "start"
        state = _get_daemon_state(nid)
        pid = 0

    if act in ("start", "restart") and (local_daemon or start_cmd):
        return _start_external_daemon_node(node, act)

    if act == "stop":
        return _stop_external_daemon_node(node, "stop")

    return {"success": False, "message": "no daemon control profile configured for this node", "data": {"node_id": nid, "role": role}}

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

def _run_flow_step(node: Dict[str, Any], step: Dict[str, Any]) -> Dict[str, Any]:
    action_type = str(step.get("action_type") or "").strip()
    target = str(step.get("target") or node.get("server_id") or "").strip()
    ticket_id = str(step.get("ticket_id") or "OPS-FLOW").strip()
    reason = str(step.get("reason") or "flow step").strip()
    payload = step.get("payload") if isinstance(step.get("payload"), dict) else {}
    dry_run = bool(step.get("dry_run"))
    operator = str(session.get("user") or "intranet-ops")
    return ops_gateway.execute_platform_action(
        node,
        action_type=action_type,
        target=target,
        payload=payload,
        actor=operator,
        reason=reason,
        ticket_id=ticket_id,
        dry_run=dry_run,
    )

def _ops_topology_meta_structured(topo: Dict[str, Any]) -> None:
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    spacing = meta.get("layout_spacing") if isinstance(meta.get("layout_spacing"), dict) else None
    spacing_customized = bool(meta.get("layout_spacing_customized"))
    meta["layout_mode"] = "structured"
    meta["updated_at"] = _now_iso()
    if spacing is not None:
        meta["layout_spacing"] = _normalize_layout_spacing(spacing)
    if spacing_customized:
        meta["layout_spacing_customized"] = True
    topo["meta"] = meta

def _ops_topology_node_map(topo: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(n.get("id") or ""): n for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "")}

def _ops_topology_edge_list(topo: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = edges
    return edges

def _effective_node_kind(node: Dict[str, Any]) -> str:
    role = str((node or {}).get("role") or "business")
    explicit = str((node or {}).get("kind") or "").strip().lower()
    if explicit in ("entry", "standard", "terminal"):
        return explicit
    return _infer_node_kind(role, "")

def _ops_port_max(port: Dict[str, Any]) -> int:
    try:
        return max(1, int(port.get("max_links") or 1))
    except Exception:
        return 1

def _ops_port_link_count(edges: List[Dict[str, Any]], node_id: str, side: str, port_id: str) -> int:
    if side == "out":
        return len([e for e in edges if isinstance(e, dict) and str(e.get("from") or "") == node_id and str(e.get("from_port") or "out-1") == port_id])
    return len([e for e in edges if isinstance(e, dict) and str(e.get("to") or "") == node_id and str(e.get("to_port") or "in-1") == port_id])

def _ops_next_port_id(ports: List[Dict[str, Any]], side: str) -> str:
    prefix = "out" if side == "out" else "in"
    used = {str(p.get("id") or "") for p in ports if isinstance(p, dict)}
    idx = 1
    while f"{prefix}-{idx}" in used:
        idx += 1
    return f"{prefix}-{idx}"

def _ops_ensure_free_port(topo_node: Dict[str, Any], side: str, edges: List[Dict[str, Any]]) -> str:
    node_id = str(topo_node.get("id") or "")
    kind = _effective_node_kind(topo_node)
    ui = topo_node.get("ui") if isinstance(topo_node.get("ui"), dict) else {}
    ports_obj = _normalize_ports(kind, ui.get("ports"))
    rows = ports_obj.get(side) if isinstance(ports_obj.get(side), list) else []
    for port in rows:
        pid = str(port.get("id") or "")
        if pid and _ops_port_link_count(edges, node_id, side, pid) < _ops_port_max(port):
            ui["ports"] = ports_obj
            topo_node["ui"] = ui
            return pid
    max_ports = 8 if kind in ("entry", "terminal") else 6
    if len(rows) >= max_ports:
        return ""
    pid = _ops_next_port_id(rows, side)
    rows.append({"id": pid, "label": pid, "kind": side, "max_links": 1, "required": False})
    ports_obj[side] = rows
    ui["ports"] = ports_obj
    topo_node["ui"] = ui
    return pid

def _ops_structured_append_edge(topo: Dict[str, Any], frm: str, to: str) -> Tuple[bool, Dict[str, Any], int]:
    if not frm or not to or frm == to:
        return False, {"ok": False, "error": "invalid edge endpoints", "message": "连线起点或终点无效"}, 400
    node_map = _ops_topology_node_map(topo)
    edges = _ops_topology_edge_list(topo)
    fn = node_map.get(frm)
    tn = node_map.get(to)
    if not fn or not tn:
        return False, {"ok": False, "error": "node not found", "message": "节点不存在"}, 404
    if not _can_link_nodes(fn, tn):
        reason = _link_role_block_reason(fn, tn) or "当前节点角色规则不允许该连线"
        return False, {"ok": False, "error": "invalid_edge_by_role", "error_code": "OPS_EDGE_ROLE_FORBIDDEN", "message": reason}, 409
    fkind = _effective_node_kind(fn)
    tkind = _effective_node_kind(tn)
    if fkind == "terminal" or tkind == "entry":
        return False, {"ok": False, "error": "node_kind_violation", "error_code": "OPS_NODE_KIND_VIOLATION", "message": "节点语义方向不允许该连线"}, 409
    if any(isinstance(e, dict) and str(e.get("from") or "") == frm and str(e.get("to") or "") == to for e in edges):
        return False, {"ok": False, "error": "edge_duplicate", "error_code": "OPS_EDGE_DUPLICATE", "message": "两个节点之间已存在连线"}, 409
    from_port = _ops_ensure_free_port(fn, "out", edges)
    to_port = _ops_ensure_free_port(tn, "in", edges)
    if not from_port or not to_port:
        return False, {"ok": False, "error": "port_capacity_exceeded", "error_code": "OPS_PORT_CAPACITY_EXCEEDED", "message": "节点端口数量已达上限"}, 409
    tn_ui = tn.get("ui") if isinstance(tn.get("ui"), dict) else {}
    if tn_ui.get("list_only"):
        tn_ui = dict(tn_ui)
        tn_ui["list_only"] = False
        tn["ui"] = tn_ui
    edge = {"id": f"edge-{uuid.uuid4().hex[:10]}", "from": frm, "to": to, "from_port": from_port, "to_port": to_port, "type": "depends_on", "note": "structured-auto", "ui": {}}
    edges.append(edge)
    return True, edge, 200

def _can_reach_without_node(edges: List[Dict[str, Any]], src: str, dst: str, blocked: str) -> bool:
    if src == dst:
        return True
    graph: Dict[str, List[str]] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        a = str(e.get("from") or "")
        b = str(e.get("to") or "")
        if not a or not b or a == blocked or b == blocked:
            continue
        graph.setdefault(a, []).append(b)
    seen = set([src])
    queue = [src]
    while queue:
        cur = queue.pop(0)
        for nxt in graph.get(cur, []):
            if nxt in seen:
                continue
            if nxt == dst:
                return True
            seen.add(nxt)
            queue.append(nxt)
    return False

def _is_critical_topology_node(topo: Dict[str, Any], node_id: str) -> bool:
    nodes = [x for x in (topo.get("nodes") or []) if isinstance(x, dict)]
    edges = [x for x in (topo.get("edges") or []) if isinstance(x, dict)]
    target = None
    for n in nodes:
        if str(n.get("id") or "") == node_id:
            target = n
            break
    if not target:
        return False

    kind = str(target.get("kind") or "standard")
    linked_edges = [e for e in edges if str(e.get("from") or "") == node_id or str(e.get("to") or "") == node_id]
    if not linked_edges:
        return False

    if kind == "entry":
        other_entry = [n for n in nodes if str(n.get("id") or "") != node_id and str(n.get("kind") or "") == "entry"]
        if not other_entry:
            return True
    if kind == "terminal":
        other_terminal = [n for n in nodes if str(n.get("id") or "") != node_id and str(n.get("kind") or "") == "terminal"]
        if not other_terminal:
            return True

    incoming = list({str(e.get("from") or "") for e in edges if str(e.get("to") or "") == node_id})
    outgoing = list({str(e.get("to") or "") for e in edges if str(e.get("from") or "") == node_id})
    incoming = [x for x in incoming if x]
    outgoing = [x for x in outgoing if x]
    if incoming and outgoing:
        for s in incoming:
            for t in outgoing:
                if not _can_reach_without_node(edges, s, t, node_id):
                    return True
    return False

def _is_critical_topology_edge(topo: Dict[str, Any], edge_id: str) -> bool:
    nodes = [x for x in (topo.get("nodes") or []) if isinstance(x, dict)]
    edges = [x for x in (topo.get("edges") or []) if isinstance(x, dict)]
    if not nodes or not edges:
        return False
    target = None
    for e in edges:
        if str(e.get("id") or "") == edge_id:
            target = e
            break
    if not target:
        return False

    entry_ids = [str(n.get("id") or "") for n in nodes if str(n.get("kind") or "") == "entry"]
    term_ids = [str(n.get("id") or "") for n in nodes if str(n.get("kind") or "") == "terminal"]
    if not entry_ids or not term_ids:
        return False

    def _reachable(edge_rows: List[Dict[str, Any]], roots: List[str]) -> set:
        graph: Dict[str, List[str]] = {}
        for e in edge_rows:
            a = str(e.get("from") or "")
            b = str(e.get("to") or "")
            if not a or not b:
                continue
            graph.setdefault(a, []).append(b)
        seen = set(roots)
        queue = list(roots)
        while queue:
            cur = queue.pop(0)
            for nxt in graph.get(cur, []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return seen

    before = _reachable(edges, entry_ids)
    after = _reachable([e for e in edges if str(e.get("id") or "") != edge_id], entry_ids)
    for tid in term_ids:
        if tid in before and tid not in after:
            return True
    return False

