# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
import services.ops.helpers as ops_helpers
from routes.ops import bp

def _page_scope():
    missing = ops_helpers._ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return None, None, None, missing
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    env_key = ops_helpers._resolve_ops_env_key(request.args.get("env_key") or "")
    return project_id, env_key, None, None

@bp.route("/admin/ops-platform")
@admin_required("gm_ops")
def ops_platform_page():
    project_id, env_key, _, redirect_resp = _page_scope()
    if redirect_resp is not None:
        return redirect_resp
    try:
        content = ops_helpers._render_local_template("ops_overview_page.html", project_id=project_id, env_key=env_key)
        return ops_helpers._render_ops_page(content, "运维平台", active_page="overview", project_id=project_id, env_key=env_key)
    except Exception:
        return ops_helpers._render_ops_page(
            '<section class="panel p-6"><h2 class="text-xl font-bold">运维平台</h2><p class="text-slate-600 mt-2">总览页面加载失败，请检查模板与静态资源。</p></section>',
            "运维平台",
            active_page="overview",
            project_id=project_id,
            env_key=env_key,
        )

@bp.route("/admin/ops-platform/actions")
@admin_required("gm_ops")
def ops_platform_actions_page():
    project_id, env_key, _, redirect_resp = _page_scope()
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template("ops_actions_page.html", project_id=project_id, env_key=env_key)
    return ops_helpers._render_ops_page(content, "动作执行中心", active_page="actions", project_id=project_id, env_key=env_key)


@bp.route("/admin/ops-platform/topology")
@admin_required("gm_ops")
def ops_platform_topology_page():
    project_id, env_key, _, redirect_resp = _page_scope()
    if redirect_resp is not None:
        return redirect_resp
    topology_id = ops_helpers._resolve_ops_topology_id(project_id, env_key, request.args.get("topology_id") or "")
    content = ops_helpers._render_local_template("ops_topology_workbench.html", project_id=project_id, env_key=env_key, topology_id=topology_id)
    return ops_helpers._render_ops_page(
        content, "拓扑与配置编排",
        active_page="topology",
        project_id=project_id,
        env_key=env_key,
        topology_id=topology_id,
        extra_css='<link rel="stylesheet" href="/static/ops_platform_topology_workbench.css?v=20260609-unified-v1">',
        extra_js='<script src="/static/ops_platform_api.js?v=20260609-unified-v1"></script>\n<script src="/static/ops_platform_workbench.js?v=20260609-unified-v1"></script>',
    )



@bp.route("/admin/ops-platform/diagnostics")
@admin_required("gm_ops")
def ops_platform_diagnostics_page():
    project_id, env_key, _, redirect_resp = _page_scope()
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template("ops_diagnostics_page.html", project_id=project_id, env_key=env_key)
    return ops_helpers._render_ops_page(content, "节点诊断中心", active_page="diagnostics", project_id=project_id, env_key=env_key)


@bp.route("/admin/ops-platform/agent-control")
@admin_required("gm_ops")
def ops_platform_agent_control_page():
    project_id, env_key, _, redirect_resp = _page_scope()
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template("ops_agent_control_page.html", project_id=project_id, env_key=env_key)
    return ops_helpers._render_ops_page(content, "Agent 控制面", active_page="agent-control", project_id=project_id, env_key=env_key)



@bp.route("/admin/ops-platform/agent-device-local")
@admin_required("gm_ops")
def ops_platform_agent_device_local_page():
    project_id, env_key, _, redirect_resp = _page_scope()
    if redirect_resp is not None:
        return redirect_resp
    device_id = str(request.args.get("device_id") or "").strip()
    content = ops_helpers._render_local_template("ops_agent_device_local_page.html", project_id=project_id, env_key=env_key, device_id=device_id)
    return ops_helpers._render_ops_page(content, "设备 Agent 组", active_page="agent-device-local", project_id=project_id, env_key=env_key)



@bp.route("/admin/ops-platform/agent-detail")
@admin_required("gm_ops")
def ops_platform_agent_detail_page():
    project_id, env_key, _, redirect_resp = _page_scope()
    if redirect_resp is not None:
        return redirect_resp
    agent_id = str(request.args.get("agent_id") or "").strip()
    content = ops_helpers._render_local_template("ops_agent_detail_page.html", project_id=project_id, env_key=env_key, agent_id=agent_id)
    return ops_helpers._render_ops_page(content, "Agent 详情", active_page="agent-detail", project_id=project_id, env_key=env_key)



@bp.route("/admin/ops-platform/change-governance")
@admin_required("gm_ops")
def ops_platform_change_governance_page():
    project_id, env_key, _, redirect_resp = _page_scope()
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template("ops_change_governance_page.html", project_id=project_id, env_key=env_key)
    return ops_helpers._render_ops_page(content, "发布与变更治理", active_page="change-governance", project_id=project_id, env_key=env_key)
