# -*- coding: utf-8 -*-
"""GM operations center route module."""

import secrets
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from flask import Blueprint, jsonify, render_template_string, request, session

from models.data import (
    create_approval,
    get_approved_approval,
    get_system_config,
    log_audit,
    project_versions_db,
    projects_db,
    resolve_project_id,
    save_project_versions,
    save_projects,
    set_system_config,
    get_channels_for_project,
)
from services.authz import admin_required, can_access_module, has_scope
from services.game_ops_client import GameOpsClient

bp = Blueprint("gm_ops", __name__)
_client = GameOpsClient()

RELEASE_PROFILES_KEY = "GM_RELEASE_PROFILES"
PENDING_ACTIONS_KEY = "GM_APPROVAL_PENDING_ACTIONS"

ACTION_CATALOG: List[Dict[str, Any]] = [
    {"actionType": "server_state", "domain": "lifecycle", "label": "开停服", "risk": "high", "scope": "gm.ops.execute", "requireApproval": True},
    {"actionType": "maintenance", "domain": "ops", "label": "维护公告", "risk": "high", "scope": "gm.ops.execute", "requireApproval": True},
    {"actionType": "feature_toggle", "domain": "feature", "label": "全局开关", "risk": "high", "scope": "gm.ops.execute", "requireApproval": True},
    {"actionType": "whitelist", "domain": "liveops", "label": "白名单", "risk": "medium", "scope": "gm.liveops.execute", "requireApproval": False},
    {"actionType": "mute_chat", "domain": "liveops", "label": "禁言", "risk": "medium", "scope": "gm.liveops.execute", "requireApproval": False},
    {"actionType": "kick_session", "domain": "incident", "label": "踢会话", "risk": "high", "scope": "gm.ops.execute", "requireApproval": True},
    {"actionType": "retry_task", "domain": "incident", "label": "重试任务", "risk": "medium", "scope": "gm.ops.execute", "requireApproval": False},
    {"actionType": "release_publish", "domain": "release", "label": "发布版本", "risk": "high", "scope": "gm.release.execute", "requireApproval": True},
    {"actionType": "release_rollback", "domain": "release", "label": "回滚版本", "risk": "high", "scope": "gm.release.execute", "requireApproval": True},
]


def _current_user() -> str:
    return (session.get("user") or "unknown").strip()


def _current_role() -> str:
    info = {}
    try:
        from models.data import users_db

        info = users_db.get(_current_user()) or {}
    except Exception:
        info = {}
    role = (info.get("role") or "viewer").strip().lower()
    if role in ("super_admin", "admin"):
        return "SuperAdmin"
    if role == "cs":
        return "CS"
    return "Operator"


def _can_execute(scope: str) -> bool:
    if has_scope(scope):
        return True
    return can_access_module("gm_ops")


def _find_action(action_type: str) -> Dict[str, Any]:
    for item in ACTION_CATALOG:
        if item.get("actionType") == action_type:
            return item
    return {}


def _normalize_release_entry(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(payload.get("id") or uuid.uuid4().hex[:16]),
        "channel": str(payload.get("channel") or "dev").strip(),
        "env": str(payload.get("env") or "dev").strip(),
        "server_profile": str(payload.get("server_profile") or "default").strip(),
        "version_name": str(payload.get("version_name") or "").strip(),
        "version_code": str(payload.get("version_code") or "").strip(),
        "platform": str(payload.get("platform") or "android").strip().lower(),
        "apk_version": str(payload.get("apk_version") or "").strip(),
        "resource_version": str(payload.get("resource_version") or "").strip(),
        "config_version": str(payload.get("config_version") or "").strip(),
        "apk_url": str(payload.get("apk_url") or "").strip(),
        "resource_url": str(payload.get("resource_url") or "").strip(),
        "config_url": str(payload.get("config_url") or "").strip(),
        "distribution_method": str(payload.get("distribution_method") or "").strip(),
        "package_name": str(payload.get("package_name") or "").strip(),
        "bundle_id": str(payload.get("bundle_id") or "").strip(),
        "min_sdk": str(payload.get("min_sdk") or "").strip(),
        "min_ios_version": str(payload.get("min_ios_version") or "").strip(),
        "changelog": str(payload.get("changelog") or "").strip(),
        "notes": str(payload.get("notes") or "").strip(),
        "build_output": str(payload.get("build_output") or "").strip(),
        "project_code": str(payload.get("project_code") or "").strip(),
        "resource_builder": str(payload.get("resource_builder") or "").strip(),
        "allow_delta": bool(payload.get("allow_delta")),
        "enable_compression": bool(payload.get("enable_compression")),
        "compression_mode": str(payload.get("compression_mode") or "").strip(),
        "compression_provider": str(payload.get("compression_provider") or "").strip(),
        "enable_encryption": bool(payload.get("enable_encryption")),
        "encrypt_mode": str(payload.get("encrypt_mode") or "").strip(),
        "encrypt_provider": str(payload.get("encrypt_provider") or "").strip(),
        "enable_sign": bool(payload.get("enable_sign")),
        "sign_provider": str(payload.get("sign_provider") or "").strip(),
        "sign_key": str(payload.get("sign_key") or "").strip(),
        "hash_manifest": bool(payload.get("hash_manifest")),
        "baseline_version_dir": str(payload.get("baseline_version_dir") or "").strip(),
        "diff_keyword": str(payload.get("diff_keyword") or "").strip(),
        "diff_preview": str(payload.get("diff_preview") or "").strip(),
        "hot_update_base_url": str(payload.get("hot_update_base_url") or "").strip(),
        "profile": str(payload.get("profile") or "").strip(),
        "client_version": str(payload.get("client_version") or "").strip(),
        "show_runtime_config": bool(payload.get("show_runtime_config")),
        "upload_provider": str(payload.get("upload_provider") or "").strip(),
        "bucket": str(payload.get("bucket") or "").strip(),
        "region": str(payload.get("region") or "").strip(),
        "cdn_prefix": str(payload.get("cdn_prefix") or "").strip(),
        "path_template": str(payload.get("path_template") or "").strip(),
        "automation_plan_path": str(payload.get("automation_plan_path") or "").strip(),
        "cli_result_path": str(payload.get("cli_result_path") or "").strip(),
        "entry_point": str(payload.get("entry_point") or "").strip(),
        "release_mode": str(payload.get("release_mode") or "").strip(),
        "targets": str(payload.get("targets") or "").strip(),
        "code_units": str(payload.get("code_units") or "").strip(),
        "config_units": str(payload.get("config_units") or "").strip(),
        "asset_units": str(payload.get("asset_units") or "").strip(),
        "publish_status": str(payload.get("publish_status") or "draft").strip(),
        "approval_id": str(payload.get("approval_id") or "").strip(),
        "publish_trace_id": str(payload.get("publish_trace_id") or "").strip(),
        "rollback_trace_id": str(payload.get("rollback_trace_id") or "").strip(),
        "updated_at": datetime.now().isoformat(),
        "updated_by": _current_user(),
        "created_at": str(payload.get("created_at") or datetime.now().isoformat()),
    }


def _normalize_release_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(payload.get("id") or "default").strip() or "default",
        "name": str(payload.get("name") or "默认档").strip(),
        "env": str(payload.get("env") or "dev").strip(),
        "channel": str(payload.get("channel") or "dev").strip(),
        "gateway_ws": str(payload.get("gateway_ws") or "").strip(),
        "login_http": str(payload.get("login_http") or "").strip(),
        "game_ws": str(payload.get("game_ws") or "").strip(),
        "battle_udp": str(payload.get("battle_udp") or "").strip(),
        "ops_http": str(payload.get("ops_http") or "").strip(),
        "notice_url": str(payload.get("notice_url") or "").strip(),
        "updated_at": datetime.now().isoformat(),
        "updated_by": _current_user(),
    }


def _load_release_profiles() -> List[Dict[str, Any]]:
    raw = get_system_config(RELEASE_PROFILES_KEY, [])
    if isinstance(raw, list):
        return raw
    return []


def _load_pending_actions() -> Dict[str, Any]:
    raw = get_system_config(PENDING_ACTIONS_KEY, {})
    if isinstance(raw, dict):
        return raw
    return {}


def _save_pending_actions(data: Dict[str, Any]) -> None:
    set_system_config(
        PENDING_ACTIONS_KEY,
        data,
        value_type="json",
        description="GM审批待执行动作缓存",
        username=_current_user(),
    )


def _save_release_profiles(profiles: List[Dict[str, Any]]) -> None:
    set_system_config(
        RELEASE_PROFILES_KEY,
        profiles,
        value_type="json",
        description="GM发版环境与网络地址配置",
        username=_current_user(),
    )


def _find_best_release(project_id: str, env: str, channel: str, platform: str, version_name: str, published_only: bool = False) -> Dict[str, Any]:
    versions = project_versions_db.get(project_id) or []
    candidates = []
    for item in versions:
        if env and str(item.get("env") or "").strip() != env:
            continue
        if channel and str(item.get("channel") or "").strip() != channel:
            continue
        if platform and str(item.get("platform") or "android").strip().lower() != platform.lower():
            continue
        if version_name and str(item.get("version_name") or "").strip() != version_name:
            continue
        if published_only and str(item.get("publish_status") or "draft").strip() != "published":
            continue
        candidates.append(item)

    if not candidates:
        return {}

    candidates.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return candidates[0]


def _resolve_profile(server_profile: str, env: str, channel: str) -> Dict[str, Any]:
    profiles = _load_release_profiles()
    if not profiles:
        return {}

    for item in profiles:
        if str(item.get("id") or "") == server_profile:
            return item

    for item in profiles:
        if str(item.get("env") or "") == env and str(item.get("channel") or "") == channel:
            return item

    return profiles[0]


def _ensure_project_exists(project_id: str) -> Tuple[bool, str]:
    pid = resolve_project_id(project_id)
    if not pid:
        return False, "project not found"
    return True, pid


def _parse_host_port_from_uri(uri: str, default_port: int) -> Tuple[str, int]:
    text = (uri or "").strip()
    if not text:
        return "", default_port
    try:
        if "://" not in text:
            text = "tcp://" + text
        p = urlparse(text)
        return str(p.hostname or ""), int(p.port or default_port)
    except Exception:
        return "", default_port


def _check_tcp_latency(host: str, port: int, timeout_sec: float = 1.5) -> Dict[str, Any]:
    result = {"ok": False, "latencyMs": -1, "error": ""}
    if not host:
        result["error"] = "missing host"
        return result
    try:
        import socket

        start = time.perf_counter()
        with socket.create_connection((host, int(port)), timeout=timeout_sec):
            pass
        latency_ms = int((time.perf_counter() - start) * 1000.0)
        result["ok"] = True
        result["latencyMs"] = latency_ms
        return result
    except Exception as ex:
        result["error"] = str(ex)
        return result


def execute_action_by_approval_id(approval_id: str, approver: str = "") -> Dict[str, Any]:
    pending = _load_pending_actions()
    action_model = pending.get(approval_id) or {}
    if not isinstance(action_model, dict) or not action_model:
        return {"ok": False, "error": "pending action not found"}

    operator = approver or _current_user()
    role = _current_role()
    operator_context = action_model.get("operatorContext") or {}
    reason = str(operator_context.get("reason") or "审批通过自动执行").strip()
    ticket_id = str(operator_context.get("ticketId") or f"GM-APPROVAL-{approval_id[:8]}").strip()

    result = _client.execute_action(
        action=action_model,
        operator=operator,
        role=role,
        reason=reason,
        ticket_id=ticket_id,
    )
    if result.get("success"):
        action_type = str(action_model.get("actionType") or "")
        if action_type in ("release_publish", "release_rollback"):
            _apply_local_release_state(action_type, action_model.get("payload") or {}, {"id": approval_id})
        pending.pop(approval_id, None)
        _save_pending_actions(pending)
    return {"ok": bool(result.get("success")), "result": result}


def _apply_local_release_state(action_type: str, action_payload: Dict[str, Any], approved_ref: Dict[str, Any]) -> None:
    """将发布/回滚动作同步到本地版本库，避免审批自动执行后出现配置对账不一致。"""
    project_id_raw = str(action_payload.get("project_id") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return
    version_name = str(action_payload.get("version_name") or "").strip()
    platform = str(action_payload.get("platform") or "android").strip().lower()
    env = str(action_payload.get("env") or "").strip()
    channel = str(action_payload.get("channel") or "").strip()
    release = _find_best_release(resolved, env, channel, platform, version_name, published_only=False)
    if not release:
        return
    if action_type == "release_publish":
        release["publish_status"] = "published"
        release["approval_id"] = str((approved_ref or {}).get("id") or "")
        release["publish_trace_id"] = uuid.uuid4().hex[:16]
    elif action_type == "release_rollback":
        release["publish_status"] = "rolled_back"
        release["rollback_trace_id"] = uuid.uuid4().hex[:16]
    release["updated_at"] = datetime.now().isoformat()
    release["updated_by"] = _current_user()
    versions = project_versions_db.get(resolved) or []
    for i, item in enumerate(versions):
        if str(item.get("id") or "") == str(release.get("id") or ""):
            versions[i] = release
            break
    project_versions_db[resolved] = versions
    save_project_versions()


def _get_project_credentials(project_id: str) -> Dict[str, Any]:
    p = projects_db.get(project_id) or {}
    return {
        "project_id": project_id,
        "project_name": str(p.get("name") or project_id),
        "game_id": str(p.get("game_id") or "").strip(),
        "game_key": str(p.get("game_key") or "").strip(),
        "game_key_hint": (str(p.get("game_key") or "").strip()[:6] + "***") if str(p.get("game_key") or "").strip() else "",
        "default_server_profile": str(p.get("default_server_profile") or "default").strip() or "default",
        "updated_at": str(p.get("game_key_updated_at") or p.get("updated_at") or "").strip(),
        "updated_by": str(p.get("game_key_updated_by") or p.get("updated_by") or "").strip(),
    }


def _project_envs_and_channels(project_id: str) -> Dict[str, List[str]]:
    versions = project_versions_db.get(project_id) or []
    envs = sorted({str(v.get("env") or "").strip() for v in versions if str(v.get("env") or "").strip()})
    channels = sorted({str(v.get("channel") or "").strip() for v in versions if str(v.get("channel") or "").strip()})
    if not envs:
        envs = ["dev", "test", "staging", "prod"]
    if not channels:
        channels = [str(c).strip() for c in ((projects_db.get(project_id) or {}).get("channels") or []) if str(c).strip()]
    return {"envs": envs, "channels": channels}


def _find_project_by_game_credentials(game_id: str, game_key: str) -> Optional[str]:
    gid = (game_id or "").strip()
    gk = (game_key or "").strip()
    if not gid or not gk:
        return None
    for project_id, payload in (projects_db or {}).items():
        item = payload if isinstance(payload, dict) else {}
        if str(item.get("game_id") or "").strip() == gid and str(item.get("game_key") or "").strip() == gk:
            return str(project_id)
    return None


def _generate_project_credentials(project_id: str) -> Tuple[str, str]:
    """生成全局唯一的 gameId/gameKey。"""
    base = (project_id or "game").strip()[:24] or "game"
    existed = {str((p or {}).get("game_id") or "").strip() for p in (projects_db or {}).values() if isinstance(p, dict)}
    gid = f"{base}-{secrets.token_hex(8)}"
    while gid in existed:
        gid = f"{base}-{secrets.token_hex(8)}"
    gkey = secrets.token_hex(32)
    return gid, gkey


def _allow_ci_access() -> bool:
    token = (request.headers.get("X-GM-CI-Token") or request.args.get("ci_token") or "").strip()
    expected = str(get_system_config("GM_CI_TOKEN", "") or "").strip()
    return bool(token and expected and token == expected)
# 页面主入口：GM 运营工作台。数据来源：项目配置、发布参数字典与 Ops 执行结果。
@bp.route("/admin/gm-ops")
@admin_required("gm_ops")
def gm_ops_page():
    content = """
<div class="gm-shell space-y-5">
  <style>
    .gm-shell .gm-card{border:1px solid #e2e8f0;background:#fff;border-radius:18px;box-shadow:0 1px 2px rgba(15,23,42,.04)}
    .gm-shell .gm-hero{border:1px solid #c7d2fe;background:linear-gradient(100deg,#0f172a,#1e293b 45%,#4338ca);border-radius:20px;box-shadow:0 8px 26px rgba(30,41,59,.2)}
    .gm-shell .gm-card-title{font-size:16px;font-weight:700;color:#0f172a}
    .gm-shell .gm-subtitle{font-size:12px;color:#64748b}
    .gm-shell select,.gm-shell input,.gm-shell textarea{border:1px solid #cbd5e1;border-radius:10px;padding:.55rem .7rem;font-size:14px}
    .gm-shell select:focus,.gm-shell input:focus,.gm-shell textarea:focus{outline:none;border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.12)}
    .gm-shell .gm-primary-btn{border:1px solid rgba(255,255,255,.28);border-radius:12px;padding:.6rem .9rem;font-size:13px;font-weight:700;color:#fff;box-shadow:inset 0 1px 0 rgba(255,255,255,.24),0 8px 18px rgba(30,41,59,.2);transition:all .15s ease}
    .gm-shell .gm-primary-btn:hover{transform:translateY(-1px);filter:brightness(1.05)}
    .gm-shell .gm-tab-btn{border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;color:#475569;padding:.64rem .8rem;font-size:13px;font-weight:700;transition:all .15s ease}
    .gm-shell .gm-tab-btn:hover{background:#eef2ff;color:#3730a3}
    .gm-shell .gm-tab-btn-active{background:linear-gradient(135deg,#4f46e5,#4338ca);color:#fff;border-color:#4f46e5;box-shadow:0 8px 18px rgba(67,56,202,.22)}
    .gm-shell .gm-tab-wrap{display:flex;flex-wrap:wrap;gap:.55rem}
    .gm-shell .gm-tab-wrap .gm-tab-btn{min-width:132px}
    .gm-shell .gm-acc{border:1px solid #e2e8f0;border-radius:14px;background:#fff;overflow:hidden}
    .gm-shell .gm-acc summary{display:flex;align-items:center;justify-content:space-between;gap:10px;cursor:pointer;padding:.72rem .9rem;background:#f8fafc;color:#1e293b;font-size:13px;font-weight:700;list-style:none}
    .gm-shell .gm-acc summary::-webkit-details-marker{display:none}
    .gm-shell .gm-acc summary .gm-acc-meta{font-size:11px;font-weight:600;color:#64748b}
    .gm-shell .gm-acc summary::after{content:'展开';font-size:11px;color:#64748b}
    .gm-shell .gm-acc[open] summary::after{content:'收起';color:#4f46e5}
    .gm-shell .gm-acc .gm-acc-body{padding:.8rem}
    .gm-shell .gm-fieldset{border:1px solid #e2e8f0;border-radius:14px;background:#f8fafc;padding:12px}
    .gm-shell .gm-fieldset h4{font-size:12px;font-weight:700;color:#334155;margin-bottom:8px;letter-spacing:.04em;text-transform:uppercase}
    .gm-shell .gm-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem}
    .gm-shell .gm-context-grid{display:grid;grid-template-columns:repeat(1,minmax(0,1fr));gap:.75rem;align-items:end}
    .gm-shell .gm-context-kpi{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}
    .gm-shell .gm-kpi{border:1px solid #dbe3f1;background:#f8fbff;border-radius:12px;padding:.5rem .65rem}
    .gm-shell .gm-kpi .k{font-size:11px;color:#64748b}
    .gm-shell .gm-kpi .v{font-size:12px;font-weight:700;color:#0f172a}
    .gm-shell .gm-nav-strip{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem}
    .gm-shell .gm-hint{font-size:12px;color:#64748b;border:1px solid #e2e8f0;background:#f8fafc;border-radius:12px;padding:.6rem .8rem}
    .gm-shell .gm-context-chip{display:inline-flex;align-items:center;padding:.2rem .55rem;border-radius:999px;border:1px solid #c7d2fe;background:#eef2ff;color:#3730a3;font-size:11px;font-weight:700}
    .gm-shell .gm-context-mini{display:flex;flex-wrap:wrap;gap:.45rem}
    .gm-shell .gm-context-mini span{font-size:11px;padding:.18rem .5rem;border-radius:999px;border:1px solid #dbe3f1;background:#fff;color:#475569}
    .gm-shell .gm-context-mini b{font-weight:700;color:#0f172a}
    .gm-shell .gm-compact-label{display:block;font-size:12px;color:#64748b;margin-bottom:.3rem;font-weight:600}
    .gm-shell .gm-fit{max-width:100%}
    @media (min-width: 900px){.gm-shell .gm-context-grid{grid-template-columns:repeat(12,minmax(0,1fr))}.gm-shell .gm-nav-strip{grid-template-columns:repeat(6,minmax(0,1fr))}}
    @media (min-width: 768px){.gm-shell .gm-actions{grid-template-columns:repeat(5,minmax(0,1fr));}.gm-shell .gm-tab-wrap .gm-tab-btn{flex:1}}
  </style>
  <section class="gm-hero p-7">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h2 class="text-2xl font-semibold text-white">GM运营中心（项目优先）</h2>
      <span class="gm-context-chip" style="background:#dbeafe;border-color:#93c5fd;color:#1d4ed8;">UI Rev 2026-05-16 R2</span>
    </div>
    <p class="mt-2 text-sm text-indigo-100/90">单项目工作台：项目身份、构建、发布、运维、快照、执行日志统一在同一上下文闭环。</p>
  </section>

  <section class="gm-card p-5 space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h3 class="gm-card-title">项目上下文</h3>
        <p class="gm-subtitle mt-1">先固定上下文，再进入分区执行，减少误操作。</p>
      </div>
      <div class="gm-context-mini">
        <span>模式：<b>单项目</b></span>
        <span>流程：<b>分区闭环</b></span>
      </div>
    </div>
    <div class="gm-context-grid">
      <div class="md:col-span-7 gm-fit">
        <label class="gm-compact-label">项目</label>
        <select id="projectSelect" class="w-full border rounded px-2 py-2 text-sm"></select>
      </div>
      <div class="md:col-span-2 gm-fit">
        <label class="gm-compact-label">环境</label>
        <select id="env" class="w-full border rounded px-2 py-2 text-sm"></select>
      </div>
      <div class="md:col-span-2 gm-fit">
        <label class="gm-compact-label">渠道</label>
        <select id="channel" class="w-full border rounded px-2 py-2 text-sm"></select>
      </div>
      <div class="md:col-span-1 gm-fit">
        <label class="gm-compact-label">平台</label>
        <select id="platform" class="w-full border rounded px-2 py-2 text-sm"><option value="android">android</option><option value="ios">ios</option></select>
      </div>
      <div class="md:col-span-3"><button onclick="loadWorkspace()" class="w-full gm-primary-btn bg-indigo-600">加载项目工作台</button></div>
      <div class="md:col-span-9 gm-context-kpi">
        <div class="gm-kpi"><div class="k">当前项目</div><div id="ctxProjectName" class="v">-</div></div>
        <div class="gm-kpi"><div class="k">上下文</div><div id="ctxContextName" class="v">-</div></div>
      </div>
    </div>
    <input id="projectId" type="hidden">
  </section>

  <section class="gm-card p-4 space-y-3">
    <div class="gm-tab-wrap gm-nav-strip text-sm">
      <button id="tabBtn-identity" onclick="switchSection('identity')" class="gm-tab-btn gm-tab-btn-active px-3 py-2.5">项目身份</button>
      <button id="tabBtn-build" onclick="switchSection('build')" class="gm-tab-btn px-3 py-2.5">构建</button>
      <button id="tabBtn-release" onclick="switchSection('release')" class="gm-tab-btn px-3 py-2.5">发布</button>
      <button id="tabBtn-ops" onclick="switchSection('ops')" class="gm-tab-btn px-3 py-2.5">运维</button>
      <button id="tabBtn-snapshot" onclick="switchSection('snapshot')" class="gm-tab-btn px-3 py-2.5">快照</button>
      <button id="tabBtn-logs" onclick="switchSection('logs')" class="gm-tab-btn px-3 py-2.5">执行日志</button>
    </div>
    <div class="gm-hint">先切换分区，再填写对应参数。发布区采用向导化布局，核心字段优先，高级字段折叠。</div>
  </section>

  <section id="sec-identity" class="gm-card p-5 space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-base font-semibold text-slate-900">项目身份与接入（只读）</h3>
      <span class="text-xs px-2 py-1 rounded bg-amber-50 text-amber-700 border border-amber-200">创建后不可修改</span>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
      <div>
        <label class="block text-xs text-slate-500 mb-1">gameId（唯一）<span class="text-rose-500"> *</span></label>
        <input id="gameId" readonly class="w-full border rounded-lg px-3 py-2 bg-slate-50">
        <p class="mt-1 text-[11px] text-slate-500">用于客户端启动鉴权，创建项目后不可修改。</p>
      </div>
      <div>
        <label class="block text-xs text-slate-500 mb-1">gameKey（掩码）<span class="text-rose-500"> *</span></label>
        <input id="gameKeyMasked" readonly class="w-full border rounded-lg px-3 py-2 bg-slate-50">
        <p class="mt-1 text-[11px] text-slate-500">敏感凭据仅掩码显示，避免明文泄漏。</p>
      </div>
      <div>
        <label class="block text-xs text-slate-500 mb-1">服务端配置档</label>
        <input id="serverProfile" class="w-full border rounded-lg px-3 py-2" placeholder="default">
        <p class="mt-1 text-[11px] text-slate-500">影响服务端路由组（登录/游戏/战斗/运维）。</p>
      </div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
      <button onclick="loadParameterClosure()" class="gm-primary-btn bg-violet-700">查看参数字典</button>
      <button onclick="compareBeforeAfter()" class="gm-primary-btn bg-emerald-700">执行前后对比</button>
      <button onclick="loadWorkspace()" class="gm-primary-btn bg-cyan-700">刷新项目身份</button>
    </div>
    <div id="credentialSummary" class="text-xs text-slate-600"></div>
  </section>

  <section id="sec-build" class="gm-card p-5 space-y-4" style="display:none;">
    <h3 class="font-semibold text-slate-900">构建域参数</h3>
    <p class="text-xs text-slate-500">对应商业化发布工具中的构建、差分、自动化导出相关配置。</p>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-3 text-sm">
      <div class="gm-fieldset">
        <h4>构建基础</h4>
        <div class="space-y-2">
          <div><label class="block text-xs text-slate-500 mb-1">构建输出目录</label><input id="buildOutput" class="w-full border rounded-lg px-3 py-2" placeholder="build_output"></div>
          <div><label class="block text-xs text-slate-500 mb-1">项目标识</label><input id="projectCode" class="w-full border rounded-lg px-3 py-2" placeholder="project_code"></div>
          <div><label class="block text-xs text-slate-500 mb-1">资源构建器</label><input id="resourceBuilder" class="w-full border rounded-lg px-3 py-2" placeholder="resource_builder"></div>
        </div>
      </div>
      <div class="gm-fieldset">
        <h4>差分策略</h4>
        <div class="space-y-2">
          <div><label class="block text-xs text-slate-500 mb-1">基线版本目录</label><input id="baselineVersionDir" class="w-full border rounded-lg px-3 py-2" placeholder="baseline_version_dir"></div>
          <div><label class="block text-xs text-slate-500 mb-1">差异查询词</label><input id="diffKeyword" class="w-full border rounded-lg px-3 py-2" placeholder="diff_keyword"></div>
          <div><label class="block text-xs text-slate-500 mb-1">热更新基础地址</label><input id="hotUpdateBaseUrl" class="w-full border rounded-lg px-3 py-2" placeholder="hot_update_base_url"></div>
        </div>
      </div>
      <div class="gm-fieldset">
        <h4>自动化执行</h4>
        <div class="space-y-2">
          <div><label class="block text-xs text-slate-500 mb-1">自动化计划路径</label><input id="automationPlanPath" class="w-full border rounded-lg px-3 py-2" placeholder="automation_plan_path"></div>
          <div><label class="block text-xs text-slate-500 mb-1">CLI结果路径</label><input id="cliResultPath" class="w-full border rounded-lg px-3 py-2" placeholder="cli_result_path"></div>
          <div><label class="block text-xs text-slate-500 mb-1">执行入口</label><input id="entryPoint" class="w-full border rounded-lg px-3 py-2" placeholder="entry_point"></div>
        </div>
      </div>
    </div>
  </section>

  <section id="sec-release" class="gm-card p-5 space-y-4" style="display:none;">
    <div class="flex items-start justify-between gap-3 flex-wrap">
      <div>
        <h3 class="font-semibold text-slate-900">发布域参数（分步向导）</h3>
        <p class="text-xs text-slate-500 mt-1">按步骤填写，先完成核心参数。高级参数默认折叠，避免信息过载。</p>
      </div>
      <label class="inline-flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" id="releaseOnlyRequired" class="rounded border-slate-300">仅看必填</label>
    </div>
    <div id="releaseStepNav" class="grid grid-cols-2 md:grid-cols-5 gap-2 text-sm">
      <button type="button" id="releaseStepBtn-1" class="gm-tab-btn gm-tab-btn-active" onclick="setReleaseStep(1)">1.版本与资源基础</button>
      <button type="button" id="releaseStepBtn-2" class="gm-tab-btn" onclick="setReleaseStep(2)">2.分发与客户端</button>
      <button type="button" id="releaseStepBtn-3" class="gm-tab-btn" onclick="setReleaseStep(3)">3.策略与执行编排</button>
      <button type="button" id="releaseStepBtn-4" class="gm-tab-btn" onclick="setReleaseStep(4)">4.路由与审批</button>
      <button type="button" id="releaseStepBtn-5" class="gm-tab-btn" onclick="setReleaseStep(5)">5.预检与执行</button>
    </div>
    <div id="releaseStepStatus" class="text-xs rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-600"></div>
    <div id="releaseStepPanes" class="space-y-3">
      <div class="gm-release-step-pane" data-step="1">
        <details class="gm-acc" open>
          <summary><span>核心发布参数（必填）</span><span class="gm-acc-meta">版本号、资源版本、下载地址</span></summary>
          <div class="gm-acc-body grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
            <div class="gm-release-field" data-required="1"><label class="block text-xs text-slate-500 mb-1">版本名称 <span class="text-rose-500">*</span></label><input id="versionName" class="w-full" placeholder="如 1.2.0-hotfix1"></div>
            <div class="gm-release-field" data-required="1"><label class="block text-xs text-slate-500 mb-1">APK 版本 <span class="text-rose-500">*</span></label><input id="apkVersion" class="w-full" placeholder="如 1.2.0"></div>
            <div class="gm-release-field" data-required="1"><label class="block text-xs text-slate-500 mb-1">资源版本 <span class="text-rose-500">*</span></label><input id="resourceVersion" class="w-full" placeholder="如 res_20260515_01"></div>
            <div class="gm-release-field" data-required="1"><label class="block text-xs text-slate-500 mb-1">配置版本 <span class="text-rose-500">*</span></label><input id="configVersion" class="w-full" placeholder="如 cfg_20260515_01"></div>
            <div class="gm-release-field" data-required="1"><label class="block text-xs text-slate-500 mb-1">APK 地址 <span class="text-rose-500">*</span></label><input id="apkUrl" class="w-full" placeholder="https://cdn.xx/game.apk"></div>
            <div class="gm-release-field" data-required="1"><label class="block text-xs text-slate-500 mb-1">资源地址 <span class="text-rose-500">*</span></label><input id="resourceUrl" class="w-full" placeholder="https://cdn.xx/res/"></div>
            <div class="gm-release-field" data-required="1"><label class="block text-xs text-slate-500 mb-1">配置地址 <span class="text-rose-500">*</span></label><input id="configUrl" class="w-full" placeholder="https://cdn.xx/cfg/"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">分发方式</label><select id="distributionMethod" class="w-full"><option value="direct">direct（直链）</option><option value="enterprise">enterprise（企业分发）</option><option value="store">store（应用商店）</option><option value="testflight">testflight（iOS测试）</option><option value="internal">internal（内部分发）</option></select></div>
            <div class="gm-release-field md:col-span-2"><label class="block text-xs text-slate-500 mb-1">更新说明</label><input id="changelog" class="w-full" placeholder="本次更新说明"></div>
          </div>
        </details>
      </div>

      <div class="gm-release-step-pane hidden" data-step="2">
        <details class="gm-acc" open>
          <summary><span>分发与客户端元数据</span><span class="gm-acc-meta">包标识、上传、CDN</span></summary>
          <div class="gm-acc-body grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">包名（Android）</label><input id="packageName" class="w-full" placeholder="package_name"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">BundleId（iOS）</label><input id="bundleId" class="w-full" placeholder="bundle_id"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">客户端版本号</label><input id="clientVersion" class="w-full" placeholder="client_version"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">上传Provider</label><select id="uploadProvider" class="w-full"><option value="aliyun_oss">aliyun_oss</option><option value="s3">s3</option><option value="local_fs">local_fs</option></select></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">Bucket</label><input id="bucket" class="w-full" placeholder="bucket"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">Region</label><input id="region" class="w-full" placeholder="region"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">CDN前缀</label><input id="cdnPrefix" class="w-full" placeholder="cdn_prefix"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">路径模板</label><input id="pathTemplate" class="w-full" placeholder="path_template"></div>
          </div>
        </details>
      </div>

      <div class="gm-release-step-pane hidden" data-step="3">
        <details class="gm-acc" open>
          <summary><span>发布策略与执行编排</span><span class="gm-acc-meta">模式、目标、执行单元</span></summary>
          <div class="gm-acc-body grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">发布模式</label><select id="releaseMode" class="w-full"><option value="build-upload">build-upload</option><option value="upload-only">upload-only</option><option value="verify-only">verify-only</option></select></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">目标对象</label><input id="targets" class="w-full" placeholder="targets"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">代码单元</label><input id="codeUnits" class="w-full" placeholder="code_units"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">配置单元</label><input id="configUnits" class="w-full" placeholder="config_units"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">资源单元</label><input id="assetUnits" class="w-full" placeholder="asset_units"></div>
          </div>
        </details>
      </div>

      <div class="gm-release-step-pane hidden" data-step="4">
        <details class="gm-acc" open>
          <summary><span>运行时路由与审批</span><span class="gm-acc-meta">服务入口 + 审批上下文</span></summary>
          <div class="gm-acc-body grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">网关WS</label><input id="gatewayWs" class="w-full" placeholder="gateway_ws"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">登录HTTP</label><input id="loginHttp" class="w-full" placeholder="login_http"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">游戏WS</label><input id="gameWs" class="w-full" placeholder="game_ws"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">战斗UDP</label><input id="battleUdp" class="w-full" placeholder="battle_udp"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">运维HTTP</label><input id="opsHttp" class="w-full" placeholder="ops_http"></div>
            <div class="gm-release-field"><label class="block text-xs text-slate-500 mb-1">公告地址</label><input id="noticeUrl" class="w-full" placeholder="notice_url"></div>
            <div class="gm-release-field md:col-span-2" data-required="1"><label class="block text-xs text-slate-500 mb-1">审批理由 <span class="text-rose-500">*</span></label><input id="reason" class="w-full" placeholder="approval_reason"></div>
          </div>
        </details>
      </div>

      <div class="gm-release-step-pane hidden" data-step="5">
        <div class="gm-fieldset">
          <h4>执行链路状态</h4>
          <div id="releaseChainStatus" class="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs"></div>
        </div>
        <div class="gm-actions">
          <button onclick="releasePrecheck()" class="gm-primary-btn bg-indigo-600">1.预检</button>
          <button onclick="releaseApply()" class="gm-primary-btn bg-amber-600">2.审批</button>
          <button onclick="releaseExecute()" class="gm-primary-btn bg-emerald-600">3.执行</button>
          <button onclick="releaseRollback()" class="gm-primary-btn bg-rose-600">4.回滚</button>
          <button onclick="releaseReconcile()" class="gm-primary-btn bg-slate-700">5.对账</button>
        </div>
      </div>
    </div>
    <div class="flex items-center justify-between gap-2 pt-1">
      <button type="button" class="gm-tab-btn" onclick="prevReleaseStep()">上一步</button>
      <div class="flex items-center gap-2">
        <button type="button" class="gm-tab-btn" onclick="saveReleaseDraft()">保存草稿</button>
        <button type="button" class="gm-tab-btn" onclick="releasePrecheck()">执行预检</button>
        <button type="button" class="gm-primary-btn bg-indigo-600" onclick="nextReleaseStep()">下一步</button>
      </div>
    </div>
  </section>

  <section id="sec-ops" class="gm-card p-5 space-y-3" style="display:none;">
    <h3 class="gm-card-title">运维与观测</h3>
    <div class="gm-actions">
      <button onclick="loadClosureEvidence()" class="gm-primary-btn bg-blue-700">闭环证据</button>
      <button onclick="runQualityGate()" class="gm-primary-btn bg-slate-900">质量门禁</button>
      <button onclick="loadRuntimeSnapshot()" class="gm-primary-btn bg-slate-700">运行时快照</button>
      <button onclick="loadInfraMetrics()" class="gm-primary-btn bg-teal-700">Mongo/Redis指标</button>
      <button onclick="saveReleaseProfile()" class="gm-primary-btn bg-sky-700">保存服务路由</button>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div id="infraSummary" class="text-xs text-slate-600 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"></div>
      <div id="workspaceSummary" class="text-xs text-slate-500 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"></div>
    </div>
  </section>

  <section id="sec-snapshot" class="gm-card p-5" style="display:none;">
    <h3 class="font-semibold mb-2">参数合成快照（执行前）</h3>
    <pre id="preview" class="w-full h-48 rounded border p-3 text-xs bg-slate-50 overflow-auto"></pre>
  </section>

  <section id="sec-logs" class="gm-card p-5 space-y-3" style="display:none;">
    <h3 class="font-semibold">执行结果 / 回读</h3>
    <div id="resultSummary" class="text-sm rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700">暂无执行结果</div>
    <details class="gm-acc">
      <summary><span>原始 JSON</span><span class="gm-acc-meta">调试/审计用</span></summary>
      <div class="gm-acc-body">
        <textarea id="result" class="w-full h-72 rounded border p-3 text-xs font-mono"></textarea>
      </div>
    </details>
  </section>

  <section class="gm-card p-5">
    <div class="flex items-center justify-between gap-3 mb-2">
      <h3 class="font-semibold">完整参数字典矩阵</h3>
      <div class="flex items-center gap-2 text-xs">
        <select id="dictCategory" class="border rounded px-2 py-1">
          <option value="all">全部分类</option><option value="project">项目</option><option value="version">版本</option><option value="strategy">策略</option><option value="diff">差分</option><option value="runtime">运行时</option><option value="upload">上传</option><option value="automation">自动化</option>
        </select>
        <input id="dictKeyword" class="border rounded px-2 py-1" placeholder="筛选参数">
      </div>
    </div>
    <div id="dictCompareHint" class="text-xs text-slate-600 mb-2 px-2 py-1 rounded bg-slate-50 border border-slate-200"></div>
    <div class="mb-2 rounded-lg border border-slate-200 overflow-hidden">
      <table class="min-w-full text-xs">
        <thead class="bg-slate-50"><tr><th class="px-2 py-2 text-left">字段</th><th class="px-2 py-2 text-left">执行前</th><th class="px-2 py-2 text-left">执行后</th><th class="px-2 py-2 text-left">状态</th></tr></thead>
        <tbody id="beforeAfterTableBody"><tr><td class="px-2 py-2 text-slate-400" colspan="4">暂无对比，请先点击“执行前后对比”。</td></tr></tbody>
      </table>
    </div>
    <div class="overflow-auto">
      <table class="min-w-full text-xs border border-slate-200">
        <thead class="bg-slate-100"><tr><th class="px-2 py-2 text-left border-b">参数</th><th class="px-2 py-2 text-left border-b">字段说明</th><th class="px-2 py-2 text-left border-b">来源层级</th><th class="px-2 py-2 text-left border-b">值</th><th class="px-2 py-2 text-left border-b">生效阶段</th><th class="px-2 py-2 text-left border-b">日志键/回读键</th></tr></thead>
        <tbody id="closureTableBody"></tbody>
      </table>
    </div>
  </section>
</div>
<script>
let __dictRows=[]; let __afterValues={};
const REQUIRED_RELEASE_FIELDS = ['versionName','apkVersion','resourceVersion','configVersion','apkUrl','resourceUrl','configUrl','reason'];
const RELEASE_STEP_TOTAL = 5;
const RELEASE_STEP_REQUIRED_MAP = {
  1: ['versionName','apkVersion','resourceVersion','configVersion','apkUrl','resourceUrl','configUrl'],
  2: [],
  3: [],
  4: ['reason'],
  5: []
};
const RELEASE_STEP_CORE_MAP = {
  1: ['versionName','apkVersion','resourceVersion','configVersion','apkUrl','resourceUrl','configUrl','distributionMethod','changelog'],
  2: ['packageName','bundleId','clientVersion','uploadProvider'],
  3: ['releaseMode','targets','codeUnits'],
  4: ['gatewayWs','loginHttp','gameWs','reason'],
  5: []
};
const RELEASE_STEP_INFO = {
  1: {title:'版本与资源基础', goal:'建立发布版本的核心身份与资源入口。', input:'完成版本名称、APK/资源/配置版本与三类下载地址。', next:'进入分发与客户端元数据配置。'},
  2: {title:'分发与客户端元数据', goal:'补齐终端识别与分发基础元信息。', input:'按平台填写包标识、上传存储与 CDN 路径。', next:'进入发布策略与执行编排。'},
  3: {title:'策略与执行编排', goal:'声明发布模式和执行单元。', input:'设置模式、目标对象与代码/配置/资源单元。', next:'进入运行时路由与审批上下文。'},
  4: {title:'路由与审批', goal:'确认服务入口与审批理由。', input:'维护网关/登录/游戏/战斗/运维路由，补齐审批理由。', next:'进入预检与执行确认。'},
  5: {title:'预检与执行', goal:'按链路执行预检、审批、发布、回滚、对账。', input:'先通过预检，再按状态条推进后续动作。', next:'执行后可在执行日志查看摘要和原始返回。'}
};
const SECTION_GUIDE = {
  identity: {title:'项目身份', goal:'确认当前项目鉴权与接入信息。', input:'此区以只读信息为主，必要时先刷新项目身份。', next:'完成后进入构建或发布分区填写参数。'},
  build: {title:'构建', goal:'维护构建、差分、自动化执行路径。', input:'根据流水线填写构建输出、差异词、CLI 路径。', next:'完成后进入发布分区执行向导。'},
  release: {title:'发布', goal:'通过五步向导组织发布参数并执行链路动作。', input:'优先填写核心必填，低频参数可在高级区按需补充。', next:'步骤完成后执行预检/审批/发布/回滚/对账。'},
  ops: {title:'运维', goal:'拉取闭环证据、质量门禁和基础设施健康。', input:'按需触发证据、门禁、运行时快照和指标采样。', next:'结果会同步写入执行日志区。'},
  snapshot: {title:'快照', goal:'查看执行前参数合成结果。', input:'输入变更后自动刷新，便于快速核对关键字段。', next:'核对完成后回到发布或运维分区执行动作。'},
  logs: {title:'执行日志', goal:'阅读结构化执行摘要与原始 JSON。', input:'先看摘要卡，再展开原始响应用于审计排障。', next:'若失败可返回对应分区修正并重试。'}
};
const RELEASE_CHAIN_ORDER = ['precheck','apply','execute','rollback','reconcile'];
const RELEASE_CHAIN_LABEL = {precheck:'预检', apply:'审批', execute:'执行', rollback:'回滚', reconcile:'对账'};
let __releaseStep = 1;
let __releaseSectionInitialized = false;
const __releaseChainState = {precheck:'idle', apply:'idle', execute:'idle', rollback:'idle', reconcile:'idle'};
const FIELD_META = {
  version_name: {desc:'发布单唯一版本标识', sourceLayer:'version', stage:'发布预检', logKey:'ConfigApplied', readback:'version_name'},
  apk_version: {desc:'客户端安装包版本号', sourceLayer:'version', stage:'发布执行', logKey:'ConfigApplied', readback:'apk_version'},
  resource_version: {desc:'资源包版本号', sourceLayer:'version', stage:'发布执行', logKey:'ConfigApplied', readback:'resource_version'},
  config_version: {desc:'配置包版本号', sourceLayer:'version', stage:'发布执行', logKey:'ConfigApplied', readback:'config_version'},
  apk_url: {desc:'APK下载地址', sourceLayer:'upload', stage:'客户端拉取', logKey:'ReleasePublished', readback:'apk_url'},
  resource_url: {desc:'资源拉取地址', sourceLayer:'upload', stage:'客户端热更', logKey:'ReleasePublished', readback:'resource_url'},
  config_url: {desc:'配置拉取地址', sourceLayer:'upload', stage:'客户端热更', logKey:'ReleasePublished', readback:'config_url'},
  gateway_ws: {desc:'网关WebSocket入口', sourceLayer:'runtime', stage:'连接建立', logKey:'TransportSelected', readback:'gateway_ws'},
  login_http: {desc:'登录短链接入口', sourceLayer:'runtime', stage:'登录鉴权', logKey:'EndpointResolve', readback:'login_http'},
  game_ws: {desc:'游戏长连接入口', sourceLayer:'runtime', stage:'会话通信', logKey:'EndpointResolve', readback:'game_ws'},
  battle_udp: {desc:'战斗UDP/KCP入口', sourceLayer:'runtime', stage:'对局同步', logKey:'EndpointResolve', readback:'battle_udp'},
  ops_http: {desc:'运维Ops入口', sourceLayer:'runtime', stage:'运维动作', logKey:'OpsActionExecuted', readback:'ops_http'},
  release_mode: {desc:'发布模式策略', sourceLayer:'strategy', stage:'发布执行', logKey:'ReleaseWorkflow', readback:'release_mode'},
  upload_provider: {desc:'上传存储Provider', sourceLayer:'upload', stage:'上传分发', logKey:'UploadSelected', readback:'upload_provider'},
  approval_reason: {desc:'审批理由/工单摘要', sourceLayer:'project', stage:'审批流', logKey:'ApprovalSubmitted', readback:'reason'},
};
function selectedProjectId(){ return (document.getElementById('projectId').value || '').trim(); }
function selectedEnv(){ return (document.getElementById('env').value || '').trim(); }
function selectedChannel(){ return (document.getElementById('channel').value || '').trim(); }
function selectedPlatform(){ return (document.getElementById('platform').value || 'android').trim(); }
function refreshContextHeader(){
  const projectSel=document.getElementById('projectSelect');
  const ptxt=projectSel?.selectedOptions?.[0]?.text || selectedProjectId() || '-';
  const ctx=[selectedEnv() || '-', selectedChannel() || '-', selectedPlatform() || '-'].join(' / ');
  const pEl=document.getElementById('ctxProjectName');
  const cEl=document.getElementById('ctxContextName');
  if(pEl){ pEl.innerText = ptxt; }
  if(cEl){ cEl.innerText = ctx; }
}
function summarizeResult(d){
  if(!d){ return '暂无执行结果'; }
  if(d.ok === false){ return '执行失败：' + String(d.error || d.message || '请检查缺失项与链路日志'); }
  if(d.ok === true){
    if(d.missing && d.missing.length){ return '未通过：缺失 ' + d.missing.length + ' 个必填项（' + d.missing.join(', ') + '）'; }
    if(d.diff_count !== undefined){ return '对账完成：发现 ' + d.diff_count + ' 项差异'; }
    if(d.generatedAt){ return '闭环/门禁已生成：' + d.generatedAt; }
    return String(d.message || '执行成功，详情可展开查看原始 JSON。');
  }
  return String(d.message || '已更新结果，请查看原始 JSON。');
}
function updateResult(d){
  const resultEl=document.getElementById('result');
  if(resultEl){ resultEl.value = JSON.stringify(d, null, 2); }
  const summaryEl=document.getElementById('resultSummary');
  if(summaryEl){ summaryEl.innerText = summarizeResult(d); }
}
function ensureSectionGuide(){
  let guide=document.getElementById('sectionGuide');
  if(guide){ return guide; }
  const card=document.querySelector('.gm-tab-wrap')?.parentElement;
  if(!card){ return null; }
  guide=document.createElement('div');
  guide.id='sectionGuide';
  guide.className='mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600';
  card.appendChild(guide);
  return guide;
}
function updateSectionGuide(group){
  const guide=ensureSectionGuide();
  if(!guide){ return; }
  const meta=SECTION_GUIDE[group] || SECTION_GUIDE.identity;
  guide.innerHTML = `<div class="font-semibold text-slate-700">${meta.title} · 目标</div><div class="mt-0.5">${meta.goal}</div><div class="mt-1 text-slate-500">输入要求：${meta.input}</div><div class="mt-1 text-indigo-600">下一步动作：${meta.next}</div>`;
}
function validateRequiredFields(fieldIds, markInvalid){
  const ids=(fieldIds && fieldIds.length) ? fieldIds : REQUIRED_RELEASE_FIELDS;
  const missing=[];
  const shouldMark = markInvalid !== false;
  ids.forEach(id=>{
    const el=document.getElementById(id);
    if(!el){ return; }
    const ok=String(el.value||'').trim().length>0;
    if(shouldMark){ el.classList.toggle('border-rose-400', !ok); }
    if(!ok){ missing.push(id); }
  });
  return missing;
}
function getMissingRequiredForStep(step){
  return validateRequiredFields(RELEASE_STEP_REQUIRED_MAP[step] || [], false);
}
function releaseStepStatusText(step){
  const missing=getMissingRequiredForStep(step);
  if(missing.length){ return `<span class="px-2 py-0.5 rounded-full bg-rose-50 text-rose-700">缺失 ${missing.length} 项</span>`; }
  if(step===5){ return `<span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">待执行</span>`; }
  return `<span class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">已完成</span>`;
}
function renderReleaseStepStatus(){
  const info=RELEASE_STEP_INFO[__releaseStep] || RELEASE_STEP_INFO[1];
  const stepList=Array.from({length: RELEASE_STEP_TOTAL}, function(_, idx){
    const step=idx+1;
    return `<div class="flex items-center justify-between gap-2 rounded-lg border ${step===__releaseStep?'border-indigo-300 bg-indigo-50':'border-slate-200 bg-white'} px-2 py-1"><span class="text-[11px] text-slate-600">第${step}步</span>${releaseStepStatusText(step)}</div>`;
  }).join('');
  const target=document.getElementById('releaseStepStatus');
  if(target){
    target.innerHTML = `<div class="font-semibold text-slate-700">当前步骤：${__releaseStep}. ${info.title}</div><div class="mt-1 text-slate-600">目标：${info.goal}</div><div class="mt-1 text-slate-500">输入要求：${info.input}</div><div class="mt-1 text-indigo-600">下一步动作：${info.next}</div><div class="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2">${stepList}</div>`;
  }
}
function chainCardHtml(key){
  const state=__releaseChainState[key] || 'idle';
  const styleByState={
    idle:'border-slate-200 bg-slate-50 text-slate-600',
    pending:'border-amber-200 bg-amber-50 text-amber-700',
    success:'border-emerald-200 bg-emerald-50 text-emerald-700',
    fail:'border-rose-200 bg-rose-50 text-rose-700'
  };
  const labelByState={idle:'未执行', pending:'执行中', success:'成功', fail:'失败'};
  return `<div class="rounded-lg border px-2 py-1 ${styleByState[state] || styleByState.idle}"><div class="font-semibold">${RELEASE_CHAIN_LABEL[key]}</div><div class="text-[11px] mt-0.5">${labelByState[state] || labelByState.idle}</div></div>`;
}
function renderReleaseChainStatus(){
  const el=document.getElementById('releaseChainStatus');
  if(!el){ return; }
  el.innerHTML = RELEASE_CHAIN_ORDER.map(chainCardHtml).join('');
}
function setReleaseChainState(key, state){
  if(!Object.prototype.hasOwnProperty.call(__releaseChainState, key)){ return; }
  __releaseChainState[key] = state;
  renderReleaseChainStatus();
}
function applyReleaseRequiredFilter(){
  const onlyRequired = !!document.getElementById('releaseOnlyRequired')?.checked;
  document.querySelectorAll('#releaseStepPanes .gm-release-step-pane').forEach(function(pane){
    const fields=Array.from(pane.querySelectorAll('.gm-release-field'));
    const hasRequired=fields.some(f=>f.dataset.required==='1');
    fields.forEach(function(field){
      const isRequired = field.dataset.required === '1';
      const shouldHide = onlyRequired && hasRequired && !isRequired;
      field.classList.toggle('hidden', shouldHide);
    });
  });
}
function applyReleaseFieldLayering(){
  document.querySelectorAll('#releaseStepPanes .gm-release-step-pane').forEach(function(pane){
    const step=Number(pane.dataset.step || 0);
    if(!step || step===5 || pane.dataset.layered === '1'){ return; }
    const sourceFields=Array.from(pane.querySelectorAll('.gm-release-field'));
    if(!sourceFields.length){ return; }
    const coreSet=new Set(RELEASE_STEP_CORE_MAP[step] || []);
    const coreFields=[];
    const advancedFields=[];
    sourceFields.forEach(function(field){
      const ctl=field.querySelector('input,select,textarea');
      const fid=(ctl && ctl.id) ? ctl.id : '';
      if(field.dataset.required==='1' || coreSet.has(fid)){ coreFields.push(field); return; }
      advancedFields.push(field);
    });
    pane.innerHTML='';
    const coreDetail=document.createElement('details');
    coreDetail.className='gm-acc';
    coreDetail.setAttribute('open','open');
    coreDetail.innerHTML='<summary><span>核心参数</span><span class="gm-acc-meta">高频与必填字段</span></summary>';
    const coreBody=document.createElement('div');
    coreBody.className='gm-acc-body grid grid-cols-1 md:grid-cols-3 gap-3 text-sm';
    (coreFields.length ? coreFields : sourceFields).forEach(function(field){ coreBody.appendChild(field); });
    coreDetail.appendChild(coreBody);
    pane.appendChild(coreDetail);
    if(advancedFields.length){
      const advDetail=document.createElement('details');
      advDetail.className='gm-acc';
      advDetail.innerHTML='<summary><span>高级参数（低频）</span><span class="gm-acc-meta">默认收起，按需展开</span></summary>';
      const advBody=document.createElement('div');
      advBody.className='gm-acc-body grid grid-cols-1 md:grid-cols-3 gap-3 text-sm';
      advancedFields.forEach(function(field){ advBody.appendChild(field); });
      advDetail.appendChild(advBody);
      pane.appendChild(advDetail);
    }
    pane.dataset.layered='1';
  });
}
function setReleaseStep(step){
  const next=Math.max(1, Math.min(RELEASE_STEP_TOTAL, Number(step)||1));
  __releaseStep = next;
  document.querySelectorAll('.gm-release-step-pane').forEach(function(pane){
    pane.classList.toggle('hidden', Number(pane.dataset.step || 0) !== __releaseStep);
  });
  for(let i=1;i<=RELEASE_STEP_TOTAL;i+=1){
    const btn=document.getElementById('releaseStepBtn-'+i);
    if(!btn){ continue; }
    btn.classList.toggle('gm-tab-btn-active', i===__releaseStep);
  }
  applyReleaseRequiredFilter();
  renderReleaseStepStatus();
  renderReleaseChainStatus();
}
function prevReleaseStep(){ setReleaseStep(__releaseStep-1); }
function nextReleaseStep(){
  const missing=getMissingRequiredForStep(__releaseStep);
  if(missing.length){
    updateResult({ok:false,error:'当前步骤存在未完成必填项',step:__releaseStep,missing});
    return;
  }
  setReleaseStep(__releaseStep+1);
}
async function saveReleaseDraft(){
  try{
    const d=await ensureReleaseEntry();
    updateResult(Object.assign({}, d || {}, {message:'草稿已保存（保持现有接口与字段）'}));
  }catch(err){
    updateResult({ok:false,error:String(err||'草稿保存失败')});
  }
}
function initReleaseSection(){
  if(__releaseSectionInitialized){ return; }
  __releaseSectionInitialized = true;
  applyReleaseFieldLayering();
  const requiredToggle=document.getElementById('releaseOnlyRequired');
  if(requiredToggle){ requiredToggle.addEventListener('change', applyReleaseRequiredFilter); }
  setReleaseStep(1);
}
function switchSection(group){
  const all=['identity','build','release','ops','snapshot','logs'];
  all.forEach(k=>{
    const el=document.getElementById('sec-'+k);
    if(el){ el.style.display=(k===group?'block':'none'); }
    const btn=document.getElementById('tabBtn-'+k);
    if(btn){ btn.classList.toggle('gm-tab-btn-active', k===group); }
  });
  updateSectionGuide(group);
  if(group==='release'){ initReleaseSection(); renderReleaseStepStatus(); renderReleaseChainStatus(); }
}
function upsertOptions(el, values, pick){ if(!el) return; el.innerHTML = (values||[]).map(v=>`<option value="${v}">${v}</option>`).join(''); if(pick && values && values.includes(pick)) el.value = pick; }
function upsertChannelOptions(el, options, pick){
  if(!el) return;
  const rows=(options||[]).filter(x=>x&&x.id).map(x=>({id:String(x.id),name:String(x.name||x.id)}));
  el.innerHTML = rows.map(x=>`<option value="${x.id}">${x.id} · ${x.name}</option>`).join('');
  if(pick && rows.some(x=>x.id===pick)) el.value=pick;
}
function currentReleasePayload(){ return { project_id: selectedProjectId(), env: selectedEnv(), channel: selectedChannel(), platform: selectedPlatform(), version_name: (document.getElementById('versionName').value || '').trim(), server_profile: (document.getElementById('serverProfile').value || '').trim() || 'default', apk_version: (document.getElementById('apkVersion').value || '').trim(), resource_version: (document.getElementById('resourceVersion').value || '').trim(), config_version: (document.getElementById('configVersion').value || '').trim(), apk_url: (document.getElementById('apkUrl').value || '').trim(), resource_url: (document.getElementById('resourceUrl').value || '').trim(), config_url: (document.getElementById('configUrl').value || '').trim(), distribution_method: (document.getElementById('distributionMethod').value || '').trim(), package_name: (document.getElementById('packageName').value || '').trim(), bundle_id: (document.getElementById('bundleId').value || '').trim(), changelog: (document.getElementById('changelog').value || '').trim(), build_output: (document.getElementById('buildOutput').value || '').trim(), project_code: (document.getElementById('projectCode').value || '').trim(), resource_builder: (document.getElementById('resourceBuilder').value || '').trim(), baseline_version_dir: (document.getElementById('baselineVersionDir').value || '').trim(), diff_keyword: (document.getElementById('diffKeyword').value || '').trim(), hot_update_base_url: (document.getElementById('hotUpdateBaseUrl').value || '').trim(), client_version: (document.getElementById('clientVersion').value || '').trim(), upload_provider: (document.getElementById('uploadProvider').value || '').trim(), bucket: (document.getElementById('bucket').value || '').trim(), region: (document.getElementById('region').value || '').trim(), cdn_prefix: (document.getElementById('cdnPrefix').value || '').trim(), path_template: (document.getElementById('pathTemplate').value || '').trim(), automation_plan_path: (document.getElementById('automationPlanPath').value || '').trim(), cli_result_path: (document.getElementById('cliResultPath').value || '').trim(), entry_point: (document.getElementById('entryPoint').value || '').trim(), release_mode: (document.getElementById('releaseMode').value || '').trim(), targets: (document.getElementById('targets').value || '').trim(), code_units: (document.getElementById('codeUnits').value || '').trim(), config_units: (document.getElementById('configUnits').value || '').trim(), asset_units: (document.getElementById('assetUnits').value || '').trim() }; }
function currentProfilePayload(){ return { id: (document.getElementById('serverProfile').value || '').trim() || 'default', name: (document.getElementById('serverProfile').value || '').trim() || 'default', env: selectedEnv(), channel: selectedChannel(), gateway_ws: (document.getElementById('gatewayWs').value||'').trim(), login_http: (document.getElementById('loginHttp').value||'').trim(), game_ws: (document.getElementById('gameWs').value||'').trim(), battle_udp: (document.getElementById('battleUdp').value||'').trim(), ops_http: (document.getElementById('opsHttp').value||'').trim(), notice_url: (document.getElementById('noticeUrl').value||'').trim() }; }
function refreshPreview(){ const p=currentReleasePayload(); document.getElementById('preview').textContent = JSON.stringify({project_id:p.project_id, env:p.env, channel:p.channel, version_name:p.version_name, apk_version:p.apk_version, resource_version:p.resource_version, config_version:p.config_version},null,2); }
function renderDictRows(rows){ const cat=(document.getElementById('dictCategory')?.value||'all'); const kw=(document.getElementById('dictKeyword')?.value||'').trim().toLowerCase(); const body=document.getElementById('closureTableBody'); if(!body) return; const filtered=(rows||[]).filter(x=>{ const okCat=(cat==='all'||String(x.sourceLayer||'')===cat); const okKw=(!kw||String(x.key||'').toLowerCase().includes(kw)||String(x.description||'').toLowerCase().includes(kw)); return okCat&&okKw;}); body.innerHTML = filtered.map(x=>`<tr class="border-b"><td class="px-2 py-1">${x.key||'-'}</td><td class="px-2 py-1">${x.description||'-'}</td><td class="px-2 py-1">${x.sourceLayer||x.source||'-'}</td><td class="px-2 py-1">${x.value===undefined||x.value===null||x.value===''?'-':String(x.value)}</td><td class="px-2 py-1">${x.effectiveStage||'-'}</td><td class="px-2 py-1">${(x.logKey||'-')+' / '+(x.readbackField||'-')}</td></tr>`).join('') || '<tr><td class="px-2 py-2" colspan="6">暂无参数映射</td></tr>'; }
function renderBeforeAfterDiff(beforeObj, afterObj){
  const body=document.getElementById('beforeAfterTableBody');
  if(!body) return;
  const keys=Array.from(new Set([...(Object.keys(beforeObj||{})), ...(Object.keys(afterObj||{}))])).sort();
  if(!keys.length){ body.innerHTML='<tr><td class="px-2 py-2 text-slate-400" colspan="4">暂无可对比字段</td></tr>'; return; }
  body.innerHTML=keys.map(k=>{
    const b=(beforeObj||{})[k]; const a=(afterObj||{})[k];
    const same=String(b??'')===String(a??'');
    const status=same?'<span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">一致</span>':'<span class="px-2 py-0.5 rounded bg-amber-50 text-amber-700">变化</span>';
    return `<tr class="border-b"><td class="px-2 py-1 font-medium text-slate-700">${k}</td><td class="px-2 py-1">${b===undefined||b===null||b===''?'-':String(b)}</td><td class="px-2 py-1">${a===undefined||a===null||a===''?'-':String(a)}</td><td class="px-2 py-1">${status}</td></tr>`;
  }).join('');
}
async function loadCatalog(){ const r=await fetch('/api/gm-ops/projects/catalog'); const d=await r.json(); if(!d.ok){ updateResult(d); return; } const rows=d.data||[]; const sel=document.getElementById('projectSelect'); sel.innerHTML=rows.map(p=>`<option value="${p.project_id}">${p.project_id} / ${p.project_name}</option>`).join(''); const q=new URLSearchParams(window.location.search); const qpid=(q.get('project_id')||'').trim(); if(qpid && rows.some(x=>String(x.project_id)===qpid)){ sel.value=qpid; } refreshContextHeader(); if(rows.length){ document.getElementById('projectId').value=(sel.value||rows[0].project_id); await loadWorkspace(); } }
async function loadWorkspace(){ const pid=(document.getElementById('projectSelect').value||'').trim(); if(!pid){ return; } document.getElementById('projectId').value=pid; const rs=await fetch('/api/gm-ops/projects/catalog?project_id='+encodeURIComponent(pid)); const d=await rs.json(); if(!d.ok){ updateResult(d); return; } const item=(d.data||[])[0]||{}; upsertOptions(document.getElementById('env'), item.envs || ['dev','test','staging','prod'], item.default_env || 'dev'); upsertChannelOptions(document.getElementById('channel'), item.channel_options || [], item.default_channel || 'default'); document.getElementById('gameId').value=item.game_id||''; document.getElementById('gameKeyMasked').value=item.game_key_masked||'***'; document.getElementById('serverProfile').value=item.default_server_profile||'default'; document.getElementById('credentialSummary').innerText=`gameId: ${item.game_id||'-'} | gameKey: ${item.game_key_masked||'***'} | 更新时间: ${item.updated_at||'-'}`; document.getElementById('workspaceSummary').innerText=`项目 ${item.project_id||pid}，可用环境 ${(item.envs||[]).join('/')||'-'}，可用渠道 ${(item.channel_options||[]).map(x=>x.id+'·'+x.name).join('/')||'-'}`; refreshContextHeader(); refreshPreview(); updateResult({ok:true, workspace:item}); }
async function saveReleaseProfile(){ const r=await fetch('/api/gm-ops/release/profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(currentProfilePayload())}); updateResult(await r.json()); }
async function ensureReleaseEntry(){ const r=await fetch('/api/gm-ops/release/versions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(currentReleasePayload())}); return await r.json(); }
async function releasePrecheck(){
  const missing=validateRequiredFields();
  if(missing.length){ setReleaseChainState('precheck','fail'); updateResult({ok:false,error:'必填字段未完成',missing}); return; }
  setReleaseChainState('precheck','pending');
  try{
    await ensureReleaseEntry();
    const r=await fetch('/api/gm-ops/release/precheck',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(currentReleasePayload())});
    const d=await r.json();
    setReleaseChainState('precheck', d.ok===false ? 'fail' : 'success');
    updateResult(d);
  }catch(err){
    setReleaseChainState('precheck','fail');
    updateResult({ok:false,error:String(err||'预检失败')});
  }
}
async function releaseApply(){
  const missing=validateRequiredFields();
  if(missing.length){ setReleaseChainState('apply','fail'); updateResult({ok:false,error:'必填字段未完成',missing}); return; }
  setReleaseChainState('apply','pending');
  try{
    await ensureReleaseEntry();
    const base=currentReleasePayload();
    const target=`${base.project_id}:${base.version_name}`;
    const p={actionType:'release_publish',domain:'release',target:target,payload:base,operatorContext:{reason:(document.getElementById('reason').value||'发布审批').trim()||'发布审批'}};
    const r=await fetch('/api/gm-ops/action/approval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
    const d=await r.json();
    setReleaseChainState('apply', d.ok===false ? 'fail' : 'success');
    updateResult(d);
  }catch(err){
    setReleaseChainState('apply','fail');
    updateResult({ok:false,error:String(err||'审批失败')});
  }
}
async function releaseExecute(){
  const missing=validateRequiredFields();
  if(missing.length){ setReleaseChainState('execute','fail'); updateResult({ok:false,error:'必填字段未完成',missing}); return; }
  setReleaseChainState('execute','pending');
  try{
    const base=currentReleasePayload();
    const target=`${base.project_id}:${base.version_name}`;
    const p={actionType:'release_publish',domain:'release',target:target,payload:base,approvalContext:{approved:true},operatorContext:{reason:'发布执行'}};
    const r=await fetch('/api/gm-ops/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
    const d=await r.json();
    setReleaseChainState('execute', d.ok===false ? 'fail' : 'success');
    updateResult(d);
  }catch(err){
    setReleaseChainState('execute','fail');
    updateResult({ok:false,error:String(err||'执行失败')});
  }
}
async function releaseRollback(){
  setReleaseChainState('rollback','pending');
  try{
    const r=await fetch('/api/gm-ops/release/rollback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(currentReleasePayload())});
    const d=await r.json();
    setReleaseChainState('rollback', d.ok===false ? 'fail' : 'success');
    updateResult(d);
  }catch(err){
    setReleaseChainState('rollback','fail');
    updateResult({ok:false,error:String(err||'回滚失败')});
  }
}
async function releaseReconcile(){
  setReleaseChainState('reconcile','pending');
  try{
    const r=await fetch('/api/gm-ops/release/reconcile?'+new URLSearchParams(currentReleasePayload()));
    const d=await r.json();
    setReleaseChainState('reconcile', d.ok===false ? 'fail' : 'success');
    updateResult(d);
  }catch(err){
    setReleaseChainState('reconcile','fail');
    updateResult({ok:false,error:String(err||'对账失败')});
  }
}
async function loadClosureEvidence(){ const r=await fetch('/api/gm-ops/closure-evidence?'+new URLSearchParams(currentReleasePayload())); updateResult(await r.json()); }
async function loadParameterClosure(){
  const payload=currentReleasePayload();
  const q=new URLSearchParams(payload);
  const r=await fetch(`/api/projects/${encodeURIComponent(selectedProjectId())}/release/parameter-dictionary?`+q.toString());
  const d=await r.json();
  __dictRows=(d.fields||[]);
  renderDictRows(__dictRows);
  if(!__dictRows.length){
    const fallbackRows=Object.keys(payload).sort().map(k=>{
      const meta=FIELD_META[k]||{};
      return {key:k,description:meta.desc||'发布/构建参数',sourceLayer:meta.sourceLayer||'runtime',value:payload[k],effectiveStage:meta.stage||'发布执行',logKey:meta.logKey||'ConfigApplied',readbackField:meta.readback||k};
    });
    renderDictRows(fallbackRows);
  }
  updateResult(d);
}
async function compareBeforeAfter(){
  const q=new URLSearchParams(currentReleasePayload());
  const r=await fetch('/api/gm-ops/release/reconcile?'+q.toString());
  const d=await r.json();
  const rel=(d.release_record||{}), cfg=(d.configured_release||{});
  const keys=Object.keys(cfg), changes=[];
  keys.forEach(k=>{ if(String(cfg[k]||'')!==String(rel[k]||'')){ changes.push(`${k}: 期望=${cfg[k]||'-'} | 实际=${rel[k]||'-'}`); }});
  renderBeforeAfterDiff(cfg, rel);
  document.getElementById('dictCompareHint').innerText = changes.length ? `发现 ${changes.length} 项差异（执行前后）` : '执行前后一致';
  updateResult({ok:d.ok,diff_count:changes.length,diffs:changes,raw:d});
}
async function runQualityGate(){ const r=await fetch('/api/gm-ops/quality-gate?'+new URLSearchParams(currentReleasePayload())); updateResult(await r.json()); }
async function loadRuntimeSnapshot(){ const r=await fetch('/api/gm-ops/runtime-snapshot'); updateResult(await r.json()); }
async function loadInfraMetrics(){ const r=await fetch('/api/gm-ops/infra/metrics'); const d=await r.json(); updateResult(d); document.getElementById('infraSummary').innerText=`Mongo: ${d.mongo?.ok?'OK':'FAIL'} | Redis: ${d.redis?.ok?'OK':'FAIL'} | QPS: ${d.observability?.qps||'-'} | P99: ${d.observability?.p99Ms||'-'}ms`; }
['versionName','apkVersion','resourceVersion','configVersion','apkUrl','resourceUrl','configUrl','distributionMethod','packageName','bundleId','changelog','reason','serverProfile','env','channel','platform','buildOutput','projectCode','resourceBuilder','baselineVersionDir','diffKeyword','hotUpdateBaseUrl','clientVersion','uploadProvider','bucket','region','cdnPrefix','pathTemplate','automationPlanPath','cliResultPath','entryPoint','releaseMode','targets','codeUnits','configUnits','assetUnits'].forEach(function(id){ const el=document.getElementById(id); if(el){ el.addEventListener('input', refreshPreview); el.addEventListener('change', refreshPreview); } });
const dc=document.getElementById('dictCategory'); if(dc){ dc.addEventListener('change', ()=>renderDictRows(__dictRows)); }
const dk=document.getElementById('dictKeyword'); if(dk){ dk.addEventListener('input', ()=>renderDictRows(__dictRows)); }
document.getElementById('projectSelect').addEventListener('change', loadWorkspace);
['env','channel','platform'].forEach(function(id){ const el=document.getElementById(id); if(el){ el.addEventListener('change', refreshContextHeader); } });
refreshContextHeader();
switchSection('identity'); loadCatalog();
</script>
"""
    try:
        from routes.admin_routes import _admin_layout
        return _admin_layout(content, "GM运营中心", back_href="/admin")
    except Exception:
        html = """
<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>GM运营中心</title><link rel=\"stylesheet\" href=\"/static/tailwind.css\"></head>
<body class=\"bg-slate-50 min-h-screen\"><div class=\"max-w-7xl mx-auto p-6\">""" + content + """</div></body></html>
"""
        return render_template_string(html)

def _build_closure_evidence(project_id: str, env: str, channel: str, platform: str, version_name: str) -> Dict[str, Any]:
    release = _find_best_release(project_id, env, channel, platform, version_name, published_only=False)
    profile = _resolve_profile(str(release.get("server_profile") if release else ""), env, channel) if release else {}
    evidence = [
        {"field": "apk_version", "source": "release_version", "runtime": bool(str((release or {}).get("apk_version") or "").strip()), "logKey": "ConfigApplied"},
        {"field": "resource_version", "source": "release_version", "runtime": bool(str((release or {}).get("resource_version") or "").strip()), "logKey": "ConfigApplied"},
        {"field": "config_version", "source": "release_version", "runtime": bool(str((release or {}).get("config_version") or "").strip()), "logKey": "ConfigApplied"},
        {"field": "gateway_ws", "source": "release_profile", "runtime": bool(str((profile or {}).get("gateway_ws") or "").strip()), "logKey": "TransportSelected"},
        {"field": "login_http", "source": "release_profile", "runtime": bool(str((profile or {}).get("login_http") or "").strip()), "logKey": "EndpointResolve"},
        {"field": "game_ws", "source": "release_profile", "runtime": bool(str((profile or {}).get("game_ws") or "").strip()), "logKey": "EndpointResolve"},
        {"field": "game_id/game_key", "source": "project_credentials", "runtime": bool(str((projects_db.get(project_id) or {}).get("game_id") or "").strip() and str((projects_db.get(project_id) or {}).get("game_key") or "").strip()), "logKey": "AuthSession"},
    ]
    score = sum(1 for row in evidence if row["runtime"])
    return {"project_id": project_id, "env": env, "channel": channel, "platform": platform, "version_name": version_name, "evidence": evidence, "score": score, "total": len(evidence)}


def _closure_evidence_core(project_id_raw: str, env: str, channel: str, platform: str, version_name: str):
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404
    report = _build_closure_evidence(resolved, env, channel, platform, version_name)
    report["ok"] = report["score"] == report["total"]
    report["generatedAt"] = datetime.now().isoformat()
    return jsonify(report)


def _quality_gate_core(project_id_raw: str, env: str, channel: str, platform: str, version_name: str):
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404

    release = _find_best_release(resolved, env, channel, platform, version_name, published_only=False)
    if release:
        required_keys = ["apk_url", "resource_url", "config_url", "apk_version", "resource_version", "config_version"]
        missing = [k for k in required_keys if not str(release.get(k) or "").strip()]
        profile = _resolve_profile(str(release.get("server_profile") or ""), str(release.get("env") or env), str(release.get("channel") or channel))
        profile_missing = [k for k in ("gateway_ws", "login_http", "game_ws", "ops_http") if not str((profile or {}).get(k) or "").strip()]
        precheck_data = {"ok": len(missing) == 0 and len(profile_missing) == 0, "missing_release_fields": missing, "missing_profile_fields": profile_missing}
    else:
        precheck_data = {"ok": False, "error": "release not found"}
    precheck_ok = bool(precheck_data.get("ok"))

    evidence = _build_closure_evidence(resolved, env, channel, platform, version_name)
    evidence_ok = evidence["score"] == evidence["total"]
    infra_data = _build_infra_metrics_payload()
    infra_ok = bool((infra_data.get("mongo") or {}).get("ok")) and bool((infra_data.get("redis") or {}).get("ok"))

    gates = [
        {"name": "release_precheck", "ok": precheck_ok, "detail": precheck_data},
        {"name": "closure_evidence", "ok": evidence_ok, "detail": evidence},
        {"name": "infra_mongo_redis", "ok": infra_ok, "detail": {"mongo": infra_data.get("mongo"), "redis": infra_data.get("redis")}},
    ]
    passed = all(item["ok"] for item in gates)
    return jsonify({"ok": passed, "project_id": resolved, "env": env, "channel": channel, "platform": platform, "version_name": version_name, "gates": gates, "generatedAt": datetime.now().isoformat()})


@bp.route("/api/gm-ops/projects/credentials")
@admin_required("gm_ops")
def gm_projects_credentials_list():
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    rows = []
    for project_id, payload in (projects_db or {}).items():
        if not isinstance(payload, dict):
            continue
        rows.append(_get_project_credentials(str(project_id)))
    rows.sort(key=lambda x: x.get("project_id") or "")
    return jsonify({"ok": True, "count": len(rows), "data": rows})


@bp.route("/api/gm-ops/projects/catalog")
@admin_required("gm_ops")
def gm_projects_catalog():
    """项目优先工作台目录：返回项目身份、渠道、环境、默认参数。"""
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    project_id_filter = (request.args.get("project_id") or "").strip()
    rows: List[Dict[str, Any]] = []
    for project_id, payload in (projects_db or {}).items():
        pid = str(project_id).strip()
        if project_id_filter and pid != project_id_filter:
            continue
        item = payload if isinstance(payload, dict) else {}
        ec = _project_envs_and_channels(pid)
        default_env = str(item.get("default_env") or (ec["envs"][0] if ec["envs"] else "dev")).strip() or "dev"
        default_channel = str(item.get("default_channel") or (ec["channels"][0] if ec["channels"] else "default")).strip() or "default"
        channel_options = []
        for item_channel in get_channels_for_project(pid):
            cid = str(item_channel.get("id") or "").strip()
            cname = str(item_channel.get("name") or cid).strip()
            if cid:
                channel_options.append({"id": cid, "name": cname})
        rows.append(
            {
                "project_id": pid,
                "project_name": str(item.get("name") or pid),
                "game_id": str(item.get("game_id") or "").strip(),
                "game_key_masked": (str(item.get("game_key") or "").strip()[:6] + "***") if str(item.get("game_key") or "").strip() else "",
                "default_server_profile": str(item.get("default_server_profile") or "default").strip() or "default",
                "default_env": default_env,
                "default_channel": default_channel,
                "envs": ec["envs"],
                "channels": ec["channels"],
                "channel_options": channel_options,
                "updated_at": str(item.get("game_key_updated_at") or item.get("updated_at") or ""),
            }
        )
    rows.sort(key=lambda x: x.get("project_id") or "")
    return jsonify({"ok": True, "count": len(rows), "data": rows})


@bp.route("/api/gm-ops/projects/credentials/apply", methods=["POST"])
@admin_required("gm_ops")
def gm_projects_credentials_apply():
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    project_id_raw = str(payload.get("project_id") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404

    project = projects_db.get(resolved) or {}
    if str(project.get("game_id") or "").strip() or str(project.get("game_key") or "").strip():
        return jsonify({"ok": False, "error": "项目凭据已初始化且不可修改。如需重置请走超级管理员线下流程。"}), 409

    mode = str(payload.get("mode") or "regen").strip().lower()  # regen|manual
    game_id = str(payload.get("game_id") or "").strip()
    game_key = str(payload.get("game_key") or "").strip()

    if mode == "manual":
        if not game_id or not game_key:
            return jsonify({"ok": False, "error": "manual mode requires game_id and game_key"}), 400
    else:
        game_id = game_id or (f"{resolved.lower()}-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        game_key = secrets.token_urlsafe(24)

    project["game_id"] = game_id
    project["game_key"] = game_key
    project["game_key_updated_at"] = datetime.now().isoformat()
    project["game_key_updated_by"] = _current_user()
    projects_db[resolved] = project
    save_projects()

    log_audit("gm_project_credentials_apply", f"project={resolved}; game_id={game_id}; mode={mode}")
    return jsonify({"ok": True, "data": _get_project_credentials(resolved), "full_game_key": game_key})


@bp.route("/api/gm-ops/projects/credentials/sync", methods=["GET", "POST"])
@admin_required("gm_ops")
def gm_projects_credentials_sync():
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    if request.method == "GET":
        project_id_raw = (request.args.get("project_id") or "").strip()
        ok, resolved = _ensure_project_exists(project_id_raw)
        if not ok:
            return jsonify({"ok": False, "error": resolved}), 404
        item = projects_db.get(resolved) or {}
        return jsonify(
            {
                "ok": True,
                "data": {
                    "project_id": resolved,
                    "game_id": str(item.get("game_id") or "").strip(),
                    "game_key": str(item.get("game_key") or "").strip(),
                    "remote_version": str(item.get("game_key_updated_at") or "").strip(),
                },
                "remote": {
                    "project_id": resolved,
                    "game_id": str(item.get("game_id") or "").strip(),
                    "game_key_masked": (str(item.get("game_key") or "").strip()[:6] + "***") if str(item.get("game_key") or "").strip() else "",
                    "updated_at": str(item.get("game_key_updated_at") or "").strip(),
                },
            }
        )

    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode") or "push").strip().lower()
    project_id_raw = str(payload.get("project_id") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404
    if mode != "push":
        return jsonify({"ok": False, "error": "unsupported mode"}), 400

    project = projects_db.get(resolved) or {}
    if str(project.get("game_id") or "").strip() or str(project.get("game_key") or "").strip():
        return jsonify({"ok": False, "error": "项目凭据为只读，创建后不可修改"}), 409

    game_id = str(payload.get("game_id") or "").strip()
    game_key = str(payload.get("game_key") or "").strip()
    if not game_id or not game_key:
        return jsonify({"ok": False, "error": "game_id and game_key required"}), 400

    project["game_id"] = game_id
    project["game_key"] = game_key
    project["game_key_updated_at"] = datetime.now().isoformat()
    project["game_key_updated_by"] = _current_user()
    projects_db[resolved] = project
    save_projects()
    log_audit("gm_project_credentials_sync_push", f"project={resolved}; game_id={game_id}")
    return jsonify({"ok": True, "project_id": resolved, "remote_version": project["game_key_updated_at"]})


@bp.route("/api/gm-ops/projects/credentials/sync-token", methods=["GET", "POST"])
def gm_projects_credentials_sync_token():
    """供 Unity 编辑器使用的 token 鉴权同步入口。"""
    if not _allow_ci_access():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    if request.method == "GET":
        project_id_raw = (request.args.get("project_id") or "").strip()
        ok, resolved = _ensure_project_exists(project_id_raw)
        if not ok:
            return jsonify({"ok": False, "error": resolved}), 404
        item = projects_db.get(resolved) or {}
        return jsonify(
            {
                "ok": True,
                "data": {
                    "project_id": resolved,
                    "game_id": str(item.get("game_id") or "").strip(),
                    "game_key": str(item.get("game_key") or "").strip(),
                    "remote_version": str(item.get("game_key_updated_at") or "").strip(),
                },
            }
        )

    payload = request.get_json(silent=True) or {}
    project_id_raw = str(payload.get("project_id") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404
    project = projects_db.get(resolved) or {}
    if str(project.get("game_id") or "").strip() or str(project.get("game_key") or "").strip():
        return jsonify({"ok": False, "error": "project credentials immutable"}), 409

    game_id = str(payload.get("game_id") or "").strip()
    game_key = str(payload.get("game_key") or "").strip()
    if not game_id or not game_key:
        return jsonify({"ok": False, "error": "game_id and game_key required"}), 400
    project["game_id"] = game_id
    project["game_key"] = game_key
    project["game_key_updated_at"] = datetime.now().isoformat()
    project["game_key_updated_by"] = "editor-token"
    projects_db[resolved] = project
    save_projects()
    return jsonify({"ok": True, "project_id": resolved, "remote_version": project["game_key_updated_at"]})


@bp.route("/api/gm-ops/projects/credentials/generate", methods=["POST"])
@admin_required("gm_ops")
def gm_projects_credentials_generate():
    """为项目生成新的 gameId/gameKey（用于初始化或重置）。"""
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id_raw = str(payload.get("project_id") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404

    project = projects_db.get(resolved) or {}
    if str(project.get("game_id") or "").strip() or str(project.get("game_key") or "").strip():
        return jsonify({"ok": False, "error": "项目凭据已存在，不可重复生成"}), 409

    game_id, game_key = _generate_project_credentials(resolved)
    project["game_id"] = game_id
    project["game_key"] = game_key
    project["game_key_updated_at"] = datetime.now().isoformat()
    project["game_key_updated_by"] = _current_user()
    projects_db[resolved] = project
    save_projects()
    log_audit("gm_project_credentials_generate", f"project={resolved}; game_id={game_id}")
    return jsonify({"ok": True, "project_id": resolved, "game_id": game_id, "game_key": game_key, "updated_at": project["game_key_updated_at"]})


@bp.route("/api/gm-ops/action-catalog")
@admin_required("gm_ops")
def gm_ops_catalog():
    return jsonify({"ok": True, "data": ACTION_CATALOG})


@bp.route("/api/gm-ops/runtime-snapshot")
@admin_required("gm_ops")
def gm_ops_runtime_snapshot():
    if not (_can_execute("gm.audit.view") or _can_execute("gm.ops.execute")):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    result = _client.get_runtime_snapshot(_current_user(), _current_role())
    return jsonify(result), (200 if result.get("success") else 502)


@bp.route("/api/gm-ops/release/versions")
@admin_required("gm_ops")
def gm_ops_release_versions():
    project_id_raw = (request.args.get("project_id") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404
    versions = project_versions_db.get(resolved) or []
    return jsonify({"ok": True, "project_id": resolved, "count": len(versions), "data": versions})


@bp.route("/api/gm-ops/release/versions", methods=["POST"])
@admin_required("gm_ops")
def gm_ops_release_upsert():
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    project_id_raw = str(payload.get("project_id") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404

    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else payload
    versions = project_versions_db.get(resolved) or []
    if not str(entry.get("id") or "").strip():
        version_name = str(entry.get("version_name") or "").strip()
        env = str(entry.get("env") or "").strip()
        channel = str(entry.get("channel") or "").strip()
        platform = str(entry.get("platform") or "android").strip().lower()
        for it in versions:
            if (
                str(it.get("version_name") or "").strip() == version_name
                and str(it.get("env") or "").strip() == env
                and str(it.get("channel") or "").strip() == channel
                and str(it.get("platform") or "android").strip().lower() == platform
            ):
                entry["id"] = str(it.get("id") or "").strip()
                break
    normalized = _normalize_release_entry(entry)
    replaced = False
    for i, item in enumerate(versions):
        if str(item.get("id") or "") == normalized["id"]:
            versions[i] = {**item, **normalized}
            replaced = True
            break
    if not replaced:
        versions.append(normalized)
    project_versions_db[resolved] = versions
    save_project_versions()

    log_audit("gm_release_upsert", f"project={resolved}; version={normalized.get('version_name')}; id={normalized.get('id')}")
    return jsonify({"ok": True, "project_id": resolved, "entry": normalized, "replaced": replaced})


@bp.route("/api/gm-ops/release/precheck", methods=["POST"])
@admin_required("gm_ops")
def gm_release_precheck():
    payload = request.get_json(silent=True) or {}
    project_id_raw = str(payload.get("project_id") or "").strip()
    version_name = str(payload.get("version_name") or "").strip()
    platform = str(payload.get("platform") or "android").strip().lower()
    env = str(payload.get("env") or "").strip()
    channel = str(payload.get("channel") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404

    release = _find_best_release(resolved, env, channel, platform, version_name, published_only=False)
    if not release:
        return jsonify({"ok": False, "error": "release not found"}), 404

    required_keys = ["apk_url", "resource_url", "config_url", "apk_version", "resource_version", "config_version"]
    missing = [k for k in required_keys if not str(release.get(k) or "").strip()]
    profile = _resolve_profile(str(release.get("server_profile") or ""), str(release.get("env") or env), str(release.get("channel") or channel))
    profile_missing = [k for k in ("gateway_ws", "login_http", "game_ws", "ops_http") if not str((profile or {}).get(k) or "").strip()]
    return jsonify(
        {
            "ok": len(missing) == 0 and len(profile_missing) == 0,
            "project_id": resolved,
            "version_id": release.get("id"),
            "version_name": release.get("version_name"),
            "missing_release_fields": missing,
            "missing_profile_fields": profile_missing,
            "publish_status": release.get("publish_status"),
            "checked_at": datetime.now().isoformat(),
        }
    )


@bp.route("/api/gm-ops/release/publish", methods=["POST"])
@admin_required("gm_ops")
def gm_release_publish():
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    project_id_raw = str(payload.get("project_id") or "").strip()
    version_name = str(payload.get("version_name") or "").strip()
    platform = str(payload.get("platform") or "android").strip().lower()
    env = str(payload.get("env") or "").strip()
    channel = str(payload.get("channel") or "").strip()

    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404

    release = _find_best_release(resolved, env, channel, platform, version_name, published_only=False)
    if not release:
        return jsonify({"ok": False, "error": "release not found"}), 404

    target_id = f"{resolved}:{release.get('version_name') or release.get('id')}"
    approved_ref = get_approved_approval("version_publish", target_id)
    if not approved_ref:
        return jsonify({"ok": False, "error": "approval required", "message": "请先审批 version_publish。", "target_id": target_id}), 412

    release["publish_status"] = "published"
    release["approval_id"] = approved_ref.get("id") or ""
    release["publish_trace_id"] = uuid.uuid4().hex[:16]
    release["updated_at"] = datetime.now().isoformat()
    release["updated_by"] = _current_user()

    versions = project_versions_db.get(resolved) or []
    for i, item in enumerate(versions):
        if str(item.get("id") or "") == str(release.get("id") or ""):
            versions[i] = release
            break
    project_versions_db[resolved] = versions
    save_project_versions()

    log_audit("gm_release_publish", f"project={resolved}; version={release.get('version_name')}; trace={release.get('publish_trace_id')}")
    return jsonify({"ok": True, "project_id": resolved, "entry": release})


@bp.route("/api/gm-ops/release/rollback", methods=["POST"])
@admin_required("gm_ops")
def gm_release_rollback():
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    project_id_raw = str(payload.get("project_id") or "").strip()
    version_name = str(payload.get("version_name") or "").strip()
    platform = str(payload.get("platform") or "android").strip().lower()
    env = str(payload.get("env") or "").strip()
    channel = str(payload.get("channel") or "").strip()

    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404

    release = _find_best_release(resolved, env, channel, platform, version_name, published_only=False)
    if not release:
        return jsonify({"ok": False, "error": "release not found"}), 404

    release["publish_status"] = "rolled_back"
    release["rollback_trace_id"] = uuid.uuid4().hex[:16]
    release["updated_at"] = datetime.now().isoformat()
    release["updated_by"] = _current_user()

    versions = project_versions_db.get(resolved) or []
    for i, item in enumerate(versions):
        if str(item.get("id") or "") == str(release.get("id") or ""):
            versions[i] = release
            break
    project_versions_db[resolved] = versions
    save_project_versions()

    log_audit("gm_release_rollback", f"project={resolved}; version={release.get('version_name')}; trace={release.get('rollback_trace_id')}")
    return jsonify({"ok": True, "project_id": resolved, "entry": release})


@bp.route("/api/gm-ops/release/reconcile")
@admin_required("gm_ops")
def gm_release_reconcile():
    project_id_raw = (request.args.get("project_id") or "").strip()
    version_name = str(request.args.get("version_name") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    env = str(request.args.get("env") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404
    release = _find_best_release(resolved, env, channel, platform, version_name, published_only=False)
    if not release:
        return jsonify({"ok": False, "error": "release not found"}), 404
    profile = _resolve_profile(str(release.get("server_profile") or ""), str(release.get("env") or env), str(release.get("channel") or channel))
    snapshot = _client.get_runtime_snapshot(_current_user(), _current_role())
    return jsonify(
        {
            "ok": True,
            "project_id": resolved,
            "release": release,
            "profile": profile,
            "runtime_snapshot": snapshot,
            "reconcile_at": datetime.now().isoformat(),
        }
    )


@bp.route("/api/gm-ops/release/profiles")
@admin_required("gm_ops")
def gm_ops_release_profiles_list():
    if not (_can_execute("gm.release.execute") or _can_execute("gm.audit.view")):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    profiles = _load_release_profiles()
    return jsonify({"ok": True, "count": len(profiles), "data": profiles})


@bp.route("/api/gm-ops/release/profiles", methods=["POST"])
@admin_required("gm_ops")
def gm_ops_release_profiles_upsert():
    if not _can_execute("gm.release.execute"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    profile = _normalize_release_profile(payload)

    profiles = _load_release_profiles()
    replaced = False
    for i, item in enumerate(profiles):
        if str(item.get("id") or "") == profile["id"]:
            profiles[i] = {**item, **profile}
            replaced = True
            break
    if not replaced:
        profiles.append(profile)
    _save_release_profiles(profiles)
    log_audit("gm_release_profile_upsert", f"profile={profile.get('id')}; env={profile.get('env')}; channel={profile.get('channel')}")
    return jsonify({"ok": True, "replaced": replaced, "entry": profile})


def _build_infra_metrics_payload():
    mongo_uri = str(get_system_config("MONGO_URI", "") or "")
    redis_uri = str(get_system_config("REDIS_URI", "") or "")
    mongo_host, mongo_port = _parse_host_port_from_uri(mongo_uri, 27017)
    redis_host, redis_port = _parse_host_port_from_uri(redis_uri, 6379)

    mongo_tcp = _check_tcp_latency(mongo_host, mongo_port)
    redis_tcp = _check_tcp_latency(redis_host, redis_port)

    mongo_metrics = {"ok": mongo_tcp.get("ok"), "host": mongo_host, "port": mongo_port, "latencyMs": mongo_tcp.get("latencyMs"), "error": mongo_tcp.get("error")}
    redis_metrics = {"ok": redis_tcp.get("ok"), "host": redis_host, "port": redis_port, "latencyMs": redis_tcp.get("latencyMs"), "error": redis_tcp.get("error")}
    snapshot = _client.get_runtime_snapshot(_current_user(), _current_role())
    data = (snapshot or {}).get("data") or {}
    observability = {
        "qps": data.get("qps", data.get("QPS", 0)),
        "p99Ms": data.get("p99Ms", data.get("P99", 0)),
        "reconnectSuccessRate": data.get("reconnectSuccessRate", data.get("ReconnectSuccessRate", 0)),
        "heartbeatTimeoutRate": data.get("heartbeatTimeoutRate", data.get("HeartbeatTimeoutRate", 0)),
        "messageBacklog": data.get("messageBacklog", data.get("MessageBacklog", 0)),
    }

    storage = _client.get_storage_metrics(_current_user(), _current_role())
    storage_data = (storage or {}).get("data") or {}
    # 当直连端口探测不可达但 Ops 侧已返回有效存储观测时，视为基础设施可观测链路可用。
    mongo_from_ops = storage_data.get("mongo") if isinstance(storage_data, dict) else None
    redis_from_ops = storage_data.get("redis") if isinstance(storage_data, dict) else None
    if not mongo_metrics.get("ok") and isinstance(mongo_from_ops, dict) and bool(mongo_from_ops.get("enabled")):
        mongo_metrics["ok"] = True
        if mongo_metrics.get("error"):
            mongo_metrics["error"] = ""
    if not redis_metrics.get("ok") and isinstance(redis_from_ops, dict) and bool(redis_from_ops.get("enabled")):
        redis_metrics["ok"] = True
        if redis_metrics.get("error"):
            redis_metrics["error"] = ""
    return {
        "ok": True,
        "mongo": mongo_metrics,
        "redis": redis_metrics,
        "slowQuery": storage_data.get("slowQuery", {"supported": False, "message": "服务端未返回慢查询统计"}),
        "hotspot": storage_data.get("hotspot", {"supported": False, "message": "服务端未返回热点统计"}),
        "observability": observability,
        "updated_at": datetime.now().isoformat(),
    }


@bp.route("/api/gm-ops/infra/metrics")
@admin_required("gm_ops")
def gm_ops_infra_metrics():
    if not (_can_execute("gm.audit.view") or _can_execute("gm.ops.execute")):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify(_build_infra_metrics_payload())


@bp.route("/api/gm-ops/storage/metrics")
@admin_required("gm_ops")
def gm_ops_storage_metrics():
    if not (_can_execute("gm.audit.view") or _can_execute("gm.ops.execute")):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    result = _client.get_storage_metrics(_current_user(), _current_role())
    return jsonify(result), (200 if result.get("success") else 502)


@bp.route("/api/gm-ops/closure-evidence")
@admin_required("gm_ops")
def gm_ops_closure_evidence():
    project_id_raw = (request.args.get("project_id") or "").strip()
    env = str(request.args.get("env") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    version_name = str(request.args.get("version_name") or "").strip()
    return _closure_evidence_core(project_id_raw, env, channel, platform, version_name)


@bp.route("/api/projects/<project_id>/release/parameter-dictionary")
@admin_required("gm_ops")
def gm_project_release_parameter_dictionary(project_id):
    env = str(request.args.get("env") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    version_name = str(request.args.get("version_name") or "").strip()
    ok, resolved = _ensure_project_exists(project_id)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404
    release = _find_best_release(resolved, env, channel, platform, version_name, published_only=False)
    item = release or {}
    fields = [
        {"key":"project_id","description":"项目唯一标识","sourceLayer":"project"},
        {"key":"build_output","description":"构建输出目录","sourceLayer":"release"},
        {"key":"project_code","description":"项目编码","sourceLayer":"release"},
        {"key":"resource_builder","description":"资源构建器标识","sourceLayer":"release"},
        {"key":"apk_version","description":"APK版本号","sourceLayer":"version"},
        {"key":"resource_version","description":"资源版本号","sourceLayer":"version"},
        {"key":"config_version","description":"配置版本号","sourceLayer":"version"},
        {"key":"apk_url","description":"APK下载地址","sourceLayer":"version"},
        {"key":"resource_url","description":"资源包地址","sourceLayer":"version"},
        {"key":"config_url","description":"配置包地址","sourceLayer":"version"},
        {"key":"allow_delta","description":"允许增量差分","sourceLayer":"strategy"},
        {"key":"enable_compression","description":"启用压缩","sourceLayer":"strategy"},
        {"key":"compression_mode","description":"压缩模式","sourceLayer":"strategy"},
        {"key":"compression_provider","description":"压缩Provider","sourceLayer":"strategy"},
        {"key":"enable_encryption","description":"启用加密","sourceLayer":"strategy"},
        {"key":"encrypt_mode","description":"加密模式","sourceLayer":"strategy"},
        {"key":"encrypt_provider","description":"加密Provider","sourceLayer":"strategy"},
        {"key":"enable_sign","description":"启用签名","sourceLayer":"strategy"},
        {"key":"sign_provider","description":"签名Provider","sourceLayer":"strategy"},
        {"key":"sign_key","description":"签名密钥","sourceLayer":"strategy"},
        {"key":"hash_manifest","description":"生成Hash清单","sourceLayer":"strategy"},
        {"key":"baseline_version_dir","description":"基线版本目录","sourceLayer":"diff"},
        {"key":"diff_keyword","description":"差异关键字","sourceLayer":"diff"},
        {"key":"diff_preview","description":"差分预览结果","sourceLayer":"diff"},
        {"key":"hot_update_base_url","description":"热更根地址","sourceLayer":"runtime"},
        {"key":"profile","description":"运行Profile","sourceLayer":"runtime"},
        {"key":"channel","description":"渠道标识","sourceLayer":"channel"},
        {"key":"client_version","description":"客户端版本号","sourceLayer":"runtime"},
        {"key":"show_runtime_config","description":"展示运行时配置","sourceLayer":"runtime"},
        {"key":"upload_provider","description":"上传Provider","sourceLayer":"upload"},
        {"key":"bucket","description":"存储Bucket","sourceLayer":"upload"},
        {"key":"region","description":"存储Region","sourceLayer":"upload"},
        {"key":"cdn_prefix","description":"CDN前缀","sourceLayer":"upload"},
        {"key":"path_template","description":"存储路径模板","sourceLayer":"upload"},
        {"key":"automation_plan_path","description":"自动化计划路径","sourceLayer":"automation"},
        {"key":"cli_result_path","description":"CLI结果路径","sourceLayer":"automation"},
        {"key":"entry_point","description":"执行入口","sourceLayer":"automation"},
        {"key":"release_mode","description":"发布模式","sourceLayer":"automation"},
        {"key":"targets","description":"目标对象集合","sourceLayer":"automation"},
        {"key":"code_units","description":"代码单元集合","sourceLayer":"automation"},
        {"key":"config_units","description":"配置单元集合","sourceLayer":"automation"},
        {"key":"asset_units","description":"资源单元集合","sourceLayer":"automation"},
    ]
    mapping = []
    for spec in fields:
        key = spec.get("key")
        mapping.append({
            "key": key,
            "description": spec.get("description") or "",
            "sourceLayer": spec.get("sourceLayer") or "release",
            "value": item.get(key, "") if key != "project_id" else resolved,
            "source": "release_version" if key != "project_id" else "project_context",
            "effectiveStage": "ConfigApplied" if key != "project_id" else "Bootstrap",
            "logKey": "ConfigApplied" if key != "project_id" else "Bootstrap",
            "readbackField": key,
        })
    return jsonify({"ok": True, "project_id": resolved, "env": env, "channel": channel, "platform": platform, "version_name": version_name, "fields": mapping})
@bp.route("/api/gm-ops/parameter-closure")
@admin_required("gm_ops")
def gm_ops_parameter_closure():
    """扩展编辑器/运营中心参数闭环映射回读。"""
    project_id_raw = (request.args.get("project_id") or "").strip()
    env = str(request.args.get("env") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    version_name = str(request.args.get("version_name") or "").strip()
    ok, resolved = _ensure_project_exists(project_id_raw)
    if not ok:
        return jsonify({"ok": False, "error": resolved}), 404
    release = _find_best_release(resolved, env, channel, platform, version_name, published_only=False)
    profile = _resolve_profile(str((release or {}).get("server_profile") or ""), env, channel) if release else {}
    project = projects_db.get(resolved) or {}
    mapping = {
        "project": {
            "game_id": {"value": project.get("game_id"), "effectiveAt": "AuthSession"},
            "game_key": {"masked": (str(project.get("game_key") or "")[:6] + "***") if str(project.get("game_key") or "") else "", "effectiveAt": "AuthSession"},
            "default_server_profile": {"value": project.get("default_server_profile"), "effectiveAt": "EndpointResolve"},
        },
        "release": {
            "apk_version": release.get("apk_version") if release else "",
            "resource_version": release.get("resource_version") if release else "",
            "config_version": release.get("config_version") if release else "",
            "apk_url": release.get("apk_url") if release else "",
            "resource_url": release.get("resource_url") if release else "",
            "config_url": release.get("config_url") if release else "",
        },
        "server_profile": {
            "gateway_ws": profile.get("gateway_ws") if profile else "",
            "login_http": profile.get("login_http") if profile else "",
            "game_ws": profile.get("game_ws") if profile else "",
            "battle_udp": profile.get("battle_udp") if profile else "",
            "ops_http": profile.get("ops_http") if profile else "",
            "notice_url": profile.get("notice_url") if profile else "",
        },
    }
    return jsonify({"ok": True, "project_id": resolved, "env": env, "channel": channel, "platform": platform, "version_name": version_name, "mapping": mapping, "generatedAt": datetime.now().isoformat()})


@bp.route("/api/gm-ops/quality-gate")
@admin_required("gm_ops")
def gm_ops_quality_gate():
    project_id_raw = (request.args.get("project_id") or "").strip()
    env = str(request.args.get("env") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    version_name = str(request.args.get("version_name") or "").strip()
    return _quality_gate_core(project_id_raw, env, channel, platform, version_name)


@bp.route("/api/gm-ops/quality-gate/ci")
def gm_ops_quality_gate_ci():
    """CI 专用门禁接口，使用 CI Token 鉴权，避免依赖浏览器登录态。"""
    if not _allow_ci_access():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id_raw = (request.args.get("project_id") or "").strip()
    env = str(request.args.get("env") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    version_name = str(request.args.get("version_name") or "").strip()
    return _quality_gate_core(project_id_raw, env, channel, platform, version_name)


@bp.route("/api/gm-ops/closure-evidence/ci")
def gm_ops_closure_evidence_ci():
    """CI 专用闭环证据接口，使用 CI Token 鉴权。"""
    if not _allow_ci_access():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id_raw = (request.args.get("project_id") or "").strip()
    env = str(request.args.get("env") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    version_name = str(request.args.get("version_name") or "").strip()
    return _closure_evidence_core(project_id_raw, env, channel, platform, version_name)


@bp.route("/api/gm-ops/action/approval", methods=["POST"])
@admin_required("gm_ops")
def gm_ops_create_approval():
    payload = request.get_json(silent=True) or {}
    action_type = str(payload.get("actionType") or "").strip()
    target = str(payload.get("target") or "").strip()
    reason = str(((payload.get("operatorContext") or {}).get("reason") or "")).strip()

    if not action_type or not target:
        return jsonify({"ok": False, "error": "actionType and target required"}), 400

    action = _find_action(action_type)
    if not action:
        return jsonify({"ok": False, "error": "unknown actionType"}), 400

    if not _can_execute(action.get("scope") or ""):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    approval_type = "version_publish" if action_type == "release_publish" else "gm_ops_action"
    aid = create_approval(
        atype=approval_type,
        applicant=_current_user(),
        target_type=action_type,
        target_id=target,
        reason=reason or f"GM action apply: {action_type}",
        project_id="",
    )
    pending = _load_pending_actions()
    pending[aid] = {
        "actionType": action_type,
        "domain": str(payload.get("domain") or "gm"),
        "target": target,
        "payload": payload.get("payload") or {},
        "dryRun": False,
        "operatorContext": payload.get("operatorContext") or {"reason": reason or f"GM action apply: {action_type}"},
        "approvalContext": {"approved": True, "approvalId": aid},
    }
    _save_pending_actions(pending)
    log_audit("gm_ops_approval_create", f"action={action_type}; target={target}; approval={aid}; type={approval_type}")
    return jsonify({"ok": True, "approval_id": aid, "status": "pending", "approval_type": approval_type})


@bp.route("/api/gm-ops/action", methods=["POST"])
@admin_required("gm_ops")
def gm_ops_execute_action():
    payload = request.get_json(silent=True) or {}
    action_type = str(payload.get("actionType") or "").strip()
    target = str(payload.get("target") or "").strip()
    domain = str(payload.get("domain") or "").strip() or "gm"
    action = _find_action(action_type)
    if not action:
        return jsonify({"ok": False, "error": "unknown actionType"}), 400

    scope = action.get("scope") or ""
    if not _can_execute(scope):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    operator_context = payload.get("operatorContext") or {}
    reason = str(operator_context.get("reason") or "").strip() or "GM操作"
    ticket_id = str(operator_context.get("ticketId") or "").strip() or ("GM-" + datetime.now().strftime("%Y%m%d%H%M%S"))

    if action.get("requireApproval"):
        approval_type = "version_publish" if action_type == "release_publish" else "gm_ops_action"
        approved_ref = get_approved_approval(approval_type, target)
        approved_flag = bool(((payload.get("approvalContext") or {}).get("approved")))
        if not approved_ref and not approved_flag:
            return jsonify({"ok": False, "error": "approval required", "message": "高风险动作未审批，请先发起审批。"}), 412

    trace_id = str(uuid.uuid4()).replace("-", "")[:16]
    request_model = {
        "actionType": action_type,
        "domain": domain,
        "target": target,
        "payload": payload.get("payload") or {},
        "dryRun": bool(payload.get("dryRun")),
        "operatorContext": {
            "operatorId": _current_user(),
            "permissionGroup": scope,
            "reason": reason,
            "ticketId": ticket_id,
            "traceId": trace_id,
        },
        "approvalContext": payload.get("approvalContext") or {},
    }

    result = _client.execute_action(
        action=request_model,
        operator=_current_user(),
        role=_current_role(),
        reason=reason,
        ticket_id=ticket_id,
    )
    if result.get("success") and action_type in ("release_publish", "release_rollback"):
        _apply_local_release_state(action_type, payload.get("payload") or {}, {"id": ((payload.get("approvalContext") or {}).get("approvalId") or "")})

    log_audit("gm_ops_action_execute", f"action={action_type}; domain={domain}; target={target}; trace={trace_id}; success={result.get('success')}")
    return jsonify({"ok": bool(result.get("success")), "traceId": trace_id, "result": result}), (200 if result.get("success") else 502)


@bp.route("/api/public/release-config")
def gm_public_release_config():
    """前端启动拉取发布配置（按 project_id）。"""
    project_id = (request.args.get("project_id") or "").strip()
    env = (request.args.get("env") or "").strip()
    channel = (request.args.get("channel") or "").strip()
    platform = (request.args.get("platform") or "android").strip().lower()
    version_name = (request.args.get("version_name") or "").strip()

    if not project_id:
        return jsonify({"ok": False, "error": "project_id required"}), 400

    release = _find_best_release(project_id, env, channel, platform, version_name, published_only=True)
    if not release:
        release = _find_best_release(project_id, env, channel, platform, version_name, published_only=False)
    if not release:
        return jsonify({"ok": False, "error": "release config not found"}), 404

    profile = _resolve_profile(str(release.get("server_profile") or ""), str(release.get("env") or env), str(release.get("channel") or channel))

    response = {
        "ok": True,
        "project_id": project_id,
        "env": release.get("env") or env,
        "channel": release.get("channel") or channel,
        "platform": release.get("platform") or platform,
            "version": {
                "version_name": release.get("version_name"),
                "version_code": release.get("version_code"),
                "apk_version": release.get("apk_version"),
                "resource_version": release.get("resource_version"),
                "config_version": release.get("config_version"),
                "apk_url": release.get("apk_url"),
                "resource_url": release.get("resource_url"),
                "config_url": release.get("config_url"),
                "distribution_method": release.get("distribution_method"),
                "package_name": release.get("package_name"),
                "bundle_id": release.get("bundle_id"),
                "min_sdk": release.get("min_sdk"),
                "min_ios_version": release.get("min_ios_version"),
                "changelog": release.get("changelog"),
                "notes": release.get("notes"),
                "server_profile": release.get("server_profile"),
                "publish_status": release.get("publish_status"),
                "updated_at": release.get("updated_at"),
            },
        "network_profile": profile,
    }
    return jsonify(response)


@bp.route("/api/public/runtime-bootstrap")
def gm_public_runtime_bootstrap():
    """前端运行时拉取入口（按 game_id + game_key）。"""
    game_id = (request.args.get("game_id") or "").strip()
    game_key = (request.args.get("game_key") or "").strip()
    env = (request.args.get("env") or "").strip()
    channel = (request.args.get("channel") or "").strip()
    platform = (request.args.get("platform") or "android").strip().lower()
    version_name = (request.args.get("version_name") or "").strip()

    if not game_id or not game_key:
        return jsonify({"ok": False, "error": "game_id and game_key required"}), 400

    project_id = _find_project_by_game_credentials(game_id, game_key)
    if not project_id:
        return jsonify({"ok": False, "error": "invalid game credentials"}), 401

    release = _find_best_release(project_id, env, channel, platform, version_name, published_only=True)
    if not release:
        release = _find_best_release(project_id, env, channel, platform, version_name, published_only=False)
    if not release:
        return jsonify({"ok": False, "error": "release config not found"}), 404

    profile = _resolve_profile(str(release.get("server_profile") or ""), str(release.get("env") or env), str(release.get("channel") or channel))
    return jsonify(
        {
            "ok": True,
            "project_id": project_id,
            "game_id": game_id,
            "env": release.get("env") or env,
            "channel": release.get("channel") or channel,
            "platform": release.get("platform") or platform,
            "bootstrap": {
                "version_name": release.get("version_name"),
                "version_code": release.get("version_code"),
                "apk_version": release.get("apk_version"),
                "resource_version": release.get("resource_version"),
                "config_version": release.get("config_version"),
                "apk_url": release.get("apk_url"),
                "resource_url": release.get("resource_url"),
                "config_url": release.get("config_url"),
                "distribution_method": release.get("distribution_method"),
                "package_name": release.get("package_name"),
                "bundle_id": release.get("bundle_id"),
                "min_sdk": release.get("min_sdk"),
                "min_ios_version": release.get("min_ios_version"),
                "changelog": release.get("changelog"),
                "notes": release.get("notes"),
                "publish_status": release.get("publish_status"),
                "network": profile,
            },
        }
    )











