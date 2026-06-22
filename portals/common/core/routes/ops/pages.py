# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
import services.ops.helpers as ops_helpers
from routes.ops import bp

def _page_scope(project_id_override: str = ""):
    if not project_id_override:
        missing = ops_helpers._ops_platform_redirect_to_runtime_project()
        if missing is not None:
            return None, None, None, missing
    else:
        missing = None
    project_id = ops_helpers._resolve_ops_project_id(project_id_override or request.args.get("project_id") or "")
    env_key = ops_helpers._resolve_ops_env_key(request.args.get("env_key") or "")
    return project_id, env_key, None, None

@bp.route("/admin/projects/<project_id>/ops")
@admin_required("gm_ops")
def ops_platform_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    try:
        content = ops_helpers._render_local_template("ops_overview_page.html", project_id=project_id, env_key=env_key)
        return ops_helpers._render_ops_page(content, "项目运维总览", active_page="overview", project_id=project_id, env_key=env_key)
    except Exception:
        return ops_helpers._render_ops_page(
            '<section class="panel p-6"><h2 class="text-xl font-bold">项目运维总览</h2><p class="text-slate-600 mt-2">总览页面加载失败，请检查模板与静态资源。</p></section>',
            "项目运维总览",
            active_page="overview",
            project_id=project_id,
            env_key=env_key,
        )

@bp.route("/admin/projects/<project_id>/actions")
@admin_required("gm_ops")
def ops_platform_actions_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template("ops_actions_page.html", project_id=project_id, env_key=env_key)
    return ops_helpers._render_ops_page(content, "动作执行中心", active_page="actions", project_id=project_id, env_key=env_key)


@bp.route("/admin/projects/<project_id>/topologies")
@admin_required("gm_ops")
def ops_platform_topology_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    topology_id = ops_helpers._resolve_ops_topology_id(project_id, env_key, request.args.get("topology_id") or "")
    content = ops_helpers._render_local_template(
        "ops_topology_workspace_page.html",
        project_id=project_id,
        env_key=env_key,
        topology_id=topology_id,
    )
    return ops_helpers._render_ops_page(
        content, "拓扑管理",
        active_page="topology",
        project_id=project_id,
        env_key=env_key,
        topology_id=topology_id,
    )


@bp.route("/admin/projects/<project_id>/topology-bindings")
@admin_required("gm_ops")
def project_topology_bindings_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template(
        "ops_topology_bindings_page.html",
        project_id=project_id,
        env_key=env_key,
    )
    return ops_helpers._render_ops_page(
        content,
        "拓扑绑定矩阵",
        active_page="topology-bindings",
        project_id=project_id,
        env_key=env_key,
    )


@bp.route("/admin/projects/<project_id>/topologies/canvas")
@admin_required("gm_ops")
def ops_platform_topology_canvas_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    topology_id = ops_helpers._resolve_ops_topology_id(project_id, env_key, request.args.get("topology_id") or "")
    content = ops_helpers._render_local_template(
        "ops_topology_workbench.html",
        project_id=project_id,
        env_key=env_key,
        topology_id=topology_id,
    )
    return ops_helpers._render_ops_page(
        content, "拓扑画布",
        active_page="topology",
        project_id=project_id,
        env_key=env_key,
        topology_id=topology_id,
        extra_css='<link rel="stylesheet" href="/static/ops_platform_topology_workbench.css?v=20260612-project-canvas-v1">',
        extra_js='<script src="/static/ops_platform_api.js?v=20260609-unified-v1"></script>\n<script src="/static/ops_platform_workbench.js?v=20260609-unified-v1"></script>',
    )



@bp.route("/admin/projects/<project_id>/diagnostics")
@admin_required("gm_ops")
def ops_platform_diagnostics_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template("ops_diagnostics_page.html", project_id=project_id, env_key=env_key)
    return ops_helpers._render_ops_page(content, "节点诊断中心", active_page="diagnostics", project_id=project_id, env_key=env_key)


@bp.route("/admin/projects/<project_id>/agents")
@admin_required("gm_ops")
def ops_platform_agent_control_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template("ops_agent_control_page.html", project_id=project_id, env_key=env_key)
    return ops_helpers._render_ops_page(content, "Agent 控制面", active_page="agent-control", project_id=project_id, env_key=env_key)



@bp.route("/admin/projects/<project_id>/agent-device-local")
@admin_required("gm_ops")
def ops_platform_agent_device_local_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    device_id = str(request.args.get("device_id") or "").strip()
    content = ops_helpers._render_local_template("ops_agent_device_local_page.html", project_id=project_id, env_key=env_key, device_id=device_id)
    return ops_helpers._render_ops_page(content, "设备 Agent 组", active_page="agent-device-local", project_id=project_id, env_key=env_key)



@bp.route("/admin/projects/<project_id>/agent-detail")
@admin_required("gm_ops")
def ops_platform_agent_detail_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    agent_id = str(request.args.get("agent_id") or "").strip()
    content = ops_helpers._render_local_template("ops_agent_detail_page.html", project_id=project_id, env_key=env_key, agent_id=agent_id)
    return ops_helpers._render_ops_page(content, "Agent 详情", active_page="agent-detail", project_id=project_id, env_key=env_key)



@bp.route("/admin/projects/<project_id>/change-governance")
@admin_required("gm_ops")
def ops_platform_change_governance_page(project_id: str = ""):
    project_id, env_key, _, redirect_resp = _page_scope(project_id)
    if redirect_resp is not None:
        return redirect_resp
    content = ops_helpers._render_local_template("ops_change_governance_page.html", project_id=project_id, env_key=env_key)
    return ops_helpers._render_ops_page(content, "发布与变更治理", active_page="change-governance", project_id=project_id, env_key=env_key)
