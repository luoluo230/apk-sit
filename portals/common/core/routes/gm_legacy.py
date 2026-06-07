# -*- coding: utf-8 -*-
"""Legacy GM extraction + Ops platform routes."""

from __future__ import annotations

import os
import sys
import json
import re
import signal
import subprocess
import uuid
import hashlib
import socket
import threading
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, redirect, render_template_string, request, session
from urllib.parse import urlencode

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


def _text_has_mojibake(text: str) -> bool:
    sample = str(text or "")
    if not sample:
        return False
    markers = ("鑺", "榛", "缃", "鍘", "涓", "璋", "鏈", "鍏", "瀹", "鍏崇")
    return any(m in sample for m in markers)


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
    missing = _ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
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
OPS_TOPOLOGY_REGISTRY_KEY = "OPS_PLATFORM_TOPOLOGY_REGISTRY"
OPS_TOPOLOGY_CONTENTS_KEY = "OPS_PLATFORM_TOPOLOGY_CONTENTS"
OPS_NODE_PRESETS_KEY = "OPS_PLATFORM_NODE_PRESETS"
OPS_TOPOLOGY_BLUEPRINTS_KEY = "OPS_PLATFORM_TOPOLOGY_BLUEPRINTS"
OPS_DAEMON_STATE_KEY = "OPS_PLATFORM_DAEMON_STATE"
_NODE_CONTRACT_REGISTRY_CACHE: Optional[Dict[str, Any]] = None
OPS_FLOW_EXEC_KEY = "OPS_PLATFORM_FLOW_EXECUTIONS"
OPS_AGENT_REGISTRY_KEY = "OPS_PLATFORM_AGENT_REGISTRY"
OPS_AGENT_REGISTRY_V2_KEY = "OPS_PLATFORM_AGENT_REGISTRY_V2"
OPS_AGENT_METRIC_WINDOW_SEC = 3600
OPS_AGENT_METRIC_MAX_POINTS = 720

_agent_metric_history_lock = threading.Lock()
_agent_metric_history: Dict[str, deque] = {}
OPS_NODE_AGENT_BINDING_KEY = "OPS_PLATFORM_NODE_AGENT_BINDING"
OPS_NODE_SERVICE_BINDING_KEY = "OPS_PLATFORM_NODE_SERVICE_BINDING"
OPS_AGENT_JOBS_KEY = "OPS_PLATFORM_AGENT_JOBS"
OPS_AGENT_POLICY_KEY = "OPS_PLATFORM_AGENT_POLICY"
OPS_RUNTIME_RUNS_KEY = "OPS_PLATFORM_RUNTIME_RUNS"
CANONICAL_LOCAL_AGENT_ID = "agent-local-cn-1"
CANONICAL_LOCAL_DEVICE_ID = "local-game-server"


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _resolve_ops_project_id(raw: str = "") -> str:
    pid = str(raw or "").strip()
    return pid or "GomeKu"


def _ops_platform_redirect_to_runtime_project():
    """Ops 平台运行时默认 GomeKu 最小联通拓扑，避免落到 RecycleTycoon 设计演示。"""
    raw = str(request.args.get("project_id") or "").strip()
    if raw == "GomeKu":
        return None
    args = request.args.to_dict(flat=True)
    args["project_id"] = "GomeKu"
    if request.path.rstrip("/").endswith("/topology"):
        args.setdefault("env_key", "production")
        if not str(args.get("topology_id") or "").strip():
            args["topology_id"] = "topology-design-gomeku-production"
    return redirect(request.path + "?" + urlencode(args))


def _resolve_ops_topology_id(project_id: str, env_key: str, raw: str = "") -> str:
    tid = str(raw or "").strip()
    if tid:
        return tid
    ctx = _resolve_topology_context(project_id, env_key, "")
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    return str(row.get("topology_id") or "")


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
        if env == "development":
            dev_topo = _design_reference_topology_content(pid, env)
            dev_topo["nodes"] = [n for n in (dev_topo.get("nodes") or []) if str(n.get("id") or "") != "db-01" and not ((n.get("ui") or {}).get("list_only"))]
            dev_topo["nodes"] = (dev_topo.get("nodes") or [])[:4]
            dev_topo["edges"] = [e for e in (dev_topo.get("edges") or []) if str(e.get("to") or "") != "tcp-01" and str(e.get("from") or "") != "tcp-01"]
            contents[row["topology_id"]] = dev_topo
        else:
            contents[row["topology_id"]] = _design_reference_topology_content(pid, env)
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


def _project_uses_runtime_topology(project_id: str) -> bool:
    pid = str(project_id or "").strip()
    if not pid:
        return False
    ctx = _resolve_topology_context(pid, "production", "")
    topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
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
    return _design_reference_topology_content(pid, env)


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
        for item in rows:
            if item.get("is_default"):
                target = item
                break
    if target is None and rows:
        target = rows[0]
    if target is None:
        target = _ensure_topology_for_scope(pid, env or "production")
        rows = _list_topologies(pid, env or "production")
    contents = _load_topology_contents()
    topo = contents.get(str(target.get("topology_id") or "")) if isinstance(contents.get(str(target.get("topology_id") or "")), dict) else {}
    if not topo:
        topo = _topology_seed_content(str(target.get("project_id") or ""), str(target.get("env_key") or "production"))
        contents[str(target.get("topology_id") or "")] = topo
        _save_topology_contents(contents)
    elif _needs_design_reference_upgrade(topo):
        meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
        if not meta.get("cluster_source") and not meta.get("runtime_topology"):
            topo = _design_reference_topology_content(str(target.get("project_id") or ""), str(target.get("env_key") or "production"))
            contents[str(target.get("topology_id") or "")] = topo
            _save_topology_contents(contents)
    topo_meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    if not topo_meta.get("cluster_source") and not topo_meta.get("runtime_topology"):
        _ensure_design_reference_bindings(str(target.get("topology_id") or ""))
        _ensure_design_reference_agents(str(target.get("project_id") or pid or ""))
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
    if os.name == "posix" and os.uname().sysname == "Darwin":
        return "local_macos"
    return "local_macos"


def _format_contract_command(template: str, port: int, extras: Optional[Dict[str, Any]] = None) -> str:
    text = str(template or "").strip()
    if not text:
        return ""
    merged = {"port": int(port or 0), "qps": 300, "duration_sec": 180}
    if isinstance(extras, dict):
        merged.update(extras)
    try:
        return text.format(**merged)
    except Exception:
        return text.replace("{port}", str(int(port or 0)))


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
        probe_host = endpoint_host or "127.0.0.1"
        if probe_host in ("0.0.0.0", "*", ""):
            probe_host = "127.0.0.1"
        bind_host = endpoint_host or ("0.0.0.0" if role in ("gateway", "transport", "edge") else "127.0.0.1")
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
            "PresetId": str(node.get("preset_id") or contract.get("preset_id") or ""),
            "ProbeStrategy": str(contract.get("probe_strategy") or "tcp"),
        }
        metadata = _build_daemon_metadata(node, contract, service_port, base_meta)
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
    endpoints = network.get("endpoints") if isinstance(network.get("endpoints"), list) else []
    host = "127.0.0.1"
    if endpoints:
        ep = str(endpoints[0] or "")
        if ":" in ep:
            host = ep.split(":")[0].strip() or host
    return {
        "service_id": node_id,
        "node_id": node_id,
        "agent_id": CANONICAL_LOCAL_AGENT_ID,
        "device_id": CANONICAL_LOCAL_DEVICE_ID,
        "project_id": str(project_id or ""),
        "display_name": str(node.get("name") or node_id),
        "service_type": role,
        "service_port": int(port or 0),
        "remote_game_server_port": int(port or 0),
        "run_state": "UNKNOWN",
        "status": "UNKNOWN",
        "probe_status": "",
        "probe_rtt_ms": 0.0,
        "metrics": {},
        "endpoints": endpoints or ([f"{host}:{port}"] if port else []),
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
    for svc in (hit.get("services") if isinstance(hit.get("services"), list) else []):
        if not isinstance(svc, dict):
            continue
        sid = str(svc.get("service_id") or svc.get("node_id") or "").strip()
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
        return {"ok": False, "error": "missing_ops_gateway_node", "message": "未找到可用的 Ops 网关节点"}
    payload = _topology_to_cluster_payload(project_id, env_key, topology_id)
    result = _ops_gateway.apply_topology(
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
        st = str(row.get("status") or "").lower()
        if op == "start" and st in ("running", "queued"):
            if latest_start is None:
                latest_start = row
        if op == "stop" and st in ("running", "queued"):
            if latest_stop is None:
                latest_stop = row
    if not latest_start:
        return {"active": False, "run_id": "", "status": "", "reason": "no_start_run"}
    start_ts = str(latest_start.get("updated_at") or latest_start.get("created_at") or "")
    stop_ts = str((latest_stop or {}).get("updated_at") or (latest_stop or {}).get("created_at") or "")
    if latest_stop and stop_ts and start_ts and stop_ts >= start_ts:
        return {"active": False, "run_id": str(latest_start.get("run_id") or ""), "status": str(latest_start.get("status") or ""), "reason": "stopped_after_start"}
    if str(latest_start.get("status") or "").lower() in ("failed", "success", "timeout", "canceled"):
        return {"active": False, "run_id": str(latest_start.get("run_id") or ""), "status": str(latest_start.get("status") or ""), "reason": "start_finished"}
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

def _resolve_game_server_repo() -> str:
    env = str(os.getenv("GAME_SERVER_REPO") or "").strip()
    if env and os.path.isdir(env):
        return env
    candidates = [
        "/Users/wangling/Desktop/MyGame/GameClient/game-server",
        r"E:\maclient\game-server",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return env or candidates[0]


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

    merged_nodes: List[Dict[str, Any]] = []
    merged_by_id: Dict[str, Dict[str, Any]] = {}

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

    merged_edge_ids: set = set()
    merged_edges: List[Dict[str, Any]] = []
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
    if existing_meta.get("runtime_topology"):
        meta["runtime_topology"] = True
    if existing_meta.get("description"):
        meta["description"] = str(existing_meta.get("description") or "")

    merged_edges = _repair_runtime_topology_edges(merged_nodes, merged_edges, meta)
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


def _redis_ping_probe(host: str, port: int, timeout: float = 1.5) -> Dict[str, Any]:
    if not host or port <= 0:
        return {"ok": False, "rtt_ms": 0.0, "error": "invalid host/port"}
    start = datetime.utcnow()
    try:
        proc = subprocess.run(
            ["redis-cli", "-h", host, "-p", str(port), "ping"],
            capture_output=True,
            text=True,
            timeout=max(1.0, timeout),
        )
        ok = proc.returncode == 0 and "PONG" in (proc.stdout or "").upper()
        rtt = max(0.0, (datetime.utcnow() - start).total_seconds() * 1000.0)
        return {"ok": ok, "rtt_ms": round(rtt, 1), "error": "" if ok else (proc.stderr or proc.stdout or "redis ping failed").strip()}
    except Exception:
        return _tcp_probe(host, port, timeout)


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


def _cluster_state_is_online(state: Any) -> bool:
    text = str(state or "").strip().upper()
    return text in ("RUNNING", "READY", "ONLINE", "ACTIVE", "0", "ONLINE")


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
) -> Dict[str, Any]:
    """统一服务级运行态：embedded 模块走 cluster 状态，其余走 TCP + cluster 兜底。"""
    svc = dict(service) if isinstance(service, dict) else {}
    sid = str(svc.get("service_id") or svc.get("node_id") or "").strip()
    port = int(svc.get("service_port") or svc.get("remote_game_server_port") or 0)
    cs_map = cluster_status if isinstance(cluster_status, dict) else {}
    cs = str(cs_map.get(sid) or "").strip().upper()
    embedded = _is_embedded_cluster_service(svc)
    probe_method = "tcp"
    open_ok = False

    if embedded:
        probe_method = "cluster-embedded"
        if cs and _cluster_state_is_online(cs):
            open_ok = True
        elif cs and not _cluster_state_is_online(cs):
            open_ok = False
        else:
            # cluster 状态未知时，不凭 TCP 误判 embedded 模块离线
            open_ok = False
            probe_method = "cluster-embedded-deferred"
    else:
        open_ok = _probe_tcp_open(host, port) if port > 0 else False
        if not open_ok and cs and _cluster_state_is_online(cs):
            open_ok = True
            probe_method = "cluster-fallback"

    if open_ok:
        svc["probe_status"] = "PASS"
        svc["status"] = "RUNNING"
        svc["run_state"] = "RUNNING"
    elif embedded and not cs:
        # GameServer 进程内模块：Ops/Gateway 可达时视为在线
        if _probe_tcp_open(host, 5504) and _probe_tcp_open(host, 15050):
            svc["probe_status"] = "PASS"
            svc["status"] = "RUNNING"
            svc["run_state"] = "RUNNING"
            probe_method = "cluster-process-up"
        else:
            svc["probe_status"] = ""
            svc["status"] = "UNKNOWN"
            svc["run_state"] = "UNKNOWN"
    else:
        svc["probe_status"] = "FAIL"
        svc["status"] = "STOPPED"
        svc["run_state"] = "STOPPED"
    svc["probe_method"] = probe_method
    if cs:
        svc["cluster_state"] = cs
    return svc


def _fetch_cluster_runtime_status(agents: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    cluster_status: Dict[str, str] = {}
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
        proc_metrics = {
            "cpu_percent": round(psutil.cpu_percent(interval=0.1), 1),
            "mem_percent": round(psutil.virtual_memory().percent, 1),
            "source": "runtime.sample",
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
    run = str(run_state or "").strip().upper()
    if run in ("RUNNING", "READY"):
        return "RUNNING"
    if run in ("STARTING", "STOPPING", "RESTARTING"):
        return run
    if run in ("STOPPED", "STOP"):
        return "STOPPED"
    base = str(status or "").strip().upper()
    if base:
        return base
    probe = str(probe_status or "").strip().upper()
    if probe == "PASS":
        return "ONLINE"
    if probe == "FAIL":
        return "OFFLINE"
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
    raw = get_system_config(OPS_NODE_PRESETS_KEY, [])
    if isinstance(raw, list) and raw:
        out: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict) and str(item.get("preset_id") or "").strip():
                pid = str(item.get("preset_id") or "").strip()
                if pid == "mysql_db":
                    continue
                out.append(_enrich_preset_from_contract(item))
        if out:
            if any(_text_has_mojibake(str(x.get("name") or "") + str(x.get("default_desc") or "")) for x in out):
                presets = _default_node_presets()
                _save_json_config(OPS_NODE_PRESETS_KEY, presets, description="Ops node preset catalog")
                return presets
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
            agent["metrics_live"] = True
    else:
        agent["effective_status"] = str(agent.get("status") or "UNKNOWN").upper()

    services = [dict(s) for s in (logical_hit.get("services") or []) if isinstance(s, dict)]
    host = str(agent.get("host_ip") or agent.get("host_name") or agent.get("probe_host") or "127.0.0.1").strip()
    services = _refresh_services_live_state(services, host=host, project_id=project_id)
    service_ids = [str(s.get("service_id") or "").strip() for s in services if str(s.get("service_id") or "").strip()]
    member_agent_ids = [str(x or "").strip() for x in (logical_hit.get("member_agent_ids") or []) if str(x or "").strip()]
    member_node_ids = [str(x or "").strip() for x in (logical_hit.get("member_node_ids") or []) if str(x or "").strip()]
    _overlay_live_metrics(agent, member_agent_ids)
    _inject_live_control_metrics(agent)
    if isinstance(hit, dict) and hit:
        hit = dict(hit)
        _inject_live_control_metrics(hit)
        reg[primary_agent_id] = hit
        _append_realtime_agent_sample(hit)
        _save_agent_registry_v2(reg)
    node_id = str(agent.get("node_id") or (member_node_ids[0] if member_node_ids else "")).strip()
    node = _resolve_ops_dispatch_node(project_id, node_id)

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
        "metrics_history": _build_agent_metric_series(agent, member_agent_ids),
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
            "can_restart_agent": bool(primary_agent_id or member_agent_ids or member_node_ids),
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


@bp.route("/api/ops-platform/overview")
@admin_required("gm_ops")
def ops_platform_overview():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    return jsonify(_build_overview(project_id=project_id))


@bp.route("/api/ops-platform/cluster/sync", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_cluster_sync():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or request.args.get("project_id") or "GomeKu").strip()
    repo = _resolve_game_server_repo()
    cluster_path = CLUSTER_JSON_PATH
    if not os.path.isfile(cluster_path):
        return jsonify({
            "ok": False,
            "error": "cluster_json_missing",
            "message": f"未找到 cluster.json: {cluster_path}",
            "game_server_repo": repo,
        }), 404
    stat = _sync_cluster_to_agents(project_id)
    return jsonify({
        "ok": True,
        "project_id": project_id,
        "game_server_repo": repo,
        "cluster_json": cluster_path,
        "sync": stat,
    })


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
        {"id": "overview", "name": "全局总览", "href": "/admin/ops-platform?project_id=GomeKu", "children": ["kpi", "risk", "todo"]},
        {"id": "topology", "name": "拓扑与配置编排", "href": "/admin/ops-platform/topology?project_id=GomeKu&env_key=production&topology_id=topology-design-gomeku-production", "children": ["node_library", "canvas", "inspector"]},
        {"id": "action_center", "name": "动作执行中心", "href": "/admin/ops-platform/actions?project_id=GomeKu", "children": ["catalog", "approval", "execute", "history"]},
        {"id": "diagnostics", "name": "诊断与体检", "href": "/admin/ops-platform/diagnostics?project_id=GomeKu", "children": ["rules", "filter", "export"]},
        {"id": "events_trace", "name": "事件与追踪", "href": "/admin/ops-platform?project_id=GomeKu", "children": ["timeline", "trace", "audit"]},
        {"id": "agent_control", "name": "Agent 管控", "href": "/admin/ops-platform/agent-control?project_id=GomeKu", "children": ["registry", "policy", "queue", "upgrade"]},
        {"id": "change_governance", "name": "发布与变更治理", "href": "/admin/ops-platform/change-governance?project_id=GomeKu", "children": ["change_window", "rollback", "postcheck"]},
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
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
            ],
            "edges": [
                ["gateway_http", "business_main"],
                ["business_main", "mongo_db"],
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
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": [
                ["gateway_http", "business_main"],
                ["business_main", "mongo_db"],
                ["business_main", "redis_cache"],
                ["business_main", "mq_kafka"],
                ["scheduler_job", "business_main"],
                ["scheduler_job", "mongo_db"],
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
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": [
                ["gateway_http", "business_main"],
                ["business_main", "mongo_db"],
                ["business_main", "redis_cache"],
                ["business_main", "mq_kafka"],
                ["scheduler_job", "business_main"],
                ["scheduler_job", "mongo_db"],
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
    project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
    status = str(request.args.get("status") or "").strip().upper()
    device_id = str(request.args.get("device_id") or "").strip()
    host_ip = str(request.args.get("host_ip") or "").strip().lower()
    region = str(request.args.get("region") or "").strip().lower()
    bound = str(request.args.get("bound") or "").strip().lower()
    bindings = _load_node_agent_bindings()
    rows = _logical_agents_for_project(project_id)
    rows = [r for r in rows if not r.get("stale")]
    cluster_status_map: Dict[str, str] = {}
    if project_id and _project_uses_runtime_topology(project_id):
        try:
            cluster_status_map = _fetch_cluster_runtime_status(rows)
        except Exception:
            cluster_status_map = {}
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
            obj["metrics_live"] = True
            obj["metrics_missing"] = {"control": not any(merged.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent", "qps", "rtt_ms")), "business": not any(base_b.get(k) is not None for k in ("qps", "rtt_p95_ms", "rtt_p99_ms", "error_rate", "conn"))}
        else:
            obj["metrics"] = {"control": base_c, "business": base_b, **base_c}
            obj["metrics_live"] = bool(obj.get("metrics_live"))
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
        svc_rows = obj.get("services") if isinstance(obj.get("services"), list) else []
        if svc_rows:
            svc_host = str(obj.get("host_ip") or obj.get("host_name") or obj.get("probe_host") or "127.0.0.1").strip()
            obj["services"] = _refresh_services_live_state(
                svc_rows,
                host=svc_host,
                project_id=project_id,
                cluster_status=cluster_status_map,
            )
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
    for idx, a in enumerate(out):
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
        member_ids = [str(x or "").strip() for x in (a.get("member_agent_ids") or []) if str(x or "").strip()]
        out[idx] = _overlay_live_metrics(a, member_ids or [str(a.get("agent_id") or "")])
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


@bp.route("/api/ops-platform/services/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_services_delete():
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
    remove_index = -1
    removed_service: Dict[str, Any] = {}
    for idx, svc in enumerate(services):
        if not isinstance(svc, dict):
            continue
        if str(svc.get("service_id") or "").strip() == service_id:
            remove_index = idx
            removed_service = dict(svc)
            break

    if remove_index < 0:
        logical_service = next(
            (
                svc for svc in _services_for_project(project_id)
                if isinstance(svc, dict)
                and str(svc.get("service_id") or "").strip() == service_id
                and str(svc.get("agent_id") or "").strip() == agent_id
            ),
            None,
        )
        logical_source = str((logical_service or {}).get("source") or "").strip().lower()
        if logical_source in ("agent.compat", "logical.agent.compat"):
            return jsonify(
                {
                    "ok": False,
                    "error": "OPS_SERVICE_DELETE_COMPAT_BLOCKED",
                    "error_code": "OPS_SERVICE_DELETE_COMPAT_BLOCKED",
                    "message": "该服务实例来自兼容聚合，需先转为正式服务实例或从源节点移除",
                }
            ), 409
        return jsonify({"ok": False, "error": "service_not_found", "error_code": "OPS_SERVICE_NOT_FOUND"}), 404

    services.pop(remove_index)
    hit["services"] = services
    hit["updated_at"] = _now_iso()
    reg[agent_id] = _normalize_agent_descriptor_v2(hit)

    bindings = _load_node_service_bindings() or {}
    removed_binding_nodes = [str(node_id or "").strip() for node_id, bound_service_id in bindings.items() if str(bound_service_id or "").strip() == service_id]
    for node_id in removed_binding_nodes:
        bindings.pop(node_id, None)

    _save_node_service_bindings(bindings)
    _save_agent_registry_v2(reg)
    log_audit("ops_platform_services_delete", f"agent_id={agent_id}; service_id={service_id}; bindings={','.join(removed_binding_nodes)}")
    return jsonify(
        {
            "ok": True,
            "agent_id": agent_id,
            "service_id": service_id,
            "service": removed_service,
            "removed_binding_nodes": removed_binding_nodes,
        }
    )


@bp.route("/api/ops-platform/services/logs", methods=["GET"])
@admin_required("gm_ops")
def ops_platform_services_logs():
    project_id = str(request.args.get("project_id") or "").strip()
    service_id = str(request.args.get("service_id") or "").strip()
    level = str(request.args.get("level") or "all").strip().lower()
    query = str(request.args.get("q") or "").strip()
    try:
        tail = int(request.args.get("tail") or 400)
    except Exception:
        tail = 400
    try:
        since_offset = int(request.args.get("since_offset") or 0)
    except Exception:
        since_offset = 0
    current_session_only = str(request.args.get("current_session") or request.args.get("session") or "1").strip().lower() in ("1", "true", "yes", "on")
    hide_lifecycle = str(request.args.get("hide_lifecycle") or "1").strip().lower() in ("1", "true", "yes", "on")
    tail = max(50, min(tail, 2000))
    payload = _read_gameserver_service_logs(
        service_id,
        level=level,
        query=query,
        tail=tail,
        since_offset=since_offset,
        current_session_only=current_session_only,
        hide_lifecycle=hide_lifecycle,
    )
    return jsonify({"ok": True, "project_id": project_id, "service_id": service_id, **payload})


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

    topology_node = _resolve_ops_dispatch_node(project_id, topology_node_id)
    if not topology_node:
        return jsonify({"ok": False, "error": "topology_node_not_found", "message": "未找到拓扑节点"}), 404

    body_payload = {
        "run_mode": "direct",
        "desired_role": str(service_hit.get("service_type") or ""),
        "desired_service_id": service_id,
        "desired_server_id": service_id,
        "topology_node_id": topology_node_id,
        "switch_required": action in ("start", "restart"),
        "launch_visible_console": bool(payload.get("launch_visible_console", action == "start")),
    }
    operator = str(session.get("user") or "admin")
    ticket_id = "OPS-SVC-" + uuid.uuid4().hex[:8]

    use_direct = (
        agent_id == CANONICAL_LOCAL_AGENT_ID
        or (_project_uses_runtime_topology(project_id) and _is_external_daemon_node(topology_node))
        or (_project_uses_runtime_topology(project_id) and agent_id == CANONICAL_LOCAL_AGENT_ID)
    )
    if _project_uses_runtime_topology(project_id):
        use_direct = True

    if use_direct:
        result = _execute_canonical_service_action(
            project_id,
            topology_node_id,
            service_id,
            action,
            operator,
            "服务实例标准运维动作",
            ticket_id,
            body_payload,
        )
        if not result.get("ok"):
            return jsonify({
                "ok": False,
                "error": "OPS_REMOTE_START_FAILED",
                "error_code": "OPS_REMOTE_START_FAILED",
                "message": str(result.get("message") or "service action failed"),
                "mode": result.get("mode") or "direct",
            }), 502
        return jsonify({
            "ok": True,
            "node_id": topology_node_id,
            "dispatch_node_id": topology_node_id,
            "agent_id": agent_id,
            "service_id": service_id,
            "action": action,
            "mode": result.get("mode") or "direct",
            "message": str(result.get("message") or ""),
            "data": result.get("data") if isinstance(result.get("data"), dict) else {},
            "trace_id": "dir-" + uuid.uuid4().hex[:12],
        })

    dispatch_node_id = str((agent_desc or {}).get("node_id") or "").strip() or topology_node_id
    node = _resolve_ops_dispatch_node(project_id, dispatch_node_id)
    if not node:
        return jsonify({"ok": False, "error": "dispatch_node_not_found", "error_code": "OPS_SERVICE_DISPATCH_NODE_MISSING"}), 404
    req = {
        "node_id": dispatch_node_id,
        "action_type": action_type,
        "target": service_id,
        "ticket_id": ticket_id,
        "reason": "服务实例标准运维动作",
        "approver": operator,
        "run_mode": "agent",
        "via_agent": True,
        "payload": dict(body_payload, run_mode="agent"),
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


@bp.route("/api/ops-platform/agents/restart", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_agents_restart():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    if not agent_id:
        return jsonify({"ok": False, "error": "missing_agent_id"}), 400

    detail = _build_agent_detail(project_id, agent_id)
    if not detail:
        return jsonify({"ok": False, "error": "agent_not_found", "error_code": "OPS_AGENT_NOT_FOUND"}), 404

    agent = detail.get("agent") if isinstance(detail.get("agent"), dict) else {}
    member_node_ids = [str(x or "").strip() for x in (detail.get("member_node_ids") or []) if str(x or "").strip()]
    dispatch_node_id = str(agent.get("node_id") or (member_node_ids[0] if member_node_ids else "")).strip()
    if not dispatch_node_id:
        return jsonify({"ok": False, "error": "missing_dispatch_node_id", "error_code": "OPS_AGENT_DISPATCH_NODE_MISSING"}), 400

    node = _resolve_ops_dispatch_node(project_id, dispatch_node_id)
    if not node:
        return jsonify({"ok": False, "error": "dispatch_node_not_found", "error_code": "OPS_AGENT_DISPATCH_NODE_MISSING"}), 404

    primary_agent_id = str(agent.get("agent_id") or agent_id).strip()
    req = {
        "node_id": dispatch_node_id,
        "action_type": "restart",
        "target": primary_agent_id or dispatch_node_id,
        "ticket_id": "OPS-AGENT-" + uuid.uuid4().hex[:8],
        "reason": "Agent 进程重启",
        "approver": str(session.get("user") or "admin"),
        "run_mode": "agent",
        "via_agent": True,
        "agent_id": primary_agent_id,
        "payload": {
            "run_mode": "agent",
            "desired_role": "agent",
            "desired_agent_id": primary_agent_id,
            "desired_service_id": "",
            "desired_server_id": "",
            "restart_current_agent": True,
            "launch_visible_console": bool(payload.get("launch_visible_console", True)),
        },
    }
    validation = _validate_ops_request(req, node)
    if not validation.get("ok"):
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing") or []}), 400

    result = _execute_validated(req, node, validation)
    if not result.get("ok"):
        return jsonify(
            {
                "ok": False,
                "error": "OPS_AGENT_RESTART_FAILED",
                "error_code": "OPS_AGENT_RESTART_FAILED",
                "message": str(result.get("message") or result.get("error") or "agent restart failed"),
            }
        ), 502
    return jsonify(
        {
            "ok": True,
            "agent_id": primary_agent_id,
            "node_id": dispatch_node_id,
            "job_id": ((result.get("data") or {}).get("job_id") if isinstance(result.get("data"), dict) else ""),
            "trace_id": str(result.get("trace_id") or ""),
            "launch_visible_console": bool(payload.get("launch_visible_console", True)),
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
    probe_results = _probe_agents_batch(rows, timeout=2.0)
    reg = _load_agent_registry_v2()
    out: List[Dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    for item in rows:
        aid = str(item.get("agent_id") or "")
        host = str(item.get("probe_host") or item.get("host_name") or "").strip()
        port = int(item.get("remote_game_server_port") or item.get("port") or 0)
        pr = probe_results.get(aid) or {}
        ok = bool(pr.get("ok"))
        rtt_ms = float(pr.get("rtt_ms") or 0.0)
        err = str(pr.get("error") or "")
        method = str(pr.get("probe_method") or "tcp")
        hit = reg.get(aid) if isinstance(reg.get(aid), dict) else None
        if hit:
            hit["probe_status"] = "PASS" if ok else "FAIL"
            hit["probe_at"] = str(pr.get("probe_at") or _now_iso())
            hit["probe_rtt_ms"] = round(rtt_ms, 1)
            hit["updated_at"] = _now_iso()
            if ok and method == "cluster-embedded":
                hit["probe_source"] = "cluster-embedded"
            reg[aid] = _normalize_agent_descriptor_v2(hit)
        if ok:
            pass_count += 1
        else:
            fail_count += 1
        if ok:
            msg = "连通性正常" if method == "tcp" else "集群内嵌模块在线"
        else:
            msg = "连通性失败: " + (err or "unknown")
        out.append({
            "agent_id": aid,
            "host_name": host,
            "port": port,
            "ok": ok,
            "rtt_ms": round(rtt_ms, 1),
            "message": msg,
            "probe_method": method,
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


@bp.route("/api/ops-platform/topologies")
@admin_required("gm_ops")
def ops_platform_topologies():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_arg = request.args.get("env_key")
    env_filter = _normalize_env_key(env_arg) if (env_arg is not None and str(env_arg).strip()) else None
    rows = _list_topologies(project_id, env_filter)
    env_values = []
    seen_env = set()
    for item in _default_env_options() + [{"env_key": str(x.get("env_key") or ""), "label": str(x.get("env_label") or _env_label(x.get("env_key") or ""))} for x in rows]:
        key = _normalize_env_key(item.get("env_key") or "")
        if not key or key in seen_env:
            continue
        seen_env.add(key)
        env_values.append({"env_key": key, "label": str(item.get("label") or _env_label(key))})
    return jsonify({"ok": True, "project_id": project_id, "env_key": env_filter or "", "count": len(rows), "topologies": rows, "environments": env_values})


@bp.route("/api/ops-platform/topologies/detail")
@admin_required("gm_ops")
def ops_platform_topologies_detail():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = _normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    scoped = _load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    return jsonify(
        {
            "ok": True,
            "project_id": str(registry.get("project_id") or project_id or ""),
            "env_key": str(registry.get("env_key") or env_key or ""),
            "topology_id": tid,
            "registry": registry,
            "topology": {
                "nodes": scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else [],
                "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
                "meta": scoped.get("meta") if isinstance(scoped.get("meta"), dict) else {},
            },
            "bindings": _load_scope_agent_bindings(tid),
            "service_bindings": _load_scope_service_bindings(tid),
        }
    )


@bp.route("/api/ops-platform/topologies/create", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topologies_create():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    name = str(payload.get("name") or "").strip()
    if not project_id:
        return jsonify({"ok": False, "error": "missing_project_id"}), 400
    if not name:
        return jsonify({"ok": False, "error": "missing_name"}), 400
    topology_id = "topology-" + uuid.uuid4().hex[:10]
    rows = _load_topology_registry()
    is_first_for_env = not any(
        isinstance(x, dict)
        and str(x.get("project_id") or "").strip() == project_id
        and _normalize_env_key(x.get("env_key") or "") == env_key
        for x in rows
    )
    row = _normalize_topology_registry_row(
        {
            "topology_id": topology_id,
            "project_id": project_id,
            "env_key": env_key,
            "name": name,
            "version_label": "v1.0.0",
            "owner": str(session.get("user") or "admin"),
            "description": str(payload.get("description") or "").strip(),
            "blueprint_id": str(payload.get("blueprint_id") or "").strip(),
            "is_default": is_first_for_env,
            "status": "draft",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
    )
    rows.append(row)
    _save_topology_registry(rows)
    contents = _load_topology_contents()
    contents[topology_id] = {"nodes": [], "edges": [], "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": _now_iso(), "layout_mode": "structured"}}
    _save_topology_contents(contents)
    log_audit("ops_platform_topology_create", f"project={project_id}; env={env_key}; topology={topology_id}")
    return jsonify({"ok": True, "topology_id": topology_id, "registry": row, "topologies": _list_topologies(project_id, env_key)})


@bp.route("/api/ops-platform/topologies/copy", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topologies_copy():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    source_topology_id = str(payload.get("source_topology_id") or payload.get("topology_id") or "").strip()
    name = str(payload.get("name") or "").strip()
    if not project_id or not source_topology_id or not name:
        return jsonify({"ok": False, "error": "missing_required_fields"}), 400
    scoped = _load_topology_scoped(project_id, env_key, source_topology_id)
    source_row = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    if not source_row:
        return jsonify({"ok": False, "error": "topology_not_found"}), 404
    topology_id = "topology-" + uuid.uuid4().hex[:10]
    row = _normalize_topology_registry_row(
        {
            "topology_id": topology_id,
            "project_id": project_id,
            "env_key": str(source_row.get("env_key") or env_key or "production"),
            "name": name,
            "version_label": "v1.0.0",
            "owner": str(session.get("user") or "admin"),
            "description": str(payload.get("description") or source_row.get("description") or ""),
            "blueprint_id": str(source_row.get("blueprint_id") or ""),
            "copied_from_topology_id": source_topology_id,
            "is_default": False,
            "status": "draft",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
    )
    rows = _load_topology_registry()
    rows.append(row)
    _save_topology_registry(rows)
    src_topo = {
        "nodes": scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else [],
        "edges": scoped.get("edges") if isinstance(scoped.get("edges"), list) else [],
        "meta": scoped.get("meta") if isinstance(scoped.get("meta"), dict) else {},
    }
    copied_nodes = []
    for node in src_topo.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        item = dict(node)
        item.pop("agent_id", None)
        copied_nodes.append(item)
    contents = _load_topology_contents()
    contents[topology_id] = {
        "nodes": copied_nodes,
        "edges": list(src_topo.get("edges") or []),
        "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": _now_iso(), "layout_mode": "structured"},
    }
    _save_topology_contents(contents)
    log_audit("ops_platform_topology_copy", f"project={project_id}; env={env_key}; source={source_topology_id}; target={topology_id}")
    return jsonify({"ok": True, "topology_id": topology_id, "registry": row, "topologies": _list_topologies(project_id, env_key)})


@bp.route("/api/ops-platform/topologies/set-default", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topologies_set_default():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    topology_id = str(payload.get("topology_id") or "").strip()
    if not topology_id:
        return jsonify({"ok": False, "error": "missing_topology_id"}), 400
    rows = _load_topology_registry()
    target = None
    for item in rows:
        if isinstance(item, dict) and str(item.get("topology_id") or "") == topology_id:
            target = _normalize_topology_registry_row(item)
            break
    if not target:
        return jsonify({"ok": False, "error": "topology_not_found"}), 404
    for idx, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        row = _normalize_topology_registry_row(item)
        if row.get("project_id") == target.get("project_id") and row.get("env_key") == target.get("env_key"):
            row["is_default"] = str(row.get("topology_id") or "") == topology_id
            row["updated_at"] = _now_iso()
            rows[idx] = row
    _save_topology_registry(rows)
    log_audit("ops_platform_topology_set_default", f"topology={topology_id}")
    return jsonify({"ok": True, "registry": target, "topologies": _list_topologies(str(target.get('project_id') or ''), str(target.get('env_key') or ''))})


@bp.route("/api/ops-platform/topologies/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topologies_delete():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    topology_id = str(payload.get("topology_id") or "").strip()
    if not topology_id:
        return jsonify({"ok": False, "error": "missing_topology_id"}), 400
    rows = _load_topology_registry()
    target = None
    for item in rows:
        if isinstance(item, dict) and str(item.get("topology_id") or "") == topology_id:
            target = _normalize_topology_registry_row(item)
            break
    if not target:
        return jsonify({"ok": False, "error": "topology_not_found"}), 404
    same_scope = [x for x in rows if isinstance(x, dict) and str(x.get("project_id") or "").strip() == str(target.get("project_id") or "") and _normalize_env_key(x.get("env_key") or "") == str(target.get("env_key") or "")]
    if len(same_scope) <= 1:
        return jsonify({"ok": False, "error": "last_topology_for_scope", "message": "当前环境至少要保留一个拓扑"}), 409
    if bool(target.get("is_default")):
        return jsonify({"ok": False, "error": "default_topology_requires_transfer", "message": "默认拓扑需先转移默认"}), 409
    active = _runtime_active_for_scope(str(target.get("project_id") or ""), str(target.get("env_key") or ""), topology_id)
    if active.get("active"):
        return jsonify({"ok": False, "error": "topology_run_active", "message": "当前拓扑仍有活动中的运行/测试任务"}), 409
    rows = [x for x in rows if not (isinstance(x, dict) and str(x.get("topology_id") or "") == topology_id)]
    _save_topology_registry(rows)
    contents = _load_topology_contents()
    contents.pop(topology_id, None)
    _save_topology_contents(contents)
    agent_bindings = _load_node_agent_bindings()
    if isinstance(agent_bindings, dict):
        for key in list(agent_bindings.keys()):
            if str(key or "").startswith(topology_id + "::"):
                agent_bindings.pop(key, None)
        _save_node_agent_bindings(agent_bindings)
    service_bindings = _load_node_service_bindings()
    if isinstance(service_bindings, dict):
        for key in list(service_bindings.keys()):
            if str(key or "").startswith(topology_id + "::"):
                service_bindings.pop(key, None)
        _save_node_service_bindings(service_bindings)
    log_audit("ops_platform_topology_delete", f"topology={topology_id}")
    return jsonify({"ok": True, "topologies": _list_topologies(str(target.get('project_id') or ''), str(target.get('env_key') or ''))})


@bp.route("/api/ops-platform/topology/node/bindings")
@admin_required("gm_ops")
def ops_platform_node_bindings():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = _normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    scoped = _load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    bindings = _load_scope_agent_bindings(tid)
    service_bindings = _load_scope_service_bindings(tid)
    valid_nodes = set(str(x.get("id") or "") for x in (scoped.get("nodes") or []) if isinstance(x, dict))
    out: Dict[str, str] = {str(nid): str(aid) for nid, aid in bindings.items() if str(nid or "").strip() in valid_nodes and str(aid or "").strip()}
    out_services: Dict[str, str] = {}
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
    return jsonify({"ok": True, "project_id": project_id, "env_key": str(registry.get("env_key") or env_key or ""), "topology_id": tid, "bindings": out, "service_bindings": out_services})


@bp.route("/api/ops-platform/topology/node/bind-agent", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_bind_node_agent():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    agent_id = str(payload.get("agent_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    scoped = _load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node = next((x for x in (scoped.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
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
    bindings = _load_scope_agent_bindings(tid)
    service_bindings = _load_scope_service_bindings(tid)
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
    _save_scope_agent_binding(tid, node_id, agent_id)
    _save_scope_service_binding(tid, node_id, str(service_bindings.get(node_id) or ""))
    if not agent_id:
        _save_scope_service_binding(tid, node_id, "")
    log_audit("ops_platform_bind_node_agent", f"node={node_id}; agent={agent_id}")
    return jsonify({"ok": True, "node_id": node_id, "agent_id": agent_id, "topology_id": tid, "bindings": bindings, "service_bindings": service_bindings})


@bp.route("/api/ops-platform/topology/node/bind-service", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_bind_node_service():
    payload = request.get_json(silent=True) or {}
    service_id = str(payload.get("service_id") or "").strip()
    if not service_id:
        return jsonify({"ok": False, "error": "missing_service_id"}), 400
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400

    scoped = _load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node = next((x for x in (scoped.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
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

    bindings = _load_scope_agent_bindings(tid)
    service_bindings = _load_scope_service_bindings(tid)
    bindings[node_id] = agent_id
    service_bindings[node_id] = service_id
    _save_scope_agent_binding(tid, node_id, agent_id)
    _save_scope_service_binding(tid, node_id, service_id)
    log_audit("ops_platform_bind_node_service", f"node={node_id}; service={service_id}; agent={agent_id}")
    return jsonify({
        "ok": True,
        "node_id": node_id,
        "agent_id": agent_id,
        "service_id": service_id,
        "topology_id": tid,
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
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    scoped = _load_topology_scoped(project_id, env_key, topology_id)
    registry = scoped.get("registry") if isinstance(scoped.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    topo_node = next((x for x in (scoped.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    node = _build_runtime_node_from_topology_node(project_id, str(registry.get("env_key") or env_key or ""), topo_node or {}, tid) if topo_node else None
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    if project_id and str(node.get("project_id") or "") and str(node.get("project_id") or "") != project_id:
        return jsonify({"ok": False, "error": "project_mismatch"}), 409

    bindings = _load_scope_agent_bindings(tid)
    service_bindings = _load_scope_service_bindings(tid)
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
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node_ids = [str(n.get("id") or "") for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "")]
    reg = _load_agent_registry_v2()
    bindings = _load_scope_agent_bindings(tid)
    bound = 0
    skipped = 0
    failed = 0
    detail: List[Dict[str, Any]] = []
    canonical = reg.get(CANONICAL_LOCAL_AGENT_ID) if isinstance(reg.get(CANONICAL_LOCAL_AGENT_ID), dict) else {}
    canonical_services = {
        str(s.get("node_id") or s.get("service_id") or "").strip()
        for s in (canonical.get("services") if isinstance(canonical.get("services"), list) else [])
        if isinstance(s, dict)
    }
    use_canonical = bool(_project_uses_runtime_topology(project_id) and canonical and not canonical.get("stale"))
    for nid in node_ids:
        matched = None
        fail_reason = ""
        if use_canonical:
            matched = CANONICAL_LOCAL_AGENT_ID
        elif not use_canonical:
            for aid, row in reg.items():
                if not isinstance(row, dict) or row.get("stale"):
                    continue
                if project_id and str(row.get("project_id") or "") not in ("", project_id):
                    continue
                if str(row.get("node_id") or "") != nid:
                    continue
                if str(row.get("probe_status") or "").upper() != "PASS":
                    fail_reason = "probe_not_pass"
                    continue
                if str(row.get("effective_status") or row.get("status") or "").upper() not in ("ONLINE", "READY", "RUNNING"):
                    fail_reason = "agent_not_online"
                    continue
                matched = str(aid or "")
                break
        if matched:
            bindings[nid] = matched
            _save_scope_agent_binding(tid, nid, matched)
            bound += 1
            detail.append({"node_id": nid, "agent_id": matched, "ok": True, "result": "bound"})
        else:
            candidates = [row for row in reg.values() if isinstance(row, dict) and str(row.get("node_id") or "") == nid]
            if candidates:
                failed += 1
                detail.append({"node_id": nid, "agent_id": "", "ok": False, "result": "failed", "reason": fail_reason or "agent_not_usable"})
            else:
                skipped += 1
                detail.append({"node_id": nid, "agent_id": "", "ok": False, "result": "skipped", "reason": "no_candidate"})
    return jsonify({"ok": True, "project_id": project_id, "env_key": str(registry.get("env_key") or env_key or ""), "topology_id": tid, "bound_count": bound, "skipped_count": skipped, "failed_count": failed, "bindings": bindings, "detail": detail})


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
    env_key = _normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    topo = _load_topology_scoped(project_id, env_key, topology_id)
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
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    workbench_mode = str(payload.get("workbench_mode") or "").strip().lower()
    locked_mode = str(payload.get("workbench_locked_mode") if payload.get("workbench_locked_mode") is not None else "").strip().lower()
    if workbench_mode and workbench_mode not in ("edit", "run", "test"):
        return jsonify({"ok": False, "error": "invalid_mode", "message": "无效的工作台模式"}), 400
    if locked_mode and locked_mode not in ("edit", "run", "test"):
        return jsonify({"ok": False, "error": "invalid_locked_mode", "message": "无效的锁定模式"}), 400
    ctx = _resolve_topology_context(project_id, env_key, topology_id)
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    tid = str(row.get("topology_id") or topology_id or "").strip()
    if not tid:
        return jsonify({"ok": False, "error": "topology_not_found"}), 404
    contents = _load_topology_contents()
    topo = contents.get(tid) if isinstance(contents.get(tid), dict) else None
    if not isinstance(topo, dict):
        scoped = _load_topology_scoped(project_id, env_key, topology_id)
        topo = scoped if isinstance(scoped, dict) else None
    if not isinstance(topo, dict):
        return jsonify({"ok": False, "error": "topology_not_found"}), 404
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    if workbench_mode in ("edit", "run", "test"):
        meta["workbench_mode"] = workbench_mode
    if "workbench_locked_mode" in payload:
        meta["workbench_locked_mode"] = locked_mode if locked_mode in ("edit", "run", "test") else ""
        if locked_mode in ("edit", "run", "test"):
            meta["workbench_mode"] = locked_mode
    meta["workbench_mode_updated_at"] = _now_iso()
    topo["meta"] = meta
    contents[tid] = topo
    _save_topology_contents(contents)
    log_audit(
        "ops_platform_topology_workbench_mode",
        f"topology={tid}; mode={meta.get('workbench_mode')}; locked={meta.get('workbench_locked_mode') or ''}",
    )
    return jsonify({
        "ok": True,
        "workbench_mode": str(meta.get("workbench_mode") or "edit"),
        "workbench_locked_mode": str(meta.get("workbench_locked_mode") or ""),
        "workbench_mode_updated_at": str(meta.get("workbench_mode_updated_at") or ""),
    })


@bp.route("/api/ops-platform/topology/save", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_save():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    topo = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
    valid, errors = _validate_topology_contract(topo)
    if not valid:
        return jsonify({"ok": False, "error": "topology_contract_invalid", "message": "；".join(errors), "errors": errors}), 400
    ctx = _resolve_topology_context(project_id, env_key, topology_id)
    registry = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    pid = str(registry.get("project_id") or project_id or "")
    tid = str(registry.get("topology_id") or topology_id or "")
    agent_stat = _upsert_agents_from_topology(pid, saved.get("nodes") if isinstance(saved.get("nodes"), list) else [])
    purge_stat = {}
    saved_meta = saved.get("meta") if isinstance(saved.get("meta"), dict) else {}
    if saved_meta.get("runtime_topology") or _project_uses_runtime_topology(pid):
        purge_stat = _purge_design_demo_project_state(pid, tid)
    sync_result = _sync_topology_to_game_server(pid, str(registry.get("env_key") or env_key or ""), tid, str(session.get("user") or "admin"))
    canonical_stat = _consolidate_runtime_agents_to_canonical(pid)
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
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
    if not node_id:
        return jsonify({"ok": False, "error": "missing node_id"}), 400

    topo = _load_topology_scoped(project_id, env_key, topology_id)
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
    target["kind"] = _infer_node_kind(str(target.get("role") or "business"), str(target.get("kind") or ""))
    target["ui"]["ports"] = _normalize_ports(str(target.get("kind") or "standard"), target["ui"].get("ports"))
    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)

    log_audit("ops_platform_topology_node_update", f"node={node_id}")
    return jsonify({"ok": True, "message": "节点属性已更新", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})


@bp.route("/api/ops-platform/topology/node/clone", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_clone():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing_node_id"}), 400
    topo = _load_topology_scoped(project_id, env_key, topology_id)
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
    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_node_clone", f"node={node_id}; clone={new_id}")
    return jsonify({"ok": True, "message": "节点已复制", "node_id": new_id, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})


@bp.route("/api/ops-platform/topology/node/disable", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_node_disable():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    disabled = bool(payload.get("disabled", True))
    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    target = next((x for x in (topo.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not target:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    ui = target.get("ui") if isinstance(target.get("ui"), dict) else {}
    ui["disabled"] = disabled
    target["ui"] = ui
    target["bizStatus"] = "offline" if disabled else "normal"
    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_node_disable", f"node={node_id}; disabled={disabled}")
    return jsonify({"ok": True, "message": "节点状态已更新", "disabled": disabled, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})


@bp.route("/api/ops-platform/topology/node/logs")
@admin_required("gm_ops")
def ops_platform_topology_node_logs():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = _normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    node_id = str(request.args.get("node_id") or "").strip()
    limit = max(1, min(200, int(request.args.get("limit") or 40)))
    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    node = next((x for x in (topo.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == node_id), None)
    if not node:
        return jsonify({"ok": False, "error": "node_not_found"}), 404
    jobs = [x for x in reversed(_load_agent_jobs()) if isinstance(x, dict) and str(x.get("node_id") or "") == node_id][:limit]
    events = [x for x in _load_json_config(OPS_EVENT_LOG_KEY, []) if isinstance(x, dict) and str(x.get("node_id") or "") == node_id]
    events = list(reversed(events[-limit:]))
    bindings = _load_scope_agent_bindings(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""))
    return jsonify({
        "ok": True,
        "node": node,
        "agent_id": str(bindings.get(node_id) or ""),
        "jobs": jobs,
        "events": events,
    })


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


@bp.route("/api/ops-platform/topology/structured/add-existing-target", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_add_existing_target():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    frm = str(payload.get("from_node_id") or payload.get("from") or "").strip()
    to = str(payload.get("to_node_id") or payload.get("to") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    ok, result, status = _ops_structured_append_edge(topo, frm, to)
    if not ok:
        return jsonify(result), status
    _ops_topology_meta_structured(topo)
    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_structured_add_existing_target", f"{frm}->{to}")
    return jsonify({"ok": True, "message": "已添加下游连线", "edge": result, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})


@bp.route("/api/ops-platform/topology/structured/add-new-target", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_structured_add_new_target():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    frm = str(payload.get("from_node_id") or payload.get("from") or "").strip()
    preset_id = str(payload.get("preset_id") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    if not frm or not preset_id:
        return jsonify({"ok": False, "error": "missing_required_fields", "message": "缺少源节点或模板"}), 400
    preset = None
    for item in _load_node_presets():
        if isinstance(item, dict) and str(item.get("preset_id") or "") == preset_id:
            preset = item
            break
    if not preset:
        return jsonify({"ok": False, "error": "preset_not_found", "message": "节点模板不存在"}), 404

    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    src_node = next((x for x in (topo.get("nodes") or []) if isinstance(x, dict) and str(x.get("id") or "") == frm), None)
    if not src_node:
        return jsonify({"ok": False, "error": "node not found", "message": "源节点不存在"}), 404
    role = str(preset.get("role") or "business")
    node_kind = _infer_node_kind(role, str(preset.get("kind") or ""))
    candidate = {
        "id": str(payload.get("id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}",
        "name": str(payload.get("name") or preset.get("name") or preset_id),
        "server_id": str(payload.get("server_id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}",
        "project_id": project_id,
        "env": str(registry.get("env_key") or env_key or "production"),
        "owner": str(payload.get("owner") or "ops-admin"),
        "role": role,
        "node_category": str(preset.get("category") or ""),
        "node_type": str(preset.get("node_type") or ""),
        "desc": str(payload.get("description") or preset.get("default_desc") or ""),
        "bizStatus": "normal",
        "tags": [str(preset.get("category") or ""), role],
        "x": 160.0,
        "y": 160.0,
        "ui": {"x": 160.0, "y": 160.0, "w": 220, "h": 90, "color": "#0f172a", "locked": False, "ports": _normalize_ports(node_kind, preset.get("default_ports"))},
    }
    if not _can_link_nodes(src_node, candidate):
        return jsonify({"ok": False, "error": "invalid_edge_by_role", "error_code": "OPS_EDGE_ROLE_FORBIDDEN", "message": "该模板不能作为当前节点的下游"}), 409
    new_id = str(candidate.get("id") or "").strip()
    if any(isinstance(x, dict) and str(x.get("id") or "") == new_id for x in (topo.get("nodes") or [])):
        return jsonify({"ok": False, "error": "node_id_exists", "message": f"节点ID已存在: {new_id}"}), 409
    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    topo["nodes"] = topo_nodes
    if not any(isinstance(n, dict) and str(n.get("id") or "") == new_id for n in topo_nodes):
        topo_nodes.append(candidate)
    ok, result, status = _ops_structured_append_edge(topo, frm, new_id)
    if not ok:
        return jsonify(result), status
    _ops_topology_meta_structured(topo)
    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_structured_add_new_target", f"{frm}->{new_id}; preset={preset_id}")
    return jsonify({"ok": True, "message": "已添加下游节点", "node": candidate, "edge": result, "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})


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
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    frm = str(payload.get("from") or "").strip()
    to = str(payload.get("to") or "").strip()
    from_port = str(payload.get("from_port") or "out-1").strip()
    to_port = str(payload.get("to_port") or "in-1").strip()
    etype = str(payload.get("type") or "depends_on").strip()
    note = str(payload.get("note") or "").strip()
    if not frm or not to or frm == to:
        return jsonify({"ok": False, "error": "invalid edge endpoints"}), 400

    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = edges
    valid = set([str(x.get("id") or "") for x in topo.get("nodes") or [] if isinstance(x, dict)])
    if frm not in valid or to not in valid:
        return jsonify({"ok": False, "error": "node not found"}), 404
    topo_nodes = {str(x.get("id") or ""): x for x in (topo.get("nodes") or []) if isinstance(x, dict)}
    fn = topo_nodes.get(frm) or {}
    tn = topo_nodes.get(to) or {}
    if not _can_link_nodes(fn, tn):
        return jsonify({
            "ok": False,
            "error": "invalid_edge_by_role",
            "error_code": "OPS_EDGE_ROLE_FORBIDDEN",
            "message": "当前节点角色规则不允许该连线",
        }), 409
    fkind = str(fn.get("kind") or _infer_node_kind(str(fn.get("role") or ""), ""))
    tkind = str(tn.get("kind") or _infer_node_kind(str(tn.get("role") or ""), ""))
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

    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_edge_upsert", f"{frm}->{to}; type={etype}")
    resp = {"ok": True, "message": "连线已保存", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry}
    return jsonify(resp)


@bp.route("/api/ops-platform/topology/edge/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_edge_delete():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    edge_id = str(payload.get("edge_id") or "").strip()
    if not edge_id:
        return jsonify({"ok": False, "error": "missing edge_id"}), 400

    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
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
    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_topology_edge_delete", f"edge={edge_id}")
    return jsonify({"ok": True, "message": "Edge deleted", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})


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
    project_id = str(payload.get("project_id") or "").strip()
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        return jsonify({"ok": False, "error": "missing node_id"}), 400

    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    tid = str(registry.get("topology_id") or topology_id or "")
    node_ids = {str(x.get("id") or "") for x in (topo.get("nodes") or []) if isinstance(x, dict)}
    if node_id not in node_ids:
        return jsonify({"ok": False, "error": "node not found"}), 404
    if _is_critical_topology_node(topo, node_id):
        return jsonify({"ok": False, "error": "node_delete_blocked", "error_code": "OPS_NODE_DELETE_BLOCKED", "message": "Critical node cannot be deleted"}), 409

    before_edges = len(topo.get("edges") or [])
    topo["nodes"] = [x for x in (topo.get("nodes") or []) if not (isinstance(x, dict) and str(x.get("id") or "") == node_id)]
    topo["edges"] = [x for x in (topo.get("edges") or []) if not (isinstance(x, dict) and (str(x.get("from") or "") == node_id or str(x.get("to") or "") == node_id))]
    saved = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), tid, topo)

    bindings = _load_scope_agent_bindings(tid)
    if node_id in bindings:
        bindings.pop(node_id, None)
        _save_scope_agent_binding(tid, node_id, "")
    service_bindings = _load_scope_service_bindings(tid)
    if node_id in service_bindings:
        service_bindings.pop(node_id, None)
        _save_scope_service_binding(tid, node_id, "")

    log_audit("ops_platform_topology_node_delete", f"node={node_id}; removed_edges={before_edges - len(saved.get('edges') or [])}")
    return jsonify({"ok": True, "message": "Node deleted", "topology": {"nodes": saved.get("nodes") or [], "edges": saved.get("edges") or [], "meta": saved.get("meta") or {}}, "bindings": bindings, "service_bindings": service_bindings, "registry": saved.get("registry") if isinstance(saved.get("registry"), dict) else registry})


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
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
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
    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    if replace_existing:
        topo = {"nodes": [], "edges": [], "meta": {"viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1, "updated_at": _now_iso()}}
    existing_ids = set(str(n.get("id") or "") for n in (topo.get("nodes") or []) if isinstance(n, dict))
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
            contract = _load_node_contract(preset_id) or {}
            default_port = int(preset.get("default_port") or contract.get("default_port") or 0)
            daemon_defaults = _contract_daemon_defaults(preset_id, default_port) if preset_id else {}
            created_node_ids.append(new_id)
            created_by_preset.setdefault(preset_id, []).append(new_id)
            remote_ui = {"port": default_port} if default_port > 0 else {}
            network_ui = {"endpoints": [f"127.0.0.1:{default_port}"]} if default_port > 0 else {}
            topo["nodes"].append(
                {
                    "id": new_id,
                    "name": f"{str(preset.get('name') or preset_id)}-{idx + 1}",
                    "server_id": new_id,
                    "preset_id": preset_id,
                    "project_id": project_id,
                    "env": str(registry.get("env_key") or env_key or "production"),
                    "role": role,
                    "kind": node_kind,
                    "desc": str(preset.get("default_desc") or ""),
                    "bizStatus": "normal",
                    "owner": "ops-admin",
                    "daemon_profile": str(preset.get("daemon_profile") or ""),
                    "daemon_start_cmd": str(daemon_defaults.get("StartCommand") or ""),
                    "daemon_stop_cmd": str(daemon_defaults.get("StopCommand") or ""),
                    "daemon_port": default_port,
                    "x": 160.0,
                    "y": 160.0,
                    "tags": [str(preset.get("category") or ""), role],
                    "ui": {
                        "x": 160.0,
                        "y": 160.0,
                        "w": 220,
                        "h": 90,
                        "color": "#0f172a",
                        "locked": False,
                        "ports": _normalize_ports(node_kind, None),
                        "remote": remote_ui,
                        "network": network_ui,
                    },
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

    saved_topo = _save_topology_scoped(str(registry.get("project_id") or project_id or ""), str(registry.get("env_key") or env_key or ""), str(registry.get("topology_id") or topology_id or ""), topo)
    log_audit("ops_platform_apply_blueprint", f"blueprint={bid}; created={len(created_node_ids)}; project={project_id}")
    return jsonify({"ok": True, "blueprint_id": bid, "created_count": len(created_node_ids), "created_node_ids": created_node_ids, "topology": {"nodes": saved_topo.get("nodes") or [], "edges": saved_topo.get("edges") or [], "meta": saved_topo.get("meta") or {}}, "registry": saved_topo.get("registry") if isinstance(saved_topo.get("registry"), dict) else registry})


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
    env_key = _normalize_env_key(payload.get("env_key") or payload.get("env") or "production")
    topology_id = str(payload.get("topology_id") or "").strip()
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

    contract = _load_node_contract(preset_id) or {}
    default_port = int(preset.get("default_port") or contract.get("default_port") or 0)
    if not daemon_start_cmd and preset_id:
        daemon_start_cmd = str(_contract_daemon_defaults(preset_id, default_port).get("StartCommand") or "").strip()
    if not daemon_stop_cmd and preset_id:
        daemon_stop_cmd = str(_contract_daemon_defaults(preset_id, default_port).get("StopCommand") or "").strip()

    rows = _load_nodes()
    new_id = str(payload.get("id") or "").strip() or f"{preset_id}-{uuid.uuid4().hex[:6]}"
    if any(str(x.get("id") or "") == new_id for x in rows):
        return jsonify({"ok": False, "error": "node_id_exists", "message": f"节点ID已存在: {new_id}"}), 409

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
            "server_id": server_id or new_id,
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
            "env": env_key,
            "channel": channel,
            "enabled": True,
            "tags": [str(preset.get("category") or ""), str(preset.get("role") or "")],
        }
    )
    rows.append(node)
    _save_nodes(rows)
    _set_daemon_state(new_id, {"status": "ADDED", "last_action": "create", "last_error": "", "pid": 0})

    ctx = _resolve_topology_context(project_id, env_key, topology_id)
    registry = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    topo = _load_topology_scoped(project_id, env_key, topology_id)
    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    topo_edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    node_kind = _infer_node_kind(str(node.get("role") or "business"), str(preset.get("kind") or ""))
    if not any(isinstance(n, dict) and str(n.get("id") or "") == new_id for n in topo_nodes):
        x = float(payload.get("x") or 20)
        y = float(payload.get("y") or 20)
        remote_ui = {"port": default_port} if default_port > 0 else {}
        network_ui = {"endpoints": [f"127.0.0.1:{default_port}"]} if default_port > 0 else {}
        topo_nodes.append(
            {
                "id": new_id,
                "name": node.get("name") or new_id,
                "server_id": node.get("server_id") or new_id,
                "preset_id": preset_id,
                "role": node.get("role") or "business",
                "kind": node_kind,
                "desc": node.get("description") or "",
                "bizStatus": node.get("biz_status") or "normal",
                "owner": node.get("owner") or "",
                "daemon_profile": str(preset.get("daemon_profile") or ""),
                "daemon_start_cmd": daemon_start_cmd,
                "daemon_stop_cmd": daemon_stop_cmd,
                "daemon_port": default_port,
                "x": x,
                "y": y,
                "ui": {
                    "x": x,
                    "y": y,
                    "w": 220,
                    "h": 90,
                    "color": "#0f172a",
                    "ports": _normalize_ports(node_kind, (preset.get("default_ports") if isinstance(preset, dict) else None)),
                    "remote": remote_ui,
                    "network": network_ui,
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
    topo["nodes"] = topo_nodes
    topo["edges"] = topo_edges
    saved_topo = _save_topology_scoped(
        str(registry.get("project_id") or project_id or ""),
        str(registry.get("env_key") or env_key or ""),
        str(registry.get("topology_id") or topology_id or ""),
        topo,
    )
    log_audit("ops_platform_node_add_from_preset", f"node={new_id}; preset={preset_id}")
    return jsonify({
        "ok": True,
        "message": "Node added",
        "node": node,
        "topology": {"nodes": saved_topo.get("nodes") or [], "edges": saved_topo.get("edges") or [], "meta": saved_topo.get("meta") or {}},
        "registry": saved_topo.get("registry") if isinstance(saved_topo.get("registry"), dict) else registry,
    })


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
        with socket.create_connection((host_name, port_val), timeout=max(0.2, float(timeout))):
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
    "mongo-db-cn-1": ["mongo", "mongosession"],
    "redis-cache-cn-1": ["redis"],
}


def _gameserver_log_artifact_paths() -> Tuple[str, str]:
    repo = _resolve_game_server_repo()
    log_dir = os.path.join(repo, "tools", "SmokeTest", "artifacts")
    return (
        os.path.join(log_dir, "server-live.out.log"),
        os.path.join(log_dir, "server-live.err.log"),
    )


def _gameserver_log_source_paths(current_session_only: bool = False) -> List[str]:
    """优先 UTF-8 结构化日志（ServerLogger 写入），再合并 nohup 控制台输出。"""
    repo = _resolve_game_server_repo()
    paths: List[str] = []
    all_cluster: List[str] = []
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
    cluster_paths = sorted(set(all_cluster), reverse=True)
    if current_session_only:
        cluster_paths = cluster_paths[:1]
    else:
        cluster_paths = cluster_paths[:3]
    paths.extend(cluster_paths)
    out_path, err_path = _gameserver_log_artifact_paths()
    if cluster_paths:
        if os.path.isfile(err_path):
            paths.append(err_path)
        if os.path.isfile(out_path):
            paths.append(out_path)
    else:
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
    paths = _gameserver_log_source_paths(current_session_only=current_session_only)
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
    has_cluster_logs = any("cluster-" in os.path.basename(p) for p in paths)
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fp:
                for line in fp:
                    if has_cluster_logs and "????" in line and _GS_LOG_LINE_RE.match(line.strip()):
                        continue
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
        merged, session_started_at = _slice_merged_from_current_session(merged)

    lv_filter = str(level or "all").strip().lower()
    q = str(query or "").strip().lower()
    parsed_rows: List[Dict[str, Any]] = []
    for byte_offset, line, path in merged:
        if since_offset > 0 and byte_offset < since_offset:
            continue
        if hide_lifecycle and _should_hide_lifecycle_log_line(line):
            continue
        parsed = _parse_gameserver_log_line(line, path)
        if lv_filter not in ("", "all") and parsed.get("level") != lv_filter:
            continue
        if service_id and not _service_log_line_matches(service_id, parsed, line):
            continue
        hay = f"{parsed.get('raw') or ''} {parsed.get('category') or ''} {parsed.get('message') or ''}".lower()
        if q and q not in hay:
            continue
        parsed_rows.append({
            **parsed,
            "offset": byte_offset,
            "source": os.path.basename(path),
        })

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


def _launch_local_game_server(reason: str = "") -> Dict[str, Any]:
    repo = _resolve_game_server_repo()
    script = os.path.join(repo, "scripts", "Start-GameServer.sh")
    if not os.path.isfile(script):
        return {"success": False, "message": f"未找到 GameServer 启动脚本: {script}"}
    log_dir = os.path.join(repo, "tools", "SmokeTest", "artifacts")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "apk-site-service-start.log")
    try:
        log_fp = open(log_path, "a", encoding="utf-8")
        log_fp.write(f"\n[{_now_iso()}] launch reason={reason or 'service-start'}\n")
        log_fp.flush()
        proc = subprocess.Popen(
            ["bash", script],
            cwd=repo,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return {
            "success": True,
            "message": "GameServer 启动脚本已在后台执行，约 30-90 秒后刷新查看状态",
            "data": {"pid": int(proc.pid), "log": log_path, "script": script},
        }
    except Exception as ex:
        return {"success": False, "message": f"启动 GameServer 失败: {ex}"}


def _stop_local_game_server() -> Dict[str, Any]:
    try:
        subprocess.call(["pkill", "-f", "GameServer.GameServerApp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "message": "已发送停止信号给 GameServer 进程"}
    except Exception as ex:
        return {"success": False, "message": f"停止 GameServer 失败: {ex}"}


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


def _fallback_local_control_metrics() -> Dict[str, Any]:
    """psutil 不可用时的轻量采样（macOS/Linux）。"""
    now = _now_iso()
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
        sample = _fallback_local_control_metrics()
        if any(sample.get(k) is not None for k in ("cpu_percent", "mem_percent", "disk_percent")):
            return sample
        return {"source": "runtime.sample", "updated_at": now}


def _inject_live_control_metrics(item: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
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
) -> List[Dict[str, Any]]:
    sample = _sample_local_control_metrics()
    cs_map = cluster_status if isinstance(cluster_status, dict) else {}
    if not cs_map and project_id:
        try:
            cs_map = _fetch_cluster_runtime_status(_agents_v2_for_project(project_id))
        except Exception:
            cs_map = {}
    out: List[Dict[str, Any]] = []
    for raw in services or []:
        if not isinstance(raw, dict):
            continue
        svc = _resolve_service_runtime_state(raw, host=host, cluster_status=cs_map)
        metrics = svc.get("metrics") if isinstance(svc.get("metrics"), dict) else {}
        merged = dict(metrics)
        for key in ("cpu_percent", "mem_percent", "disk_percent", "source", "updated_at"):
            if sample.get(key) is not None and merged.get(key) is None:
                merged[key] = sample.get(key)
        if merged:
            svc["metrics"] = merged
        svc["updated_at"] = str(svc.get("updated_at") or sample.get("updated_at") or _now_iso())
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
        if ok:
            st = "RUNNING" if act in ("start", "restart", "status") else "STOPPED"
            _update_canonical_service_runtime(service_id, status=st, run_state=st, probe_status="PASS" if st == "RUNNING" else "FAIL")
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

    ops_node = _resolve_ops_dispatch_node(project_id, "ops-cn-1") or node
    map_action = {"start": "start", "stop": "stop", "restart": "restart", "status": "status", "probe": "health_check", "logs": "log_tail"}.get(act, act)
    result = _ops_gateway.execute_platform_action(
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

    if not ok and act == "start":
        launch = _launch_local_game_server(reason)
        if launch.get("success"):
            port = int(node.get("port") or node.get("remote_game_server_port") or 0)
            if port > 0 and _probe_tcp_open("127.0.0.1", port):
                ok = True
                result = {"success": True, "message": "服务已在运行", "data": launch.get("data") or {}}
            else:
                ok = True
                result = {
                    "success": True,
                    "message": str(launch.get("message") or "GameServer 启动脚本已在后台执行"),
                    "data": dict(launch.get("data") or {}, starting=True),
                }
        else:
            result = launch

    if not ok and act in ("stop", "restart"):
        stop_res = _stop_local_game_server()
        if stop_res.get("success"):
            ok = act == "stop"
            result = stop_res
            if act == "restart":
                launch = _launch_local_game_server(reason)
                ok = bool(launch.get("success"))
                result = launch

    if ok:
        port = int(node.get("port") or node.get("remote_game_server_port") or 0)
        live = _probe_tcp_open("127.0.0.1", port) if port > 0 else bool((result.get("data") or {}).get("starting"))
        st = "STARTING" if (result.get("data") or {}).get("starting") else ("RUNNING" if act != "stop" and live else ("STOPPED" if act == "stop" else "RUNNING"))
        metrics = _sample_local_control_metrics()
        _update_canonical_service_runtime(
            service_id,
            status=st,
            run_state=st,
            probe_status="PASS" if live and st == "RUNNING" else "",
            metrics=metrics,
        )
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
    env_key = _normalize_env_key(payload.get("env_key") or "")
    topology_id = str(payload.get("topology_id") or "").strip()
    actor = str(session.get("user") or "admin")
    policy = _load_agent_policy()
    topo = _load_topology_scoped(project_id, env_key, topology_id)
    registry = topo.get("registry") if isinstance(topo.get("registry"), dict) else {}
    scoped_project_id = str(registry.get("project_id") or project_id or "")
    scoped_env_key = str(registry.get("env_key") or env_key or "production")
    scoped_topology_id = str(registry.get("topology_id") or topology_id or "")
    current_active = _runtime_active_for_scope(scoped_project_id, scoped_env_key, scoped_topology_id)
    if op == "start" and current_active.get("active"):
        return jsonify({"ok": False, "error": "topology_run_active", "message": "当前拓扑已有运行中的流程", "run_id": str(current_active.get("run_id") or "")}), 409

    topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    node_ids: List[str] = [str(n.get("id") or "").strip() for n in topo_nodes if isinstance(n, dict) and str(n.get("id") or "").strip()]
    if not node_ids:
        return jsonify({"ok": False, "error": "empty_topology", "message": "当前项目没有可执行节点"}), 400

    run_id = "run-" + uuid.uuid4().hex[:12]
    action_type = "start" if op == "start" else "stop"
    now = _now_iso()
    logs: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    bindings = _load_scope_agent_bindings(scoped_topology_id)
    reg_v2 = _load_agent_registry_v2()
    fresh_sec = max(20, int(policy.get("agent_online_fresh_sec") or 120))
    cluster_status = _fetch_cluster_runtime_status(
        [x for x in reg_v2.values() if isinstance(x, dict) and str(x.get("project_id") or "") in ("", scoped_project_id)]
    )

    for nid in node_ids:
        topo_node = next((x for x in topo_nodes if isinstance(x, dict) and str(x.get("id") or "") == nid), None)
        node = _build_runtime_node_from_topology_node(scoped_project_id, scoped_env_key, topo_node or {}, scoped_topology_id) if topo_node else None
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
        cluster_live = bool(op == "start" and probe_ok and _cluster_state_is_online(cluster_status.get(nid)))
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
                and _is_embedded_cluster_agent(bound_desc or {"node_id": nid})
            )
        ):
            items.append({"node_id": nid, "job_id": "", "trace_id": "", "status": "SUCCESS", "mode": "agent-reuse"})
            msg = f"复用已运行服务: role={desired_role or current_role or '-'}; cluster={'live' if cluster_live else 'runtime'}"
            logs.append({"ts": _now_iso(), "level": "info", "node_id": nid, "message": msg})
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
        "project_id": scoped_project_id,
        "env_key": scoped_env_key,
        "topology_id": scoped_topology_id,
        "topology_name": str(registry.get("name") or ""),
        "op": op,
        "status": "queued",
        "created_at": now,
        "updated_at": _now_iso(),
        "items": items,
        "logs": logs,
    }
    _upsert_runtime_run(run_obj)
    return jsonify({"ok": True, "run_id": run_id, "status": run_obj.get("status"), "project_id": scoped_project_id, "env_key": scoped_env_key, "topology_id": scoped_topology_id, "items": items, "logs": logs})


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
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    env_key = _normalize_env_key(request.args.get("env_key") or "")
    topology_id = str(request.args.get("topology_id") or "").strip()
    ctx = _resolve_topology_context(project_id, env_key, topology_id)
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    info = _runtime_active_for_scope(str(row.get("project_id") or project_id or ""), str(row.get("env_key") or env_key or ""), str(row.get("topology_id") or topology_id or ""))
    return jsonify({"ok": True, "project_id": str(row.get("project_id") or project_id or ""), "env_key": str(row.get("env_key") or env_key or ""), "topology_id": str(row.get("topology_id") or topology_id or ""), "active": bool(info.get("active")), "run_id": str(info.get("run_id") or ""), "status": str(info.get("status") or ""), "reason": str(info.get("reason") or "")})


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
    existing = reg_v2.get(agent_id) if isinstance(reg_v2.get(agent_id), dict) else {}
    stored_node_id = "" if agent_id == CANONICAL_LOCAL_AGENT_ID else node_id
    if agent_id == CANONICAL_LOCAL_AGENT_ID:
        device_id = CANONICAL_LOCAL_DEVICE_ID
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
    _mark_duplicate_runtime_agents(reg_v2, agent_id, node_id)
    _append_realtime_agent_sample(reg_v2[agent_id])
    _save_agent_registry_v2(reg_v2)
    if agent_id == CANONICAL_LOCAL_AGENT_ID:
        _consolidate_runtime_agents_to_canonical(str(payload.get("project_id") or node.get("project_id") or ""))
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
            "registration_origin": "runtime.agent",
            "updated_at": now,
        }
    )
    reg_v2[agent_id]["stale"] = False
    reg_v2[agent_id].pop("stale_reason", None)
    reg_v2[agent_id].pop("superseded_by", None)
    _mark_duplicate_runtime_agents(reg_v2, agent_id, node_id)
    _append_realtime_agent_sample(reg_v2[agent_id])
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
    missing = _ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
    content = _render_local_template("ops_actions_page.html", project_id=project_id)
    return _render_page(content, "动作执行中心")

@bp.route("/admin/ops-platform/topology")
@admin_required("gm_ops")
def ops_platform_topology_page():
    missing = _ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
    env_key = _normalize_env_key(request.args.get("env_key") or "production")
    topology_id = _resolve_ops_topology_id(project_id, env_key, request.args.get("topology_id") or "")
    content = _render_local_template("ops_topology_workbench.html", project_id=project_id, env_key=env_key, topology_id=topology_id)
    return _render_standalone_page(content, "拓扑与配置编排")


@bp.route("/admin/ops-platform/diagnostics")
@admin_required("gm_ops")
def ops_platform_diagnostics_page():
    missing = _ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
    content = _render_local_template("ops_diagnostics_page.html", project_id=project_id)
    return _render_page(content, "节点诊断中心")

@bp.route("/admin/ops-platform/agent-control")
@admin_required("gm_ops")
def ops_platform_agent_control_page():
    missing = _ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
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
    project_id = _resolve_ops_project_id(request.args.get("project_id") or "")
    agent_id = str(request.args.get("agent_id") or "").strip()
    content = _render_local_template("ops_agent_detail_page.html", project_id=project_id, agent_id=agent_id)
    return _render_standalone_page(content, "Agent 详情")


@bp.route("/admin/ops-platform/change-governance")
@admin_required("gm_ops")
def ops_platform_change_governance_page():
    project_id = str(request.args.get("project_id") or "").strip()
    content = _render_local_template("ops_change_governance_page.html", project_id=project_id)
    return _render_page(content, "发布与变更治理")


