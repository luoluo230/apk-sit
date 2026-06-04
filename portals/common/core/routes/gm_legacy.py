# -*- coding: utf-8 -*-
"""Legacy GM extraction + Ops platform routes."""

from __future__ import annotations

import os
import json
import signal
import subprocess
import uuid
import hashlib
import socket
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, render_template_string, request, session

from models.data import (
    approvals_db,
    audit_log_db,
    approve_or_reject,
    create_approval,
    get_approved_approval,
    get_system_config,
    log_audit,
    set_system_config,
)
from services.authz import admin_required, can_access_module, has_scope, is_admin
from services.legacy_gm_bridge_client import LegacyGmBridgeClient
from services.ops_platform_gateway import OpsPlatformGateway

bp = Blueprint("gm_legacy", __name__)
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
                "name": "鏈湴GM鑺傜偣",
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
                "description": "榛樿鑺傜偣",
                "biz_status": "normal",
                "allowed_upstream_roles": ["gateway", "scheduler", "admin"],
                "allowed_downstream_roles": ["database", "cache", "mq", "search"],
                "daemon_profile": "ops_native",
                "enabled": True,
            }
        )
    ]


def _load_nodes() -> List[Dict[str, Any]]:
    raw = get_system_config(NODE_CONFIG_KEY, [])
    if isinstance(raw, list) and raw:
        rows: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                rows.append(_normalize_node(item))
        if rows:
            return rows
    return _default_nodes()


def _save_nodes(rows: List[Dict[str, Any]]) -> None:
    normalized = [_normalize_node(item if isinstance(item, dict) else {}) for item in (rows or [])]
    set_system_config(
        NODE_CONFIG_KEY,
        normalized,
        value_type="json",
        description="Legacy GM + Ops 鑺傜偣閰嶇疆",
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
    node = _resolve_node(
        node_id=str(payload.get("node_id") or "").strip(),
        project_id=str(payload.get("project_id") or "").strip(),
        env=str(payload.get("env") or "").strip(),
        channel=str(payload.get("channel") or "").strip(),
    )
    if not node:
        return None, (jsonify({"ok": False, "error": "no node configured"}), 400)
    return node, None


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


def _render_page(content: str, title: str):
    try:
        from routes.admin_routes import _admin_layout

        return _admin_layout(content, title, back_href="/admin")
    except Exception:
        return render_template_string(
            """
<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{{ title }}</title><link rel=\"stylesheet\" href=\"/static/tailwind.css\"></head>
<body class=\"bg-slate-50 min-h-screen\"><div class=\"max-w-7xl mx-auto p-6\">{{ content|safe }}</div></body></html>
""",
            title=title,
            content=content,
        )


def _render_local_template(template_name: str, **kwargs):
    path = os.path.join(os.path.dirname(__file__), "..", "templates", template_name)
    with open(path, "r", encoding="utf-8") as f:
        return render_template_string(f.read(), **kwargs)


def _render_standalone_page(content: str, title: str):
    return render_template_string(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <link rel="stylesheet" href="/static/tailwind.css">
  <style>
    html,body{margin:0;padding:0;background:#f7f9fc}
  </style>
</head>
<body>{{ content|safe }}</body>
</html>
""",
        title=title,
        content=content,
    )


@bp.route("/admin/gm-classic")
@admin_required("gm_ops")
def gm_classic_page():
    try:
        content = _render_local_template("gm_classic_page.html")
        return _render_page(content, "经典 GM 模块")
    except Exception:
        return _render_page(
            '<section class="panel p-6"><h2 class="text-xl font-bold">经典 GM 模块</h2><p class="text-slate-600 mt-2">页面模板加载失败，请联系管理员检查模板文件。</p></section>',
            "经典 GM 模块",
        )

    content = """
<section class="space-y-5 gm-classic-shell">
  <style>
    .gm-classic-shell .panel{border:1px solid #dbe3f1;background:#fff;border-radius:16px;box-shadow:0 2px 10px rgba(15,23,42,.04)}
    .gm-classic-shell .hero{border:1px solid #bae6fd;background:linear-gradient(110deg,#082f49,#0f766e 42%,#0891b2);border-radius:18px;color:#fff}
    .gm-classic-shell .btn{border-radius:10px;padding:.54rem .82rem;font-size:13px;font-weight:700;color:#fff;box-shadow:0 6px 14px rgba(15,23,42,.18)}
    .gm-classic-shell .btn-teal{background:linear-gradient(135deg,#0d9488,#0f766e)}
    .gm-classic-shell .btn-indigo{background:linear-gradient(135deg,#4f46e5,#4338ca)}
    .gm-classic-shell .btn-rose{background:linear-gradient(135deg,#e11d48,#be123c)}
    .gm-classic-shell .btn-amber{background:linear-gradient(135deg,#f59e0b,#d97706)}
  </style>
  <section class="hero p-6">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-semibold">缁忓吀GM妯″潡锛堢嫭绔嬪墺绂伙級</h2>
        <p class="text-sm text-cyan-100/90 mt-1">閫氳繃鍐呯綉妗ユ帴灞傛帴鍏?legacy GmWebServer锛岀粺涓€鐣欑棔骞朵笌椤圭洰涓婁笅鏂囧榻愩€?/p>
      </div>
      <div class="text-xs rounded-full px-3 py-1 border border-white/30 bg-white/15">Legacy Bridge v1</div>
    </div>
  </section>

  <section class="panel p-4 grid grid-cols-1 xl:grid-cols-12 gap-4 items-end">
    <div class="xl:col-span-4"><label class="text-xs text-slate-500">鑺傜偣</label><select id="gmNode" class="w-full border rounded-lg px-3 py-2"></select></div>
    <div class="xl:col-span-3"><label class="text-xs text-slate-500">椤圭洰ID</label><input id="gmProjectId" class="w-full border rounded-lg px-3 py-2" placeholder="鍙€?></div>
    <div class="xl:col-span-2"><label class="text-xs text-slate-500">鐜</label><input id="gmEnv" class="w-full border rounded-lg px-3 py-2" placeholder="dev/test/prod"></div>
    <div class="xl:col-span-2"><label class="text-xs text-slate-500">娓犻亾</label><input id="gmChannel" class="w-full border rounded-lg px-3 py-2" placeholder="1001"></div>
    <div class="xl:col-span-1"><button class="w-full btn btn-indigo" onclick="reloadNodes()">鍒锋柊</button></div>
  </section>

  <section class="grid grid-cols-1 xl:grid-cols-2 gap-4">
    <div class="panel p-4 space-y-3">
      <h3 class="font-semibold text-slate-900">鐜╁涓庤祫婧?/h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <input id="pKeyword" class="border rounded-lg px-3 py-2" placeholder="鐜╁鍏抽敭璇?playerId">
        <button class="btn btn-teal" onclick="gmAction('search_player',{keyword:val('pKeyword')})">鐜╁妫€绱?/button>
        <input id="pIdCurrency" class="border rounded-lg px-3 py-2" placeholder="playerId">
        <div class="grid grid-cols-3 gap-2"><input id="pDia" class="border rounded-lg px-2 py-2" placeholder="閽荤煶"><input id="pGold" class="border rounded-lg px-2 py-2" placeholder="閲戝竵"><input id="pSta" class="border rounded-lg px-2 py-2" placeholder="浣撳姏"></div>
        <textarea id="pReasonCurrency" class="border rounded-lg px-3 py-2 md:col-span-2" rows="2" placeholder="鍘熷洜"></textarea>
        <button class="btn btn-amber" onclick="gmAction('adjust_currency',{playerId:val('pIdCurrency'),diamonds:val('pDia'),gold:val('pGold'),stamina:val('pSta'),reason:val('pReasonCurrency')})">璋冩暣璐у竵</button>
        <input id="pIdItem" class="border rounded-lg px-3 py-2" placeholder="playerId">
        <div class="grid grid-cols-2 gap-2"><input id="itemId" class="border rounded-lg px-2 py-2" placeholder="itemId"><input id="itemDelta" class="border rounded-lg px-2 py-2" placeholder="delta +/-"></div>
        <textarea id="pReasonItem" class="border rounded-lg px-3 py-2 md:col-span-2" rows="2" placeholder="鍘熷洜"></textarea>
        <button class="btn btn-amber" onclick="gmAction('adjust_item',{playerId:val('pIdItem'),itemId:val('itemId'),delta:val('itemDelta'),reason:val('pReasonItem')})">璋冩暣鐗╁搧</button>
      </div>
    </div>

    <div class="panel p-4 space-y-3">
      <h3 class="font-semibold text-slate-900">閭欢涓庤繍钀ュ姩浣?/h3>
      <div class="space-y-2">
        <input id="mailPid" class="w-full border rounded-lg px-3 py-2" placeholder="playerId">
        <input id="mailTitle" class="w-full border rounded-lg px-3 py-2" placeholder="閭欢鏍囬">
        <textarea id="mailBody" class="w-full border rounded-lg px-3 py-2" rows="2" placeholder="閭欢姝ｆ枃"></textarea>
        <input id="mailRewards" class="w-full border rounded-lg px-3 py-2" placeholder='濂栧姳JSON锛屽 [{"itemId":"gold","count":100}]'>
        <input id="mailReason" class="w-full border rounded-lg px-3 py-2" placeholder="鍘熷洜">
        <div class="grid grid-cols-2 gap-2">
          <button class="btn btn-indigo" onclick="gmAction('send_mail',{playerId:val('mailPid'),title:val('mailTitle'),body:val('mailBody'),rewards:val('mailRewards'),reason:val('mailReason')})">鍙戦€佸崟浜洪偖浠?/button>
          <button class="btn btn-rose" onclick="gmAction('send_broadcast',{title:val('mailTitle'),body:val('mailBody'),rewards:val('mailRewards'),reason:val('mailReason')})">鍏ㄦ湇骞挎挱閭欢</button>
        </div>
      </div>
    </div>
  </section>

  <section class="panel p-4">
    <div class="flex items-center justify-between mb-2"><h3 class="font-semibold">鎵ц缁撴灉</h3><span id="gmResultSummary" class="text-xs text-slate-500">绛夊緟鎵ц</span></div>
    <pre id="gmResult" class="w-full h-72 rounded border border-slate-200 bg-slate-50 p-3 text-xs overflow-auto"></pre>
  </section>
</section>
<script>
function val(id){ const el=document.getElementById(id); return el ? (el.value||'').trim() : ''; }
function commonPayload(){ return { node_id: val('gmNode'), project_id: val('gmProjectId'), env: val('gmEnv'), channel: val('gmChannel') }; }
async function reloadNodes(){
  const r=await fetch('/api/gm-legacy/nodes');
  const d=await r.json();
  const sel=document.getElementById('gmNode');
  const rows=d.nodes||[];
  sel.innerHTML=rows.map(n=>`<option value="${n.id}">${n.name} (${n.base_url||'-'})</option>`).join('');
}
function showResult(data){
  document.getElementById('gmResult').textContent=JSON.stringify(data,null,2);
  const ok = !!data.ok;
  document.getElementById('gmResultSummary').textContent = ok ? '鎵ц鎴愬姛' : '鎵ц澶辫触';
  document.getElementById('gmResultSummary').className = ok ? 'text-xs text-emerald-600' : 'text-xs text-rose-600';
}
async function gmAction(action,payload){
  const body=Object.assign(commonPayload(),{action:action,payload:payload||{}});
  const r=await fetch('/api/gm-classic/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  showResult(await r.json());
}
reloadNodes();
</script>
"""
    return _render_page(content, "缁忓吀GM妯″潡")


@bp.route("/admin/ops-platform")
@admin_required("gm_ops")
def ops_platform_page():
    project_id = str(request.args.get("project_id") or "").strip()
    try:
        content = render_template_string(
            open(
                os.path.join(os.path.dirname(__file__), "..", "templates", "ops_overview_page.html"),
                "r",
                encoding="utf-8",
            ).read(),
            project_id=project_id,
        )
        return _render_page(content, "运维平台")
    except Exception:
        return _render_page(
            '<section class="panel p-6"><h2 class="text-xl font-bold">运维平台</h2><p class="text-slate-600 mt-2">总览页面加载失败，请检查模板与静态资源。</p></section>',
            "运维平台",
        )
    content = """
<section class="ops-pro-shell space-y-5" data-project-id=""" + project_id + """">
  <style>
    .ops-pro-shell{font-family:"IBM Plex Sans","Source Han Sans SC","PingFang SC","Microsoft YaHei",sans-serif;color:#0f172a}
    .ops-pro-shell .hero{border:1px solid #bfdbfe;background:radial-gradient(1300px 320px at 0% 0%,#0f172a 0%,#1e3a8a 40%,#2563eb 100%);border-radius:20px;color:#eff6ff;padding:20px 24px;position:relative;overflow:hidden}
    .ops-pro-shell .hero:after{content:"";position:absolute;right:-80px;top:-60px;width:220px;height:220px;background:radial-gradient(circle,#93c5fd66 0%,#60a5fa00 72%)}
    .ops-pro-shell .panel{background:#fff;border:1px solid #dbeafe;border-radius:16px;box-shadow:0 2px 12px rgba(15,23,42,.05)}
    .ops-pro-shell .kpi{background:linear-gradient(150deg,#f8fafc,#eef2ff);border:1px solid #e2e8f0;border-radius:14px;padding:12px 14px}
    .ops-pro-shell .kpi .label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#64748b}
    .ops-pro-shell .kpi .value{font-size:24px;font-weight:700;color:#0f172a;line-height:1.2}
    .ops-pro-shell .btn{border-radius:10px;padding:.56rem .9rem;font-size:13px;font-weight:700;color:#fff;box-shadow:0 8px 18px rgba(15,23,42,.14)}
    .ops-pro-shell .btn-indigo{background:linear-gradient(135deg,#4f46e5,#3730a3)}
    .ops-pro-shell .btn-cyan{background:linear-gradient(135deg,#0891b2,#0369a1)}
    .ops-pro-shell .btn-emerald{background:linear-gradient(135deg,#10b981,#047857)}
    .ops-pro-shell .btn-rose{background:linear-gradient(135deg,#e11d48,#be123c)}
    .ops-pro-shell .btn-slate{background:linear-gradient(135deg,#334155,#1e293b)}
    .ops-pro-shell .btn-amber{background:linear-gradient(135deg,#f59e0b,#d97706)}
    .ops-pro-shell .chip{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}
    .ops-pro-shell .chip-online{background:#dcfce7;color:#166534}
    .ops-pro-shell .chip-degraded{background:#fef3c7;color:#92400e}
    .ops-pro-shell .chip-offline{background:#fee2e2;color:#991b1b}
    .ops-pro-shell .chip-maintenance{background:#ede9fe;color:#5b21b6}
    .ops-pro-shell .chip-unknown{background:#e2e8f0;color:#334155}
    .ops-pro-shell .log-item{border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;padding:10px}
    .ops-pro-shell .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace}

    .ops-pro-shell .topology-wrap{position:relative;height:460px;border:1px solid #dbeafe;border-radius:14px;overflow:hidden;background:
      radial-gradient(circle at 12% 15%, rgba(125,211,252,.18), transparent 30%),
      radial-gradient(circle at 84% 20%, rgba(165,180,252,.18), transparent 28%),
      linear-gradient(180deg,#f8fafc,#eef2ff)}
    .ops-pro-shell .topology-svg{position:absolute;inset:0;width:100%;height:100%}
    .ops-pro-shell .topology-node{position:absolute;width:172px;border-radius:14px;border:1px solid #cbd5e1;background:#fff;box-shadow:0 8px 22px rgba(15,23,42,.10);padding:8px 10px;cursor:pointer;user-select:none;transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease}
    .ops-pro-shell .topology-node:hover{transform:translateY(-2px);box-shadow:0 12px 26px rgba(15,23,42,.13)}
    .ops-pro-shell .topology-node.active{border-color:#4338ca;box-shadow:0 0 0 2px rgba(99,102,241,.15),0 10px 26px rgba(15,23,42,.16)}
    .ops-pro-shell .topology-node .n-title{font-size:13px;font-weight:700;color:#0f172a;line-height:1.2}
    .ops-pro-shell .topology-node .n-meta{font-size:11px;color:#64748b}
    .ops-pro-shell .topology-node .n-role{font-size:11px;padding:1px 6px;border-radius:999px;background:#e2e8f0;color:#334155;display:inline-flex;margin-right:4px}
    .ops-pro-shell .topology-node.bad-online{border-left:4px solid #16a34a}
    .ops-pro-shell .topology-node.bad-degraded{border-left:4px solid #f59e0b}
    .ops-pro-shell .topology-node.bad-offline{border-left:4px solid #e11d48}
    .ops-pro-shell .topology-node.bad-maintenance{border-left:4px solid #7c3aed}
    .ops-pro-shell .topology-node.bad-unknown{border-left:4px solid #64748b}

    .ops-pro-shell .section-title{font-size:16px;font-weight:700;color:#0f172a}
    .ops-pro-shell .action-group-tag{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:#e2e8f0;color:#334155}
  </style>

  <section class="hero">
    <div class="flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h2 class="text-2xl font-semibold">杩愮淮骞冲彴锛堟嫇鎵戣繍钀ョ増锛?/h2>
        <p class="text-sm text-blue-100 mt-1">鍙鍖栬妭鐐瑰叧绯?+ 鍒嗗竷寮忚鑹叉不鐞?+ 瀹℃壒闂幆鎵ц锛屼竴鐪煎畾浣嶅紓甯稿苟鐩磋揪鎿嶄綔銆?/p>
      </div>
      <div class="text-xs rounded-full px-3 py-1 border border-white/30 bg-white/10">Ops Platform v3 鈥?Topology Native</div>
    </div>
  </section>

  <section class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
    <div class="kpi"><div class="label">SLA%</div><div class="value" id="kpiSla">-</div></div>
    <div class="kpi"><div class="label">鑺傜偣鎬绘暟</div><div class="value" id="kpiNodes">-</div></div>
    <div class="kpi"><div class="label">鍋ュ悍鑺傜偣</div><div class="value" id="kpiHealthy">-</div></div>
    <div class="kpi"><div class="label">閫€鍖栬妭鐐?/div><div class="value" id="kpiDegraded">-</div></div>
    <div class="kpi"><div class="label">绂荤嚎鑺傜偣</div><div class="value" id="kpiOffline">-</div></div>
    <div class="kpi"><div class="label">鍛婅鎬绘暟</div><div class="value" id="kpiAlerts">-</div></div>
  </section>

  <section class="panel p-4 space-y-3">
    <div class="flex items-center justify-between"><h3 class="section-title">棰勫埗鑺傜偣搴擄紙鏈嶅姟鍣ㄧ被鍨嬫ā鏉匡級</h3><span class="text-xs text-slate-500">鏁版嵁搴?/ Redis / 鍘嬪姏 / 涓氬姟 / 缃戝叧绛?/span></div>
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-2">
      <div><label class="text-xs text-slate-500">妯℃澘</label><select id="presetSelect" class="w-full border rounded-lg px-3 py-2"></select></div>
      <div><label class="text-xs text-slate-500">鑺傜偣鍚嶇О</label><input id="presetNodeName" class="w-full border rounded-lg px-3 py-2" placeholder="渚嬪 pressure-cn-1"></div>
      <div><label class="text-xs text-slate-500">serverId</label><input id="presetServerId" class="w-full border rounded-lg px-3 py-2" placeholder="game-cn-1"></div>
      <div><label class="text-xs text-slate-500">璐熻矗浜?/label><input id="presetOwner" class="w-full border rounded-lg px-3 py-2" placeholder="ops-admin"></div>
      <div><label class="text-xs text-slate-500">鐜</label><input id="presetEnv" class="w-full border rounded-lg px-3 py-2" placeholder="prod"></div>
      <div><label class="text-xs text-slate-500">娓犻亾</label><input id="presetChannel" class="w-full border rounded-lg px-3 py-2" placeholder="1001"></div>
      <div class="xl:col-span-2"><label class="text-xs text-slate-500">澶囨敞</label><input id="presetDesc" class="w-full border rounded-lg px-3 py-2" placeholder="鑺傜偣鐢ㄩ€旇鏄?></div>
      <div><label class="text-xs text-slate-500">Daemon Start 鍛戒护(鍙€?</label><input id="presetStartCmd" class="w-full border rounded-lg px-3 py-2 mono" placeholder="渚嬪 docker start redis-a"></div>
      <div><label class="text-xs text-slate-500">Daemon Stop 鍛戒护(鍙€?</label><input id="presetStopCmd" class="w-full border rounded-lg px-3 py-2 mono" placeholder="渚嬪 docker stop redis-a"></div>
      <div class="flex items-end"><button class="btn btn-emerald w-full" onclick="addNodeFromPreset()">娣诲姞鑺傜偣</button></div>
      <div class="flex items-end"><button class="btn btn-slate w-full" onclick="loadNodePresets()">鍒锋柊妯℃澘</button></div>
    </div>
    <div id="presetHint" class="text-xs text-slate-500">閫夋嫨妯℃澘鍚庡彲蹇€熻惤鑺傜偣锛屽苟鑷姩娉ㄥ叆涓婁笅娓歌鍒欍€?/div>
  </section>

  <section class="panel p-4 space-y-3">
    <div class="flex items-center justify-between"><h3 class="section-title">鑺傜偣鎺ュ叆浣撴涓庨璀?/h3><button class="btn btn-amber" onclick="loadOnboarding()">鍒锋柊浣撴</button></div>
    <div class="overflow-auto max-h-[260px] border border-slate-200 rounded-xl">
      <table class="min-w-full text-sm">
        <thead class="bg-slate-50 sticky top-0"><tr><th class="px-2 py-2 text-left">鑺傜偣</th><th class="px-2 py-2 text-left">瑙掕壊</th><th class="px-2 py-2 text-left">鐘舵€?/th><th class="px-2 py-2 text-left">鎺ュ叆妫€鏌?/th><th class="px-2 py-2 text-left">鍛婅绾у埆</th></tr></thead>
        <tbody id="onboardBody"><tr><td class="px-2 py-3 text-slate-400" colspan="5">鏆傛棤鏁版嵁</td></tr></tbody>
      </table>
    </div>
    <div id="onboardSummary" class="text-xs text-slate-500">绛夊緟浣撴</div>
  </section>

  <section class="grid grid-cols-1 xl:grid-cols-12 gap-4">
    <div class="xl:col-span-8 space-y-4">
      <section class="panel p-4 space-y-3">
        <div class="flex items-center justify-between gap-2 flex-wrap">
          <h3 class="section-title">鑺傜偣鎷撴墤鍏崇郴鍥?/h3>
          <div class="flex items-center gap-2">
            <input id="opsProjectFilter" class="border rounded-lg px-3 py-2 text-sm" placeholder="project_id 杩囨护">
            <button class="btn btn-indigo" onclick="loadOverviewAndTopology()">鍒锋柊鎷撴墤</button>
          </div>
        </div>
        <div class="topology-wrap" id="topologyWrap">
          <svg class="topology-svg" id="topologySvg"></svg>
          <div id="topologyNodeLayer"></div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-slate-500">
          <div>鏀寔鎿嶄綔锛氬崟鍑昏妭鐐瑰垏鎹笂涓嬫枃銆佹嫋鍔ㄨ妭鐐瑰竷灞€銆佺紪杈戣妭鐐瑰睘鎬с€佸缓绔?鍒犻櫎鍏崇郴绾裤€?/div>
          <div>鐘舵€佽壊锛氱豢鑹插湪绾?/ 姗欒壊閫€鍖?/ 绾㈣壊绂荤嚎 / 绱壊缁存姢 / 鐏拌壊鏈煡銆?/div>
        </div>
      </section>

      <section class="panel p-4 space-y-3">
        <div class="flex items-center justify-between"><h3 class="section-title">鍛婅涓庝簨浠舵椂闂寸嚎</h3><button class="btn btn-slate" onclick="loadEvents()">鍒锋柊浜嬩欢</button></div>
        <div id="eventList" class="space-y-2 max-h-[280px] overflow-auto"></div>
      </section>
    </div>

    <div class="xl:col-span-4 space-y-4">
      <section class="panel p-4 space-y-3">
        <h3 class="section-title">鑺傜偣璇︽儏涓庣紪杈?/h3>
        <div class="grid grid-cols-1 gap-2">
          <div><label class="text-xs text-slate-500">鑺傜偣</label><input id="topoNodeId" class="w-full border rounded-lg px-3 py-2 mono" readonly></div>
          <div><label class="text-xs text-slate-500">鑺傜偣璇存槑</label><textarea id="topoNodeDesc" rows="2" class="w-full border rounded-lg px-3 py-2" placeholder="鑺傜偣鐢ㄩ€旇鏄?></textarea></div>
          <div><label class="text-xs text-slate-500">鑺傜偣瑙掕壊</label><select id="topoNodeRole" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">涓氬姟鐘舵€佹爣绛?/label><select id="topoNodeBizStatus" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">璐熻矗浜?/label><input id="topoNodeOwner" class="w-full border rounded-lg px-3 py-2" placeholder="owner"></div>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <button class="btn btn-cyan" onclick="focusNodeOnMap()">瀹氫綅鑺傜偣</button>
          <button class="btn btn-emerald" onclick="saveNodeMeta()">淇濆瓨鑺傜偣</button>
        </div>
      </section>

      <section class="panel p-4 space-y-3">
        <h3 class="section-title">鍏崇郴杩炵嚎绠＄悊</h3>
        <div class="grid grid-cols-1 gap-2">
          <div><label class="text-xs text-slate-500">璧风偣鑺傜偣</label><select id="edgeFrom" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">缁堢偣鑺傜偣</label><select id="edgeTo" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">鍏崇郴绫诲瀷</label><select id="edgeType" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">鍏崇郴璇存槑</label><input id="edgeNote" class="w-full border rounded-lg px-3 py-2" placeholder="渚嬪 缃戝叧 -> 涓氬姟"></div>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <button class="btn btn-indigo" onclick="upsertEdge()">寤虹珛/鏇存柊杩炵嚎</button>
          <button class="btn btn-rose" onclick="removeSelectedEdge()">鍒犻櫎閫変腑杩炵嚎</button>
        </div>
        <div id="edgeHint" class="text-xs text-slate-500">鐐瑰嚮鎷撴墤涓殑绾挎潯鍙€変腑鍚庡垹闄ゃ€?/div>
      </section>
    </div>
  </section>

  <section class="panel p-4 space-y-3">
    <div class="flex items-center justify-between"><h3 class="section-title">杩愮淮鍔ㄤ綔涓績锛堝晢涓氱骇鍒嗙被锛?/h3><span class="text-xs text-slate-500">闂幆锛氶妫€ 鈫?瀹℃壒 鈫?鎵ц 鈫?鍥炶</span></div>
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
      <div><label class="text-xs text-slate-500">鑺傜偣锛堜竴閿垏鎹級</label><select id="opNodeId" class="w-full border rounded-lg px-3 py-2" onchange="syncNodeContextFromSelect()"></select></div>
      <div><label class="text-xs text-slate-500">鍔ㄤ綔鍒嗙被</label><select id="opActionGroup" class="w-full border rounded-lg px-3 py-2" onchange="renderActionOptions()"></select></div>
      <div><label class="text-xs text-slate-500">鍔ㄤ綔</label><select id="opActionType" class="w-full border rounded-lg px-3 py-2" onchange="syncRiskHint()"></select></div>
      <div><label class="text-xs text-slate-500">鐩爣 (serverId / playerId / taskId / sessionId / key)</label><input id="opTarget" class="w-full border rounded-lg px-3 py-2" placeholder="渚嬪 game-cn-1"></div>
      <div><label class="text-xs text-slate-500">宸ュ崟鍙?ticketId</label><input id="opTicket" class="w-full border rounded-lg px-3 py-2" placeholder="OPS-2026-0001"></div>
      <div><label class="text-xs text-slate-500">鍙樻洿鍘熷洜 reason</label><input id="opReason" class="w-full border rounded-lg px-3 py-2" placeholder="濉啓鍙樻洿鍘熷洜"></div>
      <div><label class="text-xs text-slate-500">瀹℃壒浜?approver锛堥珮鍗卞繀濉級</label><input id="opApprover" class="w-full border rounded-lg px-3 py-2" placeholder="瀹℃壒璐ｄ换浜鸿处鍙?></div>
      <div class="flex items-end"><span id="opRiskHint" class="text-xs px-2 py-1 rounded-full bg-slate-100 text-slate-700">椋庨櫓绾у埆锛?</span></div>
      <div class="md:col-span-2 xl:col-span-4"><label class="text-xs text-slate-500">鎵╁睍 payload JSON</label><textarea id="opPayload" rows="3" class="w-full border rounded-lg px-3 py-2 mono" placeholder='{"enabled":true,"message":"maintenance notice"}'></textarea></div>
      <div class="md:col-span-2 xl:col-span-4 flex items-center gap-3">
        <label class="inline-flex items-center gap-2 text-sm"><input id="opDryRun" type="checkbox">Dry-run</label>
        <span id="opValidateHint" class="text-xs text-slate-500">灏氭湭棰勬</span>
        <span id="opGroupHint" class="action-group-tag">鍒嗙被锛?</span>
      </div>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
      <button class="btn btn-cyan" onclick="validateAction()">棰勬</button>
      <button class="btn btn-indigo" onclick="createApproval()">鍒涘缓瀹℃壒鍗?/button>
      <button class="btn btn-emerald" onclick="executeAction()">鎵ц鍔ㄤ綔</button>
      <button class="btn btn-rose" onclick="quickRollbackHint()">鍥炴粴寮曞</button>
    </div>
  </section>

  <section class="panel p-4 space-y-4">
    <div class="flex items-center justify-between"><h3 class="section-title">瀹堟姢杩涚▼涓庝笓椤规祦绋嬪伐鍏?/h3><span class="text-xs text-slate-500">鑺傜偣瀹堟姢 / 涓€閿啋鐑?/ 鍘嬫祴 / 杩佺Щ</span></div>
    <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">
      <div class="xl:col-span-4 space-y-2">
        <h4 class="text-sm font-semibold text-slate-800">瀹堟姢杩涚▼鎺у埗</h4>
        <div><label class="text-xs text-slate-500">鑺傜偣</label><select id="daemonNodeId" class="w-full border rounded-lg px-3 py-2"></select></div>
        <div><label class="text-xs text-slate-500">宸ュ崟鍙?/label><input id="daemonTicketId" class="w-full border rounded-lg px-3 py-2" placeholder="OPS-DAEMON-0001"></div>
        <div><label class="text-xs text-slate-500">鎿嶄綔鍘熷洜</label><input id="daemonReason" class="w-full border rounded-lg px-3 py-2" placeholder="渚嬪 缁存姢绐楀彛涓婄嚎"></div>
        <div class="grid grid-cols-2 gap-2">
          <button class="btn btn-cyan" onclick="runDaemonAction('status')">鐘舵€?/button>
          <button class="btn btn-emerald" onclick="runDaemonAction('start')">鍚姩</button>
          <button class="btn btn-rose" onclick="runDaemonAction('stop')">鍋滄</button>
          <button class="btn btn-indigo" onclick="runDaemonAction('restart')">閲嶅惎</button>
        </div>
        <div id="daemonHint" class="text-xs text-slate-500">璇烽€夋嫨鑺傜偣鎵ц瀹堟姢杩涚▼鍔ㄤ綔銆?/div>
      </div>
      <div class="xl:col-span-4 space-y-2">
        <h4 class="text-sm font-semibold text-slate-800">涓€閿啋鐑燂紙閫夊畾鑺傜偣閾捐矾锛?/h4>
        <div><label class="text-xs text-slate-500">鑺傜偣璺緞锛堥€楀彿鍒嗛殧 nodeId锛?/label><input id="flowPathNodes" class="w-full border rounded-lg px-3 py-2 mono" placeholder="gateway-1,business-1,database-1"></div>
        <div><label class="text-xs text-slate-500">鍐掔儫璇存槑</label><input id="flowReason" class="w-full border rounded-lg px-3 py-2" placeholder="渚嬪 鍙戝竷鍚庡叧閿摼璺啋鐑?></div>
        <button class="btn btn-slate w-full" onclick="runFlowSmoke()">鎵ц鍐掔儫</button>
        <div id="flowHint" class="text-xs text-slate-500">鑷冲皯杈撳叆涓や釜鑺傜偣锛屾寜椤哄簭鎵ц鍋ュ悍鎺㈡祴銆?/div>
      </div>
      <div class="xl:col-span-4 space-y-2">
        <h4 class="text-sm font-semibold text-slate-800">鍘嬫祴涓庤縼绉?/h4>
        <div><label class="text-xs text-slate-500">鍘嬫祴鑺傜偣</label><select id="stressNodeId" class="w-full border rounded-lg px-3 py-2"></select></div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="text-xs text-slate-500">QPS</label><input id="stressQps" class="w-full border rounded-lg px-3 py-2" value="300"></div>
          <div><label class="text-xs text-slate-500">鏃堕暱(绉?</label><input id="stressDuration" class="w-full border rounded-lg px-3 py-2" value="180"></div>
        </div>
        <div><label class="text-xs text-slate-500">鍘嬫祴鍘熷洜</label><input id="stressReason" class="w-full border rounded-lg px-3 py-2" placeholder="渚嬪 宄板€煎閲忚瘎浼?></div>
        <button class="btn btn-amber w-full" onclick="runStressTest()">鎵ц鍘嬫祴</button>
        <hr class="my-1 border-slate-200">
        <div><label class="text-xs text-slate-500">杩佺Щ鑺傜偣锛堟暟鎹簱/缂撳瓨锛?/label><select id="dbNodeId" class="w-full border rounded-lg px-3 py-2"></select></div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="text-xs text-slate-500">鏂瑰悜</label><select id="dbDirection" class="w-full border rounded-lg px-3 py-2"><option value="up">up</option><option value="down">down</option></select></div>
          <div><label class="text-xs text-slate-500">鐗堟湰</label><input id="dbVersion" class="w-full border rounded-lg px-3 py-2" placeholder="20260524-01"></div>
        </div>
        <div><label class="text-xs text-slate-500">杩佺Щ鍛戒护锛堝彲閫夛級</label><input id="dbCommand" class="w-full border rounded-lg px-3 py-2 mono" placeholder="渚嬪 alembic upgrade head"></div>
        <div><label class="text-xs text-slate-500">杩佺Щ鍘熷洜</label><input id="dbReason" class="w-full border rounded-lg px-3 py-2" placeholder="渚嬪 鍙戝竷鐗堟湰 1.3.0"></div>
        <button class="btn btn-rose w-full" onclick="runDbMigration()">鎵ц杩佺Щ</button>
      </div>
    </div>
  </section>

  <section class="grid grid-cols-1 xl:grid-cols-12 gap-4">
    <section class="panel p-4 space-y-3 xl:col-span-7">
      <div class="flex items-center justify-between"><h3 class="section-title">鎵ц娴佹按锛堢粨鏋勫寲锛?/h3><span id="streamSummary" class="text-xs text-slate-500">绛夊緟鎵ц</span></div>
      <div id="streamList" class="space-y-2 max-h-[300px] overflow-auto"></div>
    </section>
    <section class="panel p-4 space-y-3 xl:col-span-5">
      <div class="flex items-center justify-between"><h3 class="section-title">Trace 鍥炴斁</h3><span class="text-xs text-slate-500">鎸?traceId 鏌ヨ</span></div>
      <div class="flex gap-2"><input id="traceQuery" class="flex-1 border rounded-lg px-3 py-2 mono" placeholder="杈撳叆 traceId"><button class="btn btn-slate" onclick="queryTrace()">鏌ヨ</button></div>
      <pre id="traceDetail" class="w-full h-52 rounded border border-slate-200 bg-slate-50 p-3 text-xs overflow-auto mono"></pre>
    </section>
  </section>

  <section class="panel p-4 hidden" id="nodeConfigPanel">
    <div class="flex items-center justify-between mb-2"><h3 class="section-title">鑺傜偣閰嶇疆锛堥珮绾?JSON锛?/h3><button class="btn btn-slate" onclick="toggleNodeConfig(false)">鏀惰捣</button></div>
    <textarea id="nodeConfigJson" class="w-full h-48 border rounded-lg px-3 py-2 font-mono text-xs"></textarea>
    <div class="mt-2 flex gap-2"><button class="btn btn-indigo" onclick="saveNodesRawJson()">淇濆瓨鑺傜偣閰嶇疆</button></div>
  </section>
  <div class="flex justify-end"><button class="btn btn-slate" onclick="toggleNodeConfig(true)">鑺傜偣閰嶇疆</button></div>
</section>
<script>
const ROLE_OPTIONS=['gateway','business','pressure','database','cache','mq','search','scheduler','admin','edge','analytics'];
const BIZ_STATUS_OPTIONS=['normal','observe','degraded','error','offline'];
const EDGE_TYPES=['gateway_to_business','business_to_db','business_to_cache','business_to_mq','sync','async','depends_on'];

const ACTION_CATALOG=[
  {group:'观测',groupId:'observe',value:'health_check',label:'健康检查',risk:'low'},
  {group:'观测',groupId:'observe',value:'ready_check',label:'就绪检查',risk:'low'},
  {group:'观测',groupId:'observe',value:'status',label:'运行快照',risk:'low'},
  {group:'观测',groupId:'observe',value:'runtime_snapshot',label:'运行态详情',risk:'low'},
  {group:'生命周期',groupId:'lifecycle',value:'start',label:'启动节点',risk:'high'},
  {group:'生命周期',groupId:'lifecycle',value:'stop',label:'停止节点',risk:'high'},
  {group:'生命周期',groupId:'lifecycle',value:'restart',label:'重启节点',risk:'high'},
  {group:'生命周期',groupId:'lifecycle',value:'start_all',label:'启动全节点',risk:'high'},
  {group:'生命周期',groupId:'lifecycle',value:'stop_all',label:'停止全节点',risk:'high'},
  {group:'专项作业',groupId:'special',value:'smoke_test',label:'冒烟测试',risk:'medium'},
  {group:'专项作业',groupId:'special',value:'stress_test',label:'压力测试',risk:'high'}
];

let NODE_ROWS=[];
let LAST_OVERVIEW_NODES=[];
let TOPOLOGY={nodes:[],edges:[]};
let SELECTED_NODE_ID='';
let SELECTED_EDGE_ID='';
let DRAG_NODE_ID='';
let DRAG_OFFSET={x:0,y:0};
let NODE_PRESETS=[];

function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));}
function read(id){const e=document.getElementById(id);return e?(e.value||'').trim():'';}
function readJson(id){const t=read(id); if(!t) return {}; try{return JSON.parse(t);}catch(_){throw new Error('payload JSON 瑙ｆ瀽澶辫触');}}
function byId(id){return document.getElementById(id);}
function findMeta(nodeId){return (TOPOLOGY.nodes||[]).find(n=>n.id===nodeId)||null;}
function setText(id,v){const e=byId(id); if(e){e.textContent=v;}}

function statusClass(s){
  const t=String(s||'UNKNOWN').toUpperCase();
  if(t==='ONLINE') return 'bad-online';
  if(t==='DEGRADED') return 'bad-degraded';
  if(t==='OFFLINE') return 'bad-offline';
  if(t==='MAINTENANCE') return 'bad-maintenance';
  return 'bad-unknown';
}

function chipHtml(status){
  const s=String(status||'UNKNOWN').toUpperCase();
  let cls='chip-unknown';
  if(s==='ONLINE') cls='chip-online';
  else if(s==='DEGRADED') cls='chip-degraded';
  else if(s==='OFFLINE') cls='chip-offline';
  else if(s==='MAINTENANCE') cls='chip-maintenance';
  return `<span class="chip ${cls}">${esc(s)}</span>`;
}

function buildNodeRuntimeMap(){
  const map={};
  (LAST_OVERVIEW_NODES||[]).forEach(n=>{ map[n.id]=n; });
  return map;
}

function defaultNodePosition(idx,total){
  const cols=Math.max(3,Math.min(5,Math.ceil(Math.sqrt(total||1))));
  const row=Math.floor(idx/cols), col=idx%cols;
  return {x:26+col*185,y:26+row*132};
}

function normalizeTopologyByNodes(){
  const runtimeMap=buildNodeRuntimeMap();
  const ids=(NODE_ROWS||[]).map(n=>String(n.id||'')).filter(Boolean);
  const existed={};
  (TOPOLOGY.nodes||[]).forEach(n=>{if(n&&n.id) existed[n.id]=n;});

  const merged=[];
  ids.forEach((id,idx)=>{
    const base=(NODE_ROWS||[]).find(x=>x.id===id)||{};
    const old=existed[id]||{};
    const pos=old.x!=null && old.y!=null ? {x:Number(old.x),y:Number(old.y)} : defaultNodePosition(idx,ids.length);
    merged.push({
      id,
      role:String(old.role||base.role||'business'),
      desc:String(old.desc||base.description||''),
      bizStatus:String(old.bizStatus||'normal'),
      owner:String(old.owner||base.owner||''),
      x:Math.max(4,Math.min(1200,pos.x||0)),
      y:Math.max(4,Math.min(900,pos.y||0)),
    });
  });
  TOPOLOGY.nodes=merged;

  const validIdSet=new Set(ids);
  TOPOLOGY.edges=(TOPOLOGY.edges||[]).filter(e=>e&&validIdSet.has(e.from)&&validIdSet.has(e.to));
}

function syncKpi(d){
  const s=d.summary||{};
  setText('kpiSla',s.sla_percent==null?'-':String(Number(s.sla_percent).toFixed(1)));
  setText('kpiNodes',s.total_nodes ?? '-');
  setText('kpiHealthy',s.healthy_nodes ?? '-');
  setText('kpiDegraded',s.degraded_nodes ?? '-');
  setText('kpiOffline',s.offline_nodes ?? '-');
  setText('kpiAlerts',s.alert_count ?? '-');
}

function syncNodeSelects(){
  const opts=(NODE_ROWS||[]).map(n=>`<option value="${esc(n.id)}">${esc(n.name)} (${esc(n.server_id||'-')})</option>`).join('');
  const syncIds=['opNodeId','edgeFrom','edgeTo','daemonNodeId','stressNodeId','dbNodeId'];
  syncIds.forEach(id=>{const el=byId(id); if(el){el.innerHTML=opts;}});
  if(SELECTED_NODE_ID){
    ['opNodeId','edgeFrom','daemonNodeId','stressNodeId','dbNodeId'].forEach(id=>{const el=byId(id); if(el){el.value=SELECTED_NODE_ID;}});
  }
}

function drawTopology(){
  const wrap=byId('topologyWrap');
  const svg=byId('topologySvg');
  const layer=byId('topologyNodeLayer');
  if(!wrap||!svg||!layer) return;
  const runtime=buildNodeRuntimeMap();

  svg.innerHTML='';
  layer.innerHTML='';

  const nodeMap={};
  (TOPOLOGY.nodes||[]).forEach(n=>{nodeMap[n.id]=n;});

  (TOPOLOGY.edges||[]).forEach((e,idx)=>{
    const a=nodeMap[e.from], b=nodeMap[e.to];
    if(!a||!b) return;
    const x1=a.x+86, y1=a.y+56, x2=b.x+86, y2=b.y+56;
    const line=document.createElementNS('http://www.w3.org/2000/svg','line');
    line.setAttribute('x1',String(x1)); line.setAttribute('y1',String(y1));
    line.setAttribute('x2',String(x2)); line.setAttribute('y2',String(y2));
    line.setAttribute('stroke', SELECTED_EDGE_ID===e.id ? '#dc2626' : '#64748b');
    line.setAttribute('stroke-width', SELECTED_EDGE_ID===e.id ? '3' : '2');
    line.setAttribute('opacity', '0.75');
    line.style.cursor='pointer';
    line.addEventListener('click',()=>{SELECTED_EDGE_ID=e.id;byId('edgeHint').textContent='宸查€変腑杩炵嚎锛?+e.from+' -> '+e.to+'锛堢偣鍑诲垹闄ゅ彲绉婚櫎锛?;drawTopology();});
    svg.appendChild(line);

    const mid=document.createElementNS('http://www.w3.org/2000/svg','text');
    mid.setAttribute('x',String((x1+x2)/2));
    mid.setAttribute('y',String((y1+y2)/2-4));
    mid.setAttribute('fill','#334155');
    mid.setAttribute('font-size','10');
    mid.setAttribute('text-anchor','middle');
    mid.textContent=String(e.type||'link');
    svg.appendChild(mid);
  });

  (TOPOLOGY.nodes||[]).forEach(n=>{
    const rt=runtime[n.id]||{};
    const st=String(rt.status||'UNKNOWN').toUpperCase();
    const div=document.createElement('div');
    div.className='topology-node '+statusClass(st)+(SELECTED_NODE_ID===n.id?' active':'');
    div.style.left=n.x+'px';
    div.style.top=n.y+'px';
    div.innerHTML=`<div class="n-title">${esc(rt.name||n.id)}</div>
      <div class="n-meta"><span class="n-role">${esc(n.role||'business')}</span>${chipHtml(st)}</div>
      <div class="n-meta">${esc(rt.server_id||'-')} 路 ${esc(rt.env||'-')}</div>
      <div class="n-meta">${esc(n.desc||'鏃犺鏄?)}</div>`;
    div.addEventListener('click',(ev)=>{ev.stopPropagation();selectNode(n.id,true);});
    div.addEventListener('mousedown',(ev)=>{
      if(ev.button!==0) return;
      DRAG_NODE_ID=n.id;
      DRAG_OFFSET={x:ev.clientX-n.x,y:ev.clientY-n.y};
      ev.preventDefault();
    });
    layer.appendChild(div);
  });

  wrap.onmousemove=(ev)=>{
    if(!DRAG_NODE_ID) return;
    const node=findMeta(DRAG_NODE_ID);
    if(!node) return;
    const rect=wrap.getBoundingClientRect();
    node.x=Math.max(2,Math.min(rect.width-176,ev.clientX-rect.left-DRAG_OFFSET.x));
    node.y=Math.max(2,Math.min(rect.height-112,ev.clientY-rect.top-DRAG_OFFSET.y));
    drawTopology();
  };
  wrap.onmouseup=()=>{ if(DRAG_NODE_ID){ DRAG_NODE_ID=''; saveTopologyLayout(); } };
  wrap.onmouseleave=()=>{DRAG_NODE_ID='';};
  wrap.onclick=()=>{SELECTED_EDGE_ID=''; byId('edgeHint').textContent='鐐瑰嚮鎷撴墤涓殑绾挎潯鍙€変腑鍚庡垹闄ゃ€?; drawTopology();};
}

function selectNode(nodeId,fromMap){
  SELECTED_NODE_ID=nodeId||'';
  const m=findMeta(SELECTED_NODE_ID)||{};
  byId('topoNodeId').value=SELECTED_NODE_ID;
  byId('topoNodeDesc').value=m.desc||'';
  byId('topoNodeRole').value=m.role||'business';
  byId('topoNodeBizStatus').value=m.bizStatus||'normal';
  byId('topoNodeOwner').value=m.owner||'';
  byId('edgeFrom').value=SELECTED_NODE_ID;

  const rt=(LAST_OVERVIEW_NODES||[]).find(x=>x.id===SELECTED_NODE_ID)||{};
  if(rt.server_id){byId('opTarget').value=rt.server_id;}
  byId('opNodeId').value=SELECTED_NODE_ID;
  ['daemonNodeId','stressNodeId','dbNodeId'].forEach(id=>{const el=byId(id); if(el){el.value=SELECTED_NODE_ID;}});
  drawTopology();
  if(fromMap){window.scrollTo({top:document.querySelector('.panel').offsetTop+360,behavior:'smooth'});}
}

function focusNodeOnMap(){
  if(!SELECTED_NODE_ID){return;}
  const node=findMeta(SELECTED_NODE_ID); if(!node) return;
  byId('edgeHint').textContent='鑺傜偣宸插畾浣嶏細'+SELECTED_NODE_ID;
  drawTopology();
}

async function saveNodeMeta(){
  const nodeId=read('topoNodeId'); if(!nodeId){alert('璇峰厛閫夋嫨鑺傜偣');return;}
  const patch={
    desc:read('topoNodeDesc'), role:read('topoNodeRole'), bizStatus:read('topoNodeBizStatus'), owner:read('topoNodeOwner')
  };
  const r=await fetch('/api/ops-platform/topology/node/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({node_id:nodeId,patch})});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'topology_node_update',trace_id:'',node:nodeId,message:d.message||d.error||'',raw:d});
  if(d.ok){
    TOPOLOGY=d.topology||TOPOLOGY;
    const m=findMeta(nodeId); if(m){Object.assign(m,patch);} 
    drawTopology();
  }
}

async function upsertEdge(){
  const from=read('edgeFrom'), to=read('edgeTo');
  if(!from||!to||from===to){alert('璇烽€夋嫨鏈夋晥鐨勮捣鐐瑰拰缁堢偣');return;}
  const payload={from,to,type:read('edgeType')||'depends_on',note:read('edgeNote')};
  const r=await fetch('/api/ops-platform/topology/edge/upsert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'topology_edge_upsert',trace_id:'',node:from,message:d.message||d.error||'',raw:d});
  if(d.ok){TOPOLOGY=d.topology||TOPOLOGY; SELECTED_EDGE_ID=''; drawTopology();}
}

async function removeSelectedEdge(){
  if(!SELECTED_EDGE_ID){alert('璇峰厛鍦ㄥ浘涓婄偣閫変竴鏉¤繛绾?);return;}
  const r=await fetch('/api/ops-platform/topology/edge/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({edge_id:SELECTED_EDGE_ID})});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'topology_edge_delete',trace_id:'',node:'-',message:d.message||d.error||'',raw:d});
  if(d.ok){TOPOLOGY=d.topology||TOPOLOGY; SELECTED_EDGE_ID=''; byId('edgeHint').textContent='鐐瑰嚮鎷撴墤涓殑绾挎潯鍙€変腑鍚庡垹闄ゃ€?; drawTopology();}
}

async function loadTopology(){
  const q=read('opsProjectFilter')?('?project_id='+encodeURIComponent(read('opsProjectFilter'))):'';
  const r=await fetch('/api/ops-platform/topology'+q);
  const d=await r.json();
  if(!d.ok){addStream({time:new Date().toISOString(),ok:false,action:'topology_load',trace_id:'',node:'-',message:d.error||'鍔犺浇澶辫触',raw:d});return;}
  TOPOLOGY=d.topology||{nodes:[],edges:[]};
  normalizeTopologyByNodes();
  if(!SELECTED_NODE_ID && TOPOLOGY.nodes.length){SELECTED_NODE_ID=TOPOLOGY.nodes[0].id;}
  syncNodeSelects();
  if(SELECTED_NODE_ID){selectNode(SELECTED_NODE_ID,false);} else {drawTopology();}
}

async function saveTopologyLayout(){
  const r=await fetch('/api/ops-platform/topology/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topology:TOPOLOGY})});
  const d=await r.json();
  if(!d.ok){addStream({time:new Date().toISOString(),ok:false,action:'topology_save',trace_id:'',node:'-',message:d.error||'淇濆瓨澶辫触',raw:d});return false;}
  return true;
}

function renderActionGroupOptions(){
  const groups=[];
  ACTION_CATALOG.forEach(a=>{if(!groups.includes(a.groupId)) groups.push(a.groupId);});
  const map={observe:'鍙宸℃',lifecycle:'鐢熷懡鍛ㄦ湡',incident:'鏁呴殰搴旀€?,operation:'杩愯惀鎺у埗',special:'涓撻」浣滀笟'};
  byId('opActionGroup').innerHTML=groups.map(g=>`<option value="${g}">${map[g]||g}</option>`).join('');
}

function renderActionOptions(){
  const g=read('opActionGroup')||'observe';
  const rows=ACTION_CATALOG.filter(a=>a.groupId===g);
  byId('opActionType').innerHTML=rows.map(a=>`<option value="${a.value}">${a.label}</option>`).join('');
  setText('opGroupHint','鍒嗙被锛?+(rows[0]?rows[0].group:'-'));
  syncRiskHint();
}

function syncRiskHint(){
  const action=read('opActionType');
  const found=ACTION_CATALOG.find(x=>x.value===action)||{risk:'medium',group:'鏈煡'};
  const hint=byId('opRiskHint');
  hint.textContent='椋庨櫓绾у埆锛?+found.risk.toUpperCase();
  hint.className='text-xs px-2 py-1 rounded-full '+(found.risk==='high'?'bg-rose-100 text-rose-700':(found.risk==='medium'?'bg-amber-100 text-amber-700':'bg-emerald-100 text-emerald-700'));
  setText('opGroupHint','鍒嗙被锛?+found.group);
}

function syncNodeContextFromSelect(){
  const nodeId=read('opNodeId');
  if(!nodeId) return;
  selectNode(nodeId,false);
}

function addStream(item){
  const box=byId('streamList');
  const row=document.createElement('div');
  row.className='log-item';
  row.innerHTML='<div class="flex items-center justify-between gap-2"><div class="text-xs text-slate-500">'+esc(item.time||'')+'</div><div class="text-xs '+(item.ok?'text-emerald-600':'text-rose-600')+'">'+(item.ok?'SUCCESS':'FAIL')+'</div></div>'+
                '<div class="mt-1 text-sm font-semibold text-slate-900">'+esc(item.action||'-')+' @ '+esc(item.node||'-')+'</div>'+
                '<div class="mt-1 text-xs text-slate-600">traceId: <span class="mono">'+esc(item.trace_id||'-')+'</span></div>'+
                '<div class="mt-1 text-xs text-slate-700">'+esc(item.message||'')+'</div>'+
                '<details class="mt-1"><summary class="text-xs text-slate-500 cursor-pointer">灞曞紑鍘熸枃</summary><pre class="mt-1 text-[11px] p-2 bg-white border rounded mono overflow-auto">'+esc(JSON.stringify(item.raw||{},null,2))+'</pre></details>';
  box.prepend(row);
  while(box.children.length>120){box.removeChild(box.lastChild);} 
}

function renderEvents(rows){
  const box=byId('eventList');
  box.innerHTML=(rows||[]).map(e=>`<div class="rounded-xl border border-slate-200 p-2 bg-slate-50"><div class="flex items-center justify-between"><span class="text-[11px] px-2 py-0.5 rounded-full ${e.severity==='critical'?'bg-rose-100 text-rose-700':(e.severity==='warning'?'bg-amber-100 text-amber-700':'bg-sky-100 text-sky-700')}">${esc(e.severity||'info')}</span><span class="text-xs text-slate-400">${esc(e.time||'')}</span></div><div class="mt-1 text-sm text-slate-800">${esc(e.title||'-')}</div><div class="text-xs text-slate-500">${esc(e.message||'')}</div></div>`).join('') || '<div class="text-sm text-slate-400">鏆傛棤浜嬩欢</div>';
}

async function loadEvents(){
  const r=await fetch('/api/ops-platform/events?limit=120');
  const d=await r.json();
  renderEvents((d.events||[]));
}

function updatePresetHint(preset){
  const hint=byId('presetHint');
  if(!hint){return;}
  if(!preset){
    hint.textContent='閫夋嫨妯℃澘鍚庡彲蹇€熻惤鑺傜偣锛屽苟鑷姩娉ㄥ叆涓婁笅娓歌鍒欍€?;
    return;
  }
  const up=(preset.fixed_upstream_roles||[]).join(', ')||'鏃?;
  const down=(preset.fixed_downstream_roles||[]).join(', ')||'鏃?;
  hint.textContent='瑙掕壊 '+(preset.role||'-')+'锛涗笂娓? '+up+'锛涗笅娓? '+down+'锛涜鏄? '+(preset.default_desc||'');
}

function selectedPreset(){
  const pid=read('presetSelect');
  return (NODE_PRESETS||[]).find(x=>String(x.preset_id||'')===pid)||null;
}

async function loadNodePresets(){
  const res=await fetch('/api/ops-platform/node-presets');
  const data=await res.json();
  if(!data.ok){
    addStream({time:new Date().toISOString(),ok:false,action:'node_presets',trace_id:'',node:'-',message:data.message||data.error||'妯℃澘鍔犺浇澶辫触',raw:data});
    return;
  }
  NODE_PRESETS=Array.isArray(data.presets)?data.presets:[];
  const select=byId('presetSelect');
  select.innerHTML=NODE_PRESETS.map(p=>`<option value="${esc(p.preset_id)}">${esc(p.name)} (${esc(p.role||'-')})</option>`).join('');
  select.onchange=()=>updatePresetHint(selectedPreset());
  updatePresetHint(selectedPreset());
}

async function addNodeFromPreset(){
  const preset=selectedPreset();
  if(!preset){alert('璇峰厛閫夋嫨妯℃澘');return;}
  const body={
    preset_id:String(preset.preset_id||''),
    name:read('presetNodeName'),
    server_id:read('presetServerId'),
    project_id:read('opsProjectFilter'),
    owner:read('presetOwner'),
    env:read('presetEnv'),
    channel:read('presetChannel'),
    description:read('presetDesc'),
    daemon_start_cmd:read('presetStartCmd'),
    daemon_stop_cmd:read('presetStopCmd'),
  };
  const res=await fetch('/api/ops-platform/node/add-from-preset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await res.json();
  addStream({time:new Date().toISOString(),ok:!!data.ok,action:'add_node_from_preset',trace_id:'',node:(data.node||{}).id||'-',message:data.message||data.error||'',raw:data});
  if(!data.ok){alert(data.message||data.error||'娣诲姞澶辫触');return;}
  if(data.node&&data.node.id){
    byId('presetNodeName').value='';
    byId('presetServerId').value='';
    byId('presetDesc').value='';
    SELECTED_NODE_ID=String(data.node.id);
  }
  await loadOverviewAndTopology();
  await loadOnboarding();
  alert('鑺傜偣宸叉坊鍔犲苟绾冲叆鎷撴墤銆?);
}

function renderOnboarding(data){
  const body=byId('onboardBody');
  const rows=Array.isArray(data.checks)?data.checks:[];
  if(!rows.length){
    body.innerHTML='<tr><td class="px-2 py-3 text-slate-400" colspan="5">鏆傛棤鏁版嵁</td></tr>';
    return;
  }
  body.innerHTML=rows.map(row=>{
    const sev=String(row.severity||'ok');
    const sevClass=sev==='critical'?'text-rose-600':(sev==='warning'?'text-amber-600':'text-emerald-600');
    const issues=(row.issues||[]).join('锛?)||'閫氳繃';
    return `<tr>
      <td class="px-2 py-2">${esc(row.node_name||row.node_id||'-')}<div class="text-xs text-slate-400 mono">${esc(row.node_id||'-')}</div></td>
      <td class="px-2 py-2">${esc(row.role||'-')}</td>
      <td class="px-2 py-2">${chipHtml(row.status||'UNKNOWN')}</td>
      <td class="px-2 py-2 text-xs">${esc(issues)}</td>
      <td class="px-2 py-2 text-xs font-semibold ${sevClass}">${esc(sev)}</td>
    </tr>`;
  }).join('');
}

async function loadOnboarding(){
  const res=await fetch('/api/ops-platform/node-onboarding');
  const data=await res.json();
  if(!data.ok){
    addStream({time:new Date().toISOString(),ok:false,action:'node_onboarding',trace_id:'',node:'-',message:data.message||data.error||'浣撴澶辫触',raw:data});
    return;
  }
  renderOnboarding(data);
  const s=data.summary||{};
  setText('onboardSummary','鎬昏妭鐐?'+(s.total_nodes||0)+'锛屼弗閲?'+(s.critical||0)+'锛屽憡璀?'+(s.warning||0)+'锛岄€氳繃 '+(s.ok_nodes||0));
}

async function loadNodes(){
  const r=await fetch('/api/gm-legacy/nodes');
  const d=await r.json();
  NODE_ROWS=d.nodes||[];
  byId('nodeConfigJson').value = JSON.stringify(NODE_ROWS,null,2);
  syncNodeSelects();
}

async function loadOverview(){
  const projectId=read('opsProjectFilter');
  const q=projectId?('?project_id='+encodeURIComponent(projectId)):'';
  const r=await fetch('/api/ops-platform/overview'+q);
  const d=await r.json();
  if(!d.ok){ addStream({time:new Date().toISOString(),ok:false,action:'overview',message:d.error||'鎬昏鍔犺浇澶辫触',raw:d}); return; }
  LAST_OVERVIEW_NODES=d.nodes||[];
  syncKpi(d);
}

async function loadOverviewAndTopology(){
  await loadNodes();
  await loadOverview();
  await loadTopology();
  await loadEvents();
  await loadOnboarding();
}

function roleAndStatusInit(){
  byId('topoNodeRole').innerHTML=ROLE_OPTIONS.map(x=>`<option value="${x}">${x}</option>`).join('');
  byId('topoNodeBizStatus').innerHTML=BIZ_STATUS_OPTIONS.map(x=>`<option value="${x}">${x}</option>`).join('');
  byId('edgeType').innerHTML=EDGE_TYPES.map(x=>`<option value="${x}">${x}</option>`).join('');
}

async function validateAction(){
  let payload={};
  try{payload=readJson('opPayload');}catch(e){alert(e.message);return;}
  const req={node_id:read('opNodeId'),action_type:read('opActionType'),target:read('opTarget'),ticket_id:read('opTicket'),reason:read('opReason'),approver:read('opApprover'),dry_run:byId('opDryRun').checked,payload};
  const r=await fetch('/api/ops-platform/actions/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  const hint=byId('opValidateHint');
  if(d.ok){
    hint.textContent='棰勬閫氳繃'+(d.require_approval?'锛堥珮鍗遍渶瀹℃壒锛?:'');
    hint.className='text-xs text-emerald-600';
  }else{
    hint.textContent='棰勬澶辫触锛?+(d.message||d.error||'鍙傛暟缂哄け');
    hint.className='text-xs text-rose-600';
  }
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'validate',trace_id:d.trace_id||'',node:req.node_id,message:d.message||d.error||'validate',raw:d});
}

async function createApproval(){
  let payload={};
  try{payload=readJson('opPayload');}catch(e){alert(e.message);return;}
  const req={node_id:read('opNodeId'),action_type:read('opActionType'),target:read('opTarget'),ticket_id:read('opTicket'),reason:read('opReason'),approver:read('opApprover'),payload};
  const r=await fetch('/api/ops-platform/actions/approval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'approval',trace_id:d.trace_id||'',node:req.node_id,message:d.message||d.error||'approval',raw:d});
  if(d.ok){ alert('瀹℃壒鍗曞凡鍒涘缓: '+(d.approval_id||'')); }
}

async function executeAction(){
  let payload={};
  try{payload=readJson('opPayload');}catch(e){alert(e.message);return;}
  const req={node_id:read('opNodeId'),action_type:read('opActionType'),target:read('opTarget'),ticket_id:read('opTicket'),reason:read('opReason'),approver:read('opApprover'),dry_run:byId('opDryRun').checked,payload};
  const r=await fetch('/api/ops-platform/actions/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  byId('streamSummary').textContent=d.ok?'鎵ц鎴愬姛':'鎵ц澶辫触';
  byId('streamSummary').className=d.ok?'text-xs text-emerald-600':'text-xs text-rose-600';
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:req.action_type,trace_id:d.trace_id||'',node:req.node_id,message:d.message||d.error||'',raw:d});
  if(d.trace_id){ byId('traceQuery').value=d.trace_id; }
  await loadOverview();
  await loadTopology();
  await loadEvents();
  await loadOnboarding();
}

async function runDaemonAction(action){
  const node_id=read('daemonNodeId')||read('opNodeId');
  if(!node_id){alert('璇峰厛閫夋嫨鑺傜偣');return;}
  const req={node_id,action,ticket_id:read('daemonTicketId')||'OPS-DAEMON',reason:read('daemonReason')||'瀹堟姢杩涚▼鎿嶄綔'};
  const r=await fetch('/api/ops-platform/node/daemon-action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  const ok=!!d.ok;
  byId('daemonHint').textContent=(ok?'鎵ц鎴愬姛锛?:'鎵ц澶辫触锛?)+(d.message||d.error||'-');
  byId('daemonHint').className='text-xs '+(ok?'text-emerald-600':'text-rose-600');
  addStream({time:new Date().toISOString(),ok,action:'daemon_'+action,trace_id:d.trace_id||'',node:node_id,message:d.message||d.error||'',raw:d});
  await loadOverview();
  await loadTopology();
  await loadEvents();
  await loadOnboarding();
}

async function runFlowSmoke(){
  const raw=read('flowPathNodes');
  const path_nodes=raw.split(',').map(s=>s.trim()).filter(Boolean);
  if(path_nodes.length<2){alert('璇疯嚦灏戝～鍐欎袱涓妭鐐笽D');return;}
  const req={path_nodes,reason:read('flowReason')||'涓€閿啋鐑?};
  const r=await fetch('/api/ops-platform/flow-smoke',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  const ok=!!d.ok;
  byId('flowHint').textContent=(ok?'鍐掔儫閫氳繃锛宖lowId=':'鍐掔儫澶辫触锛宖lowId=')+(d.flow_id||'-');
  byId('flowHint').className='text-xs '+(ok?'text-emerald-600':'text-rose-600');
  addStream({time:new Date().toISOString(),ok,action:'flow_smoke',trace_id:d.flow_id||'',node:path_nodes.join(' -> '),message:d.message||d.error||'',raw:d});
  await loadEvents();
}

async function runStressTest(){
  const node_id=read('stressNodeId')||read('opNodeId');
  if(!node_id){alert('璇峰厛閫夋嫨鍘嬫祴鑺傜偣');return;}
  const qps=Number(read('stressQps')||300);
  const duration_sec=Number(read('stressDuration')||180);
  const req={node_id,qps,duration_sec,reason:read('stressReason')||'鍘嬪姏娴嬭瘯'};
  const r=await fetch('/api/ops-platform/stress-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'stress_test',trace_id:d.trace_id||'',node:node_id,message:d.message||d.error||'',raw:d});
  await loadEvents();
}

async function runDbMigration(){
  const node_id=read('dbNodeId')||read('opNodeId');
  if(!node_id){alert('璇峰厛閫夋嫨杩佺Щ鑺傜偣');return;}
  const req={node_id,direction:read('dbDirection')||'up',version:read('dbVersion'),command:read('dbCommand'),reason:read('dbReason')||'鏁版嵁搴撹縼绉?};
  const r=await fetch('/api/ops-platform/db-migration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'db_migration',trace_id:d.trace_id||'',node:node_id,message:d.message||d.error||'',raw:d});
  await loadOverview();
  await loadTopology();
  await loadEvents();
  await loadOnboarding();
}

async function queryTrace(){
  const id=read('traceQuery');
  if(!id){return;}
  const r=await fetch('/api/ops-platform/actions/'+encodeURIComponent(id));
  const d=await r.json();
  byId('traceDetail').textContent=JSON.stringify(d,null,2);
}

function quickRollbackHint(){
  const t=read('traceQuery');
  alert(t?('璇峰熀浜?traceId '+t+' 鍒涘缓鍥炴粴鍔ㄤ綔骞堕噸鏂版墽琛岋紙寤鸿鍏?dry-run锛夈€?):'璇峰厛鎵ц鍔ㄤ綔骞惰幏鍙?traceId锛屽啀杩涜鍥炴粴銆?);
}

function toggleNodeConfig(show){
  const panel=byId('nodeConfigPanel');
  if(show){panel.classList.remove('hidden');}else{panel.classList.add('hidden');}
}

async function saveNodesRawJson(){
  let rows=[];
  try{rows=JSON.parse(byId('nodeConfigJson').value||'[]');}catch(_){alert('JSON 瑙ｆ瀽澶辫触');return;}
  const r=await fetch('/api/gm-legacy/nodes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nodes:rows})});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'save_nodes',trace_id:'',node:'-',message:d.ok?'鑺傜偣閰嶇疆宸蹭繚瀛?:'鑺傜偣閰嶇疆淇濆瓨澶辫触',raw:d});
  await loadOverviewAndTopology();
}

window.addEventListener('beforeunload', ()=>{ if(DRAG_NODE_ID){ DRAG_NODE_ID=''; } });

(async function bootstrap(){
  roleAndStatusInit();
  renderActionGroupOptions();
  renderActionOptions();
  const projectId=(document.querySelector('.ops-pro-shell')||{}).dataset?.projectId||'';
  if(projectId){byId('opsProjectFilter').value=projectId;}
  await loadNodePresets();
  await loadOverviewAndTopology();
})();
</script>
"""
    return _render_page(content, "杩愮淮骞冲彴")


@bp.route("/api/gm-legacy/nodes")
@admin_required("gm_ops")
def gm_legacy_nodes_list():
    return jsonify({"ok": True, "count": len(_load_nodes()), "nodes": _load_nodes()})


@bp.route("/api/gm-legacy/nodes", methods=["POST"])
@admin_required("gm_ops")
def gm_legacy_nodes_save():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    _save_nodes(rows)
    return jsonify({"ok": True, "count": len(_load_nodes()), "nodes": _load_nodes()})


@bp.route("/api/gm-classic/action", methods=["POST"])
@admin_required("gm_ops")
def gm_classic_action():
    if not _allow_gm_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯 GM 鎵ц鏉冮檺 (gm.classic.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip()
    if action not in GM_ACTION_PATHS:
        return jsonify({"ok": False, "error": "unsupported action"}), 400

    node, err = _node_or_400(payload)
    if err:
        return err

    result = _client.submit_form(
        base_url=str(node.get("base_url") or ""),
        username=str(node.get("username") or ""),
        password=str(node.get("password") or ""),
        path=GM_ACTION_PATHS[action],
        form=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
    )
    return jsonify({"ok": bool(result.get("success")), "node": node.get("id"), "action": action, "result": result}), (200 if result.get("success") else 502)


# ---------------------------
# Ops Platform V2 (native)
# ---------------------------

_ops_gateway = OpsPlatformGateway()
OPS_TRACE_LOG_KEY = "OPS_PLATFORM_TRACE_LOGS"
OPS_EVENT_LOG_KEY = "OPS_PLATFORM_EVENT_LOGS"
OPS_ALERT_SNAPSHOT_KEY = "OPS_PLATFORM_ALERT_SNAPSHOT"
OPS_TOPOLOGY_KEY = "OPS_PLATFORM_TOPOLOGY"
OPS_NODE_PRESETS_KEY = "OPS_PLATFORM_NODE_PRESETS"
OPS_TOPOLOGY_BLUEPRINTS_KEY = "OPS_PLATFORM_TOPOLOGY_BLUEPRINTS"
OPS_DAEMON_STATE_KEY = "OPS_PLATFORM_DAEMON_STATE"
OPS_FLOW_EXEC_KEY = "OPS_PLATFORM_FLOW_EXECUTIONS"
OPS_AGENT_REGISTRY_KEY = "OPS_PLATFORM_AGENT_REGISTRY"
OPS_AGENT_REGISTRY_V2_KEY = "OPS_PLATFORM_AGENT_REGISTRY_V2"
OPS_NODE_AGENT_BINDING_KEY = "OPS_PLATFORM_NODE_AGENT_BINDING"
OPS_NODE_SERVICE_BINDING_KEY = "OPS_PLATFORM_NODE_SERVICE_BINDING"
OPS_AGENT_JOBS_KEY = "OPS_PLATFORM_AGENT_JOBS"
OPS_AGENT_POLICY_KEY = "OPS_PLATFORM_AGENT_POLICY"
OPS_RUNTIME_RUNS_KEY = "OPS_PLATFORM_RUNTIME_RUNS"


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _load_json_config(key: str, default):
    raw = get_system_config(key, default)
    if isinstance(raw, type(default)):
        return raw
    return default


def _save_json_config(key: str, value, description: str = "") -> None:
    try:
        user = str(session.get("user") or "system")
    except RuntimeError:
        user = "system"
    set_system_config(key, value, value_type="json", description=description, username=user)


def _load_agent_registry() -> Dict[str, Any]:
    raw = _load_json_config(OPS_AGENT_REGISTRY_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_agent_registry(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_AGENT_REGISTRY_KEY, data if isinstance(data, dict) else {}, description="Ops Agent registry and heartbeat state")


def _load_agent_registry_v2() -> Dict[str, Any]:
    raw = _load_json_config(OPS_AGENT_REGISTRY_V2_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_agent_registry_v2(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_AGENT_REGISTRY_V2_KEY, data if isinstance(data, dict) else {}, description="Ops Agent registry v2")


def _load_node_agent_bindings() -> Dict[str, Any]:
    raw = _load_json_config(OPS_NODE_AGENT_BINDING_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_node_agent_bindings(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_NODE_AGENT_BINDING_KEY, data if isinstance(data, dict) else {}, description="Ops node->agent primary binding")


def _load_node_service_bindings() -> Dict[str, Any]:
    raw = _load_json_config(OPS_NODE_SERVICE_BINDING_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_node_service_bindings(data: Dict[str, Any]) -> None:
    _save_json_config(OPS_NODE_SERVICE_BINDING_KEY, data if isinstance(data, dict) else {}, description="Ops node->service primary binding")


def _load_agent_jobs() -> List[Dict[str, Any]]:
    raw = _load_json_config(OPS_AGENT_JOBS_KEY, [])
    return raw if isinstance(raw, list) else []


def _save_agent_jobs(rows: List[Dict[str, Any]]) -> None:
    items = rows if isinstance(rows, list) else []
    if len(items) > 1200:
        items = items[-1200:]
    _save_json_config(OPS_AGENT_JOBS_KEY, items, description="Ops Agent 浠诲姟闃熷垪涓庣姸鎬佹満")


def _load_runtime_runs() -> List[Dict[str, Any]]:
    raw = _load_json_config(OPS_RUNTIME_RUNS_KEY, [])
    return raw if isinstance(raw, list) else []


def _save_runtime_runs(rows: List[Dict[str, Any]]) -> None:
    items = rows if isinstance(rows, list) else []
    if len(items) > 80:
        items = items[-80:]
    _save_json_config(OPS_RUNTIME_RUNS_KEY, items, description="Ops runtime start/stop run logs")


def _upsert_runtime_run(run_obj: Dict[str, Any]) -> None:
    rid = str((run_obj or {}).get("run_id") or "").strip()
    if not rid:
        return
    rows = _load_runtime_runs()
    replaced = False
    for idx, row in enumerate(rows):
        if str((row or {}).get("run_id") or "") == rid:
            rows[idx] = run_obj
            replaced = True
            break
    if not replaced:
        rows.insert(0, run_obj)
    _save_runtime_runs(rows)


def _find_runtime_run(run_id: str) -> Optional[Dict[str, Any]]:
    rid = str(run_id or "").strip()
    if not rid:
        return None
    for row in _load_runtime_runs():
        if not isinstance(row, dict):
            continue
        if str(row.get("run_id") or "") == rid:
            return row
    return None


def _runtime_active_for_project(project_id: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    rows = _load_runtime_runs()
    latest_start = None
    latest_stop = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if pid and str(row.get("project_id") or "") != pid:
            continue
        op = str(row.get("op") or "").lower()
        st = str(row.get("status") or "").lower()
        if op == "start" and st in ("running", "success"):
            if latest_start is None:
                latest_start = row
        if op == "stop" and st in ("running", "success"):
            if latest_stop is None:
                latest_stop = row
    if not latest_start:
        return {"active": False, "run_id": "", "status": "", "reason": "no_start_run"}
    start_ts = str(latest_start.get("updated_at") or latest_start.get("created_at") or "")
    stop_ts = str((latest_stop or {}).get("updated_at") or (latest_stop or {}).get("created_at") or "")
    if latest_stop and stop_ts and start_ts and stop_ts >= start_ts:
        return {"active": False, "run_id": str(latest_start.get("run_id") or ""), "status": str(latest_start.get("status") or ""), "reason": "stopped_after_start"}
    return {"active": True, "run_id": str(latest_start.get("run_id") or ""), "status": str(latest_start.get("status") or ""), "reason": "start_alive"}


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

CLUSTER_JSON_PATH = os.path.join(
    os.getenv("GAME_SERVER_REPO", r"E:\maclient\game-server"),
    "config", "cluster.json",
)


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
                         ("capabilities", capabilities)]:
                if hit.get(k) != v:
                    hit[k] = v
                    changed = True
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
                "probe_proto": "udp" if srv_type.upper() == "KCP" else "tcp",
                "updated_at": now,
            })
            added += 1

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

    return {"synced": len(servers), "added": added, "updated": updated, "stale": stale_count}


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


def _probe_by_protocol(host: str, port: int, proto: str = "tcp", timeout: float = 1.5) -> Dict[str, Any]:
    """根据协议类型选择探活方式。"""
    if proto == "udp":
        return _udp_probe(host, port, timeout)
    return _tcp_probe(host, port, timeout)


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
        proto = str(agent.get("probe_proto") or "tcp").strip().lower()
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

    # 尝试从 game-server /ops/cluster 拉取集群实际运行状态
    cluster_status: Dict[str, str] = {}
    try:
        gw = OpsPlatformGateway()
        # 找第一个 ops_base_url 可用的节点
        for a in agents:
            node_candidate = _resolve_node(node_id=str(a.get("node_id") or ""))
            if node_candidate and node_candidate.get("ops_base_url"):
                cluster_resp = gw.cluster(node_candidate, actor="probe", reason="realtime-status", ticket_id="OPS-REALTIME")
                if cluster_resp and cluster_resp.get("success"):
                    cluster_data = cluster_resp.get("data") or {}
                    servers = cluster_data.get("Servers") or cluster_data.get("servers") or []
                    for srv in servers:
                        sid = str(srv.get("ServerId") or srv.get("serverId") or "").strip()
                        st = str(srv.get("State") or srv.get("state") or "").strip().upper()
                        if sid and st:
                            cluster_status[sid] = st
                break
    except Exception:
        pass

    # 合并 cluster 状态：如果 cluster.json 里配了 Maintenance 但端口通，标记为 MAINTENANCE
    for aid, probe_info in results.items():
        # 从 agent 列表反查 node_id
        for a in agents:
            if str(a.get("agent_id") or "") == aid:
                nid = str(a.get("node_id") or "").strip()
                config_state = str(a.get("config_state") or "").strip().upper()
                if nid and nid in cluster_status:
                    srv_state = cluster_status[nid]
                    if srv_state == "MAINTENANCE":
                        probe_info["effective_status"] = "MAINTENANCE"
                    elif srv_state == "OFFLINE" and not probe_info["ok"]:
                        probe_info["effective_status"] = "OFFLINE"
                # 也考虑 config_state（cluster.json 配的 State 字段）
                if config_state == "MAINTENANCE":
                    probe_info["effective_status"] = "MAINTENANCE"
                break

    return results


# ──────────────────────────────────────────────────────────────────────
#  后台探活引擎 + SSE 推送：定时探活缓存结果，状态变化时推送前端
# ──────────────────────────────────────────────────────────────────────

import queue as _queue_mod
import time as _time_mod
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 全局探活缓存 ---
_probe_cache: Dict[str, Dict[str, Any]] = {}          # agent_id -> probe result
_probe_cache_agents: List[Dict[str, Any]] = []          # 上次全量 agent 列表
_probe_cache_ts: float = 0.0                           # 上次探活完成时间
_probe_cache_sync_ts: float = 0.0                     # 上次 cluster sync 时间
_probe_cache_lock = threading.Lock()                  # 保护缓存写
_probe_change_seq = 0                                 # 变更序号，每次变化+1

# --- SSE 订阅者队列 ---
_sse_subscribers: List[_queue_mod.Queue] = []
_sse_sub_lock = threading.Lock()

# 探活线程池（限制并发，避免瞬时暴打远端）
_probe_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ops-probe")

PROBE_INTERVAL_SEC = 5.0      # 探活轮次间隔
PROBE_SYNC_INTERVAL_SEC = 30.0  # cluster.json 同步间隔


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
        proto = str(a.get("probe_proto") or "tcp").strip().lower()
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
                            "source": "real",
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
                                "source": "real",
                            }
            except Exception:
                pass
    except Exception:
        pass

    # 采集本机指标（Redis/MongoDB/Daemon 等非 game-server 节点）
    try:
        import psutil
        proc_metrics = {
            "cpu_percent": round(psutil.cpu_percent(interval=0.1), 1),
            "mem_percent": round(psutil.virtual_memory().percent, 1),
        }
    except ImportError:
        proc_metrics = {}
    except Exception:
        proc_metrics = {}

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
    # game-server 集群节点不绑独立端口，TCP probe 不通不代表 OFFLINE
    # 用 cluster_status (来自 /ops/cluster) 判断实际状态
    for aid, probe_info in probe_results.items():
        for a in agents:
            if str(a.get("agent_id") or "") == aid:
                nid = str(a.get("node_id") or "").strip()
                config_state = str(a.get("config_state") or "").strip().upper()
                cat = str(a.get("category") or "").strip().lower()
                # cluster 状态覆盖
                if nid and nid in cluster_status:
                    cs = cluster_status[nid]
                    # State 枚举: 0=Online, 1=Maintenance, 2=Stopped(集群视图)
                    # 多进程模式下 State=2 不代表真 OFFLINE，只是不在同一进程内
                    if cs in ("RUNNING", "READY", "ONLINE", "ACTIVE", "0"):
                        probe_info["effective_status"] = "ONLINE"
                    elif cs == "MAINTENANCE" or cs == "1":
                        probe_info["effective_status"] = "MAINTENANCE"
                    elif cs in ("STOPPED", "OFFLINE", "DOWN", "2"):
                        # 多进程模式下不信任 cluster 视图的 Stopped
                        # 如果 TCP probe 通了，保持 ONLINE
                        if probe_info["ok"]:
                            pass  # 保持 TCP probe 结果
                        else:
                            # 不绑端口的内部节点（auth/game/cross），
                            # 如果 game-server 进程在运行就算 ONLINE
                            if cat in ("application", "service"):
                                probe_info["effective_status"] = "ONLINE"
                            else:
                                probe_info["effective_status"] = "OFFLINE"
                    # 其他状态保持 TCP probe 结果
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


@bp.route("/api/ops-platform/agents/stream")
@admin_required("gm_ops")
def ops_platform_agents_stream():
    """SSE 推送端点：前端用 EventSource 订阅，状态变化时推送完整 payload。"""
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    _ensure_probe_bg_started()

    q: _queue_mod.Queue = _queue_mod.Queue(maxsize=64)
    with _sse_sub_lock:
        _sse_subscribers.append(q)

    def _generate():
        # 先推一次全量快照
        snap = None
        try:
            with _probe_cache_lock:
                snap = _build_sse_payload(
                    _probe_cache_agents, _probe_cache
                ) if _probe_cache_agents else None
        except Exception as exc:
            import logging
            logging.getLogger("ops.agent_stream").warning("build initial SSE payload failed: %s", exc, exc_info=True)
        if snap:
            yield f"event: full\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n"

        # 后续增量推送
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"event: change\ndata: {msg}\n\n"
                except _queue_mod.Empty:
                    # 心跳：30s 无变化也推一次，防止连接超时
                    yield f": heartbeat {int(_time_mod.time())}\n\n"
        finally:
            with _sse_sub_lock:
                try:
                    _sse_subscribers.remove(q)
                except ValueError:
                    pass

    from flask import Response
    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


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
    _save_json_config(OPS_AGENT_POLICY_KEY, out, description="Ops Agent 绛栫暐閰嶇疆")


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


def _parse_iso_ts(value: str) -> Optional[datetime]:
    v = str(value or "").strip()
    if not v:
        return None
    try:
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v)
    except Exception:
        return None


def _reconcile_agent_jobs(node_id: str, jobs: List[Dict[str, Any]], *, lease_timeout_sec: int, max_retries: int) -> bool:
    changed = False
    now = datetime.utcnow()
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if str(item.get("node_id") or "") != node_id:
            continue
        status = str(item.get("status") or "").upper()
        if status != "RUNNING":
            continue
        lease = item.get("lease") if isinstance(item.get("lease"), dict) else {}
        leased_at = _parse_iso_ts(str(lease.get("leased_at") or item.get("updated_at") or ""))
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
        "config_state": str(item.get("config_state") or "").upper(),
        "category": str(item.get("category") or "").strip(),
        "role": str(item.get("role") or "").strip(),
        "probe_host": str(item.get("probe_host") or item.get("host_name") or "").strip(),
        "probe_source": str(item.get("probe_source") or "").strip(),
        "probe_proto": str(item.get("probe_proto") or "tcp").strip().lower(),
    }


def _agents_v2_for_project(project_id: str = "") -> List[Dict[str, Any]]:
    rows = _load_agent_registry_v2()
    out: List[Dict[str, Any]] = []
    pid = str(project_id or "").strip()
    for v in rows.values():
        if not isinstance(v, dict):
            continue
        item = _normalize_agent_descriptor_v2(v)
        if pid and item.get("project_id") and item.get("project_id") != pid:
            continue
        out.append(item)
    return out


def _services_for_project(project_id: str = "") -> List[Dict[str, Any]]:
    rows = _logical_agents_for_project(project_id)
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


def _logical_agents_for_project(project_id: str = "") -> List[Dict[str, Any]]:
    rows = _agents_v2_for_project(project_id)
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
                    service_seen.add(sid)
                    services.append(
                        {
                            "service_id": sid,
                            "agent_id": member_agent_id,
                            "node_id": str(svc.get("node_id") or member_node_id or "").strip(),
                            "device_id": device_id,
                            "project_id": str(member.get("project_id") or ""),
                            "display_name": str(svc.get("display_name") or sid),
                            "service_type": str(svc.get("service_type") or svc.get("type") or member.get("role") or ""),
                            "service_port": int(svc.get("service_port") or svc.get("port") or member.get("remote_game_server_port") or member.get("port") or 0),
                            "remote_game_server_port": int(svc.get("remote_game_server_port") or svc.get("service_port") or svc.get("port") or member.get("remote_game_server_port") or member.get("port") or 0),
                            "run_state": str(svc.get("run_state") or member.get("run_state") or ""),
                            "status": str(svc.get("status") or member.get("status") or "UNKNOWN"),
                            "probe_status": str(svc.get("probe_status") or member.get("probe_status") or ""),
                            "probe_rtt_ms": float(svc.get("probe_rtt_ms") or member.get("probe_rtt_ms") or 0.0),
                            "metrics": svc.get("metrics") if isinstance(svc.get("metrics"), dict) else (member.get("metrics") if isinstance(member.get("metrics"), dict) else {}),
                            "endpoints": svc.get("endpoints") if isinstance(svc.get("endpoints"), list) else [],
                            "updated_at": str(svc.get("updated_at") or member.get("updated_at") or member.get("last_seen") or ""),
                            "source": "logical.agent.services",
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
                            "status": str(member.get("status") or "UNKNOWN"),
                            "probe_status": str(member.get("probe_status") or ""),
                            "probe_rtt_ms": float(member.get("probe_rtt_ms") or 0.0),
                            "metrics": m.get("business") if isinstance(m.get("business"), dict) else m,
                            "endpoints": ((member.get("network") or {}).get("endpoints") if isinstance(member.get("network"), dict) else []) or [],
                            "updated_at": str(member.get("updated_at") or member.get("last_seen") or ""),
                            "source": "logical.agent.compat",
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


def _default_node_presets() -> List[Dict[str, Any]]:
    return [
        {
            "preset_id": "gateway_http",
            "name": "缃戝叧鑺傜偣",
            "category": "application",
            "role": "gateway",
            "node_type": "gateway_server",
            "default_desc": "鍏ュ彛缃戝叧锛屾壙鎺ユ祦閲忓苟杞彂涓氬姟鏈嶅姟",
            "fixed_upstream_roles": ["edge", "lb", "admin"],
            "fixed_downstream_roles": ["business", "pressure"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "business_main",
            "name": "涓氬姟鑺傜偣",
            "category": "application",
            "role": "business",
            "node_type": "business_server",
            "default_desc": "鏍稿績涓氬姟澶勭悊鑺傜偣",
            "fixed_upstream_roles": ["gateway", "scheduler", "admin"],
            "fixed_downstream_roles": ["database", "cache", "mq", "search"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "pressure_worker",
            "name": "鍘嬪姏鑺傜偣",
            "category": "test",
            "role": "pressure",
            "node_type": "pressure_server",
            "default_desc": "鍘嬫祴娴侀噺涓庢€ц兘鍥炲綊鑺傜偣",
            "fixed_upstream_roles": ["gateway", "admin"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "redis_cache",
            "name": "Redis 缂撳瓨",
            "category": "infrastructure",
            "role": "cache",
            "node_type": "redis_cache",
            "default_desc": "Cache and session storage node",
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
            "default_desc": "涓氬姟涓诲瓨鍌ㄦ暟鎹簱",
            "fixed_upstream_roles": ["business", "scheduler", "admin"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mysql_db",
            "name": "MySQL Database",
            "category": "database",
            "role": "database",
            "node_type": "mysql_database",
            "default_desc": "鍏崇郴鍨嬫暟鎹簱鑺傜偣",
            "fixed_upstream_roles": ["business", "scheduler", "admin"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mq_kafka",
            "name": "娑堟伅闃熷垪",
            "category": "infrastructure",
            "role": "mq",
            "node_type": "mq_kafka",
            "default_desc": "寮傛浜嬩欢闃熷垪",
            "fixed_upstream_roles": ["business", "gateway", "scheduler"],
            "fixed_downstream_roles": ["business", "analytics"],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "scheduler_job",
            "name": "璋冨害鑺傜偣",
            "category": "application",
            "role": "scheduler",
            "node_type": "scheduler_server",
            "default_desc": "瀹氭椂浠诲姟涓庢壒澶勭悊鑺傜偣",
            "fixed_upstream_roles": ["admin"],
            "fixed_downstream_roles": ["business", "database", "cache", "mq"],
            "daemon_profile": "ops_native",
        },
    ]


def _load_node_presets() -> List[Dict[str, Any]]:
    raw = get_system_config(OPS_NODE_PRESETS_KEY, [])
    if isinstance(raw, list) and raw:
        out: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict) and str(item.get("preset_id") or "").strip():
                out.append(item)
        if out:
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
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _can_link_nodes(from_node: Dict[str, Any], to_node: Dict[str, Any]) -> bool:
    from_role = str(from_node.get("role") or "").strip()
    to_role = str(to_node.get("role") or "").strip()
    allow_down = from_node.get("allowed_downstream_roles") if isinstance(from_node.get("allowed_downstream_roles"), list) else []
    allow_up = to_node.get("allowed_upstream_roles") if isinstance(to_node.get("allowed_upstream_roles"), list) else []
    if allow_down and to_role and to_role not in allow_down:
        return False
    if allow_up and from_role and from_role not in allow_up:
        return False
    return True


def _infer_node_kind(role: str, explicit_kind: str = "") -> str:
    ek = str(explicit_kind or "").strip().lower()
    if ek in ("entry", "standard", "terminal"):
        return ek
    r = str(role or "").strip().lower()
    if r in ("gateway", "edge"):
        return "entry"
    if r in ("database", "cache", "mq", "search"):
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
    _save_json_config(OPS_TOPOLOGY_KEY, payload, description="Ops 骞冲彴鎷撴墤閰嶇疆")
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
    _append_bounded(OPS_TRACE_LOG_KEY, entry, limit=500, description="Ops 骞冲彴鎵ц娴佹按")


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


def _build_agent_metric_series(agent: Dict[str, Any]) -> Dict[str, Any]:
    metrics = agent.get("metrics") if isinstance(agent.get("metrics"), dict) else {}
    control = metrics.get("control") if isinstance(metrics.get("control"), dict) else metrics
    updated_at = str(control.get("updated_at") or agent.get("updated_at") or agent.get("last_seen") or "")
    points: List[Dict[str, Any]] = []
    if updated_at:
        points.append(
            {
                "time": updated_at,
                "cpu_percent": control.get("cpu_percent"),
                "mem_percent": control.get("mem_percent"),
                "disk_percent": control.get("disk_percent"),
            }
        )
    return {
        "window": "1h",
        "points": points,
        "cpu_percent": [{"time": p["time"], "value": p.get("cpu_percent")} for p in points if p.get("cpu_percent") is not None],
        "mem_percent": [{"time": p["time"], "value": p.get("mem_percent")} for p in points if p.get("mem_percent") is not None],
        "disk_percent": [{"time": p["time"], "value": p.get("disk_percent")} for p in points if p.get("disk_percent") is not None],
        "has_history": len(points) > 1,
    }


def _build_agent_detail(project_id: str, agent_id: str) -> Optional[Dict[str, Any]]:
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
    else:
        agent["effective_status"] = str(agent.get("status") or "UNKNOWN").upper()

    services = [dict(s) for s in (logical_hit.get("services") or []) if isinstance(s, dict)]
    service_ids = [str(s.get("service_id") or "").strip() for s in services if str(s.get("service_id") or "").strip()]
    member_agent_ids = [str(x or "").strip() for x in (logical_hit.get("member_agent_ids") or []) if str(x or "").strip()]
    member_node_ids = [str(x or "").strip() for x in (logical_hit.get("member_node_ids") or []) if str(x or "").strip()]
    node_id = str(agent.get("node_id") or (member_node_ids[0] if member_node_ids else "")).strip()
    nodes = _load_nodes()
    node = next((x for x in nodes if isinstance(x, dict) and str(x.get("id") or "").strip() == node_id), None)

    jobs_all = _load_agent_jobs()
    jobs = []
    for item in reversed(jobs_all):
        if not isinstance(item, dict):
            continue
        if member_node_ids and str(item.get("node_id") or "").strip() not in member_node_ids:
            continue
        jobs.append(item)
        if len(jobs) >= 30:
            break

    snapshot = _load_json_config(OPS_ALERT_SNAPSHOT_KEY, {})
    alerts = snapshot.get("alerts") if isinstance(snapshot, dict) and isinstance(snapshot.get("alerts"), list) else []
    event_rows = _load_json_config(OPS_EVENT_LOG_KEY, [])
    events_merged: List[Dict[str, Any]] = []
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

    events = [x for x in events_merged if _matches_logical_scope(x)][:30]

    traces_raw = _load_json_config(OPS_TRACE_LOG_KEY, [])
    traces = [x for x in traces_raw if isinstance(x, dict) and _matches_logical_scope(x)][:30]

    audits = []
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
        "online": len([s for s in services if str(s.get("status") or s.get("run_state") or "").upper() in ("ONLINE", "RUNNING", "READY")]),
        "abnormal": len([s for s in services if str(s.get("status") or s.get("run_state") or "").upper() in ("DEGRADED", "ERROR", "FAILED", "OFFLINE", "STOPPED")]),
    }
    service_summary["stopped"] = max(0, service_summary["total"] - service_summary["online"] - service_summary["abnormal"])

    current_alerts = len([x for x in events if str(x.get("status") or "").lower() not in ("resolved", "closed", "done", "recovered")])
    healthy_ratio = 100
    if service_summary["total"]:
        healthy_ratio = int(round((service_summary["online"] / max(1, service_summary["total"])) * 100))
    elif str(agent.get("effective_status") or "").upper() not in ("ONLINE", "RUNNING", "READY"):
        healthy_ratio = 0

    detail = {
        "agent": agent,
        "node": node or {},
        "services": services,
        "member_agent_ids": member_agent_ids,
        "member_node_ids": member_node_ids,
        "service_summary": service_summary,
        "jobs": jobs,
        "events": events,
        "traces": traces,
        "audits": audits,
        "metrics_history": _build_agent_metric_series(agent),
        "config": {
            "policy": _load_agent_policy(),
            "transport": hit.get("transport") if isinstance(hit.get("transport"), dict) else {},
            "network": hit.get("network") if isinstance(hit.get("network"), dict) else {},
            "capabilities": hit.get("capabilities") if isinstance(hit.get("capabilities"), list) else [],
            "services": [{"service_id": s.get("service_id"), "service_type": s.get("service_type"), "network": s.get("network"), "endpoints": s.get("endpoints")} for s in services],
        },
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
            "can_restart_agent": bool(services),
            "can_restart_services": bool(services),
        },
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
                "title": f"鑺傜偣鐘舵€佸紓甯? {node_name}",
                "message": f"鐘舵€?{status}; serverId={n.get('server_id') or '-'}",
                "status": "open",
                "node_id": n.get("id"),
            })
        p99 = n.get("p99_ms")
        if isinstance(p99, (int, float)) and p99 >= 200:
            alerts.append({
                "id": f"alert-{n.get('id')}-p99",
                "time": _now_iso(),
                "severity": "warning",
                "title": f"寤惰繜鍋忛珮: {node_name}",
                "message": f"P99={p99:.1f}ms",
                "status": "open",
                "node_id": n.get("id"),
            })
    return alerts


def _build_overview(project_id: str = "") -> Dict[str, Any]:
    rows = _load_nodes()
    topo = _load_topology(rows)
    topo_map = {}
    for item in topo.get("nodes") or []:
        if isinstance(item, dict):
            nid = str(item.get("id") or "").strip()
            if nid:
                topo_map[nid] = item
    operator = str(session.get("user") or "intranet-ops")
    project = str(project_id or "").strip()
    out_nodes: List[Dict[str, Any]] = []
    for item in rows:
        if not item.get("enabled"):
            continue
        if project and str(item.get("project_id") or "") != project:
            continue
        try:
            overview = _ops_gateway.build_node_overview(item, actor=operator)
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
    _save_json_config(OPS_ALERT_SNAPSHOT_KEY, snapshot, description="Ops 骞冲彴鍛婅蹇収")

    return {
        "ok": True,
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

    risk, require_approval, domain = _ops_gateway.inspect_risk(action_type)
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
                "title": f"Agent 浠诲姟鍏ラ槦: {action_type}",
                "message": f"node={node.get('id')}; job={queued.get('job_id')}; target={target}",
                "trace_id": trace_id,
                "node_id": node.get("id"),
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

    result = _ops_gateway.execute_platform_action(
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
            "title": f"鍔ㄤ綔鎵ц{'鎴愬姛' if success else '澶辫触'}: {action_type}",
            "message": f"node={node.get('id')}; target={target}; traceId={trace_id}; msg={message}",
            "trace_id": trace_id,
            "node_id": node.get("id"),
        }
    )

    log_audit("ops_platform_action_execute", f"action={action_type}; node={node.get('id')}; target={target}; trace={trace_id}; ok={success}")

    return {
        "ok": success,
        "message": message or ("鎵ц鎴愬姛" if success else "鎵ц澶辫触"),
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


@bp.route("/api/ops-platform/overview")
@admin_required("gm_ops")
def ops_platform_overview():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    return jsonify(_build_overview(project_id=project_id))


@bp.route("/api/ops-platform/deployment-catalog")
@admin_required("gm_ops")
def ops_platform_deployment_catalog():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403

    operator = str(session.get("user") or "intranet-ops")
    rows = [x for x in _load_nodes() if x.get("enabled")]
    out_nodes: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for node in rows:
        result = _ops_gateway.deployment_catalog(node, actor=operator, reason="ops deployment catalog", ticket_id="OPS-CATALOG")
        if not result.get("success"):
            warnings.append(f"{node.get('id')}: {result.get('message')}")
            continue
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
        for item in nodes:
            if not isinstance(item, dict):
                continue
            out_nodes.append({
                "source_node_id": node.get("id"),
                "source_ops_base_url": node.get("ops_base_url"),
                **item,
            })

    # de-dup by serverId while preserving latest payload.
    dedup: Dict[str, Dict[str, Any]] = {}
    for item in out_nodes:
        sid = str(item.get("serverId") or "").strip()
        if sid:
            dedup[sid] = item
    merged = list(dedup.values())
    merged.sort(key=lambda x: str(x.get("serverId") or ""))
    return jsonify({
        "ok": True,
        "count": len(merged),
        "nodes": merged,
        "warnings": warnings,
        "generated_at": _now_iso(),
    })


@bp.route("/api/ops-platform/events")
@admin_required("gm_ops")
def ops_platform_events():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    limit_text = str(request.args.get("limit") or "80").strip()
    try:
        limit = max(1, min(int(limit_text), 300))
    except Exception:
        limit = 80

    rows = _load_json_config(OPS_EVENT_LOG_KEY, [])
    if not isinstance(rows, list):
        rows = []

    snapshot = _load_json_config(OPS_ALERT_SNAPSHOT_KEY, {})
    alerts = snapshot.get("alerts") if isinstance(snapshot, dict) and isinstance(snapshot.get("alerts"), list) else []

    merged: List[Dict[str, Any]] = []
    merged.extend([x for x in alerts if isinstance(x, dict)])
    merged.extend([x for x in rows if isinstance(x, dict)])
    merged.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    return jsonify({"ok": True, "count": len(merged[:limit]), "events": merged[:limit]})


@bp.route("/api/ops-platform/client-log", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_client_log():
    payload = request.get_json(silent=True) or {}
    event = str(payload.get("event") or "unknown_event").strip()
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    try:
        compact = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        compact = "{}"
    if len(compact) > 1800:
        compact = compact[:1800] + "...(truncated)"
    log_audit("ops_platform_client_log", f"{event}: {compact}")
    return jsonify({"ok": True})


@bp.route("/api/ops-platform/module-map")
@admin_required("gm_ops")
def ops_platform_module_map():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    modules = [
        {"id": "overview", "name": "全局总览", "href": "/admin/ops-platform", "children": ["kpi", "risk", "todo"]},
        {"id": "topology", "name": "拓扑与配置编排", "href": "/admin/ops-platform/topology", "children": ["node_library", "canvas", "inspector"]},
        {"id": "action_center", "name": "动作执行中心", "href": "/admin/ops-platform/actions", "children": ["catalog", "approval", "execute", "history"]},
        {"id": "diagnostics", "name": "诊断与体检", "href": "/admin/ops-platform/diagnostics", "children": ["rules", "filter", "export"]},
        {"id": "events_trace", "name": "事件与追踪", "href": "/admin/ops-platform", "children": ["timeline", "trace", "audit"]},
        {"id": "agent_control", "name": "Agent 管控", "href": "/admin/ops-platform/agent-control", "children": ["registry", "policy", "queue", "upgrade"]},
        {"id": "change_governance", "name": "发布与变更治理", "href": "/admin/ops-platform/change-governance", "children": ["change_window", "rollback", "postcheck"]},
        {"id": "governance", "name": "权限与合规", "href": "/admin/approval", "children": ["rbac", "approval", "audit"]},
    ]
    return jsonify({"ok": True, "modules": modules})


def _default_topology_blueprints() -> List[Dict[str, Any]]:
    return [
        {
            "blueprint_id": "minimal_framework",
            "name": "最小框架",
            "desc": "入口 + 业务 + 数据与缓存，适合快速起服",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "business_main", "count": 1},
                {"preset_id": "mysql_db", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
            ],
            "edges": [
                ["gateway_http", "business_main"],
                ["business_main", "mysql_db"],
                ["business_main", "redis_cache"],
            ],
        },
        {
            "blueprint_id": "medium_framework",
            "name": "中型框架",
            "desc": "增加调度与消息队列，适合常规商业服",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "business_main", "count": 2},
                {"preset_id": "scheduler_job", "count": 1},
                {"preset_id": "mysql_db", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": [
                ["gateway_http", "business_main"],
                ["business_main", "mysql_db"],
                ["business_main", "redis_cache"],
                ["business_main", "mq_kafka"],
                ["scheduler_job", "business_main"],
                ["scheduler_job", "mysql_db"],
            ],
        },
        {
            "blueprint_id": "full_framework",
            "name": "全量框架",
            "desc": "入口、核心业务、调度、压测、消息、多库，适合完整运维链路",
            "nodes": [
                {"preset_id": "gateway_http", "count": 2},
                {"preset_id": "business_main", "count": 3},
                {"preset_id": "scheduler_job", "count": 1},
                {"preset_id": "pressure_worker", "count": 1},
                {"preset_id": "mysql_db", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": [
                ["gateway_http", "business_main"],
                ["business_main", "mysql_db"],
                ["business_main", "mongo_db"],
                ["business_main", "redis_cache"],
                ["business_main", "mq_kafka"],
                ["scheduler_job", "business_main"],
                ["scheduler_job", "mysql_db"],
                ["pressure_worker", "business_main"],
            ],
        },
    ]


def _load_topology_blueprints() -> List[Dict[str, Any]]:
    raw = get_system_config(OPS_TOPOLOGY_BLUEPRINTS_KEY, [])
    if isinstance(raw, list) and raw:
        out: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict) and str(item.get("blueprint_id") or "").strip():
                out.append(item)
        if out:
            return out
    rows = _default_topology_blueprints()
    _save_json_config(OPS_TOPOLOGY_BLUEPRINTS_KEY, rows, description="Ops topology blueprints")
    return rows
    return jsonify({"ok": True, "modules": modules})


@bp.route("/api/ops-platform/control-plane/summary")
@admin_required("gm_ops")
def ops_platform_control_plane_summary():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    _ensure_probe_bg_started()
    # 走缓存，不再每次请求都同步+探活
    with _probe_cache_lock:
        cached_probe = dict(_probe_cache)
        cached_agents = list(_probe_cache_agents)
    agents = [_normalize_agent_descriptor_v2(x) for x in cached_agents if isinstance(x, dict)]
    agents = [a for a in agents if not a.get("stale")]
    for a in agents:
        aid = str(a.get("agent_id") or "")
        pr = cached_probe.get(aid)
        if pr:
            a["effective_status"] = pr.get("effective_status", "UNKNOWN")
            a["probe_status"] = "PASS" if pr.get("ok") else "FAIL"
            a["probe_rtt_ms"] = pr.get("rtt_ms", 0.0)
            a["probe_source"] = "bg-engine"
        else:
            a["effective_status"] = "UNKNOWN"
            a["probe_source"] = "missing"
    jobs = _load_agent_jobs()
    queue: Dict[str, int] = {"PENDING": 0, "RUNNING": 0, "SUCCESS": 0, "FAILED": 0, "CANCELED": 0, "TIMEOUT": 0}
    for item in jobs:
        if not isinstance(item, dict):
            continue
        st = str(item.get("status") or "").upper()
        if st in queue:
            queue[st] += 1
    online = 0
    for a in agents:
        es = str(a.get("effective_status") or a.get("status") or "").upper()
        if es in ("ONLINE", "READY", "RUNNING"):
            online += 1
    metrics = {
        "agents_total": len(agents),
        "agents_online": online,
        "jobs_pending": queue.get("PENDING") or 0,
        "jobs_running": queue.get("RUNNING") or 0,
        "probe_cache_age_sec": round(max(0, _time_mod.time() - _probe_cache_ts), 1),
    }
    return jsonify({"ok": True, "metrics": metrics, "queue": queue, "agents": agents, "policy": _load_agent_policy()})


@bp.route("/api/ops-platform/agents")
@admin_required("gm_ops")
def ops_platform_agents_list():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    _ensure_probe_bg_started()
    project_id = str(request.args.get("project_id") or "").strip()
    status = str(request.args.get("status") or "").strip().upper()
    device_id = str(request.args.get("device_id") or "").strip()
    host_ip = str(request.args.get("host_ip") or "").strip().lower()
    region = str(request.args.get("region") or "").strip().lower()
    bound = str(request.args.get("bound") or "").strip().lower()
    bindings = _load_node_agent_bindings()
    rows = _logical_agents_for_project(project_id)
    rows = [r for r in rows if not r.get("stale")]
    bound_agent_ids = set(str(v or "") for v in bindings.values() if str(v or "").strip())
        # 走缓存：不再每次请求都探活，用后台引擎缓存结果
    with _probe_cache_lock:
        cached_probe = dict(_probe_cache)
    # 指标也走探活缓存（而不是 registry 里的旧 metrics）
    # device_snap = _device_metrics_snapshot(rows)  # 旧逻辑
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
                "updated_at": str(base_c.get("updated_at") or pr_c.get("updated_at") or _now_iso()),
                "source": str(base_c.get("source") or pr_c.get("source") or "agent"),
            }
            obj["metrics"] = {
                "control": merged,
                "business": base_b,
                **merged,
            }
            obj["metrics_missing"] = {"control": not any(merged.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")), "business": not any(base_b.get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"))}
        else:
            obj["metrics"] = {"control": base_c, "business": base_b, **base_c}
            obj["metrics_missing"] = {"control": not any(base_c.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")), "business": not any(base_b.get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"))}
        obj["device_metrics_snapshot"] = {}
        # 探活状态
        if cached_pr:
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
            obj["probe_source"] = "fallback"
        last_seen_raw = str(obj.get("last_seen") or "")
        try:
            last_seen_ts = datetime.fromisoformat(last_seen_raw.replace("Z", "")).timestamp()
            obj["last_seen_age_sec"] = max(0, int(now_ts - last_seen_ts))
        except Exception:
            obj["last_seen_age_sec"] = None
        # 走缓存结果（bg-engine），不再实时探活
        if status and str(obj.get("effective_status") or "").upper() != status:
            continue
        obj["is_bound"] = is_bound
        obj["topology_group"] = str(obj.get("node_id") or "ungrouped").split("-", 1)[0]
        obj["placement"] = {
            "region": str(obj.get("region") or ""),
            "zone": str(obj.get("zone") or ""),
            "host_ip": str(obj.get("host_ip") or obj.get("host_name") or ""),
            "device_id": str(obj.get("device_id") or ""),
        }
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
    for a in out:
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
    return jsonify({"ok": True, "count": len(out), "agents": out, "bindings": bindings})


@bp.route("/api/ops-platform/agents/devices")
@admin_required("gm_ops")
def ops_platform_agents_devices():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    _ensure_probe_bg_started()
    project_id = str(request.args.get("project_id") or "").strip()
    rows = _agents_v2_for_project(project_id)
    rows = [r for r in rows if not r.get("stale")]
    # 走缓存
    with _probe_cache_lock:
        cached_probe = dict(_probe_cache)
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
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    agent_id = str(payload.get("agent_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    reg = _load_agent_registry_v2()
    hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else {}
    create_if_missing = bool(payload.get("create_if_missing"))
    if not hit:
        if not create_if_missing:
            return jsonify({"ok": False, "error": "agent_not_found"}), 404
        now = _now_iso()
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
    hit["updated_at"] = _now_iso()
    reg[agent_id] = _normalize_agent_descriptor_v2(hit)
    _save_agent_registry_v2(reg)
    log_audit("ops_platform_agents_upsert", f"agent_id={agent_id}")
    return jsonify({"ok": True, "agent": reg[agent_id]})


@bp.route("/api/ops-platform/services")
@admin_required("gm_ops")
def ops_platform_services_list():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    rows = _services_for_project(project_id)
    return jsonify({"ok": True, "count": len(rows), "services": rows})


@bp.route("/api/ops-platform/services/upsert", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_services_upsert():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    service_id = str(payload.get("service_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    if not service_id:
        return jsonify({"ok": False, "error": "missing_service_id"}), 400

    reg = _load_agent_registry_v2()
    hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
    if not hit:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    if project_id:
        ag_project = str(hit.get("project_id") or "").strip()
        if ag_project and ag_project != project_id:
            return jsonify({"ok": False, "error": "OPS_AGENT_NOT_IN_PROJECT", "error_code": "OPS_AGENT_NOT_IN_PROJECT"}), 409

    services = hit.get("services") if isinstance(hit.get("services"), list) else []
    idx = -1
    for i, svc in enumerate(services):
        if isinstance(svc, dict) and str(svc.get("service_id") or "").strip() == service_id:
            idx = i
            break
    now = _now_iso()
    svc_obj = dict(services[idx]) if idx >= 0 and isinstance(services[idx], dict) else {}
    svc_obj["service_id"] = service_id
    svc_obj["agent_id"] = agent_id
    svc_obj["project_id"] = str(payload.get("project_id") or svc_obj.get("project_id") or hit.get("project_id") or "")
    svc_obj["node_id"] = str(payload.get("node_id") or svc_obj.get("node_id") or "")
    svc_obj["display_name"] = str(payload.get("display_name") or svc_obj.get("display_name") or service_id)
    svc_obj["service_type"] = str(payload.get("service_type") or svc_obj.get("service_type") or "standard")
    if "service_port" in payload:
        try:
            svc_obj["service_port"] = int(payload.get("service_port") or 0)
        except Exception:
            svc_obj["service_port"] = 0
    if "remote_game_server_port" in payload:
        try:
            svc_obj["remote_game_server_port"] = int(payload.get("remote_game_server_port") or 0)
        except Exception:
            svc_obj["remote_game_server_port"] = 0
    if "run_state" in payload:
        svc_obj["run_state"] = str(payload.get("run_state") or "")
    if "status" in payload:
        svc_obj["status"] = str(payload.get("status") or "")
    if "desc" in payload:
        svc_obj["desc"] = str(payload.get("desc") or "")
    if "network" in payload and isinstance(payload.get("network"), dict):
        svc_obj["network"] = payload.get("network")
    svc_obj["updated_at"] = now

    if idx >= 0:
        services[idx] = svc_obj
    else:
        services.append(svc_obj)
    hit["services"] = services
    hit["updated_at"] = now
    reg[agent_id] = _normalize_agent_descriptor_v2(hit)
    _save_agent_registry_v2(reg)
    return jsonify({"ok": True, "service": svc_obj})


@bp.route("/api/ops-platform/services/action", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_services_action():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    service_id = str(payload.get("service_id") or "").strip()
    action = str(payload.get("action") or "status").strip().lower()
    if not service_id:
        return jsonify({"ok": False, "error": "missing_service_id"}), 400

    service_hit = None
    for svc in _services_for_project(project_id):
        if isinstance(svc, dict) and str(svc.get("service_id") or "").strip() == service_id:
            service_hit = svc
            break
    if not service_hit:
        return jsonify({"ok": False, "error": "service_not_found", "error_code": "OPS_SERVICE_NOT_FOUND"}), 404

    topology_node_id = str(payload.get("node_id") or service_hit.get("node_id") or "").strip()
    if not topology_node_id:
        for bound_node_id, bound_service_id in (_load_node_service_bindings() or {}).items():
            if str(bound_service_id or "").strip() == service_id:
                topology_node_id = str(bound_node_id or "").strip()
                break
    agent_id = str(service_hit.get("agent_id") or payload.get("agent_id") or "").strip()
    reg = _load_agent_registry_v2()
    agent_desc = reg.get(agent_id) if agent_id and isinstance(reg.get(agent_id), dict) else {}
    dispatch_node_id = str((agent_desc or {}).get("node_id") or "").strip()
    if not dispatch_node_id:
        dispatch_node_id = topology_node_id
    if not dispatch_node_id:
        return jsonify({"ok": False, "error": "missing_dispatch_node_id", "error_code": "OPS_SERVICE_DISPATCH_NODE_MISSING"}), 400
    action_map = {
        "start": "start",
        "stop": "stop",
        "restart": "restart",
        "status": "status",
        "probe": "health_check",
        "logs": "log_tail",
    }
    action_type = action_map.get(action, "")
    if not action_type:
        return jsonify({"ok": False, "error": "unsupported_action"}), 400

    nodes = _load_nodes()
    node = next((x for x in nodes if isinstance(x, dict) and str(x.get("id") or "") == dispatch_node_id), None)
    if not node:
        return jsonify({"ok": False, "error": "dispatch_node_not_found", "error_code": "OPS_SERVICE_DISPATCH_NODE_MISSING"}), 404
    req = {
        "node_id": dispatch_node_id,
        "action_type": action_type,
        "target": service_id,
        "ticket_id": "OPS-SVC-" + uuid.uuid4().hex[:8],
        "reason": "服务实例标准运维动作",
        "approver": str(session.get("user") or "admin"),
        "run_mode": "agent",
        "via_agent": True,
        "payload": {
            "run_mode": "agent",
            "desired_role": str(service_hit.get("service_type") or ""),
            "desired_service_id": service_id,
            "desired_server_id": service_id,
            "topology_node_id": topology_node_id,
            "switch_required": action in ("start", "restart"),
            "launch_visible_console": bool(payload.get("launch_visible_console", True)),
        },
    }
    validation = _validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing") or []}), 400
    result = _execute_validated(req, node, validation)
    if not result.get("ok"):
        return jsonify({"ok": False, "error": "OPS_REMOTE_START_FAILED", "error_code": "OPS_REMOTE_START_FAILED", "message": str(result.get("message") or result.get("error") or "service action failed")}), 502
    return jsonify({
        "ok": True,
        "node_id": topology_node_id,
        "dispatch_node_id": dispatch_node_id,
        "agent_id": agent_id,
        "service_id": service_id,
        "action": action,
        "job_id": ((result.get("data") or {}).get("job_id") if isinstance(result.get("data"), dict) else ""),
        "trace_id": str(result.get("trace_id") or ""),
    })


@bp.route("/api/ops-platform/agents/probe", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_probe():
    if not _allow_ops_execute():
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
        reg = _load_agent_registry_v2()
        hit = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
        if hit:
            hit["probe_status"] = "PASS" if ok else "FAIL"
            hit["probe_at"] = _now_iso()
            hit["probe_rtt_ms"] = round(spent, 1)
            hit["updated_at"] = _now_iso()
            reg[agent_id] = _normalize_agent_descriptor_v2(hit)
            _save_agent_registry_v2(reg)
            out["agent_id"] = agent_id
            out["probe_status"] = hit["probe_status"]
    return jsonify(
        {
            **out
        }
    )


@bp.route("/api/ops-platform/agents/probe-all", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_probe_all():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    rows = _agents_v2_for_project(project_id)
    reg = _load_agent_registry_v2()
    out: List[Dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    for item in rows:
        aid = str(item.get("agent_id") or "")
        host = str(item.get("host_name") or "")
        port = int(item.get("remote_game_server_port") or item.get("port") or 0)
        if not host or port <= 0:
            fail_count += 1
            out.append({"agent_id": aid, "ok": False, "message": "缺少 host/port"})
            continue
        ok = False
        msg = ""
        rtt_ms = 0.0
        start = datetime.utcnow()
        try:
            with socket.create_connection((host, port), timeout=2.0):
                ok = True
        except Exception as ex:
            ok = False
            msg = str(ex)
        rtt_ms = max(0.0, (datetime.utcnow() - start).total_seconds() * 1000.0)
        hit = reg.get(aid) if isinstance(reg.get(aid), dict) else None
        if hit:
            hit["probe_status"] = "PASS" if ok else "FAIL"
            hit["probe_at"] = _now_iso()
            hit["probe_rtt_ms"] = round(rtt_ms, 1)
            hit["updated_at"] = _now_iso()
            reg[aid] = _normalize_agent_descriptor_v2(hit)
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
    _save_agent_registry_v2(reg)
    return jsonify({"ok": True, "project_id": project_id, "pass_count": pass_count, "fail_count": fail_count, "results": out})


@bp.route("/api/ops-platform/agents/probe-repair", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_probe_repair():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    default_host = str(payload.get("default_host") or "127.0.0.1").strip() or "127.0.0.1"
    rows = _agents_v2_for_project(project_id)
    reg = _load_agent_registry_v2()
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
        hit["probe_at"] = _now_iso()
        hit["probe_rtt_ms"] = round(rtt_ms, 1)
        hit["updated_at"] = _now_iso()
        reg[aid] = _normalize_agent_descriptor_v2(hit)
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
    _save_agent_registry_v2(reg)
    return jsonify({"ok": True, "project_id": project_id, "fixed_count": fixed, "pass_count": pass_count, "fail_count": fail_count, "results": out})


@bp.route("/api/ops-platform/agents/cleanup-expired", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_cleanup_expired():
    if not _allow_ops_execute():
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

    reg = _load_agent_registry_v2()
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

    bindings = _load_node_agent_bindings()
    service_bindings = _load_node_service_bindings()
    removed_bindings = 0
    removed_service_bindings = 0
    if deleted_agent_ids:
        deleted_set = set(deleted_agent_ids)
        for node_id, aid in list(bindings.items()):
            if str(aid or "").strip() in deleted_set:
                bindings.pop(node_id, None)
                removed_bindings += 1
        services = _services_for_project(project_id)
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

    _save_agent_registry_v2(reg)
    _save_node_agent_bindings(bindings)
    _save_node_service_bindings(service_bindings)
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


@bp.route("/api/ops-platform/topology/node/bindings")
@admin_required("gm_ops")
def ops_platform_node_bindings():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    bindings = _load_node_agent_bindings()
    service_bindings = _load_node_service_bindings()
    rows = _load_nodes()
    valid_nodes = set(str(x.get("id") or "") for x in rows if isinstance(x, dict))
    out: Dict[str, str] = {}
    out_services: Dict[str, str] = {}
    for nid, aid in bindings.items():
        n = str(nid or "").strip()
        a = str(aid or "").strip()
        if not n or not a or n not in valid_nodes:
            continue
        out[n] = a
    valid_services = set(
        str(x.get("service_id") or "").strip()
        for x in _services_for_project(project_id)
        if isinstance(x, dict)
    )
    for nid, sid in service_bindings.items():
        n = str(nid or "").strip()
        s = str(sid or "").strip()
        if not n or not s or n not in valid_nodes:
            continue
        if valid_services and s not in valid_services:
            continue
        out_services[n] = s
    return jsonify({"ok": True, "project_id": project_id, "bindings": out, "service_bindings": out_services})


@bp.route("/api/ops-platform/topology/node/bind-agent", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_bind_node_agent():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    rows = _load_nodes()
    node = None
    for x in rows:
        if isinstance(x, dict) and str(x.get("id") or "") == node_id:
            node = x
            break
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    reg = _load_agent_registry_v2()
    if agent_id:
        ag = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
        if not ag:
            return jsonify({"ok": False, "error": "agent_not_found"}), 404
        ag_project = str(ag.get("project_id") or "")
        if project_id and ag_project and ag_project != project_id:
            return jsonify({"ok": False, "error": "OPS_AGENT_NOT_IN_PROJECT", "error_code": "OPS_AGENT_NOT_IN_PROJECT"}), 409
        if str(ag.get("probe_status") or "").upper() != "PASS":
            return jsonify({"ok": False, "error": "OPS_AGENT_PROBE_REQUIRED", "error_code": "OPS_AGENT_PROBE_REQUIRED", "message": "Agent 尚未通过联通测试，禁止绑定"}), 412
    bindings = _load_node_agent_bindings()
    service_bindings = _load_node_service_bindings()
    if agent_id:
        bindings[node_id] = agent_id
        # Backward-compat: if service primary missing, map by node->service candidate under this agent.
        if not str(service_bindings.get(node_id) or "").strip():
            for svc in _services_for_project(project_id):
                if not isinstance(svc, dict):
                    continue
                if str(svc.get("agent_id") or "").strip() != agent_id:
                    continue
                if str(svc.get("node_id") or "").strip() == node_id:
                    sid = str(svc.get("service_id") or "").strip()
                    if sid:
                        service_bindings[node_id] = sid
                        break
    else:
        bindings.pop(node_id, None)
        service_bindings.pop(node_id, None)
    _save_node_agent_bindings(bindings)
    _save_node_service_bindings(service_bindings)
    log_audit("ops_platform_bind_node_agent", f"node={node_id}; agent={agent_id}")
    return jsonify({"ok": True, "node_id": node_id, "agent_id": agent_id, "bindings": bindings, "service_bindings": service_bindings})


@bp.route("/api/ops-platform/topology/node/bind-service", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_bind_node_service():
    payload = request.get_json(silent=True) or {}
    service_id = str(payload.get("service_id") or "").strip()
    if not service_id:
        return jsonify({"ok": False, "error": "missing_service_id"}), 400
    project_id = str(payload.get("project_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400

    rows = _load_nodes()
    node = None
    for x in rows:
        if isinstance(x, dict) and str(x.get("id") or "") == node_id:
            node = x
            break
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404

    agent_id = str(payload.get("agent_id") or "").strip()
    service_hit = None
    for svc in _services_for_project(project_id):
        if not isinstance(svc, dict):
            continue
        if str(svc.get("service_id") or "").strip() == service_id:
            service_hit = svc
            break
    if not service_hit:
        return jsonify({"ok": False, "error": "service_not_found", "error_code": "OPS_SERVICE_NOT_FOUND"}), 404
    if not agent_id:
        agent_id = str(service_hit.get("agent_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    reg = _load_agent_registry_v2()
    ag = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
    if not ag:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    ag_project = str(ag.get("project_id") or "")
    if project_id and ag_project and ag_project != project_id:
        return jsonify({"ok": False, "error": "OPS_AGENT_NOT_IN_PROJECT", "error_code": "OPS_AGENT_NOT_IN_PROJECT"}), 409
    if str(ag.get("probe_status") or "").upper() != "PASS":
        return jsonify({"ok": False, "error": "OPS_AGENT_PROBE_REQUIRED", "error_code": "OPS_AGENT_PROBE_REQUIRED", "message": "Agent 尚未通过联通测试，禁止绑定"}), 412

    bindings = _load_node_agent_bindings()
    service_bindings = _load_node_service_bindings()
    bindings[node_id] = agent_id
    service_bindings[node_id] = service_id
    _save_node_agent_bindings(bindings)
    _save_node_service_bindings(service_bindings)
    log_audit("ops_platform_bind_node_service", f"node={node_id}; service={service_id}; agent={agent_id}")
    return jsonify({
        "ok": True,
        "node_id": node_id,
        "agent_id": agent_id,
        "service_id": service_id,
        "binding_mode": "service_primary",
        "bindings": bindings,
        "service_bindings": service_bindings,
    })


@bp.route("/api/ops-platform/topology/node/start-remote", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_start_remote():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    nodes = _load_nodes()
    node = None
    for x in nodes:
        if isinstance(x, dict) and str(x.get("id") or "") == node_id:
            node = x
            break
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    if project_id and str(node.get("project_id") or "") and str(node.get("project_id") or "") != project_id:
        return jsonify({"ok": False, "error": "project_mismatch"}), 409

    bindings = _load_node_agent_bindings()
    service_bindings = _load_node_service_bindings()
    bound_service_id = str(payload.get("service_id") or service_bindings.get(node_id) or "").strip()
    agent_id = str(bindings.get(node_id) or "")
    if bound_service_id and not agent_id:
        for svc in _services_for_project(project_id):
            if not isinstance(svc, dict):
                continue
            if str(svc.get("service_id") or "").strip() == bound_service_id:
                agent_id = str(svc.get("agent_id") or "").strip()
                if agent_id:
                    break
    if not agent_id:
        return jsonify({"ok": False, "error": "agent_not_bound", "error_code": "OPS_REMOTE_START_FAILED", "message": "节点未绑定 Agent"}), 412
    reg = _load_agent_registry_v2()
    ag = reg.get(agent_id) if isinstance(reg.get(agent_id), dict) else None
    if not ag:
        return jsonify({"ok": False, "error": "agent_not_registered", "error_code": "OPS_REMOTE_START_FAILED", "message": "绑定 Agent 不存在"}), 404
    if str(ag.get("probe_status") or "").upper() != "PASS":
        return jsonify({"ok": False, "error": "OPS_AGENT_PROBE_FAILED", "error_code": "OPS_AGENT_PROBE_FAILED", "message": "Agent 联通测试未通过"}), 412

    req = {
        "node_id": node_id,
        "action_type": "start",
        "target": node_id,
        "ticket_id": "OPS-REMOTE-" + uuid.uuid4().hex[:8],
        "reason": "节点编辑器远端启动",
        "approver": str(session.get("user") or "admin"),
        "run_mode": "agent",
        "via_agent": True,
        "payload": {
            "run_mode": "agent",
            "desired_role": str(node.get("role") or ""),
            "desired_server_id": str(node.get("server_id") or ""),
            "desired_service_id": bound_service_id,
            "switch_required": True,
            "launch_visible_console": bool(payload.get("launch_visible_console", True)),
        },
    }
    validation = _validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing") or []}), 400
    if validation.get("require_approval") and not validation.get("approved"):
        aid = create_approval(
            "gm_ops_action",
            str(session.get("user") or "admin"),
            "ops_action",
            str(validation.get("approval_target_id") or ""),
            reason=str(validation.get("reason") or "remote start"),
            project_id=str(node.get("project_id") or project_id),
        )
        ok, err = approve_or_reject(aid, str(session.get("user") or "admin"), "approve", "remote start auto approve")
        if not ok:
            return jsonify({"ok": False, "error": "approval_failed", "message": str(err or "approval failed")}), 502
        req["approval_id"] = aid
        validation = _validate_ops_request(req, node)

    result = _execute_validated(req, node, validation)
    if not result.get("ok"):
        return jsonify({"ok": False, "error": "OPS_REMOTE_START_FAILED", "error_code": "OPS_REMOTE_START_FAILED", "message": str(result.get("message") or result.get("error") or "remote start failed")}), 502
    return jsonify({
        "ok": True,
        "node_id": node_id,
        "agent_id": agent_id,
        "service_id": bound_service_id,
        "job_id": ((result.get("data") or {}).get("job_id") if isinstance(result.get("data"), dict) else ""),
        "trace_id": str(result.get("trace_id") or ""),
    })


@bp.route("/api/ops-platform/topology/auto-bind-agents", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_auto_bind_agents():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    topo = _load_topology(_load_nodes())
    node_ids = [str(n.get("id") or "") for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "")]
    reg = _load_agent_registry_v2()
    bindings = _load_node_agent_bindings()
    bound = 0
    skipped = 0
    detail: List[Dict[str, Any]] = []
    for nid in node_ids:
        matched = None
        for aid, row in reg.items():
            if not isinstance(row, dict):
                continue
            if project_id and str(row.get("project_id") or "") not in ("", project_id):
                continue
            if str(row.get("node_id") or "") != nid:
                continue
            if str(row.get("probe_status") or "").upper() != "PASS":
                continue
            if str(row.get("effective_status") or row.get("status") or "").upper() not in ("ONLINE", "READY", "RUNNING"):
                continue
            matched = str(aid or "")
            break
        if matched:
            bindings[nid] = matched
            bound += 1
            detail.append({"node_id": nid, "agent_id": matched, "ok": True})
        else:
            skipped += 1
            detail.append({"node_id": nid, "agent_id": "", "ok": False})
    _save_node_agent_bindings(bindings)
    return jsonify({"ok": True, "project_id": project_id, "bound_count": bound, "skipped_count": skipped, "bindings": bindings, "detail": detail})


@bp.route("/api/ops-platform/change-governance/summary")
@admin_required("gm_ops")
def ops_platform_change_governance_summary():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    events = _load_json_config(OPS_EVENT_LOG_KEY, [])
    if not isinstance(events, list):
        events = []
    recent = [x for x in events if isinstance(x, dict)][:200]
    high_risk = 0
    failed = 0
    change_evt = 0
    for item in recent:
        level = str(item.get("level") or item.get("risk") or "").lower()
        action = str(item.get("action") or "").lower()
        ok = bool(item.get("ok", True))
        if level in ("high", "critical"):
            high_risk += 1
        if not ok:
            failed += 1
        if ("deploy" in action) or ("migration" in action) or ("release" in action) or ("rollback" in action):
            change_evt += 1
    pending_approvals = 0
    for item in approvals_db:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").lower() in ("pending", "open"):
            pending_approvals += 1
    metrics = {
        "pending_approvals": pending_approvals,
        "high_risk_actions_24h": high_risk,
        "failed_actions_24h": failed,
        "change_events_24h": change_evt,
    }
    window = {"freeze_active": False}
    return jsonify({"ok": True, "metrics": metrics, "events": recent[:20], "window": window})


@bp.route("/api/ops-platform/action-catalog")
@admin_required("gm_ops")
def ops_platform_action_catalog():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    rows = [
        {"groupId": "observe", "group": "Observe", "value": "health_check", "label": "健康检查", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "ready_check", "label": "就绪检查", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "status", "label": "运行快照", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "runtime_snapshot", "label": "运行态详情", "risk": "low"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "start", "label": "启动节点", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "stop", "label": "停止节点", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "restart", "label": "重启节点", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "start_all", "label": "启动全节点", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "stop_all", "label": "停止全节点", "risk": "high"},
        {"groupId": "special", "group": "Special Job", "value": "smoke_test", "label": "冒烟测试", "risk": "medium"},
        {"groupId": "special", "group": "Special Job", "value": "stress_test", "label": "压力测试", "risk": "high"},
    ]
    return jsonify({"ok": True, "data": rows})


@bp.route("/api/ops-platform/topology")
@admin_required("gm_ops")
def ops_platform_topology():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    all_nodes = _load_nodes()
    if project_id:
        nodes = [x for x in all_nodes if str(x.get("project_id") or "").strip() == project_id]
    else:
        nodes = list(all_nodes)
    topo = _load_topology(nodes)
    return jsonify({"ok": True, "project_id": project_id, "topology": topo, "node_count": len(nodes)})


@bp.route("/api/ops-platform/topology/save", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_save():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    topo = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
    normalized = _load_topology(_load_nodes())
    incoming_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    incoming_edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    incoming_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}

    node_index = {str(x.get("id") or ""): x for x in (normalized.get("nodes") or []) if isinstance(x, dict)}
    for item in incoming_nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid or nid not in node_index:
            continue
        src = node_index[nid]
        src["role"] = str(item.get("role") or src.get("role") or "business")
        src["kind"] = _infer_node_kind(str(src.get("role") or "business"), str(item.get("kind") or src.get("kind") or ""))
        src["desc"] = str(item.get("desc") or src.get("desc") or "")
        src["bizStatus"] = str(item.get("bizStatus") or src.get("bizStatus") or "normal")
        src["owner"] = str(item.get("owner") or src.get("owner") or "")
        src["tags"] = item.get("tags") if isinstance(item.get("tags"), list) else (src.get("tags") if isinstance(src.get("tags"), list) else [])
        src["ui"] = item.get("ui") if isinstance(item.get("ui"), dict) else (src.get("ui") if isinstance(src.get("ui"), dict) else {})
        src["ui"]["ports"] = _normalize_ports(str(src.get("kind") or "standard"), src["ui"].get("ports"))
        try:
            src["x"] = float(item.get("x"))
            src["y"] = float(item.get("y"))
        except Exception:
            pass
        if isinstance(src.get("ui"), dict):
            if "x" not in src["ui"]:
                src["ui"]["x"] = src.get("x", 0)
            if "y" not in src["ui"]:
                src["ui"]["y"] = src.get("y", 0)

    valid_ids = set(node_index.keys())
    merged_edges: List[Dict[str, Any]] = []
    for edge in incoming_edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to or frm not in valid_ids or to not in valid_ids or frm == to:
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
    final_topo = {"nodes": list(node_index.values()), "edges": merged_edges, "meta": incoming_meta if isinstance(incoming_meta, dict) else {}}
    saved = _save_topology(final_topo)
    log_audit("ops_platform_topology_save", f"nodes={len(final_topo.get('nodes') or [])}; edges={len(merged_edges)}")
    return jsonify({"ok": True, "message": "Topology saved", "topology": saved})


@bp.route("/api/ops-platform/topology/node/update", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_update():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
    if not node_id:
        return jsonify({"ok": False, "error": "missing node_id"}), 400

    topo = _load_topology(_load_nodes())
    target = None
    for item in topo.get("nodes") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == node_id:
            target = item
            break
    if not target:
        return jsonify({"ok": False, "error": "node not found"}), 404

    if "role" in patch:
        target["role"] = str(patch.get("role") or "business")
    if "kind" in patch:
        target["kind"] = _infer_node_kind(str(target.get("role") or "business"), str(patch.get("kind") or ""))
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
    if "ui" in patch and isinstance(patch.get("ui"), dict):
        target["ui"] = patch.get("ui")
    if not isinstance(target.get("ui"), dict):
        target["ui"] = {}
    target["kind"] = _infer_node_kind(str(target.get("role") or "business"), str(target.get("kind") or ""))
    target["ui"]["ports"] = _normalize_ports(str(target.get("kind") or "standard"), target["ui"].get("ports"))
    saved = _save_topology(topo)

    rows = _load_nodes()
    changed = False
    for item in rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == node_id:
            item["owner"] = target.get("owner") or item.get("owner") or ""
            item["role"] = target.get("role") or item.get("role") or "business"
            item["description"] = target.get("desc") or item.get("description") or ""
            changed = True
            break
    if changed:
        _save_nodes(rows)

    log_audit("ops_platform_topology_node_update", f"node={node_id}")
    return jsonify({"ok": True, "message": "鑺傜偣灞炴€у凡鏇存柊", "topology": saved})


def _ops_topology_meta_structured(topo: Dict[str, Any]) -> None:
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    meta["layout_mode"] = "structured"
    meta["updated_at"] = _now_iso()
    topo["meta"] = meta


def _ops_topology_node_map(topo: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(n.get("id") or ""): n for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "")}


def _ops_topology_edge_list(topo: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = edges
    return edges


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
    kind = str(topo_node.get("kind") or _infer_node_kind(str(topo_node.get("role") or "business"), ""))
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
    from_node = _resolve_node(node_id=frm) or fn
    to_node = _resolve_node(node_id=to) or tn
    if not _can_link_nodes(from_node, to_node):
        return False, {"ok": False, "error": "invalid_edge_by_role", "error_code": "OPS_EDGE_ROLE_FORBIDDEN", "message": "当前节点角色规则不允许该连线"}, 409
    fkind = str(fn.get("kind") or _infer_node_kind(str(fn.get("role") or from_node.get("role") or ""), ""))
    tkind = str(tn.get("kind") or _infer_node_kind(str(tn.get("role") or to_node.get("role") or ""), ""))
    if fkind == "terminal" or tkind == "entry":
        return False, {"ok": False, "error": "node_kind_violation", "error_code": "OPS_NODE_KIND_VIOLATION", "message": "节点语义方向不允许该连线"}, 409
    if any(isinstance(e, dict) and str(e.get("from") or "") == frm and str(e.get("to") or "") == to for e in edges):
        return False, {"ok": False, "error": "edge_duplicate", "error_code": "OPS_EDGE_DUPLICATE", "message": "两个节点之间已存在连线"}, 409
    from_port = _ops_ensure_free_port(fn, "out", edges)
    to_port = _ops_ensure_free_port(tn, "in", edges)
    if not from_port or not to_port:
        return False, {"ok": False, "error": "port_capacity_exceeded", "error_code": "OPS_PORT_CAPACITY_EXCEEDED", "message": "节点端口数量已达上限"}, 409
    edge = {"id": f"edge-{uuid.uuid4().hex[:10]}", "from": frm, "to": to, "from_port": from_port, "to_port": to_port, "type": "depends_on", "note": "structured-auto", "ui": {}}
    edges.append(edge)
    return True, edge, 200


@bp.route("/api/ops-platform/topology/structured/add-existing-target", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_add_existing_target():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    frm = str(payload.get("from_node_id") or payload.get("from") or "").strip()
    to = str(payload.get("to_node_id") or payload.get("to") or "").strip()
    topo = _load_topology(_load_nodes())
    ok, result, status = _ops_structured_append_edge(topo, frm, to)
    if not ok:
        return jsonify(result), status
    _ops_topology_meta_structured(topo)
    saved = _save_topology(topo)
    log_audit("ops_platform_structured_add_existing_target", f"{frm}->{to}")
    return jsonify({"ok": True, "message": "已添加下游连线", "edge": result, "topology": saved})


@bp.route("/api/ops-platform/topology/structured/add-new-target", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_add_new_target():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    frm = str(payload.get("from_node_id") or payload.get("from") or "").strip()
    preset_id = str(payload.get("preset_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    if not frm or not preset_id:
        return jsonify({"ok": False, "error": "missing_required_fields", "message": "缺少源节点或模板"}), 400
    preset = None
    for item in _load_node_presets():
        if isinstance(item, dict) and str(item.get("preset_id") or "") == preset_id:
            preset = item
            break
    if not preset:
        return jsonify({"ok": False, "error": "preset_not_found", "message": "节点模板不存在"}), 404

    rows = _load_nodes()
    src_node = next((x for x in rows if isinstance(x, dict) and str(x.get("id") or "") == frm), None)
    if not src_node:
        return jsonify({"ok": False, "error": "node not found", "message": "源节点不存在"}), 404
    role = str(preset.get("role") or "business")
    node_kind = _infer_node_kind(role, str(preset.get("kind") or ""))
    candidate = _normalize_node(
        {
            "id": str(payload.get("id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}",
            "name": str(payload.get("name") or preset.get("name") or preset_id),
            "server_id": "",
            "project_id": project_id,
            "owner": str(payload.get("owner") or "ops-admin"),
            "role": role,
            "node_category": str(preset.get("category") or ""),
            "node_type": str(preset.get("node_type") or ""),
            "description": str(payload.get("description") or preset.get("default_desc") or ""),
            "biz_status": "normal",
            "allowed_upstream_roles": list(preset.get("fixed_upstream_roles") or []),
            "allowed_downstream_roles": list(preset.get("fixed_downstream_roles") or []),
            "daemon_profile": str(preset.get("daemon_profile") or ""),
            "enabled": True,
            "tags": [str(preset.get("category") or ""), role],
        }
    )
    if not _can_link_nodes(src_node, candidate):
        return jsonify({"ok": False, "error": "invalid_edge_by_role", "error_code": "OPS_EDGE_ROLE_FORBIDDEN", "message": "该模板不能作为当前节点的下游"}), 409
    new_id = str(candidate.get("id") or "").strip()
    if any(isinstance(x, dict) and str(x.get("id") or "") == new_id for x in rows):
        return jsonify({"ok": False, "error": "node_id_exists", "message": f"节点ID已存在: {new_id}"}), 409
    rows.append(candidate)
    _save_nodes(rows)
    _set_daemon_state(new_id, {"status": "ADDED", "last_action": "create", "last_error": "", "pid": 0})

    topo = _load_topology(rows)
    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    topo["nodes"] = topo_nodes
    if not any(isinstance(n, dict) and str(n.get("id") or "") == new_id for n in topo_nodes):
        topo_nodes.append(
            {
                "id": new_id,
                "role": role,
                "kind": node_kind,
                "desc": str(candidate.get("description") or ""),
                "bizStatus": "normal",
                "owner": str(candidate.get("owner") or ""),
                "tags": list(candidate.get("tags") or []),
                "ui": {"x": 160.0, "y": 160.0, "w": 240, "h": 104, "color": "#0f172a", "ports": _normalize_ports(node_kind, preset.get("default_ports"))},
            }
        )
    ok, result, status = _ops_structured_append_edge(topo, frm, new_id)
    if not ok:
        # Roll back the created node if the edge fails validation after persistence.
        rows = [x for x in _load_nodes() if not (isinstance(x, dict) and str(x.get("id") or "") == new_id)]
        _save_nodes(rows)
        return jsonify(result), status
    _ops_topology_meta_structured(topo)
    saved = _save_topology(topo)
    log_audit("ops_platform_structured_add_new_target", f"{frm}->{new_id}; preset={preset_id}")
    return jsonify({"ok": True, "message": "已添加下游节点", "node": candidate, "edge": result, "topology": saved})


@bp.route("/api/ops-platform/topology/structured/delete-node", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_delete_node():
    return ops_platform_topology_node_delete()


@bp.route("/api/ops-platform/topology/structured/delete-edge", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_delete_edge():
    return ops_platform_topology_edge_delete()


@bp.route("/api/ops-platform/topology/edge/upsert", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_edge_upsert():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    frm = str(payload.get("from") or "").strip()
    to = str(payload.get("to") or "").strip()
    from_port = str(payload.get("from_port") or "out-1").strip()
    to_port = str(payload.get("to_port") or "in-1").strip()
    etype = str(payload.get("type") or "depends_on").strip()
    note = str(payload.get("note") or "").strip()
    if not frm or not to or frm == to:
        return jsonify({"ok": False, "error": "invalid edge endpoints"}), 400

    topo = _load_topology(_load_nodes())
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = edges
    valid = set([str(x.get("id") or "") for x in topo.get("nodes") or [] if isinstance(x, dict)])
    if frm not in valid or to not in valid:
        return jsonify({"ok": False, "error": "node not found"}), 404
    from_node = _resolve_node(node_id=frm) or {}
    to_node = _resolve_node(node_id=to) or {}
    if not _can_link_nodes(from_node, to_node):
        return jsonify({
            "ok": False,
            "error": "invalid_edge_by_role",
            "error_code": "OPS_EDGE_ROLE_FORBIDDEN",
            "message": "当前节点角色规则不允许该连线",
        }), 409
    topo_nodes = {str(x.get("id") or ""): x for x in (topo.get("nodes") or []) if isinstance(x, dict)}
    fn = topo_nodes.get(frm) or {}
    tn = topo_nodes.get(to) or {}
    fkind = str(fn.get("kind") or _infer_node_kind(str(fn.get("role") or from_node.get("role") or ""), ""))
    tkind = str(tn.get("kind") or _infer_node_kind(str(tn.get("role") or to_node.get("role") or ""), ""))
    if fkind == "terminal" or tkind == "entry":
        return jsonify({"ok": False, "error": "node_kind_violation", "error_code": "OPS_NODE_KIND_VIOLATION", "message": "Node kind direction is not allowed"}), 400
    fports = _normalize_ports(fkind, ((fn.get("ui") or {}).get("ports") if isinstance(fn.get("ui"), dict) else None))
    tports = _normalize_ports(tkind, ((tn.get("ui") or {}).get("ports") if isinstance(tn.get("ui"), dict) else None))
    if from_port not in [str(p.get("id") or "") for p in fports.get("out", [])] or to_port not in [str(p.get("id") or "") for p in tports.get("in", [])]:
        return jsonify({"ok": False, "error": "port_not_found", "error_code": "OPS_PORT_NOT_FOUND", "message": "Port not found"}), 400
    for ex in edges:
        if not isinstance(ex, dict):
            continue
        if str(ex.get("from") or "") == frm and str(ex.get("to") or "") == to and str(ex.get("from_port") or "out-1") == from_port and str(ex.get("to_port") or "in-1") == to_port:
            return jsonify({"ok": False, "error": "edge_duplicate", "error_code": "OPS_EDGE_DUPLICATE", "message": "Duplicate edge"}), 409
    incoming_count = 0
    for ex in edges:
        if isinstance(ex, dict) and str(ex.get("to") or "") == to and str(ex.get("to_port") or "in-1") == to_port:
            incoming_count += 1
    in_max = 1
    for p in tports.get("in", []):
        if str(p.get("id") or "") == to_port:
            in_max = int(p.get("max_links") or 1)
            break
    if incoming_count >= in_max:
        return jsonify({"ok": False, "error": "port_capacity_exceeded", "error_code": "OPS_PORT_CAPACITY_EXCEEDED", "message": "Input port capacity exceeded"}), 409
    outgoing_count = 0
    for ex in edges:
        if isinstance(ex, dict) and str(ex.get("from") or "") == frm and str(ex.get("from_port") or "out-1") == from_port:
            outgoing_count += 1
    out_max = 1
    for p in fports.get("out", []):
        if str(p.get("id") or "") == from_port:
            out_max = int(p.get("max_links") or 1)
            break
    if outgoing_count >= out_max:
        return jsonify({"ok": False, "error": "port_capacity_exceeded", "error_code": "OPS_PORT_CAPACITY_EXCEEDED", "message": "Output port capacity exceeded"}), 409

    updated = False
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("from") or "") == frm and str(edge.get("to") or "") == to and str(edge.get("from_port") or "out-1") == from_port and str(edge.get("to_port") or "in-1") == to_port:
            edge["type"] = etype
            edge["note"] = note
            updated = True
            break
    if not updated:
        edges.append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": frm, "to": to, "from_port": from_port, "to_port": to_port, "type": etype, "note": note})

    saved = _save_topology(topo)
    log_audit("ops_platform_topology_edge_upsert", f"{frm}->{to}; type={etype}")
    resp = {"ok": True, "message": "连线已保存", "topology": saved}
    return jsonify(resp)


@bp.route("/api/ops-platform/topology/edge/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_edge_delete():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    edge_id = str(payload.get("edge_id") or "").strip()
    if not edge_id:
        return jsonify({"ok": False, "error": "missing edge_id"}), 400

    topo = _load_topology(_load_nodes())
    if _is_critical_topology_edge(topo, edge_id):
        return jsonify({
            "ok": False,
            "error": "edge_delete_blocked",
            "error_code": "OPS_EDGE_DELETE_BLOCKED",
            "message": "关键链路连线不可删除（会导致架构断裂）",
        }), 409
    before = len(topo.get("edges") or [])
    topo["edges"] = [x for x in (topo.get("edges") or []) if not (isinstance(x, dict) and str(x.get("id") or "") == edge_id)]
    after = len(topo.get("edges") or [])
    if after == before:
        return jsonify({"ok": False, "error": "edge not found"}), 404
    saved = _save_topology(topo)
    log_audit("ops_platform_topology_edge_delete", f"edge={edge_id}")
    return jsonify({"ok": True, "message": "Edge deleted", "topology": saved})


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


@bp.route("/api/ops-platform/topology/node/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_delete():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "Missing ops execute permission"}), 403
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing node_id"}), 400

    topo = _load_topology(_load_nodes())
    node_ids = {str(x.get("id") or "") for x in (topo.get("nodes") or []) if isinstance(x, dict)}
    if node_id not in node_ids:
        return jsonify({"ok": False, "error": "node not found"}), 404
    if _is_critical_topology_node(topo, node_id):
        return jsonify({"ok": False, "error": "node_delete_blocked", "error_code": "OPS_NODE_DELETE_BLOCKED", "message": "Critical node cannot be deleted"}), 409

    before_edges = len(topo.get("edges") or [])
    topo["nodes"] = [x for x in (topo.get("nodes") or []) if not (isinstance(x, dict) and str(x.get("id") or "") == node_id)]
    topo["edges"] = [x for x in (topo.get("edges") or []) if not (isinstance(x, dict) and (str(x.get("from") or "") == node_id or str(x.get("to") or "") == node_id))]
    saved = _save_topology(topo)

    rows = _load_nodes()
    rows = [x for x in rows if not (isinstance(x, dict) and str(x.get("id") or "") == node_id)]
    _save_nodes(rows)

    bindings = _load_node_agent_bindings()
    if node_id in bindings:
        bindings.pop(node_id, None)
        _save_node_agent_bindings(bindings)

    log_audit("ops_platform_topology_node_delete", f"node={node_id}; removed_edges={before_edges - len(saved.get('edges') or [])}")
    return jsonify({"ok": True, "message": "Node deleted", "topology": saved, "bindings": bindings})


@bp.route("/api/ops-platform/node-presets")
@admin_required("gm_ops")
def ops_platform_node_presets():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    presets = _load_node_presets()
    out = []
    for p in presets:
        if not isinstance(p, dict):
            continue
        role = str(p.get("role") or "business")
        kind = _infer_node_kind(role, str(p.get("kind") or ""))
        item = dict(p)
        item["kind"] = kind
        item["default_ports"] = _normalize_ports(kind, p.get("default_ports"))
        out.append(item)
    return jsonify({"ok": True, "count": len(out), "presets": out})


@bp.route("/api/ops-platform/topology-blueprints")
@admin_required("gm_ops")
def ops_platform_topology_blueprints():
    rows = _load_topology_blueprints()
    out: List[Dict[str, Any]] = []
    for x in rows:
        if not isinstance(x, dict):
            continue
        out.append(
            {
                "blueprint_id": str(x.get("blueprint_id") or ""),
                "name": str(x.get("name") or ""),
                "desc": str(x.get("desc") or ""),
                "nodes": x.get("nodes") if isinstance(x.get("nodes"), list) else [],
                "edges": x.get("edges") if isinstance(x.get("edges"), list) else [],
            }
        )
    return jsonify({"ok": True, "count": len(out), "blueprints": out})


@bp.route("/api/ops-platform/topology/apply-blueprint", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_apply_blueprint():
    payload = request.get_json(silent=True) or {}
    bid = str(payload.get("blueprint_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    replace_existing = bool(payload.get("replace_existing", True))
    if not bid:
        return jsonify({"ok": False, "error": "missing_blueprint_id"}), 400

    bp_item = None
    for item in _load_topology_blueprints():
        if isinstance(item, dict) and str(item.get("blueprint_id") or "") == bid:
            bp_item = item
            break
    if not bp_item:
        return jsonify({"ok": False, "error": "blueprint_not_found"}), 404

    presets = _load_node_presets()
    preset_map = {str(p.get("preset_id") or ""): p for p in presets if isinstance(p, dict)}
    nodes = _load_nodes()
    topo = _load_topology(nodes)
    if replace_existing:
        # Clear currently displayed topology scope before applying blueprint.
        # Scope rule: remove all nodes currently in topology canvas, then reset canvas.
        current_topo_ids = set()
        for item in (topo.get("nodes") or []):
            if isinstance(item, dict):
                nid = str(item.get("id") or "").strip()
                if nid:
                    current_topo_ids.add(nid)
        if current_topo_ids:
            nodes = [n for n in nodes if isinstance(n, dict) and str(n.get("id") or "") not in current_topo_ids]
        topo = {"nodes": [], "edges": [], "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": _now_iso()}}
    existing_ids = set(str(n.get("id") or "") for n in (nodes or []) if isinstance(n, dict))
    created_node_ids: List[str] = []
    created_by_preset: Dict[str, List[str]] = {}

    plan_nodes = bp_item.get("nodes") if isinstance(bp_item.get("nodes"), list) else []
    for entry in plan_nodes:
        if not isinstance(entry, dict):
            continue
        preset_id = str(entry.get("preset_id") or "").strip()
        count = max(1, min(20, int(entry.get("count") or 1)))
        preset = preset_map.get(preset_id)
        if not preset:
            continue
        for idx in range(count):
            new_id = f"{preset_id}-{uuid.uuid4().hex[:6]}"
            while new_id in existing_ids:
                new_id = f"{preset_id}-{uuid.uuid4().hex[:6]}"
            existing_ids.add(new_id)
            role = str(preset.get("role") or "business")
            node_kind = _infer_node_kind(role, str(preset.get("kind") or ""))
            new_node = _normalize_node(
                {
                    "id": new_id,
                    "name": f"{str(preset.get('name') or preset_id)}-{idx + 1}",
                    "project_id": project_id,
                    "server_id": new_id,
                    "owner": "ops-admin",
                    "role": role,
                    "node_category": str(preset.get("category") or ""),
                    "node_type": str(preset.get("node_type") or ""),
                    "description": str(preset.get("default_desc") or ""),
                    "biz_status": "normal",
                    "allowed_upstream_roles": list(preset.get("fixed_upstream_roles") or []),
                    "allowed_downstream_roles": list(preset.get("fixed_downstream_roles") or []),
                    "daemon_profile": str(preset.get("daemon_profile") or ""),
                    "tags": [str(preset.get("category") or ""), role],
                }
            )
            nodes.append(new_node)
            created_node_ids.append(new_id)
            created_by_preset.setdefault(preset_id, []).append(new_id)
            topo["nodes"].append(
                {
                    "id": new_id,
                    "role": role,
                    "kind": node_kind,
                    "desc": str(new_node.get("description") or ""),
                    "bizStatus": "normal",
                    "owner": str(new_node.get("owner") or ""),
                    "x": 160.0,
                    "y": 160.0,
                    "tags": list(new_node.get("tags") or []),
                    "ui": {"x": 160.0, "y": 160.0, "w": 220, "h": 90, "color": "#0f172a", "locked": False, "ports": _normalize_ports(node_kind, None)},
                }
            )

    # layout newly created nodes in a grid region
    created_set = set(created_node_ids)
    created_nodes = [n for n in topo.get("nodes") if isinstance(n, dict) and str(n.get("id") or "") in created_set]
    for idx, n in enumerate(created_nodes):
        col = idx % 4
        row = idx // 4
        x = float(120 + col * 300)
        y = float(120 + row * 180)
        n["x"] = x
        n["y"] = y
        ui = n.get("ui") if isinstance(n.get("ui"), dict) else {}
        ui["x"] = x
        ui["y"] = y
        if "w" not in ui:
            ui["w"] = 220
        if "h" not in ui:
            ui["h"] = 90
        n["ui"] = ui

    # connect edges by blueprint relation between first-available node instances
    plan_edges = bp_item.get("edges") if isinstance(bp_item.get("edges"), list) else []
    for rel in plan_edges:
        if not (isinstance(rel, list) and len(rel) == 2):
            continue
        sp = str(rel[0] or "").strip()
        tp = str(rel[1] or "").strip()
        s_nodes = created_by_preset.get(sp) or []
        t_nodes = created_by_preset.get(tp) or []
        if not s_nodes or not t_nodes:
            continue
        for si, s_id in enumerate(s_nodes):
            t_id = t_nodes[si % len(t_nodes)]
            dup = False
            for e in (topo.get("edges") or []):
                if not isinstance(e, dict):
                    continue
                if str(e.get("from") or "") == s_id and str(e.get("to") or "") == t_id:
                    dup = True
                    break
            if dup:
                continue
            topo["edges"].append(
                {
                    "id": f"edge-{uuid.uuid4().hex[:10]}",
                    "from": s_id,
                    "to": t_id,
                    "from_port": "out-1",
                    "to_port": "in-1",
                    "type": "depends_on",
                    "note": "blueprint-auto",
                }
            )

    _save_nodes(nodes)
    saved_topo = _save_topology(topo)
    log_audit("ops_platform_apply_blueprint", f"blueprint={bid}; created={len(created_node_ids)}; project={project_id}")
    return jsonify({"ok": True, "blueprint_id": bid, "created_count": len(created_node_ids), "created_node_ids": created_node_ids, "topology": saved_topo})


@bp.route("/api/ops-platform/node/add-from-preset", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_add_node_from_preset():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    preset_id = str(payload.get("preset_id") or "").strip()
    name = str(payload.get("name") or "").strip()
    server_id = str(payload.get("server_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env = str(payload.get("env") or "").strip()
    channel = str(payload.get("channel") or "").strip()
    owner = str(payload.get("owner") or "").strip()
    node_note = str(payload.get("description") or "").strip()
    daemon_start_cmd = str(payload.get("daemon_start_cmd") or "").strip()
    daemon_stop_cmd = str(payload.get("daemon_stop_cmd") or "").strip()

    presets = _load_node_presets()
    preset = None
    for item in presets:
        if str(item.get("preset_id") or "") == preset_id:
            preset = item
            break
    if not preset:
        return jsonify({"ok": False, "error": "preset_not_found"}), 404

    rows = _load_nodes()
    new_id = str(payload.get("id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}"
    if any(str(x.get("id") or "") == new_id for x in rows):
        return jsonify({"ok": False, "error": "node_id_exists", "message": f"鑺傜偣ID宸插瓨鍦? {new_id}"}), 409

    node = _normalize_node(
        {
            "id": new_id,
            "name": name or f"{preset.get('name')}-{new_id[-4:]}",
            "base_url": str(payload.get("base_url") or "").strip(),
            "ops_base_url": str(payload.get("ops_base_url") or "").strip(),
            "ops_read_key": str(payload.get("ops_read_key") or "").strip(),
            "ops_write_key": str(payload.get("ops_write_key") or "").strip(),
            "ops_actor": str(payload.get("ops_actor") or "").strip(),
            "ops_role": str(payload.get("ops_role") or "SuperAdmin").strip(),
            "server_id": server_id,
            "project_id": project_id,
            "owner": owner,
            "role": str(preset.get("role") or "business"),
            "node_category": str(preset.get("category") or ""),
            "node_type": str(preset.get("node_type") or ""),
            "description": node_note or str(preset.get("default_desc") or ""),
            "biz_status": "normal",
            "allowed_upstream_roles": list(preset.get("fixed_upstream_roles") or []),
            "allowed_downstream_roles": list(preset.get("fixed_downstream_roles") or []),
            "daemon_profile": str(preset.get("daemon_profile") or ""),
            "daemon_start_cmd": daemon_start_cmd,
            "daemon_stop_cmd": daemon_stop_cmd,
            "env": env,
            "channel": channel,
            "enabled": True,
            "tags": [str(preset.get("category") or ""), str(preset.get("role") or "")],
        }
    )
    rows.append(node)
    _save_nodes(rows)
    _set_daemon_state(new_id, {"status": "ADDED", "last_action": "create", "last_error": "", "pid": 0})

    node_kind = _infer_node_kind(str(node.get("role") or "business"), str(preset.get("kind") or ""))
    topo = _load_topology(rows)
    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    topo_edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["nodes"] = topo_nodes
    topo["edges"] = topo_edges
    if not any(isinstance(n, dict) and str(n.get("id") or "") == new_id for n in topo_nodes):
        default_pos = _default_topology_for_nodes(rows).get("nodes") or []
        pos = None
        for n in default_pos:
            if isinstance(n, dict) and str(n.get("id") or "") == new_id:
                pos = n
                break
        topo_nodes.append(
            {
                "id": new_id,
                "role": node.get("role") or "business",
                "kind": node_kind,
                "desc": node.get("description") or "",
                "bizStatus": node.get("biz_status") or "normal",
                "owner": node.get("owner") or "",
                "x": (pos or {}).get("x", 20),
                "y": (pos or {}).get("y", 20),
                "ui": {
                    "x": (pos or {}).get("x", 20),
                    "y": (pos or {}).get("y", 20),
                    "w": 220,
                    "h": 90,
                    "color": "#0f172a",
                    "ports": _normalize_ports(node_kind, (preset.get("default_ports") if isinstance(preset, dict) else None)),
                },
            }
        )
    for exist in topo_nodes:
        if not isinstance(exist, dict):
            continue
        eid = str(exist.get("id") or "")
        if not eid or eid == new_id:
            continue
        src = _resolve_node(node_id=eid) or {}
        if not src:
            continue
        if _can_link_nodes(src, node):
            exists = any(isinstance(e, dict) and str(e.get("from") or "") == eid and str(e.get("to") or "") == new_id for e in topo_edges)
            if not exists:
                topo_edges.append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": eid, "to": new_id, "from_port": "out-1", "to_port": "in-1", "type": "depends_on", "note": "preset-auto"})
        if _can_link_nodes(node, src):
            exists = any(isinstance(e, dict) and str(e.get("from") or "") == new_id and str(e.get("to") or "") == eid for e in topo_edges)
            if not exists:
                topo_edges.append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": new_id, "to": eid, "from_port": "out-1", "to_port": "in-1", "type": "depends_on", "note": "preset-auto"})
    saved_topo = _save_topology(topo)
    log_audit("ops_platform_node_add_from_preset", f"node={new_id}; preset={preset_id}")
    return jsonify({"ok": True, "message": "Node added", "node": node, "topology": saved_topo})


def _ops_platform_daemon_action(node: Dict[str, Any], action: str, reason: str, ticket_id: str, operator: str) -> Dict[str, Any]:
    nid = str(node.get("id") or "")
    act = str(action or "").strip().lower()
    server_id = str(node.get("server_id") or "").strip()
    role = str(node.get("role") or "").strip()
    start_cmd = str(node.get("daemon_start_cmd") or "").strip()
    stop_cmd = str(node.get("daemon_stop_cmd") or "").strip()
    state = _get_daemon_state(nid)
    pid = int(state.get("pid") or 0) if str(state.get("pid") or "").strip().isdigit() else 0

    # Prefer native Ops API path in distributed deployment.
    if server_id and act in ("start", "stop", "restart", "status"):
        map_action = {"start": "start", "stop": "stop", "restart": "restart", "status": "status"}.get(act, "status")
        result = _ops_gateway.execute_platform_action(
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
        running = _is_process_running(pid) if pid > 0 else False
        now_status = "RUNNING" if running else str(state.get("status") or "ADDED")
        if pid > 0 and not running and now_status == "RUNNING":
            now_status = "CRASHED"
            state = _set_daemon_state(nid, {"status": now_status, "last_error": "process not alive", "pid": 0, "last_action": "status"})
        return {"success": True, "message": "daemon status (local fallback)", "data": {"node_id": nid, "status": now_status, "pid": pid, "state": state}}

    if start_cmd and act in ("start", "restart"):
        if act == "restart":
            try:
                if pid > 0 and _is_process_running(pid):
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        proc = subprocess.Popen(start_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        state = _set_daemon_state(nid, {"status": "RUNNING", "pid": int(proc.pid), "last_error": "", "last_action": act})
        return {"success": True, "message": f"daemon {act} via local cmd", "data": {"node_id": nid, "status": "RUNNING", "pid": proc.pid, "state": state}}

    if act in ("stop", "restart"):
        stopped = False
        if pid > 0 and _is_process_running(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                stopped = True
            except Exception as ex:
                _set_daemon_state(nid, {"status": "ERROR", "last_error": str(ex), "last_action": act})
                return {"success": False, "message": f"daemon stop failed: {ex}", "data": {"node_id": nid}}
        elif stop_cmd:
            code = subprocess.call(stop_cmd, shell=True)
            stopped = code == 0
        if stopped:
            state = _set_daemon_state(nid, {"status": "STOPPED", "pid": 0, "last_error": "", "last_action": act})
            if act == "restart" and server_id:
                pass
            return {"success": True, "message": "daemon stopped", "data": {"node_id": nid, "status": "STOPPED", "state": state}}

    return {"success": False, "message": "no daemon control profile configured for this node", "data": {"node_id": nid, "role": role}}


@bp.route("/api/ops-platform/node/daemon-action", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_node_daemon_action():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err
    action = str(payload.get("action") or "status").strip().lower()
    ticket_id = str(payload.get("ticket_id") or "OPS-DAEMON").strip()
    reason = str(payload.get("reason") or "daemon action").strip()
    operator = str(session.get("user") or "intranet-ops")
    result = _ops_platform_daemon_action(node, action, reason, ticket_id, operator)
    ok = bool(result.get("success"))
    if ok:
        _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": "info", "status": "resolved", "title": f"瀹堟姢杩涚▼鍔ㄤ綔: {action}", "message": f"node={node.get('id')}; {result.get('message')}", "node_id": node.get("id")})
    else:
        _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": "critical", "status": "open", "title": f"瀹堟姢杩涚▼鍔ㄤ綔澶辫触: {action}", "message": f"node={node.get('id')}; {result.get('message')}", "node_id": node.get("id")})
    log_audit("ops_platform_daemon_action", f"node={node.get('id')}; action={action}; ok={ok}")
    return jsonify({"ok": ok, "node": node.get("id"), "action": action, "message": str(result.get("message") or ""), "result": result}), (200 if ok else 502)


def _build_node_onboarding() -> Dict[str, Any]:
    overview = _build_overview(project_id="")
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
                "node_id": nid,
                "node_name": n.get("name"),
                "role": n.get("role"),
                "status": status or "UNKNOWN",
                "severity": severity,
                "issues": issues,
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


@bp.route("/api/ops-platform/node-onboarding")
@admin_required("gm_ops")
def ops_platform_node_onboarding():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    return jsonify(_build_node_onboarding())


def _run_flow_step(node: Dict[str, Any], step: Dict[str, Any]) -> Dict[str, Any]:
    action_type = str(step.get("action_type") or "").strip()
    target = str(step.get("target") or node.get("server_id") or "").strip()
    ticket_id = str(step.get("ticket_id") or "OPS-FLOW").strip()
    reason = str(step.get("reason") or "flow step").strip()
    payload = step.get("payload") if isinstance(step.get("payload"), dict) else {}
    dry_run = bool(step.get("dry_run"))
    operator = str(session.get("user") or "intranet-ops")
    return _ops_gateway.execute_platform_action(
        node,
        action_type=action_type,
        target=target,
        payload=payload,
        actor=operator,
        reason=reason,
        ticket_id=ticket_id,
        dry_run=dry_run,
    )


@bp.route("/api/ops-platform/flow-smoke", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_flow_smoke():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    path_nodes = payload.get("path_nodes") if isinstance(payload.get("path_nodes"), list) else []
    if len(path_nodes) < 2:
        return jsonify({"ok": False, "error": "invalid_path", "message": "鑷冲皯閫夋嫨涓や釜鑺傜偣"}), 400
    result_steps: List[Dict[str, Any]] = []
    success = True
    trace_ids: List[str] = []
    job_ids: List[str] = []
    for nid in path_nodes:
        node = _resolve_node(node_id=str(nid or "").strip())
        if not node:
            result_steps.append({"node_id": nid, "ok": False, "message": "node not found"})
            success = False
            continue
        req = {
            "node_id": str(node.get("id") or ""),
            "action_type": "smoke_test",
            "target": str(node.get("server_id") or ""),
            "ticket_id": "OPS-SMOKE",
            "reason": "flow smoke",
            "run_mode": "agent",
            "via_agent": True,
            "payload": {"flow_smoke": True, "path_nodes": path_nodes},
        }
        validation = _validate_ops_request(req, node)
        if not validation.get("ok"):
            msg = "validation failed"
            if validation.get("unsupported"):
                msg = "smoke_test unsupported by agent"
            result_steps.append({"node_id": node.get("id"), "ok": False, "message": msg, "validation": validation})
            success = False
            continue
        executed = _execute_validated(req, node, validation)
        ok = bool(executed.get("ok"))
        msg = str(executed.get("message") or "")
        trace_id = str(executed.get("trace_id") or "")
        job_id = str(((executed.get("data") or {}) if isinstance(executed.get("data"), dict) else {}).get("job_id") or "")
        if trace_id:
            trace_ids.append(trace_id)
        if job_id:
            job_ids.append(job_id)
        result_steps.append({"node_id": node.get("id"), "ok": ok, "message": msg, "trace_id": trace_id, "job_id": job_id, "result": executed})
        if not ok:
            success = False
    flow_id = "flow-" + uuid.uuid4().hex[:12]
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if success else "critical"), "status": ("resolved" if success else "open"), "title": "娴佺▼鍐掔儫娴嬭瘯", "message": f"flow={flow_id}; nodes={len(path_nodes)}; success={success}"})
    _append_bounded(OPS_FLOW_EXEC_KEY, {"flow_id": flow_id, "time": _now_iso(), "type": "smoke", "ok": success, "steps": result_steps}, limit=120, description="娴佺▼鎵ц璁板綍")
    return jsonify({"ok": success, "flow_id": flow_id, "trace_ids": trace_ids, "job_ids": job_ids, "steps": result_steps}), (200 if success else 502)


@bp.route("/api/ops-platform/stress-test", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_stress_test():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err
    qps = int(payload.get("qps") or 300)
    duration_sec = int(payload.get("duration_sec") or 180)
    reason = str(payload.get("reason") or "stress test").strip()
    req = {
        "node_id": str(node.get("id") or ""),
        "action_type": "stress_test",
        "target": str(node.get("server_id") or ""),
        "ticket_id": "OPS-STRESS",
        "reason": reason,
        "run_mode": "agent",
        "via_agent": True,
        "payload": {"qps": qps, "duration_sec": duration_sec},
    }
    validation = _validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "error_code": validation.get("error_code") or "",
            "message": "压力测试请求未通过校验",
            "validation": validation,
        }), 400
    result = _execute_validated(req, node, validation)
    ok = bool(result.get("ok"))
    msg = str(result.get("message") or "")
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if ok else "warning"), "status": ("resolved" if ok else "open"), "title": "鍘嬪姏娴嬭瘯瑙﹀彂", "message": f"node={node.get('id')}; qps={qps}; duration={duration_sec}s; ok={ok}"})
    return jsonify({"ok": ok, "message": msg, "trace_id": result.get("trace_id"), "job_id": ((result.get("data") or {}) if isinstance(result.get("data"), dict) else {}).get("job_id"), "result": result}), (200 if ok else 502)


@bp.route("/api/ops-platform/db-migration", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_db_migration():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err
    direction = str(payload.get("direction") or "up").strip().lower()
    version = str(payload.get("version") or "").strip()
    reason = str(payload.get("reason") or "db migration").strip()
    if str(node.get("role") or "") not in ("database", "cache"):
        return jsonify({"ok": False, "error": "invalid_role", "message": "Only database/cache nodes support db migration"}), 400
    cmd = str(payload.get("command") or node.get("daemon_start_cmd") or "").strip()

    native = _ops_gateway.execute_platform_action(
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
        _append_trace({
            "trace_id": trace_id,
            "time": _now_iso(),
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
        _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": "info", "status": "resolved", "title": "DB Migration", "message": f"node={node.get('id')}; direction={direction}; version={version}; mode=native"})
        log_audit("ops_platform_db_migration", f"node={node.get('id')}; direction={direction}; version={version}; mode=native")
        return jsonify({"ok": True, "message": native.get("message") or "Migration accepted", "trace_id": trace_id, "job_id": None, "result": native})

    if not cmd:
        return jsonify({"ok": False, "error": "native_failed_no_command", "message": f"鍘熺敓杩佺Щ鑳藉姏澶辫触涓旀湭鎻愪緵鏈湴鍛戒护: {native.get('message') or 'unknown'}"}), 502

    code = subprocess.call(cmd, shell=True)
    ok = code == 0
    _set_daemon_state(str(node.get("id") or ""), {"last_action": f"db_migration_{direction}", "last_error": ("" if ok else f"exit_code={code}")})
    trace_id = "mig-" + uuid.uuid4().hex[:16]
    _append_trace({
        "trace_id": trace_id,
        "time": _now_iso(),
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
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if ok else "critical"), "status": ("resolved" if ok else "open"), "title": "DB Migration", "message": f"node={node.get('id')}; direction={direction}; version={version}; mode=fallback; code={code}"})
    log_audit("ops_platform_db_migration", f"node={node.get('id')}; direction={direction}; version={version}; mode=fallback; code={code}")
    return jsonify({"ok": ok, "message": ("Migration success (fallback)" if ok else "Migration failed (fallback)"), "trace_id": trace_id, "job_id": None, "exit_code": code, "native_error": native.get("message")}), (200 if ok else 502)


@bp.route("/api/ops-platform/actions/validate", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_actions_validate():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err

    validation = _validate_ops_request(payload, node)
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
        "message": "棰勬閫氳繃",
        "risk": validation.get("risk"),
        "domain": validation.get("domain"),
        "require_approval": validation.get("require_approval"),
        "approval_target_id": validation.get("approval_target_id"),
        "approved": validation.get("approved"),
    })


@bp.route("/api/ops-platform/actions/approval", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_actions_approval():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err

    validation = _validate_ops_request(payload, node)
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
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err

    validation = _validate_ops_request(payload, node)
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

    if validation.get("require_approval") and (not validation.get("dry_run")) and (not validation.get("approved")):
        return jsonify({
            "ok": False,
            "error": "approval_required",
            "message": "High risk action requires approval before execute.",
            "approval_target_id": validation.get("approval_target_id"),
            "approval_center": "/admin/approval",
        }), 412

    result = _execute_validated(payload, node, validation)
    status = 200 if result.get("ok") else 502
    return jsonify(result), status


@bp.route("/api/ops-platform/actions/<trace_id>")
@admin_required("gm_ops")
def ops_platform_action_detail(trace_id: str):
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    item = _find_trace(trace_id)
    if not item:
        return jsonify({"ok": False, "error": "trace_not_found"}), 404
    return jsonify({"ok": True, "trace": item})


@bp.route("/api/ops-platform/runtime/flow-control", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_runtime_flow_control():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    op = str(payload.get("op") or "").strip().lower()
    if op not in ("start", "stop"):
        return jsonify({"ok": False, "error": "invalid_op", "message": "op must be start or stop"}), 400
    project_id = str(payload.get("project_id") or "").strip()
    actor = str(session.get("user") or "admin")
    policy = _load_agent_policy()

    all_nodes = _load_nodes()
    all_nodes_map = {str(n.get("id") or ""): n for n in all_nodes if isinstance(n, dict) and n.get("id")}
    topo = _load_topology(all_nodes)
    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    node_ids: List[str] = []
    for n in topo_nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        if not nid:
            continue
        raw = all_nodes_map.get(nid) or {}
        if project_id and str(raw.get("project_id") or "") != project_id:
            continue
        node_ids.append(nid)
    if not node_ids:
        return jsonify({"ok": False, "error": "empty_topology", "message": "当前项目没有可执行节点"}), 400

    run_id = "run-" + uuid.uuid4().hex[:12]
    action_type = "start" if op == "start" else "stop"
    now = _now_iso()
    logs: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    bindings = _load_node_agent_bindings()
    reg_v2 = _load_agent_registry_v2()
    fresh_sec = max(20, int(policy.get("agent_online_fresh_sec") or 120))

    for nid in node_ids:
        node = all_nodes_map.get(nid) or _resolve_node(node_id=nid)
        if not node:
            logs.append({"ts": _now_iso(), "level": "error", "node_id": nid, "message": "节点不存在，已跳过"})
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
        if op == "start" and use_agent_mode and desired_role and current_role == desired_role and current_state in ("RUNNING", "ONLINE", "READY", "SUCCESS"):
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS", "mode": "agent-reuse"})
            logs.append({"ts": _now_iso(), "level": "info", "node_id": nid, "message": f"复用远端已运行服务: role={desired_role}; 无需重启"})
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
        validation = _validate_ops_request(req, node)
        if not validation.get("ok"):
            logs.append({"ts": _now_iso(), "level": "error", "node_id": nid, "message": "参数校验失败: " + ",".join(validation.get("missing") or [])})
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
                logs.append({"ts": _now_iso(), "level": "error", "node_id": nid, "message": "自动审批失败: " + str(err or "unknown")})
                continue
            req["approval_id"] = aid
            validation = _validate_ops_request(req, node)
        if bool((req.get("payload") or {}).get("switch_required")):
            logs.append(
                {
                    "ts": _now_iso(),
                    "level": "warn",
                    "node_id": nid,
                    "message": f"远端Agent当前类型为 {current_role or '-'}，将先停止后切换到 {desired_role or '-'}",
                }
            )
        result = _execute_validated(req, node, validation)
        if not result.get("ok"):
            logs.append({"ts": _now_iso(), "level": "error", "node_id": nid, "message": str(result.get("message") or result.get("error") or "execute failed")})
            continue
        job_id = str(((result.get("data") or {}).get("job_id")) or "")
        trace_id = str(result.get("trace_id") or "")
        if use_agent_mode and job_id:
            items.append({"node_id": nid, "job_id": job_id, "trace_id": trace_id, "status": "PENDING", "mode": "agent"})
            logs.append({"ts": _now_iso(), "level": "info", "node_id": nid, "job_id": job_id, "message": "已入队: " + job_id})
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
            logs.append({"ts": _now_iso(), "level": "warn", "node_id": nid, "message": detail})

    run_obj = {
        "run_id": run_id,
        "project_id": project_id,
        "op": op,
        "status": "queued",
        "created_at": now,
        "updated_at": _now_iso(),
        "items": items,
        "logs": logs,
    }
    _upsert_runtime_run(run_obj)
    return jsonify({"ok": True, "run_id": run_id, "status": run_obj.get("status"), "items": items, "logs": logs})


@bp.route("/api/ops-platform/runtime/flow-status")
@admin_required("gm_ops")
def ops_platform_runtime_flow_status():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    run_id = str(request.args.get("run_id") or "").strip()
    run_obj = _find_runtime_run(run_id)
    if not run_obj:
        return jsonify({"ok": False, "error": "run_not_found"}), 404

    jobs = _load_agent_jobs()
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
        if cur in ("SUCCESS", "FAILED", "TIMEOUT", "CANCELED"):
            done += 1
        if cur in ("FAILED", "TIMEOUT", "CANCELED"):
            fail += 1
        if cur != prev:
            msg = f"{item.get('node_id')}: {prev} -> {cur}"
            changed_logs.append({"ts": _now_iso(), "level": "error" if cur in ("FAILED", "TIMEOUT", "CANCELED") else "info", "node_id": item.get("node_id"), "job_id": job_id, "message": msg})

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
    run_obj["updated_at"] = _now_iso()
    _upsert_runtime_run(run_obj)
    debug_obj = {
        "server_time": _now_iso(),
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
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    info = _runtime_active_for_project(project_id)
    return jsonify({"ok": True, "project_id": project_id, "active": bool(info.get("active")), "run_id": str(info.get("run_id") or ""), "status": str(info.get("status") or ""), "reason": str(info.get("reason") or "")})


@bp.route("/api/ops-platform/agent/register", methods=["POST"])
def ops_platform_agent_register():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip() or ("agent-" + uuid.uuid4().hex[:8])
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    device_id = str(payload.get("device_id") or payload.get("host_name") or payload.get("hostname") or request.remote_addr or "unknown-device").strip()
    policy = _load_agent_policy()
    node = _auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    reg = _load_agent_registry()
    reg_v2 = _load_agent_registry_v2()
    now = _now_iso()
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
    _save_agent_registry(reg)
    reg_v2[agent_id] = _normalize_agent_descriptor_v2(
        {
            "agent_id": agent_id,
            "device_id": device_id,
            "host_name": str(payload.get("host_name") or payload.get("hostname") or ""),
            "node_id": node_id,
            "project_id": str(payload.get("project_id") or node.get("project_id") or ""),
            "status": "ONLINE",
            "version": str(payload.get("version") or ""),
            "last_seen": now,
            "display_name": str(payload.get("display_name") or agent_id),
            "port": int(payload.get("port") or 0),
            "remote_game_server_port": int(payload.get("remote_game_server_port") or payload.get("port") or 0),
            "desc": str(payload.get("desc") or ""),
            "run_state": str(payload.get("run_state") or "RUNNING"),
            "network": payload.get("network") if isinstance(payload.get("network"), dict) else {"endpoints": []},
            "region": str(payload.get("region") or ""),
            "zone": str(payload.get("zone") or ""),
            "rack": str(payload.get("rack") or ""),
            "host_ip": str(payload.get("host_ip") or payload.get("host_name") or payload.get("hostname") or ""),
            "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else [],
            "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            "runtime": payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {},
            "transport": {
                "mode": str(payload.get("transport_mode") or "remote"),
                "local_bus": {
                    "enabled": bool(payload.get("local_bus_enabled", True)),
                    "endpoint": str(payload.get("local_bus_endpoint") or ""),
                    "auth_mode": str(payload.get("local_bus_auth_mode") or "token"),
                },
            },
            "updated_at": now,
        }
    )
    _save_agent_registry_v2(reg_v2)
    upgrade = _desired_agent_upgrade(agent_id, policy)
    return jsonify({"ok": True, "agent_id": agent_id, "node_id": node_id, "device_id": device_id, "poll_interval_sec": 5, "mtls_required": bool(policy.get("mtls_required")), "upgrade": upgrade})


@bp.route("/api/ops-platform/agent/heartbeat", methods=["POST"])
def ops_platform_agent_heartbeat():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    device_id = str(payload.get("device_id") or payload.get("host_name") or payload.get("hostname") or request.remote_addr or "unknown-device").strip()
    policy = _load_agent_policy()
    node = _auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    reg = _load_agent_registry()
    reg_v2 = _load_agent_registry_v2()
    cur = reg.get(node_id) if isinstance(reg.get(node_id), dict) else {}
    cur.update(
        {
            "node_id": node_id,
            "agent_id": agent_id or str(cur.get("agent_id") or ""),
            "status": str(payload.get("status") or "ONLINE"),
            "last_seen": _now_iso(),
            "updated_at": _now_iso(),
            "runtime": payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {},
            "version": str(payload.get("version") or cur.get("version") or ""),
            "cert_fingerprint": cert_fp or str(cur.get("cert_fingerprint") or ""),
        }
    )
    reg[node_id] = cur
    _save_agent_registry(reg)
    now = _now_iso()
    prev = reg_v2.get(agent_id) if isinstance(reg_v2.get(agent_id), dict) else {}
    reg_v2[agent_id] = _normalize_agent_descriptor_v2(
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
            "updated_at": now,
        }
    )
    _save_agent_registry_v2(reg_v2)
    jobs = _load_agent_jobs()
    if _reconcile_agent_jobs(
        node_id,
        jobs,
        lease_timeout_sec=int(policy.get("lease_timeout_sec") or 60),
        max_retries=int(policy.get("max_retries") or 2),
    ):
        _save_agent_jobs(jobs)
    pending = len([x for x in jobs if isinstance(x, dict) and str(x.get("node_id") or "") == node_id and str(x.get("status") or "") == "PENDING"])
    upgrade = _desired_agent_upgrade(agent_id, policy)
    return jsonify({"ok": True, "pending_jobs": pending, "server_time": _now_iso(), "upgrade": upgrade})


@bp.route("/api/ops-platform/agent/pull", methods=["POST"])
def ops_platform_agent_pull():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    policy = _load_agent_policy()
    node = _auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    limit = max(1, min(20, int(payload.get("limit") or 5)))
    jobs = _load_agent_jobs()
    changed = _reconcile_agent_jobs(
        node_id,
        jobs,
        lease_timeout_sec=int(policy.get("lease_timeout_sec") or 60),
        max_retries=int(policy.get("max_retries") or 2),
    )
    out: List[Dict[str, Any]] = []
    now = _now_iso()
    node_max = int(node.get("agent_max_concurrency") or policy.get("default_node_concurrency") or 1)
    node_max = max(1, min(20, node_max))
    running = [x for x in jobs if isinstance(x, dict) and str(x.get("node_id") or "") == node_id and str(x.get("status") or "").upper() == "RUNNING"]
    slots = max(0, node_max - len(running))
    if slots <= 0:
        upgrade = _desired_agent_upgrade(agent_id, policy)
        if changed:
            _save_agent_jobs(jobs)
        return jsonify({"ok": True, "jobs": [], "count": 0, "upgrade": upgrade, "node_concurrency": node_max})

    # preempt: if there is high-priority pending preempt job, cancel one running
    preempt_candidate = None
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if str(item.get("node_id") or "") != node_id or str(item.get("status") or "") != "PENDING":
            continue
        if bool(item.get("preempt")):
            preempt_candidate = item
            break
    if preempt_candidate and running:
        victim = sorted(running, key=lambda x: str(x.get("updated_at") or ""))[0]
        victim["status"] = "CANCELED"
        victim["updated_at"] = _now_iso()
        victim["result"] = {"message": "preempted by higher priority job"}
        changed = True
        slots = max(1, slots)

    for item in jobs:
        if not isinstance(item, dict):
            continue
        if str(item.get("node_id") or "") != node_id:
            continue
        if str(item.get("status") or "") != "PENDING":
            continue
        if bool(item.get("require_approval")) and (not bool(item.get("approved"))):
            approval_target_id = str(item.get("approval_target_id") or "").strip()
            if not approval_target_id:
                approval_target_id = _approval_target_id(
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
        _save_agent_jobs(jobs)
    upgrade = _desired_agent_upgrade(agent_id, policy)
    return jsonify({"ok": True, "jobs": out, "count": len(out), "upgrade": upgrade, "node_concurrency": node_max})


@bp.route("/api/ops-platform/agent/report", methods=["POST"])
def ops_platform_agent_report():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    node = _auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    job_id = str(payload.get("job_id") or "").strip()
    status = str(payload.get("status") or "").strip().upper()
    if not job_id or status not in ("RUNNING", "SUCCESS", "FAILED", "CANCELED", "TIMEOUT"):
        return jsonify({"ok": False, "error": "invalid_report_payload"}), 400
    jobs = _load_agent_jobs()
    hit = None
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if str(item.get("job_id") or "") != job_id:
            continue
        if str(item.get("node_id") or "") != node_id:
            continue
        hit = item
        break
    if not hit:
        return jsonify({"ok": False, "error": "job_not_found"}), 404
    hit["status"] = status
    hit["updated_at"] = _now_iso()
    hit["lease"] = {"agent_id": agent_id, "updated_at": _now_iso()}
    hit["result"] = payload.get("result") if isinstance(payload.get("result"), dict) else {"message": str(payload.get("message") or "")}
    if status in ("FAILED", "TIMEOUT"):
        attempts = int(hit.get("attempt") or 0)
        max_retries = int(hit.get("max_retries") or _load_agent_policy().get("max_retries") or 2)
        if attempts < max_retries:
            hit["status"] = "PENDING"
            hit["attempt"] = attempts + 1
            hit["lease"] = {}
            hit["updated_at"] = _now_iso()
            hit["result"] = {"message": "scheduled retry after failure", "last_status": status}
    _save_agent_jobs(jobs)
    reg_v2 = _load_agent_registry_v2()
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
        runtime["updated_at"] = _now_iso()
        cur_agent["runtime"] = runtime
        cur_agent["run_state"] = runtime.get("state") or cur_agent.get("run_state") or ""
        cur_agent["updated_at"] = _now_iso()
        reg_v2[agent_id] = _normalize_agent_descriptor_v2(cur_agent)
        _save_agent_registry_v2(reg_v2)

    _append_event(
        {
            "id": "evt-" + uuid.uuid4().hex[:12],
            "time": _now_iso(),
            "severity": "info" if status in ("SUCCESS", "RUNNING") else "critical",
            "status": "resolved" if _agent_status_terminal(status) and status == "SUCCESS" else "open",
            "title": f"Agent 浠诲姟{status}: {hit.get('action_type')}",
            "message": f"node={node_id}; job={job_id}; agent={agent_id}",
            "trace_id": "",
            "node_id": node_id,
        }
    )
    return jsonify({"ok": True, "job_id": job_id, "status": status})


@bp.route("/api/ops-platform/agent/jobs")
@admin_required("gm_ops")
def ops_platform_agent_jobs():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    node_id = str(request.args.get("node_id") or "").strip()
    status = str(request.args.get("status") or "").strip().upper()
    limit = max(1, min(200, int(request.args.get("limit") or 50)))
    rows = _load_agent_jobs()
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
    reg = _load_agent_registry_v2()
    return jsonify({"ok": True, "count": len(out), "jobs": out, "agents": [_normalize_agent_descriptor_v2(x) for x in reg.values() if isinstance(x, dict)], "policy": _load_agent_policy()})


@bp.route("/api/ops-platform/agent/detail")
@admin_required("gm_ops")
def ops_platform_agent_detail():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    agent_id = str(request.args.get("agent_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    detail = _build_agent_detail(project_id, agent_id)
    if not detail:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    return jsonify({"ok": True, **detail})


@bp.route("/api/ops-platform/agent/audit")
@admin_required("gm_ops")
def ops_platform_agent_audit():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    agent_id = str(request.args.get("agent_id") or "").strip()
    limit = max(1, min(200, int(request.args.get("limit") or 60)))
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400
    detail = _build_agent_detail(project_id, agent_id)
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
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    if request.method == "GET":
        return jsonify({"ok": True, "policy": _load_agent_policy()})
    payload = request.get_json(silent=True) or {}
    current = _load_agent_policy()
    merged = dict(current)
    for k in ("mtls_required", "lease_timeout_sec", "max_retries", "default_node_concurrency"):
        if k in payload:
            merged[k] = payload.get(k)
    if isinstance(payload.get("rollout"), dict):
        rollout = merged.get("rollout") if isinstance(merged.get("rollout"), dict) else {}
        rollout.update(payload.get("rollout"))
        merged["rollout"] = rollout
    _save_agent_policy(merged)
    log_audit("ops_platform_agent_policy_update", f"user={session.get('user')}; policy_updated=true")
    return jsonify({"ok": True, "policy": _load_agent_policy()})


@bp.route("/api/ops-platform/agent/upgrade/report", methods=["POST"])
def ops_platform_agent_upgrade_report():
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("node_id") or "").strip()
    token = str(request.headers.get("X-Agent-Token") or payload.get("token") or "").strip()
    cert_fp = str(request.headers.get("X-Client-Cert-Fingerprint") or payload.get("cert_fingerprint") or "").strip()
    node = _auth_agent_node(node_id, token, cert_fp=cert_fp)
    if not node:
        return jsonify({"ok": False, "error": "agent_auth_failed"}), 403
    reg = _load_agent_registry()
    cur = reg.get(node_id) if isinstance(reg.get(node_id), dict) else {}
    cur["version"] = str(payload.get("version") or cur.get("version") or "")
    cur["upgrade_status"] = str(payload.get("status") or "")
    cur["upgrade_message"] = str(payload.get("message") or "")
    cur["last_seen"] = _now_iso()
    cur["updated_at"] = _now_iso()
    reg[node_id] = cur
    _save_agent_registry(reg)
    return jsonify({"ok": True, "node_id": node_id, "version": cur.get("version")})


@bp.route("/api/ops-platform/summary")
@admin_required("gm_ops")
def ops_platform_summary():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    overview = _build_overview(project_id=project_id)
    nodes = overview.get("nodes") if isinstance(overview.get("nodes"), list) else []
    legacy_rows: List[Dict[str, Any]] = []
    for n in nodes:
        status_value = str(n.get("status") or "UNKNOWN")
        legacy_rows.append(
            {
                "id": n.get("id"),
                "name": n.get("name"),
                "base_url": n.get("base_url"),
                "ops_base_url": n.get("ops_base_url"),
                "server_id": n.get("server_id"),
                "status": {
                    "success": status_value in ("ONLINE", "MAINTENANCE", "DEGRADED"),
                    "data": {
                        "status": status_value,
                        "cpu": n.get("cpu"),
                        "memoryMb": n.get("memory_mb"),
                        "diskUsagePercent": n.get("disk_percent"),
                    },
                    "message": status_value,
                },
                "ops_health": {
                    "success": bool(n.get("health_ok")),
                    "data": {"ready": n.get("ready_ok")},
                    "message": "OK" if n.get("health_ok") else "FAIL",
                },
            }
        )
    return jsonify({"ok": True, "count": len(legacy_rows), "nodes": legacy_rows, "summary": overview.get("summary")})


@bp.route("/api/ops-platform/action", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_action():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    form_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}

    mapped = {
        "agent_status": "health_check",
        "online": "start",
        "offline": "stop",
        "start_all": "start_all",
        "stop_all": "stop_all",
    }.get(action)

    if not mapped:
        return jsonify({"ok": False, "error": "unsupported action"}), 400

    req = {
        "node_id": payload.get("node_id") or "",
        "project_id": payload.get("project_id") or "",
        "env": payload.get("env") or "",
        "channel": payload.get("channel") or "",
        "action_type": mapped,
        "target": str(form_payload.get("serverId") or "").strip(),
        "ticket_id": str(form_payload.get("ticketId") or form_payload.get("ticket_id") or "OPS-COMPAT").strip(),
        "reason": str(form_payload.get("reason") or "compat action").strip(),
        "approver": str(form_payload.get("approver") or session.get("user") or "").strip(),
        "dry_run": bool(form_payload.get("dryRun") or form_payload.get("dry_run") or False),
        "payload": form_payload,
        "approval_id": str(form_payload.get("approval_id") or "").strip(),
    }

    node, err = _node_or_400(req)
    if err:
        return err

    validation = _validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing"), "message": "缺少必填字段"}), 400
    if validation.get("require_approval") and (not validation.get("dry_run")) and (not validation.get("approved")):
        return jsonify({"ok": False, "error": "approval required", "message": "High risk action requires approval"}), 412

    executed = _execute_validated(req, node, validation)
    result = executed.get("result") if isinstance(executed.get("result"), dict) else {}
    return jsonify({
        "ok": bool(executed.get("ok")),
        "node": node.get("id"),
        "action": action,
        "trace_id": executed.get("trace_id"),
        "message": executed.get("message"),
        "result": result,
    }), (200 if executed.get("ok") else 502)


@bp.route("/admin/ops-platform/actions")
@admin_required("gm_ops")
def ops_platform_actions_page():
    project_id = str(request.args.get("project_id") or "").strip()
    content = _render_local_template("ops_actions_page.html", project_id=project_id)
    return _render_page(content, "动作执行中心")

@bp.route("/admin/ops-platform/topology")
@admin_required("gm_ops")
def ops_platform_topology_page():
    project_id = str(request.args.get("project_id") or "").strip()
    content = _render_local_template("ops_topology_workbench.html", project_id=project_id)
    return _render_page(content, "拓扑与配置编排")


@bp.route("/admin/ops-platform/diagnostics")
@admin_required("gm_ops")
def ops_platform_diagnostics_page():
    project_id = str(request.args.get("project_id") or "").strip()
    content = _render_local_template("ops_diagnostics_page.html", project_id=project_id)
    return _render_page(content, "节点诊断中心")

@bp.route("/admin/ops-platform/agent-control")
@admin_required("gm_ops")
def ops_platform_agent_control_page():
    project_id = str(request.args.get("project_id") or "").strip()
    content = _render_local_template("ops_agent_control_page.html", project_id=project_id)
    return _render_standalone_page(content, "Agent 控制面")


@bp.route("/admin/ops-platform/agent-device-local")
@admin_required("gm_ops")
def ops_platform_agent_device_local_page():
    project_id = str(request.args.get("project_id") or "").strip()
    device_id = str(request.args.get("device_id") or "").strip()
    content = _render_local_template("ops_agent_device_local_page.html", project_id=project_id, device_id=device_id)
    return _render_page(content, "设备 Agent 组")


@bp.route("/admin/ops-platform/agent-detail")
@admin_required("gm_ops")
def ops_platform_agent_detail_page():
    project_id = str(request.args.get("project_id") or "").strip()
    agent_id = str(request.args.get("agent_id") or "").strip()
    content = _render_local_template("ops_agent_detail_page.html", project_id=project_id, agent_id=agent_id)
    return _render_standalone_page(content, "Agent 详情")


@bp.route("/admin/ops-platform/change-governance")
@admin_required("gm_ops")
def ops_platform_change_governance_page():
    project_id = str(request.args.get("project_id") or "").strip()
    content = _render_local_template("ops_change_governance_page.html", project_id=project_id)
    return _render_page(content, "发布与变更治理")


