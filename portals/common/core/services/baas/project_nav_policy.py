# -*- coding: utf-8 -*-
"""Project shell / hub visibility by server_mode (single source of truth)."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Set

from services.server_mode import project_server_mode

# Nav item ids under project groups
TOPOLOGY_ONLY: FrozenSet[str] = frozenset({
    "agent-control",
    "actions",
    "diagnostics",
})

BAAS_ONLY: FrozenSet[str] = frozenset({
    "casual-services",
    "baas-gm",
})

# Always keep for both modes when in project context
SHARED_OK: FrozenSet[str] = frozenset({
    "project-home",
    "environment-runtime",
    "release-hub",
    "server-management",
    "community",
    "project-tasks",
    "project-docs",
    "approval-center",
    "change-governance",
    "audit-log",
    "project-settings",
    "test-devices",
    "project-channels",
})


def visible_nav_item_ids(project_id: str) -> Set[str]:
    mode = project_server_mode(project_id)
    visible = set(SHARED_OK)
    if mode == "casual_baas":
        visible |= set(BAAS_ONLY)
    else:
        visible |= set(TOPOLOGY_ONLY)
    return visible


def filter_shell_groups(groups: list[dict], project_id: str) -> list[dict]:
    """Drop nav items/groups not allowed for this project's server_mode."""
    if not str(project_id or "").strip():
        return groups
    allowed = visible_nav_item_ids(project_id)
    out: list[dict] = []
    for group in groups:
        items = [it for it in (group.get("items") or []) if str(it.get("id") or "") in allowed]
        if not items:
            continue
        row = dict(group)
        row["items"] = items
        mode = project_server_mode(project_id)
        # Relabel runtime group for BaaS
        if row.get("id") == "runtime" and mode == "casual_baas":
            row["label"] = "BaaS 运行"
        if row.get("id") == "operations":
            item_ids = {str(it.get("id") or "") for it in items}
            if mode == "casual_baas":
                row["label"] = "BaaS 运维"
            elif not item_ids.intersection(BAAS_ONLY):
                # topology：无功能配置/GM，仅剩共享项（通常只有 community）
                row["label"] = "社区" if item_ids <= {"community"} else "运营"
        out.append(row)
    return out


def hub_tab_flags(project_id: str) -> Dict[str, Any]:
    # monitor_only=True ⇒ 项目内 Hub 仅监听/GM/区服，前端不渲染卡片 CRUD
    mode = project_server_mode(project_id) if project_id else "topology"
    if not project_id:
        return {
            "server_mode": "",
            "show_topology_tab": True,
            "show_baas_tab": False,
            "default_tab": "topology",
            "monitor_only": False,
        }
    if mode == "casual_baas":
        return {
            "server_mode": mode,
            "show_topology_tab": False,
            "show_baas_tab": True,
            "default_tab": "baas",
            "monitor_only": True,
        }
    return {
        "server_mode": mode,
        "show_topology_tab": True,
        "show_baas_tab": False,
        "default_tab": "topology",
        "monitor_only": False,
    }
