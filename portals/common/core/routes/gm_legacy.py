# -*- coding: utf-8 -*-
"""Legacy GM extraction + Ops platform routes."""

from __future__ import annotations

import os
import json
import signal
import subprocess
import uuid
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, render_template_string, request, session

from models.data import (
    approvals_db,
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
    ops_read_key = str(os.getenv("GM_LEGACY_OPS_READ_KEY", "")).strip()
    ops_write_key = str(os.getenv("GM_LEGACY_OPS_WRITE_KEY", "")).strip()
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


@bp.route("/admin/gm-classic")
@admin_required("gm_ops")
def gm_classic_page():
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
        pass
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
  {group:'鍙宸℃',groupId:'observe',value:'health_check',label:'鍋ュ悍妫€鏌?,risk:'low'},
  {group:'鍙宸℃',groupId:'observe',value:'ready_check',label:'灏辩华妫€鏌?,risk:'low'},
  {group:'鍙宸℃',groupId:'observe',value:'status',label:'杩愯蹇収',risk:'low'},
  {group:'鍙宸℃',groupId:'observe',value:'metrics_snapshot',label:'鎸囨爣蹇収',risk:'low'},
  {group:'鍙宸℃',groupId:'observe',value:'log_tail',label:'鏃ュ織灏鹃儴(鍗犱綅)',risk:'low'},

  {group:'鐢熷懡鍛ㄦ湡',groupId:'lifecycle',value:'start',label:'鑺傜偣涓婄嚎',risk:'high'},
  {group:'鐢熷懡鍛ㄦ湡',groupId:'lifecycle',value:'stop',label:'鑺傜偣涓嬬嚎',risk:'high'},
  {group:'鐢熷懡鍛ㄦ湡',groupId:'lifecycle',value:'restart',label:'鑺傜偣閲嶅惎',risk:'high'},
  {group:'鐢熷懡鍛ㄦ湡',groupId:'lifecycle',value:'start_all',label:'鍏ㄩ噺涓婄嚎',risk:'high'},
  {group:'鐢熷懡鍛ㄦ湡',groupId:'lifecycle',value:'stop_all',label:'鍏ㄩ噺涓嬬嚎',risk:'high'},

  {group:'鏁呴殰搴旀€?,groupId:'incident',value:'drain_node',label:'鎽樻祦鑺傜偣',risk:'high'},
  {group:'鏁呴殰搴旀€?,groupId:'incident',value:'isolate_node',label:'闅旂鑺傜偣',risk:'high'},
  {group:'鏁呴殰搴旀€?,groupId:'incident',value:'recover_node',label:'鎭㈠鑺傜偣',risk:'high'},
  {group:'鏁呴殰搴旀€?,groupId:'incident',value:'kick_session',label:'韪細璇?,risk:'high'},
  {group:'鏁呴殰搴旀€?,groupId:'incident',value:'retry_task',label:'閲嶈瘯浠诲姟',risk:'medium'},

  {group:'杩愯惀鎺у埗',groupId:'operation',value:'maintenance',label:'缁存姢鍏憡',risk:'medium'},
  {group:'杩愯惀鎺у埗',groupId:'operation',value:'feature_toggle',label:'鍏ㄥ眬寮€鍏?,risk:'medium'},
  {group:'杩愯惀鎺у埗',groupId:'operation',value:'whitelist',label:'鐧藉悕鍗?,risk:'medium'},
  {group:'杩愯惀鎺у埗',groupId:'operation',value:'mute_chat',label:'绂佽█',risk:'medium'},

  {group:'涓撻」浣滀笟',groupId:'special',value:'smoke_test',label:'閾捐矾鍐掔儫',risk:'medium'},
  {group:'涓撻」浣滀笟',groupId:'special',value:'stress_test',label:'鍘嬪姏娴嬭瘯',risk:'high'},
  {group:'涓撻」浣滀笟',groupId:'special',value:'db_migration',label:'鏁版嵁搴撹縼绉?,risk:'high'}
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
    set_system_config(key, value, value_type="json", description=description, username=str(session.get("user") or "system"))


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


def _default_agent_policy() -> Dict[str, Any]:
    return {
        "mtls_required": False,
        "lease_timeout_sec": 60,
        "max_retries": 2,
        "default_node_concurrency": 1,
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
        for k in ("mtls_required", "lease_timeout_sec", "max_retries", "default_node_concurrency"):
            if k in raw:
                out[k] = raw[k]
        if isinstance(raw.get("rollout"), dict):
            merged_rollout = out["rollout"]
            merged_rollout.update(raw.get("rollout"))
            out["rollout"] = merged_rollout
    return out


def _save_agent_policy(policy: Dict[str, Any]) -> None:
    out = _default_agent_policy()
    if isinstance(policy, dict):
        for k in ("mtls_required", "lease_timeout_sec", "max_retries", "default_node_concurrency"):
            if k in policy:
                out[k] = policy.get(k)
        if isinstance(policy.get("rollout"), dict):
            merged_rollout = out["rollout"]
            merged_rollout.update(policy.get("rollout"))
            out["rollout"] = merged_rollout
    _save_json_config(OPS_AGENT_POLICY_KEY, out, description="Ops Agent 绛栫暐閰嶇疆")


def _agent_token_for_node(node: Dict[str, Any]) -> str:
    return str(node.get("ops_write_key") or node.get("ops_read_key") or "").strip()


def _auth_agent_node(node_id: str, token: str, cert_fp: str = "") -> Optional[Dict[str, Any]]:
    nid = str(node_id or "").strip()
    tok = str(token or "").strip()
    if not nid or not tok:
        return None
    node = _resolve_node(node_id=nid)
    if not node:
        return None
    expected = _agent_token_for_node(node)
    if not expected or expected != tok:
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
    return {
        "agent_id": str(item.get("agent_id") or ""),
        "device_id": str(item.get("device_id") or ""),
        "host_name": str(item.get("host_name") or item.get("hostname") or ""),
        "node_id": str(item.get("node_id") or ""),
        "project_id": str(item.get("project_id") or ""),
        "status": str(item.get("status") or "UNKNOWN").upper(),
        "version": str(item.get("version") or ""),
        "last_seen": str(item.get("last_seen") or ""),
        "display_name": str(item.get("display_name") or item.get("agent_id") or ""),
        "port": int(item.get("port") or 0),
        "desc": str(item.get("desc") or ""),
        "run_state": str(item.get("run_state") or ""),
        "capabilities": item.get("capabilities") if isinstance(item.get("capabilities"), list) else [],
        "transport": {
            "mode": str(transport.get("mode") or "remote").lower(),
            "local_endpoint": str(local_bus.get("endpoint") or transport.get("local_endpoint") or ""),
            "local_enabled": bool(local_bus.get("enabled", True)),
            "local_auth_mode": str(local_bus.get("auth_mode") or "token"),
            "degraded": bool(transport.get("degraded", False)),
            "degrade_reason": str(transport.get("degrade_reason") or ""),
        },
        "updated_at": str(item.get("updated_at") or ""),
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
        overview = _ops_gateway.build_node_overview(item, actor=operator)
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

    return {
        "ok": len(missing) == 0,
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    return jsonify(_build_overview(project_id=project_id))


@bp.route("/api/ops-platform/deployment-catalog")
@admin_required("gm_ops")
def ops_platform_deployment_catalog():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403

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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
    reg_v2 = _load_agent_registry_v2()
    agents: List[Dict[str, Any]] = [_normalize_agent_descriptor_v2(x) for x in reg_v2.values() if isinstance(x, dict)]
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
        st = str(a.get("status") or "").upper()
        if st in ("ONLINE", "READY", "RUNNING"):
            online += 1
    metrics = {
        "agents_total": len(agents),
        "agents_online": online,
        "jobs_pending": queue.get("PENDING") or 0,
        "jobs_running": queue.get("RUNNING") or 0,
    }
    return jsonify({"ok": True, "metrics": metrics, "queue": queue, "agents": agents, "policy": _load_agent_policy()})


@bp.route("/api/ops-platform/agents")
@admin_required("gm_ops")
def ops_platform_agents_list():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    status = str(request.args.get("status") or "").strip().upper()
    device_id = str(request.args.get("device_id") or "").strip()
    bound = str(request.args.get("bound") or "").strip().lower()
    bindings = _load_node_agent_bindings()
    rows = _agents_v2_for_project(project_id)
    bound_agent_ids = set(str(v or "") for v in bindings.values() if str(v or "").strip())
    out: List[Dict[str, Any]] = []
    for item in rows:
        if status and str(item.get("status") or "").upper() != status:
            continue
        if device_id and str(item.get("device_id") or "") != device_id:
            continue
        is_bound = str(item.get("agent_id") or "") in bound_agent_ids
        if bound == "yes" and not is_bound:
            continue
        if bound == "no" and is_bound:
            continue
        obj = dict(item)
        obj["is_bound"] = is_bound
        out.append(obj)
    return jsonify({"ok": True, "count": len(out), "agents": out, "bindings": bindings})


@bp.route("/api/ops-platform/agents/devices")
@admin_required("gm_ops")
def ops_platform_agents_devices():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    rows = _agents_v2_for_project(project_id)
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        did = str(item.get("device_id") or "unknown-device")
        cur = grouped.get(did) if isinstance(grouped.get(did), dict) else {"device_id": did, "project_id": project_id, "agents": []}
        cur["agents"].append(item)
        grouped[did] = cur
    out = list(grouped.values())
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
    if not hit:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    if "port" in payload:
        try:
            port_val = int(payload.get("port") or 0)
            if port_val < 0 or port_val > 65535:
                return jsonify({"ok": False, "error": "OPS_AGENT_PORT_INVALID", "error_code": "OPS_AGENT_PORT_INVALID"}), 400
            hit["port"] = port_val
        except Exception:
            return jsonify({"ok": False, "error": "OPS_AGENT_PORT_INVALID", "error_code": "OPS_AGENT_PORT_INVALID"}), 400
    for k in ("display_name", "desc", "run_state", "status"):
        if k in payload:
            hit[k] = str(payload.get(k) or "")
    hit["updated_at"] = _now_iso()
    reg[agent_id] = _normalize_agent_descriptor_v2(hit)
    _save_agent_registry_v2(reg)
    log_audit("ops_platform_agents_upsert", f"agent_id={agent_id}")
    return jsonify({"ok": True, "agent": reg[agent_id]})


@bp.route("/api/ops-platform/topology/node/bindings")
@admin_required("gm_ops")
def ops_platform_node_bindings():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    project_id = str(request.args.get("project_id") or "").strip()
    bindings = _load_node_agent_bindings()
    rows = _load_nodes()
    valid_nodes = set(str(x.get("id") or "") for x in rows if isinstance(x, dict))
    out: Dict[str, str] = {}
    for nid, aid in bindings.items():
        n = str(nid or "").strip()
        a = str(aid or "").strip()
        if not n or not a or n not in valid_nodes:
            continue
        out[n] = a
    return jsonify({"ok": True, "project_id": project_id, "bindings": out})


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
    bindings = _load_node_agent_bindings()
    if agent_id:
        bindings[node_id] = agent_id
    else:
        bindings.pop(node_id, None)
    _save_node_agent_bindings(bindings)
    log_audit("ops_platform_bind_node_agent", f"node={node_id}; agent={agent_id}")
    return jsonify({"ok": True, "node_id": node_id, "agent_id": agent_id, "bindings": bindings})


@bp.route("/api/ops-platform/change-governance/summary")
@admin_required("gm_ops")
def ops_platform_change_governance_summary():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
    rows = [
        {"groupId": "observe", "group": "Observe", "value": "health_check", "label": "Health Check", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "ready_check", "label": "Ready Check", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "status", "label": "Runtime Snapshot", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "metrics_snapshot", "label": "Metrics Snapshot", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "log_tail", "label": "Log Tail", "risk": "low"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "start", "label": "Start Node", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "stop", "label": "Stop Node", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "restart", "label": "Restart Node", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "start_all", "label": "Start All", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "stop_all", "label": "Stop All", "risk": "high"},
        {"groupId": "incident", "group": "Incident", "value": "drain_node", "label": "Drain Node", "risk": "high"},
        {"groupId": "incident", "group": "Incident", "value": "isolate_node", "label": "Isolate Node", "risk": "high"},
        {"groupId": "incident", "group": "Incident", "value": "recover_node", "label": "Recover Node", "risk": "high"},
        {"groupId": "incident", "group": "Incident", "value": "kick_session", "label": "Kick Session", "risk": "high"},
        {"groupId": "incident", "group": "Incident", "value": "retry_task", "label": "Retry Task", "risk": "medium"},
        {"groupId": "operation", "group": "Operation", "value": "maintenance", "label": "Maintenance Notice", "risk": "medium"},
        {"groupId": "operation", "group": "Operation", "value": "feature_toggle", "label": "Feature Toggle", "risk": "medium"},
        {"groupId": "operation", "group": "Operation", "value": "whitelist", "label": "Whitelist", "risk": "medium"},
        {"groupId": "operation", "group": "Operation", "value": "mute_chat", "label": "Mute Chat", "risk": "medium"},
        {"groupId": "special", "group": "Special Job", "value": "smoke_test", "label": "Smoke Test", "risk": "medium"},
        {"groupId": "special", "group": "Special Job", "value": "stress_test", "label": "Stress Test", "risk": "high"},
        {"groupId": "special", "group": "Special Job", "value": "db_migration", "label": "DB Migration", "risk": "high"},
    ]
    return jsonify({"ok": True, "data": rows})


@bp.route("/api/ops-platform/topology")
@admin_required("gm_ops")
def ops_platform_topology():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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


@bp.route("/api/ops-platform/topology/edge/upsert", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_edge_upsert():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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
    valid = set([str(x.get("id") or "") for x in topo.get("nodes") or [] if isinstance(x, dict)])
    if frm not in valid or to not in valid:
        return jsonify({"ok": False, "error": "node not found"}), 404
    from_node = _resolve_node(node_id=frm) or {}
    to_node = _resolve_node(node_id=to) or {}
    if not _can_link_nodes(from_node, to_node):
        return jsonify({"ok": False, "error": "invalid_edge_by_role", "message": "Node role relationship is not allowed by preset rules"}), 400
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
    for ex in topo.get("edges") or []:
        if not isinstance(ex, dict):
            continue
        if str(ex.get("from") or "") == frm and str(ex.get("to") or "") == to and str(ex.get("from_port") or "out-1") == from_port and str(ex.get("to_port") or "in-1") == to_port:
            return jsonify({"ok": False, "error": "edge_duplicate", "error_code": "OPS_EDGE_DUPLICATE", "message": "Duplicate edge"}), 409
    incoming_count = 0
    for ex in topo.get("edges") or []:
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
    for ex in topo.get("edges") or []:
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
    for edge in topo.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("from") or "") == frm and str(edge.get("to") or "") == to and str(edge.get("from_port") or "out-1") == from_port and str(edge.get("to_port") or "in-1") == to_port:
            edge["type"] = etype
            edge["note"] = note
            updated = True
            break
    if not updated:
        (topo.get("edges") or []).append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": frm, "to": to, "from_port": from_port, "to_port": to_port, "type": etype, "note": note})

    saved = _save_topology(topo)
    log_audit("ops_platform_topology_edge_upsert", f"{frm}->{to}; type={etype}")
    return jsonify({"ok": True, "message": "Edge updated", "topology": saved})


@bp.route("/api/ops-platform/topology/edge/delete", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_edge_delete():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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

    topo = _load_topology(rows)
    if not any(isinstance(n, dict) and str(n.get("id") or "") == new_id for n in (topo.get("nodes") or [])):
        default_pos = _default_topology_for_nodes(rows).get("nodes") or []
        pos = None
        for n in default_pos:
            if isinstance(n, dict) and str(n.get("id") or "") == new_id:
                pos = n
                break
        (topo.get("nodes") or []).append(
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
    for exist in (topo.get("nodes") or []):
        if not isinstance(exist, dict):
            continue
        eid = str(exist.get("id") or "")
        if not eid or eid == new_id:
            continue
        src = _resolve_node(node_id=eid) or {}
        if not src:
            continue
        if _can_link_nodes(src, node):
            exists = any(isinstance(e, dict) and str(e.get("from") or "") == eid and str(e.get("to") or "") == new_id for e in (topo.get("edges") or []))
            if not exists:
                (topo.get("edges") or []).append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": eid, "to": new_id, "from_port": "out-1", "to_port": "in-1", "type": "depends_on", "note": "preset-auto"})
        if _can_link_nodes(node, src):
            exists = any(isinstance(e, dict) and str(e.get("from") or "") == new_id and str(e.get("to") or "") == eid for e in (topo.get("edges") or []))
            if not exists:
                (topo.get("edges") or []).append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": new_id, "to": eid, "from_port": "out-1", "to_port": "in-1", "type": "depends_on", "note": "preset-auto"})
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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
            issues.append("缂哄皯 server_id")
        if not str(n.get("ops_base_url") or ""):
            issues.append("缂哄皯 ops_base_url")
        if not str(n.get("owner") or ""):
            issues.append("缂哄皯 owner")
        if not str(n.get("description") or ""):
            issues.append("缂哄皯鑺傜偣璇存槑")
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    path_nodes = payload.get("path_nodes") if isinstance(payload.get("path_nodes"), list) else []
    if len(path_nodes) < 2:
        return jsonify({"ok": False, "error": "invalid_path", "message": "鑷冲皯閫夋嫨涓や釜鑺傜偣"}), 400
    result_steps: List[Dict[str, Any]] = []
    success = True
    for nid in path_nodes:
        node = _resolve_node(node_id=str(nid or "").strip())
        if not node:
            result_steps.append({"node_id": nid, "ok": False, "message": "node not found"})
            success = False
            continue
        smoke = _run_flow_step(node, {"action_type": "health_check", "target": str(node.get("server_id") or ""), "ticket_id": "OPS-SMOKE", "reason": "flow smoke"})
        ok = bool(smoke.get("success"))
        msg = str(smoke.get("message") or "")
        degraded = False
        if (not ok) and (
            "Ops service unavailable" in msg
            or "missing ops_base_url" in msg
            or "Failed to establish a new connection" in msg
        ):
            ok = True
            degraded = True
            msg = "下游 Ops 服务不可达，冒烟步骤降级为平台模拟通过"
            smoke = {
                **(smoke if isinstance(smoke, dict) else {}),
                "success": True,
                "status": 200,
                "degraded": True,
                "result_code": "OPS_DOWNSTREAM_UNAVAILABLE",
                "result_message": msg,
            }
        result_steps.append({"node_id": node.get("id"), "ok": ok, "degraded": degraded, "message": msg, "result": smoke})
        if not ok:
            success = False
    flow_id = "flow-" + uuid.uuid4().hex[:12]
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if success else "critical"), "status": ("resolved" if success else "open"), "title": "娴佺▼鍐掔儫娴嬭瘯", "message": f"flow={flow_id}; nodes={len(path_nodes)}; success={success}"})
    _append_bounded(OPS_FLOW_EXEC_KEY, {"flow_id": flow_id, "time": _now_iso(), "type": "smoke", "ok": success, "steps": result_steps}, limit=120, description="娴佺▼鎵ц璁板綍")
    return jsonify({"ok": success, "flow_id": flow_id, "steps": result_steps}), (200 if success else 502)


@bp.route("/api/ops-platform/stress-test", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_stress_test():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err
    qps = int(payload.get("qps") or 300)
    duration_sec = int(payload.get("duration_sec") or 180)
    reason = str(payload.get("reason") or "stress test").strip()
    result = _ops_gateway.execute_platform_action(
        node,
        action_type="stress_test",
        target=str(node.get("server_id") or ""),
        payload={"qps": qps, "duration_sec": duration_sec},
        actor=str(session.get("user") or "intranet-ops"),
        reason=reason,
        ticket_id="OPS-STRESS",
        dry_run=False,
    )
    ok = bool(result.get("success"))
    msg = str(result.get("message") or "")
    degraded = False
    if (not ok) and (
        "Ops service unavailable" in msg
        or "missing ops_base_url" in msg
        or "Failed to establish a new connection" in msg
    ):
        ok = True
        degraded = True
        msg = "下游 Ops 服务不可达，压力测试降级为平台模拟提交"
        result = {
            **(result if isinstance(result, dict) else {}),
            "success": True,
            "status": 200,
            "degraded": True,
            "result_code": "OPS_DOWNSTREAM_UNAVAILABLE",
            "result_message": msg,
        }
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if ok else "warning"), "status": ("resolved" if ok else "open"), "title": "鍘嬪姏娴嬭瘯瑙﹀彂", "message": f"node={node.get('id')}; qps={qps}; duration={duration_sec}s; ok={ok}; degraded={degraded}"})
    return jsonify({"ok": ok, "message": msg, "degraded": degraded, "result": result}), (200 if ok else 502)


@bp.route("/api/ops-platform/db-migration", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_db_migration():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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
        _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": "info", "status": "resolved", "title": "DB Migration", "message": f"node={node.get('id')}; direction={direction}; version={version}; mode=native"})
        log_audit("ops_platform_db_migration", f"node={node.get('id')}; direction={direction}; version={version}; mode=native")
        return jsonify({"ok": True, "message": native.get("message") or "Migration accepted", "result": native})

    if not cmd:
        return jsonify({"ok": False, "error": "native_failed_no_command", "message": f"鍘熺敓杩佺Щ鑳藉姏澶辫触涓旀湭鎻愪緵鏈湴鍛戒护: {native.get('message') or 'unknown'}"}), 502

    code = subprocess.call(cmd, shell=True)
    ok = code == 0
    _set_daemon_state(str(node.get("id") or ""), {"last_action": f"db_migration_{direction}", "last_error": ("" if ok else f"exit_code={code}")})
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if ok else "critical"), "status": ("resolved" if ok else "open"), "title": "DB Migration", "message": f"node={node.get('id')}; direction={direction}; version={version}; mode=fallback; code={code}"})
    log_audit("ops_platform_db_migration", f"node={node.get('id')}; direction={direction}; version={version}; mode=fallback; code={code}")
    return jsonify({"ok": ok, "message": ("Migration success (fallback)" if ok else "Migration failed (fallback)"), "exit_code": code, "native_error": native.get("message")}), (200 if ok else 502)


@bp.route("/api/ops-platform/actions/validate", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_actions_validate():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err

    validation = _validate_ops_request(payload, node)
    if not validation.get("ok"):
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "message": "缂哄皯蹇呭～瀛楁: " + ", ".join(validation.get("missing") or []),
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err

    validation = _validate_ops_request(payload, node)
    if not validation.get("ok"):
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "message": "缂哄皯蹇呭～瀛楁: " + ", ".join(validation.get("missing") or []),
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
    item = _find_trace(trace_id)
    if not item:
        return jsonify({"ok": False, "error": "trace_not_found"}), 404
    return jsonify({"ok": True, "trace": item})


@bp.route("/api/ops-platform/runtime/flow-control", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_runtime_flow_control():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    op = str(payload.get("op") or "").strip().lower()
    if op not in ("start", "stop"):
        return jsonify({"ok": False, "error": "invalid_op", "message": "op must be start or stop"}), 400
    project_id = str(payload.get("project_id") or "").strip()
    actor = str(session.get("user") or "admin")

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

    for nid in node_ids:
        node = all_nodes_map.get(nid) or _resolve_node(node_id=nid)
        if not node:
            logs.append({"ts": _now_iso(), "level": "error", "node_id": nid, "message": "节点不存在，已跳过"})
            continue
        bound_agent = str(bindings.get(nid) or "")
        bound_desc = reg_v2.get(bound_agent) if bound_agent else None
        online = bool(bound_desc and str(bound_desc.get("status") or "").upper() == "ONLINE")
        fresh = False
        if bound_desc and bound_desc.get("last_seen"):
            try:
                hb = datetime.fromisoformat(str(bound_desc.get("last_seen")).replace("Z", ""))
                fresh = (datetime.utcnow() - hb).total_seconds() <= 20
            except Exception:
                fresh = False
        online = online and fresh
        use_agent_mode = online
        req = {
            "node_id": nid,
            "action_type": action_type,
            "target": nid,
            "ticket_id": "OPS-RUN-" + run_id[-6:],
            "reason": "拓扑运行模式一键" + ("启动" if op == "start" else "停止"),
            "approver": actor,
            "run_mode": "agent" if use_agent_mode else "direct",
            "via_agent": bool(use_agent_mode),
            "payload": {"run_mode": "agent" if use_agent_mode else "direct"},
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
            logs.append({"ts": _now_iso(), "level": "warn", "node_id": nid, "message": "未命中在线Agent，已走直连执行"})

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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
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
    return jsonify({
        "ok": True,
        "run_id": run_obj.get("run_id"),
        "status": run_obj.get("status"),
        "done": done,
        "total": total,
        "failed": fail,
        "items": items,
        "logs": run_logs[-120:],
    })


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
            "desc": str(payload.get("desc") or ""),
            "run_state": str(payload.get("run_state") or "RUNNING"),
            "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else [],
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
            "desc": str(payload.get("desc") or prev.get("desc") or ""),
            "run_state": str(payload.get("run_state") or prev.get("run_state") or ""),
            "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else prev.get("capabilities") or [],
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鏌ョ湅鏉冮檺 (ops.platform.view)"}), 403
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
        return jsonify({"ok": False, "error": "forbidden", "message": "缂哄皯杩愮淮鎵ц鏉冮檺 (ops.platform.execute)"}), 403
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
        return jsonify({"ok": False, "error": "validation_failed", "missing": validation.get("missing"), "message": "缂哄皯蹇呭～瀛楁"}), 400
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
    return _render_page(content, "Agent 控制面")


@bp.route("/admin/ops-platform/agent-device-local")
@admin_required("gm_ops")
def ops_platform_agent_device_local_page():
    project_id = str(request.args.get("project_id") or "").strip()
    device_id = str(request.args.get("device_id") or "").strip()
    content = _render_local_template("ops_agent_device_local_page.html", project_id=project_id, device_id=device_id)
    return _render_page(content, "设备 Agent 组")


@bp.route("/admin/ops-platform/change-governance")
@admin_required("gm_ops")
def ops_platform_change_governance_page():
    project_id = str(request.args.get("project_id") or "").strip()
    content = _render_local_template("ops_change_governance_page.html", project_id=project_id)
    return _render_page(content, "发布与变更治理")

