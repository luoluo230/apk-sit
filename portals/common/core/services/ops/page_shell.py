# -*- coding: utf-8 -*-
"""Ops page shell: permission checks and the shared admin wrapper."""

from __future__ import annotations

import os

from flask import has_request_context, render_template, render_template_string, request, session

from models.data import projects_db
from services.authz import can_access_module, has_scope, is_admin
from services.ops.shared_bootstrap import OPS_COMPACT_CSS, OPS_SHELL_ASSET_VER, PM_UI_CSS
from services.ops.topology_registry import _resolve_ops_env_key, _resolve_ops_project_id
from services.ops.topology_service import _env_label


def _session_username(default: str = "system") -> str:
    try:
        if has_request_context():
            return str(session.get("user") or default)
    except Exception:
        pass
    return default


def _allow_ops_view() -> bool:
    return bool(
        is_admin()
        or can_access_module("gm_ops")
        or has_scope("ops.platform.view")
        or has_scope("gm.ops.execute")
        or has_scope("gm.audit.view")
    )


def _allow_ops_execute() -> bool:
    return bool(
        is_admin()
        or can_access_module("gm_ops")
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


def _ops_csrf_token() -> str:
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except Exception:
        return ""


def _render_ops_page(
    content: str,
    title: str,
    active_page: str = "",
    project_id: str = "",
    env_key: str = "",
    topology_id: str = "",
    breadcrumb_module: str = "",
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
    unread_notification_count = 0
    try:
        from data.notifications import get_notifications_for_user

        unread_notification_count = sum(
            1 for n in get_notifications_for_user(user_name, limit=200) if not n.get("read_at")
        )
    except Exception:
        unread_notification_count = 0
    return render_template(
        "ops_shell.html",
        content=content,
        title=title,
        active_page=active_page,
        project_id=project_id,
        project_name=project_name,
        project_label=project_name or "未选择项目",
        env_key=env_key,
        env_label=env_label,
        topology_id=topology_id,
        avatar_text=(user_name[:1] or "A").upper(),
        user_name=user_name,
        unread_notification_count=unread_notification_count,
        breadcrumb_module=breadcrumb_module or "项目工作区",
        extra_css=PM_UI_CSS + OPS_COMPACT_CSS + extra_css,
        extra_js=extra_js,
        csrf_token=_ops_csrf_token(),
        ops_shell_asset_ver=OPS_SHELL_ASSET_VER,
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
