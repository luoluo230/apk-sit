# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
import services.ops.helpers as ops_helpers
from routes.ops import bp

@bp.route("/admin/ops-platform")
@admin_required("gm_ops")
def ops_platform_page():
    missing = ops_helpers._ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    try:
        content = ops_helpers._render_local_template("ops_overview_page.html", project_id=project_id)
        return ops_helpers._render_page(content, "运维平台")
    except Exception:
        return ops_helpers._render_page(
            '<section class="panel p-6"><h2 class="text-xl font-bold">运维平台</h2><p class="text-slate-600 mt-2">总览页面加载失败，请检查模板与静态资源。</p></section>',
            "运维平台",
        )
@bp.route("/admin/ops-platform/actions")
@admin_required("gm_ops")
def ops_platform_actions_page():
    missing = ops_helpers._ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    content = ops_helpers._render_local_template("ops_actions_page.html", project_id=project_id)
    return ops_helpers._render_page(content, "动作执行中心")


@bp.route("/admin/ops-platform/topology")
@admin_required("gm_ops")
def ops_platform_topology_page():
    missing = ops_helpers._ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    env_key = ops_helpers._normalize_env_key(request.args.get("env_key") or "production")
    topology_id = ops_helpers._resolve_ops_topology_id(project_id, env_key, request.args.get("topology_id") or "")
    content = ops_helpers._render_local_template("ops_topology_workbench.html", project_id=project_id, env_key=env_key, topology_id=topology_id)
    return ops_helpers._render_standalone_page(content, "拓扑与配置编排")



@bp.route("/admin/ops-platform/diagnostics")
@admin_required("gm_ops")
def ops_platform_diagnostics_page():
    missing = ops_helpers._ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    content = ops_helpers._render_local_template("ops_diagnostics_page.html", project_id=project_id)
    return ops_helpers._render_page(content, "节点诊断中心")


@bp.route("/admin/ops-platform/agent-control")
@admin_required("gm_ops")
def ops_platform_agent_control_page():
    missing = ops_helpers._ops_platform_redirect_to_runtime_project()
    if missing is not None:
        return missing
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    content = ops_helpers._render_local_template("ops_agent_control_page.html", project_id=project_id)
    return ops_helpers._render_standalone_page(content, "Agent 控制面")



@bp.route("/admin/ops-platform/agent-device-local")
@admin_required("gm_ops")
def ops_platform_agent_device_local_page():
    project_id = str(request.args.get("project_id") or "").strip()
    device_id = str(request.args.get("device_id") or "").strip()
    content = ops_helpers._render_local_template("ops_agent_device_local_page.html", project_id=project_id, device_id=device_id)
    return ops_helpers._render_page(content, "设备 Agent 组")



@bp.route("/admin/ops-platform/agent-detail")
@admin_required("gm_ops")
def ops_platform_agent_detail_page():
    project_id = ops_helpers._resolve_ops_project_id(request.args.get("project_id") or "")
    agent_id = str(request.args.get("agent_id") or "").strip()
    content = ops_helpers._render_local_template("ops_agent_detail_page.html", project_id=project_id, agent_id=agent_id)
    return ops_helpers._render_standalone_page(content, "Agent 详情")



@bp.route("/admin/ops-platform/change-governance")
@admin_required("gm_ops")
def ops_platform_change_governance_page():
    project_id = str(request.args.get("project_id") or "").strip()
    content = ops_helpers._render_local_template("ops_change_governance_page.html", project_id=project_id)
    return ops_helpers._render_page(content, "发布与变更治理")


