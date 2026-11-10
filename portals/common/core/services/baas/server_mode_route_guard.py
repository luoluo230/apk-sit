# -*- coding: utf-8 -*-
"""Block deep-linked project pages that conflict with project server_mode (nav policy SSOT)."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

from flask import Response, redirect

from services.baas.project_nav_policy import BAAS_ONLY, TOPOLOGY_ONLY, visible_nav_item_ids
from services.server_mode import project_server_mode

# Ops/topology HTML routes (active_page) — BaaS projects must not open these via URL.
TOPOLOGY_DEEP_LINK_PAGES = frozenset(
    {
        "topology",
        "agent-control",
        "actions",
        "diagnostics",
        "agent-device-local",
        "agent-detail",
    }
    | set(TOPOLOGY_ONLY)
)

BAAS_DEEP_LINK_PAGES = frozenset(BAAS_ONLY)


def _topology_pages_allowed(project_id: str) -> bool:
    return "agent-control" in visible_nav_item_ids(project_id)


def _baas_pages_allowed(project_id: str) -> bool:
    return "casual-services" in visible_nav_item_ids(project_id)


def redirect_if_server_mode_blocks_page(
    project_id: str,
    active_page: str,
    env_key: str = "",
) -> Optional[Response]:
    """Return Flask redirect when deep-linked page disagrees with project_nav_policy."""
    pid = str(project_id or "").strip()
    page = str(active_page or "").strip()
    if not pid or not page:
        return None
    env = str(env_key or request_env_fallback()).strip() or "development"

    if page in TOPOLOGY_DEEP_LINK_PAGES and not _topology_pages_allowed(pid):
        mode = project_server_mode(pid)
        msg = (
            "当前项目为轻度 BaaS 模式，无法访问中重度拓扑或 Agent 页面。"
            if mode == "casual_baas"
            else "当前项目服务器模式不允许访问该页面。"
        )
        params = {
            "env_key": env,
            "server_mode_blocked": "1",
            "blocked_page": page,
        }
        return redirect(f"/admin/projects/{pid}/server-management?{urlencode(params)}")

    if page in BAAS_DEEP_LINK_PAGES and not _baas_pages_allowed(pid):
        mode = project_server_mode(pid)
        msg = (
            "当前项目为中重度拓扑模式，无法访问 BaaS 功能配置或 GM 页面。"
            if mode == "topology"
            else "当前项目服务器模式不允许访问该页面。"
        )
        _ = msg  # reserved for flash banner when overview supports query hint
        params = {
            "env_key": env,
            "server_mode_blocked": "1",
            "blocked_page": page,
        }
        return redirect(f"/admin/projects/{pid}/overview?{urlencode(params)}")

    return None


def request_env_fallback() -> str:
    try:
        from flask import request

        return str(request.args.get("env_key") or "").strip()
    except RuntimeError:
        return ""
