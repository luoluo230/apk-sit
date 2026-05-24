# -*- coding: utf-8 -*-
"""Legacy GM extraction + Ops platform routes."""

from __future__ import annotations

import os
import signal
import subprocess
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, render_template_string, request, session

from models.data import (
    approvals_db,
    create_approval,
    get_approved_approval,
    get_system_config,
    log_audit,
    set_system_config,
)
from services.authz import admin_required, can_access_module, has_scope
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
    return {
        "id": node_id,
        "name": str(payload.get("name") or node_id).strip(),
        "base_url": str(payload.get("base_url") or "").strip(),
        "ops_base_url": str(payload.get("ops_base_url") or "").strip(),
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
        can_access_module("gm_ops")
        or has_scope("ops.platform.view")
        or has_scope("gm.ops.execute")
        or has_scope("gm.audit.view")
    )


def _allow_ops_execute() -> bool:
    return bool(
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
        <h2 class="text-2xl font-semibold">经典GM模块（独立剥离）</h2>
        <p class="text-sm text-cyan-100/90 mt-1">通过内网桥接层接入 legacy GmWebServer，统一留痕并与项目上下文对齐。</p>
      </div>
      <div class="text-xs rounded-full px-3 py-1 border border-white/30 bg-white/15">Legacy Bridge v1</div>
    </div>
  </section>

  <section class="panel p-4 grid grid-cols-1 xl:grid-cols-12 gap-4 items-end">
    <div class="xl:col-span-4"><label class="text-xs text-slate-500">节点</label><select id="gmNode" class="w-full border rounded-lg px-3 py-2"></select></div>
    <div class="xl:col-span-3"><label class="text-xs text-slate-500">项目ID</label><input id="gmProjectId" class="w-full border rounded-lg px-3 py-2" placeholder="可选"></div>
    <div class="xl:col-span-2"><label class="text-xs text-slate-500">环境</label><input id="gmEnv" class="w-full border rounded-lg px-3 py-2" placeholder="dev/test/prod"></div>
    <div class="xl:col-span-2"><label class="text-xs text-slate-500">渠道</label><input id="gmChannel" class="w-full border rounded-lg px-3 py-2" placeholder="1001"></div>
    <div class="xl:col-span-1"><button class="w-full btn btn-indigo" onclick="reloadNodes()">刷新</button></div>
  </section>

  <section class="grid grid-cols-1 xl:grid-cols-2 gap-4">
    <div class="panel p-4 space-y-3">
      <h3 class="font-semibold text-slate-900">玩家与资源</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <input id="pKeyword" class="border rounded-lg px-3 py-2" placeholder="玩家关键词/playerId">
        <button class="btn btn-teal" onclick="gmAction('search_player',{keyword:val('pKeyword')})">玩家检索</button>
        <input id="pIdCurrency" class="border rounded-lg px-3 py-2" placeholder="playerId">
        <div class="grid grid-cols-3 gap-2"><input id="pDia" class="border rounded-lg px-2 py-2" placeholder="钻石"><input id="pGold" class="border rounded-lg px-2 py-2" placeholder="金币"><input id="pSta" class="border rounded-lg px-2 py-2" placeholder="体力"></div>
        <textarea id="pReasonCurrency" class="border rounded-lg px-3 py-2 md:col-span-2" rows="2" placeholder="原因"></textarea>
        <button class="btn btn-amber" onclick="gmAction('adjust_currency',{playerId:val('pIdCurrency'),diamonds:val('pDia'),gold:val('pGold'),stamina:val('pSta'),reason:val('pReasonCurrency')})">调整货币</button>
        <input id="pIdItem" class="border rounded-lg px-3 py-2" placeholder="playerId">
        <div class="grid grid-cols-2 gap-2"><input id="itemId" class="border rounded-lg px-2 py-2" placeholder="itemId"><input id="itemDelta" class="border rounded-lg px-2 py-2" placeholder="delta +/-"></div>
        <textarea id="pReasonItem" class="border rounded-lg px-3 py-2 md:col-span-2" rows="2" placeholder="原因"></textarea>
        <button class="btn btn-amber" onclick="gmAction('adjust_item',{playerId:val('pIdItem'),itemId:val('itemId'),delta:val('itemDelta'),reason:val('pReasonItem')})">调整物品</button>
      </div>
    </div>

    <div class="panel p-4 space-y-3">
      <h3 class="font-semibold text-slate-900">邮件与运营动作</h3>
      <div class="space-y-2">
        <input id="mailPid" class="w-full border rounded-lg px-3 py-2" placeholder="playerId">
        <input id="mailTitle" class="w-full border rounded-lg px-3 py-2" placeholder="邮件标题">
        <textarea id="mailBody" class="w-full border rounded-lg px-3 py-2" rows="2" placeholder="邮件正文"></textarea>
        <input id="mailRewards" class="w-full border rounded-lg px-3 py-2" placeholder='奖励JSON，如 [{"itemId":"gold","count":100}]'>
        <input id="mailReason" class="w-full border rounded-lg px-3 py-2" placeholder="原因">
        <div class="grid grid-cols-2 gap-2">
          <button class="btn btn-indigo" onclick="gmAction('send_mail',{playerId:val('mailPid'),title:val('mailTitle'),body:val('mailBody'),rewards:val('mailRewards'),reason:val('mailReason')})">发送单人邮件</button>
          <button class="btn btn-rose" onclick="gmAction('send_broadcast',{title:val('mailTitle'),body:val('mailBody'),rewards:val('mailRewards'),reason:val('mailReason')})">全服广播邮件</button>
        </div>
      </div>
    </div>
  </section>

  <section class="panel p-4">
    <div class="flex items-center justify-between mb-2"><h3 class="font-semibold">执行结果</h3><span id="gmResultSummary" class="text-xs text-slate-500">等待执行</span></div>
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
  document.getElementById('gmResultSummary').textContent = ok ? '执行成功' : '执行失败';
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
    return _render_page(content, "经典GM模块")


@bp.route("/admin/ops-platform")
@admin_required("gm_ops")
def ops_platform_page():
    project_id = str(request.args.get("project_id") or "").strip()
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
        <h2 class="text-2xl font-semibold">运维平台（拓扑运营版）</h2>
        <p class="text-sm text-blue-100 mt-1">可视化节点关系 + 分布式角色治理 + 审批闭环执行，一眼定位异常并直达操作。</p>
      </div>
      <div class="text-xs rounded-full px-3 py-1 border border-white/30 bg-white/10">Ops Platform v3 • Topology Native</div>
    </div>
  </section>

  <section class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
    <div class="kpi"><div class="label">SLA%</div><div class="value" id="kpiSla">-</div></div>
    <div class="kpi"><div class="label">节点总数</div><div class="value" id="kpiNodes">-</div></div>
    <div class="kpi"><div class="label">健康节点</div><div class="value" id="kpiHealthy">-</div></div>
    <div class="kpi"><div class="label">退化节点</div><div class="value" id="kpiDegraded">-</div></div>
    <div class="kpi"><div class="label">离线节点</div><div class="value" id="kpiOffline">-</div></div>
    <div class="kpi"><div class="label">告警总数</div><div class="value" id="kpiAlerts">-</div></div>
  </section>

  <section class="panel p-4 space-y-3">
    <div class="flex items-center justify-between"><h3 class="section-title">预制节点库（服务器类型模板）</h3><span class="text-xs text-slate-500">数据库 / Redis / 压力 / 业务 / 网关等</span></div>
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-2">
      <div><label class="text-xs text-slate-500">模板</label><select id="presetSelect" class="w-full border rounded-lg px-3 py-2"></select></div>
      <div><label class="text-xs text-slate-500">节点名称</label><input id="presetNodeName" class="w-full border rounded-lg px-3 py-2" placeholder="例如 pressure-cn-1"></div>
      <div><label class="text-xs text-slate-500">serverId</label><input id="presetServerId" class="w-full border rounded-lg px-3 py-2" placeholder="game-cn-1"></div>
      <div><label class="text-xs text-slate-500">负责人</label><input id="presetOwner" class="w-full border rounded-lg px-3 py-2" placeholder="ops-admin"></div>
      <div><label class="text-xs text-slate-500">环境</label><input id="presetEnv" class="w-full border rounded-lg px-3 py-2" placeholder="prod"></div>
      <div><label class="text-xs text-slate-500">渠道</label><input id="presetChannel" class="w-full border rounded-lg px-3 py-2" placeholder="1001"></div>
      <div class="xl:col-span-2"><label class="text-xs text-slate-500">备注</label><input id="presetDesc" class="w-full border rounded-lg px-3 py-2" placeholder="节点用途说明"></div>
      <div><label class="text-xs text-slate-500">Daemon Start 命令(可选)</label><input id="presetStartCmd" class="w-full border rounded-lg px-3 py-2 mono" placeholder="例如 docker start redis-a"></div>
      <div><label class="text-xs text-slate-500">Daemon Stop 命令(可选)</label><input id="presetStopCmd" class="w-full border rounded-lg px-3 py-2 mono" placeholder="例如 docker stop redis-a"></div>
      <div class="flex items-end"><button class="btn btn-emerald w-full" onclick="addNodeFromPreset()">添加节点</button></div>
      <div class="flex items-end"><button class="btn btn-slate w-full" onclick="loadNodePresets()">刷新模板</button></div>
    </div>
    <div id="presetHint" class="text-xs text-slate-500">选择模板后可快速落节点，并自动注入上下游规则。</div>
  </section>

  <section class="panel p-4 space-y-3">
    <div class="flex items-center justify-between"><h3 class="section-title">节点接入体检与预警</h3><button class="btn btn-amber" onclick="loadOnboarding()">刷新体检</button></div>
    <div class="overflow-auto max-h-[260px] border border-slate-200 rounded-xl">
      <table class="min-w-full text-sm">
        <thead class="bg-slate-50 sticky top-0"><tr><th class="px-2 py-2 text-left">节点</th><th class="px-2 py-2 text-left">角色</th><th class="px-2 py-2 text-left">状态</th><th class="px-2 py-2 text-left">接入检查</th><th class="px-2 py-2 text-left">告警级别</th></tr></thead>
        <tbody id="onboardBody"><tr><td class="px-2 py-3 text-slate-400" colspan="5">暂无数据</td></tr></tbody>
      </table>
    </div>
    <div id="onboardSummary" class="text-xs text-slate-500">等待体检</div>
  </section>

  <section class="grid grid-cols-1 xl:grid-cols-12 gap-4">
    <div class="xl:col-span-8 space-y-4">
      <section class="panel p-4 space-y-3">
        <div class="flex items-center justify-between gap-2 flex-wrap">
          <h3 class="section-title">节点拓扑关系图</h3>
          <div class="flex items-center gap-2">
            <input id="opsProjectFilter" class="border rounded-lg px-3 py-2 text-sm" placeholder="project_id 过滤">
            <button class="btn btn-indigo" onclick="loadOverviewAndTopology()">刷新拓扑</button>
          </div>
        </div>
        <div class="topology-wrap" id="topologyWrap">
          <svg class="topology-svg" id="topologySvg"></svg>
          <div id="topologyNodeLayer"></div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-slate-500">
          <div>支持操作：单击节点切换上下文、拖动节点布局、编辑节点属性、建立/删除关系线。</div>
          <div>状态色：绿色在线 / 橙色退化 / 红色离线 / 紫色维护 / 灰色未知。</div>
        </div>
      </section>

      <section class="panel p-4 space-y-3">
        <div class="flex items-center justify-between"><h3 class="section-title">告警与事件时间线</h3><button class="btn btn-slate" onclick="loadEvents()">刷新事件</button></div>
        <div id="eventList" class="space-y-2 max-h-[280px] overflow-auto"></div>
      </section>
    </div>

    <div class="xl:col-span-4 space-y-4">
      <section class="panel p-4 space-y-3">
        <h3 class="section-title">节点详情与编辑</h3>
        <div class="grid grid-cols-1 gap-2">
          <div><label class="text-xs text-slate-500">节点</label><input id="topoNodeId" class="w-full border rounded-lg px-3 py-2 mono" readonly></div>
          <div><label class="text-xs text-slate-500">节点说明</label><textarea id="topoNodeDesc" rows="2" class="w-full border rounded-lg px-3 py-2" placeholder="节点用途说明"></textarea></div>
          <div><label class="text-xs text-slate-500">节点角色</label><select id="topoNodeRole" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">业务状态标签</label><select id="topoNodeBizStatus" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">负责人</label><input id="topoNodeOwner" class="w-full border rounded-lg px-3 py-2" placeholder="owner"></div>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <button class="btn btn-cyan" onclick="focusNodeOnMap()">定位节点</button>
          <button class="btn btn-emerald" onclick="saveNodeMeta()">保存节点</button>
        </div>
      </section>

      <section class="panel p-4 space-y-3">
        <h3 class="section-title">关系连线管理</h3>
        <div class="grid grid-cols-1 gap-2">
          <div><label class="text-xs text-slate-500">起点节点</label><select id="edgeFrom" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">终点节点</label><select id="edgeTo" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">关系类型</label><select id="edgeType" class="w-full border rounded-lg px-3 py-2"></select></div>
          <div><label class="text-xs text-slate-500">关系说明</label><input id="edgeNote" class="w-full border rounded-lg px-3 py-2" placeholder="例如 网关 -> 业务"></div>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <button class="btn btn-indigo" onclick="upsertEdge()">建立/更新连线</button>
          <button class="btn btn-rose" onclick="removeSelectedEdge()">删除选中连线</button>
        </div>
        <div id="edgeHint" class="text-xs text-slate-500">点击拓扑中的线条可选中后删除。</div>
      </section>
    </div>
  </section>

  <section class="panel p-4 space-y-3">
    <div class="flex items-center justify-between"><h3 class="section-title">运维动作中心（商业级分类）</h3><span class="text-xs text-slate-500">闭环：预检 → 审批 → 执行 → 回读</span></div>
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
      <div><label class="text-xs text-slate-500">节点（一键切换）</label><select id="opNodeId" class="w-full border rounded-lg px-3 py-2" onchange="syncNodeContextFromSelect()"></select></div>
      <div><label class="text-xs text-slate-500">动作分类</label><select id="opActionGroup" class="w-full border rounded-lg px-3 py-2" onchange="renderActionOptions()"></select></div>
      <div><label class="text-xs text-slate-500">动作</label><select id="opActionType" class="w-full border rounded-lg px-3 py-2" onchange="syncRiskHint()"></select></div>
      <div><label class="text-xs text-slate-500">目标 (serverId / playerId / taskId / sessionId / key)</label><input id="opTarget" class="w-full border rounded-lg px-3 py-2" placeholder="例如 game-cn-1"></div>
      <div><label class="text-xs text-slate-500">工单号 ticketId</label><input id="opTicket" class="w-full border rounded-lg px-3 py-2" placeholder="OPS-2026-0001"></div>
      <div><label class="text-xs text-slate-500">变更原因 reason</label><input id="opReason" class="w-full border rounded-lg px-3 py-2" placeholder="填写变更原因"></div>
      <div><label class="text-xs text-slate-500">审批人 approver（高危必填）</label><input id="opApprover" class="w-full border rounded-lg px-3 py-2" placeholder="审批责任人账号"></div>
      <div class="flex items-end"><span id="opRiskHint" class="text-xs px-2 py-1 rounded-full bg-slate-100 text-slate-700">风险级别：-</span></div>
      <div class="md:col-span-2 xl:col-span-4"><label class="text-xs text-slate-500">扩展 payload JSON</label><textarea id="opPayload" rows="3" class="w-full border rounded-lg px-3 py-2 mono" placeholder='{"enabled":true,"message":"maintenance notice"}'></textarea></div>
      <div class="md:col-span-2 xl:col-span-4 flex items-center gap-3">
        <label class="inline-flex items-center gap-2 text-sm"><input id="opDryRun" type="checkbox">Dry-run</label>
        <span id="opValidateHint" class="text-xs text-slate-500">尚未预检</span>
        <span id="opGroupHint" class="action-group-tag">分类：-</span>
      </div>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
      <button class="btn btn-cyan" onclick="validateAction()">预检</button>
      <button class="btn btn-indigo" onclick="createApproval()">创建审批单</button>
      <button class="btn btn-emerald" onclick="executeAction()">执行动作</button>
      <button class="btn btn-rose" onclick="quickRollbackHint()">回滚引导</button>
    </div>
  </section>

  <section class="panel p-4 space-y-4">
    <div class="flex items-center justify-between"><h3 class="section-title">守护进程与专项流程工具</h3><span class="text-xs text-slate-500">节点守护 / 一键冒烟 / 压测 / 迁移</span></div>
    <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">
      <div class="xl:col-span-4 space-y-2">
        <h4 class="text-sm font-semibold text-slate-800">守护进程控制</h4>
        <div><label class="text-xs text-slate-500">节点</label><select id="daemonNodeId" class="w-full border rounded-lg px-3 py-2"></select></div>
        <div><label class="text-xs text-slate-500">工单号</label><input id="daemonTicketId" class="w-full border rounded-lg px-3 py-2" placeholder="OPS-DAEMON-0001"></div>
        <div><label class="text-xs text-slate-500">操作原因</label><input id="daemonReason" class="w-full border rounded-lg px-3 py-2" placeholder="例如 维护窗口上线"></div>
        <div class="grid grid-cols-2 gap-2">
          <button class="btn btn-cyan" onclick="runDaemonAction('status')">状态</button>
          <button class="btn btn-emerald" onclick="runDaemonAction('start')">启动</button>
          <button class="btn btn-rose" onclick="runDaemonAction('stop')">停止</button>
          <button class="btn btn-indigo" onclick="runDaemonAction('restart')">重启</button>
        </div>
        <div id="daemonHint" class="text-xs text-slate-500">请选择节点执行守护进程动作。</div>
      </div>
      <div class="xl:col-span-4 space-y-2">
        <h4 class="text-sm font-semibold text-slate-800">一键冒烟（选定节点链路）</h4>
        <div><label class="text-xs text-slate-500">节点路径（逗号分隔 nodeId）</label><input id="flowPathNodes" class="w-full border rounded-lg px-3 py-2 mono" placeholder="gateway-1,business-1,database-1"></div>
        <div><label class="text-xs text-slate-500">冒烟说明</label><input id="flowReason" class="w-full border rounded-lg px-3 py-2" placeholder="例如 发布后关键链路冒烟"></div>
        <button class="btn btn-slate w-full" onclick="runFlowSmoke()">执行冒烟</button>
        <div id="flowHint" class="text-xs text-slate-500">至少输入两个节点，按顺序执行健康探测。</div>
      </div>
      <div class="xl:col-span-4 space-y-2">
        <h4 class="text-sm font-semibold text-slate-800">压测与迁移</h4>
        <div><label class="text-xs text-slate-500">压测节点</label><select id="stressNodeId" class="w-full border rounded-lg px-3 py-2"></select></div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="text-xs text-slate-500">QPS</label><input id="stressQps" class="w-full border rounded-lg px-3 py-2" value="300"></div>
          <div><label class="text-xs text-slate-500">时长(秒)</label><input id="stressDuration" class="w-full border rounded-lg px-3 py-2" value="180"></div>
        </div>
        <div><label class="text-xs text-slate-500">压测原因</label><input id="stressReason" class="w-full border rounded-lg px-3 py-2" placeholder="例如 峰值容量评估"></div>
        <button class="btn btn-amber w-full" onclick="runStressTest()">执行压测</button>
        <hr class="my-1 border-slate-200">
        <div><label class="text-xs text-slate-500">迁移节点（数据库/缓存）</label><select id="dbNodeId" class="w-full border rounded-lg px-3 py-2"></select></div>
        <div class="grid grid-cols-2 gap-2">
          <div><label class="text-xs text-slate-500">方向</label><select id="dbDirection" class="w-full border rounded-lg px-3 py-2"><option value="up">up</option><option value="down">down</option></select></div>
          <div><label class="text-xs text-slate-500">版本</label><input id="dbVersion" class="w-full border rounded-lg px-3 py-2" placeholder="20260524-01"></div>
        </div>
        <div><label class="text-xs text-slate-500">迁移命令（可选）</label><input id="dbCommand" class="w-full border rounded-lg px-3 py-2 mono" placeholder="例如 alembic upgrade head"></div>
        <div><label class="text-xs text-slate-500">迁移原因</label><input id="dbReason" class="w-full border rounded-lg px-3 py-2" placeholder="例如 发布版本 1.3.0"></div>
        <button class="btn btn-rose w-full" onclick="runDbMigration()">执行迁移</button>
      </div>
    </div>
  </section>

  <section class="grid grid-cols-1 xl:grid-cols-12 gap-4">
    <section class="panel p-4 space-y-3 xl:col-span-7">
      <div class="flex items-center justify-between"><h3 class="section-title">执行流水（结构化）</h3><span id="streamSummary" class="text-xs text-slate-500">等待执行</span></div>
      <div id="streamList" class="space-y-2 max-h-[300px] overflow-auto"></div>
    </section>
    <section class="panel p-4 space-y-3 xl:col-span-5">
      <div class="flex items-center justify-between"><h3 class="section-title">Trace 回放</h3><span class="text-xs text-slate-500">按 traceId 查询</span></div>
      <div class="flex gap-2"><input id="traceQuery" class="flex-1 border rounded-lg px-3 py-2 mono" placeholder="输入 traceId"><button class="btn btn-slate" onclick="queryTrace()">查询</button></div>
      <pre id="traceDetail" class="w-full h-52 rounded border border-slate-200 bg-slate-50 p-3 text-xs overflow-auto mono"></pre>
    </section>
  </section>

  <section class="panel p-4 hidden" id="nodeConfigPanel">
    <div class="flex items-center justify-between mb-2"><h3 class="section-title">节点配置（高级 JSON）</h3><button class="btn btn-slate" onclick="toggleNodeConfig(false)">收起</button></div>
    <textarea id="nodeConfigJson" class="w-full h-48 border rounded-lg px-3 py-2 font-mono text-xs"></textarea>
    <div class="mt-2 flex gap-2"><button class="btn btn-indigo" onclick="saveNodesRawJson()">保存节点配置</button></div>
  </section>
  <div class="flex justify-end"><button class="btn btn-slate" onclick="toggleNodeConfig(true)">节点配置</button></div>
</section>
<script>
const ROLE_OPTIONS=['gateway','business','pressure','database','cache','mq','search','scheduler','admin','edge','analytics'];
const BIZ_STATUS_OPTIONS=['normal','observe','degraded','error','offline'];
const EDGE_TYPES=['gateway_to_business','business_to_db','business_to_cache','business_to_mq','sync','async','depends_on'];

const ACTION_CATALOG=[
  {group:'只读巡检',groupId:'observe',value:'health_check',label:'健康检查',risk:'low'},
  {group:'只读巡检',groupId:'observe',value:'ready_check',label:'就绪检查',risk:'low'},
  {group:'只读巡检',groupId:'observe',value:'status',label:'运行快照',risk:'low'},
  {group:'只读巡检',groupId:'observe',value:'metrics_snapshot',label:'指标快照',risk:'low'},
  {group:'只读巡检',groupId:'observe',value:'log_tail',label:'日志尾部(占位)',risk:'low'},

  {group:'生命周期',groupId:'lifecycle',value:'start',label:'节点上线',risk:'high'},
  {group:'生命周期',groupId:'lifecycle',value:'stop',label:'节点下线',risk:'high'},
  {group:'生命周期',groupId:'lifecycle',value:'restart',label:'节点重启',risk:'high'},
  {group:'生命周期',groupId:'lifecycle',value:'start_all',label:'全量上线',risk:'high'},
  {group:'生命周期',groupId:'lifecycle',value:'stop_all',label:'全量下线',risk:'high'},

  {group:'故障应急',groupId:'incident',value:'drain_node',label:'摘流节点',risk:'high'},
  {group:'故障应急',groupId:'incident',value:'isolate_node',label:'隔离节点',risk:'high'},
  {group:'故障应急',groupId:'incident',value:'recover_node',label:'恢复节点',risk:'high'},
  {group:'故障应急',groupId:'incident',value:'kick_session',label:'踢会话',risk:'high'},
  {group:'故障应急',groupId:'incident',value:'retry_task',label:'重试任务',risk:'medium'},

  {group:'运营控制',groupId:'operation',value:'maintenance',label:'维护公告',risk:'medium'},
  {group:'运营控制',groupId:'operation',value:'feature_toggle',label:'全局开关',risk:'medium'},
  {group:'运营控制',groupId:'operation',value:'whitelist',label:'白名单',risk:'medium'},
  {group:'运营控制',groupId:'operation',value:'mute_chat',label:'禁言',risk:'medium'},

  {group:'专项作业',groupId:'special',value:'smoke_test',label:'链路冒烟',risk:'medium'},
  {group:'专项作业',groupId:'special',value:'stress_test',label:'压力测试',risk:'high'},
  {group:'专项作业',groupId:'special',value:'db_migration',label:'数据库迁移',risk:'high'}
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
function readJson(id){const t=read(id); if(!t) return {}; try{return JSON.parse(t);}catch(_){throw new Error('payload JSON 解析失败');}}
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
    line.addEventListener('click',()=>{SELECTED_EDGE_ID=e.id;byId('edgeHint').textContent='已选中连线：'+e.from+' -> '+e.to+'（点击删除可移除）';drawTopology();});
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
      <div class="n-meta">${esc(rt.server_id||'-')} · ${esc(rt.env||'-')}</div>
      <div class="n-meta">${esc(n.desc||'无说明')}</div>`;
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
  wrap.onclick=()=>{SELECTED_EDGE_ID=''; byId('edgeHint').textContent='点击拓扑中的线条可选中后删除。'; drawTopology();};
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
  byId('edgeHint').textContent='节点已定位：'+SELECTED_NODE_ID;
  drawTopology();
}

async function saveNodeMeta(){
  const nodeId=read('topoNodeId'); if(!nodeId){alert('请先选择节点');return;}
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
  if(!from||!to||from===to){alert('请选择有效的起点和终点');return;}
  const payload={from,to,type:read('edgeType')||'depends_on',note:read('edgeNote')};
  const r=await fetch('/api/ops-platform/topology/edge/upsert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'topology_edge_upsert',trace_id:'',node:from,message:d.message||d.error||'',raw:d});
  if(d.ok){TOPOLOGY=d.topology||TOPOLOGY; SELECTED_EDGE_ID=''; drawTopology();}
}

async function removeSelectedEdge(){
  if(!SELECTED_EDGE_ID){alert('请先在图上点选一条连线');return;}
  const r=await fetch('/api/ops-platform/topology/edge/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({edge_id:SELECTED_EDGE_ID})});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'topology_edge_delete',trace_id:'',node:'-',message:d.message||d.error||'',raw:d});
  if(d.ok){TOPOLOGY=d.topology||TOPOLOGY; SELECTED_EDGE_ID=''; byId('edgeHint').textContent='点击拓扑中的线条可选中后删除。'; drawTopology();}
}

async function loadTopology(){
  const q=read('opsProjectFilter')?('?project_id='+encodeURIComponent(read('opsProjectFilter'))):'';
  const r=await fetch('/api/ops-platform/topology'+q);
  const d=await r.json();
  if(!d.ok){addStream({time:new Date().toISOString(),ok:false,action:'topology_load',trace_id:'',node:'-',message:d.error||'加载失败',raw:d});return;}
  TOPOLOGY=d.topology||{nodes:[],edges:[]};
  normalizeTopologyByNodes();
  if(!SELECTED_NODE_ID && TOPOLOGY.nodes.length){SELECTED_NODE_ID=TOPOLOGY.nodes[0].id;}
  syncNodeSelects();
  if(SELECTED_NODE_ID){selectNode(SELECTED_NODE_ID,false);} else {drawTopology();}
}

async function saveTopologyLayout(){
  const r=await fetch('/api/ops-platform/topology/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topology:TOPOLOGY})});
  const d=await r.json();
  if(!d.ok){addStream({time:new Date().toISOString(),ok:false,action:'topology_save',trace_id:'',node:'-',message:d.error||'保存失败',raw:d});return false;}
  return true;
}

function renderActionGroupOptions(){
  const groups=[];
  ACTION_CATALOG.forEach(a=>{if(!groups.includes(a.groupId)) groups.push(a.groupId);});
  const map={observe:'只读巡检',lifecycle:'生命周期',incident:'故障应急',operation:'运营控制',special:'专项作业'};
  byId('opActionGroup').innerHTML=groups.map(g=>`<option value="${g}">${map[g]||g}</option>`).join('');
}

function renderActionOptions(){
  const g=read('opActionGroup')||'observe';
  const rows=ACTION_CATALOG.filter(a=>a.groupId===g);
  byId('opActionType').innerHTML=rows.map(a=>`<option value="${a.value}">${a.label}</option>`).join('');
  setText('opGroupHint','分类：'+(rows[0]?rows[0].group:'-'));
  syncRiskHint();
}

function syncRiskHint(){
  const action=read('opActionType');
  const found=ACTION_CATALOG.find(x=>x.value===action)||{risk:'medium',group:'未知'};
  const hint=byId('opRiskHint');
  hint.textContent='风险级别：'+found.risk.toUpperCase();
  hint.className='text-xs px-2 py-1 rounded-full '+(found.risk==='high'?'bg-rose-100 text-rose-700':(found.risk==='medium'?'bg-amber-100 text-amber-700':'bg-emerald-100 text-emerald-700'));
  setText('opGroupHint','分类：'+found.group);
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
                '<details class="mt-1"><summary class="text-xs text-slate-500 cursor-pointer">展开原文</summary><pre class="mt-1 text-[11px] p-2 bg-white border rounded mono overflow-auto">'+esc(JSON.stringify(item.raw||{},null,2))+'</pre></details>';
  box.prepend(row);
  while(box.children.length>120){box.removeChild(box.lastChild);} 
}

function renderEvents(rows){
  const box=byId('eventList');
  box.innerHTML=(rows||[]).map(e=>`<div class="rounded-xl border border-slate-200 p-2 bg-slate-50"><div class="flex items-center justify-between"><span class="text-[11px] px-2 py-0.5 rounded-full ${e.severity==='critical'?'bg-rose-100 text-rose-700':(e.severity==='warning'?'bg-amber-100 text-amber-700':'bg-sky-100 text-sky-700')}">${esc(e.severity||'info')}</span><span class="text-xs text-slate-400">${esc(e.time||'')}</span></div><div class="mt-1 text-sm text-slate-800">${esc(e.title||'-')}</div><div class="text-xs text-slate-500">${esc(e.message||'')}</div></div>`).join('') || '<div class="text-sm text-slate-400">暂无事件</div>';
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
    hint.textContent='选择模板后可快速落节点，并自动注入上下游规则。';
    return;
  }
  const up=(preset.fixed_upstream_roles||[]).join(', ')||'无';
  const down=(preset.fixed_downstream_roles||[]).join(', ')||'无';
  hint.textContent='角色 '+(preset.role||'-')+'；上游: '+up+'；下游: '+down+'；说明: '+(preset.default_desc||'');
}

function selectedPreset(){
  const pid=read('presetSelect');
  return (NODE_PRESETS||[]).find(x=>String(x.preset_id||'')===pid)||null;
}

async function loadNodePresets(){
  const res=await fetch('/api/ops-platform/node-presets');
  const data=await res.json();
  if(!data.ok){
    addStream({time:new Date().toISOString(),ok:false,action:'node_presets',trace_id:'',node:'-',message:data.message||data.error||'模板加载失败',raw:data});
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
  if(!preset){alert('请先选择模板');return;}
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
  if(!data.ok){alert(data.message||data.error||'添加失败');return;}
  if(data.node&&data.node.id){
    byId('presetNodeName').value='';
    byId('presetServerId').value='';
    byId('presetDesc').value='';
    SELECTED_NODE_ID=String(data.node.id);
  }
  await loadOverviewAndTopology();
  await loadOnboarding();
  alert('节点已添加并纳入拓扑。');
}

function renderOnboarding(data){
  const body=byId('onboardBody');
  const rows=Array.isArray(data.checks)?data.checks:[];
  if(!rows.length){
    body.innerHTML='<tr><td class="px-2 py-3 text-slate-400" colspan="5">暂无数据</td></tr>';
    return;
  }
  body.innerHTML=rows.map(row=>{
    const sev=String(row.severity||'ok');
    const sevClass=sev==='critical'?'text-rose-600':(sev==='warning'?'text-amber-600':'text-emerald-600');
    const issues=(row.issues||[]).join('；')||'通过';
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
    addStream({time:new Date().toISOString(),ok:false,action:'node_onboarding',trace_id:'',node:'-',message:data.message||data.error||'体检失败',raw:data});
    return;
  }
  renderOnboarding(data);
  const s=data.summary||{};
  setText('onboardSummary','总节点 '+(s.total_nodes||0)+'，严重 '+(s.critical||0)+'，告警 '+(s.warning||0)+'，通过 '+(s.ok_nodes||0));
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
  if(!d.ok){ addStream({time:new Date().toISOString(),ok:false,action:'overview',message:d.error||'总览加载失败',raw:d}); return; }
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
    hint.textContent='预检通过'+(d.require_approval?'（高危需审批）':'');
    hint.className='text-xs text-emerald-600';
  }else{
    hint.textContent='预检失败：'+(d.message||d.error||'参数缺失');
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
  if(d.ok){ alert('审批单已创建: '+(d.approval_id||'')); }
}

async function executeAction(){
  let payload={};
  try{payload=readJson('opPayload');}catch(e){alert(e.message);return;}
  const req={node_id:read('opNodeId'),action_type:read('opActionType'),target:read('opTarget'),ticket_id:read('opTicket'),reason:read('opReason'),approver:read('opApprover'),dry_run:byId('opDryRun').checked,payload};
  const r=await fetch('/api/ops-platform/actions/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  byId('streamSummary').textContent=d.ok?'执行成功':'执行失败';
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
  if(!node_id){alert('请先选择节点');return;}
  const req={node_id,action,ticket_id:read('daemonTicketId')||'OPS-DAEMON',reason:read('daemonReason')||'守护进程操作'};
  const r=await fetch('/api/ops-platform/node/daemon-action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  const ok=!!d.ok;
  byId('daemonHint').textContent=(ok?'执行成功：':'执行失败：')+(d.message||d.error||'-');
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
  if(path_nodes.length<2){alert('请至少填写两个节点ID');return;}
  const req={path_nodes,reason:read('flowReason')||'一键冒烟'};
  const r=await fetch('/api/ops-platform/flow-smoke',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  const ok=!!d.ok;
  byId('flowHint').textContent=(ok?'冒烟通过，flowId=':'冒烟失败，flowId=')+(d.flow_id||'-');
  byId('flowHint').className='text-xs '+(ok?'text-emerald-600':'text-rose-600');
  addStream({time:new Date().toISOString(),ok,action:'flow_smoke',trace_id:d.flow_id||'',node:path_nodes.join(' -> '),message:d.message||d.error||'',raw:d});
  await loadEvents();
}

async function runStressTest(){
  const node_id=read('stressNodeId')||read('opNodeId');
  if(!node_id){alert('请先选择压测节点');return;}
  const qps=Number(read('stressQps')||300);
  const duration_sec=Number(read('stressDuration')||180);
  const req={node_id,qps,duration_sec,reason:read('stressReason')||'压力测试'};
  const r=await fetch('/api/ops-platform/stress-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'stress_test',trace_id:d.trace_id||'',node:node_id,message:d.message||d.error||'',raw:d});
  await loadEvents();
}

async function runDbMigration(){
  const node_id=read('dbNodeId')||read('opNodeId');
  if(!node_id){alert('请先选择迁移节点');return;}
  const req={node_id,direction:read('dbDirection')||'up',version:read('dbVersion'),command:read('dbCommand'),reason:read('dbReason')||'数据库迁移'};
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
  alert(t?('请基于 traceId '+t+' 创建回滚动作并重新执行（建议先 dry-run）。'):'请先执行动作并获取 traceId，再进行回滚。');
}

function toggleNodeConfig(show){
  const panel=byId('nodeConfigPanel');
  if(show){panel.classList.remove('hidden');}else{panel.classList.add('hidden');}
}

async function saveNodesRawJson(){
  let rows=[];
  try{rows=JSON.parse(byId('nodeConfigJson').value||'[]');}catch(_){alert('JSON 解析失败');return;}
  const r=await fetch('/api/gm-legacy/nodes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nodes:rows})});
  const d=await r.json();
  addStream({time:new Date().toISOString(),ok:!!d.ok,action:'save_nodes',trace_id:'',node:'-',message:d.ok?'节点配置已保存':'节点配置保存失败',raw:d});
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
    return _render_page(content, "运维平台")


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
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少 GM 执行权限 (gm.classic.execute)"}), 403
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
OPS_DAEMON_STATE_KEY = "OPS_PLATFORM_DAEMON_STATE"
OPS_FLOW_EXEC_KEY = "OPS_PLATFORM_FLOW_EXECUTIONS"


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _load_json_config(key: str, default):
    raw = get_system_config(key, default)
    if isinstance(raw, type(default)):
        return raw
    return default


def _save_json_config(key: str, value, description: str = "") -> None:
    set_system_config(key, value, value_type="json", description=description, username=str(session.get("user") or "system"))


def _default_node_presets() -> List[Dict[str, Any]]:
    return [
        {
            "preset_id": "gateway_http",
            "name": "网关节点",
            "category": "application",
            "role": "gateway",
            "node_type": "gateway_server",
            "default_desc": "入口网关，承接流量并转发业务服务",
            "fixed_upstream_roles": ["edge", "lb", "admin"],
            "fixed_downstream_roles": ["business", "pressure"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "business_main",
            "name": "业务节点",
            "category": "application",
            "role": "business",
            "node_type": "business_server",
            "default_desc": "核心业务处理节点",
            "fixed_upstream_roles": ["gateway", "scheduler", "admin"],
            "fixed_downstream_roles": ["database", "cache", "mq", "search"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "pressure_worker",
            "name": "压力节点",
            "category": "test",
            "role": "pressure",
            "node_type": "pressure_server",
            "default_desc": "压测流量与性能回归节点",
            "fixed_upstream_roles": ["gateway", "admin"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "redis_cache",
            "name": "Redis 缓存",
            "category": "infrastructure",
            "role": "cache",
            "node_type": "redis_cache",
            "default_desc": "缓存与会话存储",
            "fixed_upstream_roles": ["business", "gateway", "scheduler"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mongo_db",
            "name": "Mongo 数据库",
            "category": "database",
            "role": "database",
            "node_type": "mongo_database",
            "default_desc": "业务主存储数据库",
            "fixed_upstream_roles": ["business", "scheduler", "admin"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mysql_db",
            "name": "MySQL 数据库",
            "category": "database",
            "role": "database",
            "node_type": "mysql_database",
            "default_desc": "关系型数据库节点",
            "fixed_upstream_roles": ["business", "scheduler", "admin"],
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
            "name": "调度节点",
            "category": "application",
            "role": "scheduler",
            "node_type": "scheduler_server",
            "default_desc": "定时任务与批处理节点",
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
    _save_json_config(OPS_NODE_PRESETS_KEY, presets, description="Ops 预制节点库")
    return presets


def _load_daemon_state() -> Dict[str, Any]:
    raw = get_system_config(OPS_DAEMON_STATE_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_daemon_state(state: Dict[str, Any]) -> None:
    _save_json_config(OPS_DAEMON_STATE_KEY, state if isinstance(state, dict) else {}, description="Ops 节点守护进程状态")


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


def _default_topology_for_nodes(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    out_nodes: List[Dict[str, Any]] = []
    out_edges: List[Dict[str, Any]] = []
    total = max(1, len(nodes))
    cols = max(3, min(5, int((total ** 0.5) + 0.8)))
    for idx, n in enumerate(nodes):
        row = idx // cols
        col = idx % cols
        out_nodes.append(
            {
                "id": str(n.get("id") or ""),
                "role": str(n.get("role") or "business"),
                "desc": str(n.get("description") or ""),
                "bizStatus": str(n.get("biz_status") or "normal"),
                "owner": str(n.get("owner") or ""),
                "x": int(26 + col * 185),
                "y": int(26 + row * 132),
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
                    "type": "depends_on",
                    "note": "",
                }
            )
    return {"nodes": out_nodes, "edges": out_edges}


def _load_topology(current_nodes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = current_nodes if isinstance(current_nodes, list) else _load_nodes()
    raw = get_system_config(OPS_TOPOLOGY_KEY, {})
    if isinstance(raw, dict):
        nodes = raw.get("nodes") if isinstance(raw.get("nodes"), list) else []
        edges = raw.get("edges") if isinstance(raw.get("edges"), list) else []
    else:
        nodes, edges = [], []

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
                "desc": str(item.get("desc") or ""),
                "bizStatus": str(item.get("bizStatus") or "normal"),
                "owner": str(item.get("owner") or ""),
                "x": float(item.get("x") or 0),
                "y": float(item.get("y") or 0),
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
                "type": str(edge.get("type") or "depends_on"),
                "note": str(edge.get("note") or ""),
            }
        )
    return {"nodes": merged_nodes, "edges": merged_edges}


def _save_topology(topology: Dict[str, Any]) -> Dict[str, Any]:
    nodes = topology.get("nodes") if isinstance(topology, dict) and isinstance(topology.get("nodes"), list) else []
    edges = topology.get("edges") if isinstance(topology, dict) and isinstance(topology.get("edges"), list) else []
    payload = {"nodes": nodes, "edges": edges, "updated_at": _now_iso()}
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
    _append_bounded(OPS_EVENT_LOG_KEY, entry, limit=800, description="Ops 平台事件时间线")


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
                "title": f"节点状态异常: {node_name}",
                "message": f"状态={status}; serverId={n.get('server_id') or '-'}",
                "status": "open",
                "node_id": n.get("id"),
            })
        p99 = n.get("p99_ms")
        if isinstance(p99, (int, float)) and p99 >= 200:
            alerts.append({
                "id": f"alert-{n.get('id')}-p99",
                "time": _now_iso(),
                "severity": "warning",
                "title": f"延迟偏高: {node_name}",
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
    _save_json_config(OPS_ALERT_SNAPSHOT_KEY, snapshot, description="Ops 平台告警快照")

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
    }
    _append_trace(trace_entry)

    _append_event(
        {
            "id": "evt-" + uuid.uuid4().hex[:12],
            "time": _now_iso(),
            "severity": "info" if success else "critical",
            "status": "open" if not success else "resolved",
            "title": f"动作执行{'成功' if success else '失败'}: {action_type}",
            "message": f"node={node.get('id')}; target={target}; traceId={trace_id}; msg={message}",
            "trace_id": trace_id,
            "node_id": node.get("id"),
        }
    )

    log_audit("ops_platform_action_execute", f"action={action_type}; node={node.get('id')}; target={target}; trace={trace_id}; ok={success}")

    return {
        "ok": success,
        "message": message or ("执行成功" if success else "执行失败"),
        "trace_id": trace_id,
        "data": result.get("data") if isinstance(result.get("data"), dict) else result.get("data"),
        "result": result,
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


@bp.route("/api/ops-platform/action-catalog")
@admin_required("gm_ops")
def ops_platform_action_catalog():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    rows = [
        {"groupId": "observe", "group": "只读巡检", "value": "health_check", "label": "健康检查", "risk": "low"},
        {"groupId": "observe", "group": "只读巡检", "value": "ready_check", "label": "就绪检查", "risk": "low"},
        {"groupId": "observe", "group": "只读巡检", "value": "status", "label": "运行快照", "risk": "low"},
        {"groupId": "observe", "group": "只读巡检", "value": "metrics_snapshot", "label": "指标快照", "risk": "low"},
        {"groupId": "observe", "group": "只读巡检", "value": "log_tail", "label": "日志尾部(占位)", "risk": "low"},
        {"groupId": "lifecycle", "group": "生命周期", "value": "start", "label": "节点上线", "risk": "high"},
        {"groupId": "lifecycle", "group": "生命周期", "value": "stop", "label": "节点下线", "risk": "high"},
        {"groupId": "lifecycle", "group": "生命周期", "value": "restart", "label": "节点重启", "risk": "high"},
        {"groupId": "lifecycle", "group": "生命周期", "value": "start_all", "label": "全量上线", "risk": "high"},
        {"groupId": "lifecycle", "group": "生命周期", "value": "stop_all", "label": "全量下线", "risk": "high"},
        {"groupId": "incident", "group": "故障应急", "value": "drain_node", "label": "摘流节点", "risk": "high"},
        {"groupId": "incident", "group": "故障应急", "value": "isolate_node", "label": "隔离节点", "risk": "high"},
        {"groupId": "incident", "group": "故障应急", "value": "recover_node", "label": "恢复节点", "risk": "high"},
        {"groupId": "incident", "group": "故障应急", "value": "kick_session", "label": "踢会话", "risk": "high"},
        {"groupId": "incident", "group": "故障应急", "value": "retry_task", "label": "重试任务", "risk": "medium"},
        {"groupId": "operation", "group": "运营控制", "value": "maintenance", "label": "维护公告", "risk": "medium"},
        {"groupId": "operation", "group": "运营控制", "value": "feature_toggle", "label": "全局开关", "risk": "medium"},
        {"groupId": "operation", "group": "运营控制", "value": "whitelist", "label": "白名单", "risk": "medium"},
        {"groupId": "operation", "group": "运营控制", "value": "mute_chat", "label": "禁言", "risk": "medium"},
        {"groupId": "special", "group": "专项作业", "value": "smoke_test", "label": "链路冒烟", "risk": "medium"},
        {"groupId": "special", "group": "专项作业", "value": "stress_test", "label": "压力测试", "risk": "high"},
        {"groupId": "special", "group": "专项作业", "value": "db_migration", "label": "数据库迁移", "risk": "high"},
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

    node_index = {str(x.get("id") or ""): x for x in (normalized.get("nodes") or []) if isinstance(x, dict)}
    for item in incoming_nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid or nid not in node_index:
            continue
        src = node_index[nid]
        src["role"] = str(item.get("role") or src.get("role") or "business")
        src["desc"] = str(item.get("desc") or src.get("desc") or "")
        src["bizStatus"] = str(item.get("bizStatus") or src.get("bizStatus") or "normal")
        src["owner"] = str(item.get("owner") or src.get("owner") or "")
        try:
            src["x"] = float(item.get("x"))
            src["y"] = float(item.get("y"))
        except Exception:
            pass

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
                "type": str(edge.get("type") or "depends_on"),
                "note": str(edge.get("note") or ""),
            }
        )
    final_topo = {"nodes": list(node_index.values()), "edges": merged_edges}
    saved = _save_topology(final_topo)
    log_audit("ops_platform_topology_save", f"nodes={len(final_topo.get('nodes') or [])}; edges={len(merged_edges)}")
    return jsonify({"ok": True, "message": "拓扑已保存", "topology": saved})


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
    return jsonify({"ok": True, "message": "节点属性已更新", "topology": saved})


@bp.route("/api/ops-platform/topology/edge/upsert", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_topology_edge_upsert():
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    frm = str(payload.get("from") or "").strip()
    to = str(payload.get("to") or "").strip()
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
        return jsonify({"ok": False, "error": "invalid_edge_by_role", "message": "该节点上下游关系不在预制规则中。"}), 400

    updated = False
    for edge in topo.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("from") or "") == frm and str(edge.get("to") or "") == to:
            edge["type"] = etype
            edge["note"] = note
            updated = True
            break
    if not updated:
        (topo.get("edges") or []).append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": frm, "to": to, "type": etype, "note": note})

    saved = _save_topology(topo)
    log_audit("ops_platform_topology_edge_upsert", f"{frm}->{to}; type={etype}")
    return jsonify({"ok": True, "message": "连线已更新", "topology": saved})


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
    before = len(topo.get("edges") or [])
    topo["edges"] = [x for x in (topo.get("edges") or []) if not (isinstance(x, dict) and str(x.get("id") or "") == edge_id)]
    after = len(topo.get("edges") or [])
    if after == before:
        return jsonify({"ok": False, "error": "edge not found"}), 404
    saved = _save_topology(topo)
    log_audit("ops_platform_topology_edge_delete", f"edge={edge_id}")
    return jsonify({"ok": True, "message": "连线已删除", "topology": saved})


@bp.route("/api/ops-platform/node-presets")
@admin_required("gm_ops")
def ops_platform_node_presets():
    if not _allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403
    return jsonify({"ok": True, "count": len(_load_node_presets()), "presets": _load_node_presets()})


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
                "desc": node.get("description") or "",
                "bizStatus": node.get("biz_status") or "normal",
                "owner": node.get("owner") or "",
                "x": (pos or {}).get("x", 20),
                "y": (pos or {}).get("y", 20),
            }
        )
    role = str(node.get("role") or "")
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
                (topo.get("edges") or []).append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": eid, "to": new_id, "type": "depends_on", "note": "preset-auto"})
        if _can_link_nodes(node, src):
            exists = any(isinstance(e, dict) and str(e.get("from") or "") == new_id and str(e.get("to") or "") == eid for e in (topo.get("edges") or []))
            if not exists:
                (topo.get("edges") or []).append({"id": f"edge-{uuid.uuid4().hex[:10]}", "from": new_id, "to": eid, "type": "depends_on", "note": "preset-auto"})
    saved_topo = _save_topology(topo)
    log_audit("ops_platform_node_add_from_preset", f"node={new_id}; preset={preset_id}")
    return jsonify({"ok": True, "message": "节点已添加", "node": node, "topology": saved_topo})


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
        _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": "info", "status": "resolved", "title": f"守护进程动作: {action}", "message": f"node={node.get('id')}; {result.get('message')}", "node_id": node.get("id")})
    else:
        _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": "critical", "status": "open", "title": f"守护进程动作失败: {action}", "message": f"node={node.get('id')}; {result.get('message')}", "node_id": node.get("id")})
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
            issues.append("未接入拓扑关系")
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
        return jsonify({"ok": False, "error": "invalid_path", "message": "至少选择两个节点"}), 400
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
        result_steps.append({"node_id": node.get("id"), "ok": ok, "message": smoke.get("message"), "result": smoke})
        if not ok:
            success = False
    flow_id = "flow-" + uuid.uuid4().hex[:12]
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if success else "critical"), "status": ("resolved" if success else "open"), "title": "流程冒烟测试", "message": f"flow={flow_id}; nodes={len(path_nodes)}; success={success}"})
    _append_bounded(OPS_FLOW_EXEC_KEY, {"flow_id": flow_id, "time": _now_iso(), "type": "smoke", "ok": success, "steps": result_steps}, limit=120, description="流程执行记录")
    return jsonify({"ok": success, "flow_id": flow_id, "steps": result_steps}), (200 if success else 502)


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
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if ok else "warning"), "status": ("resolved" if ok else "open"), "title": "压力测试触发", "message": f"node={node.get('id')}; qps={qps}; duration={duration_sec}s; ok={ok}"})
    return jsonify({"ok": ok, "message": result.get("message"), "result": result}), (200 if ok else 502)


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
        return jsonify({"ok": False, "error": "invalid_role", "message": "仅数据库/缓存节点支持迁移流程。"}), 400
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
        _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": "info", "status": "resolved", "title": "数据库迁移", "message": f"node={node.get('id')}; direction={direction}; version={version}; mode=native"})
        log_audit("ops_platform_db_migration", f"node={node.get('id')}; direction={direction}; version={version}; mode=native")
        return jsonify({"ok": True, "message": native.get("message") or "迁移任务已受理", "result": native})

    if not cmd:
        return jsonify({"ok": False, "error": "native_failed_no_command", "message": f"原生迁移能力失败且未提供本地命令: {native.get('message') or 'unknown'}"}), 502

    code = subprocess.call(cmd, shell=True)
    ok = code == 0
    _set_daemon_state(str(node.get("id") or ""), {"last_action": f"db_migration_{direction}", "last_error": ("" if ok else f"exit_code={code}")})
    _append_event({"id": "evt-" + uuid.uuid4().hex[:12], "time": _now_iso(), "severity": ("info" if ok else "critical"), "status": ("resolved" if ok else "open"), "title": "数据库迁移", "message": f"node={node.get('id')}; direction={direction}; version={version}; mode=fallback; code={code}"})
    log_audit("ops_platform_db_migration", f"node={node.get('id')}; direction={direction}; version={version}; mode=fallback; code={code}")
    return jsonify({"ok": ok, "message": ("迁移成功（fallback）" if ok else "迁移失败（fallback）"), "exit_code": code, "native_error": native.get("message")}), (200 if ok else 502)


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
    if not _allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    node, err = _node_or_400(payload)
    if err:
        return err

    validation = _validate_ops_request(payload, node)
    if not validation.get("require_approval"):
        return jsonify({"ok": False, "error": "approval_not_required", "message": "当前动作无需审批。"}), 400

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
        "message": "审批单已创建，请到审批中心通过后执行。",
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
            "message": "高风险动作未审批，请先创建并通过审批。",
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
        return jsonify({"ok": False, "error": "approval required", "message": "高风险动作未审批，请先发起审批。"}), 412

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
