# -*- coding: utf-8
"""Build node registry — delegates to unified infra_nodes DB (P1-05)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.infra import infra_node_registry as _registry


def list_nodes(*, role: str = "") -> List[Dict[str, Any]]:
    return _registry.list_nodes(role=role, plane="build")


def get_node(node_id: str) -> Optional[Dict[str, Any]]:
    return _registry.get_node(node_id)


def register_or_heartbeat(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _registry.register_or_heartbeat(payload)


def delete_node(node_id: str) -> bool:
    return _registry.delete_node(node_id)


def build_grid_summary() -> Dict[str, Any]:
    return _registry.build_grid_summary()


def assert_build_ready(platform: str, *, required_unity_version: str = "") -> None:
    """Raise ValueError when platform cannot build or no online agent."""
    from services.build.platform_capability import assert_platform_build_allowed

    assert_platform_build_allowed(platform)
    from services.build.build_grid import BUILD_ROLES, normalize_build_platform, resolve_build_role_for_platform

    plat = normalize_build_platform(platform)
    role = resolve_build_role_for_platform(plat)
    label = str((BUILD_ROLES.get(role) or {}).get("label") or "")
    if not label:
        return
    online = [n for n in list_nodes(role=role) if n.get("online")]
    if not online:
        display = str((BUILD_ROLES.get(role) or {}).get("display_name") or role)
        raise ValueError(f"无在线构建节点（{display} / label={label}）。请先安装并启动对应 Agent。")
    req = str(required_unity_version or "").strip()
    if not req:
        return
    if not any(str(n.get("unity_version") or "") == req for n in online):
        raise ValueError(f"构建节点 Unity 版本与项目要求不一致：需要 {req}")
