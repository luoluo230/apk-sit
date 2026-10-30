# -*- coding: utf-8 -*-
"""Topology server plane: registry, graph, runtime activity, and agent deploy."""

from __future__ import annotations

from typing import Any, Dict

from services.ops.topology_graph import add_node_from_preset, upsert_edge
from services.ops.topology_graph_remove import delete_edge, delete_node
from services.ops.topology_registry import (
    create_topology_registry_entry,
    delete_topology_registry_entry,
    update_topology_registry_entry,
)
from services.release.server_release_service import (
    create_server_release,
    deploy_server_release,
    get_server_release,
)


def open_topology(project_id: str, env_key: str, topology_id: str, name: str, actor: str = "admin") -> Dict[str, Any]:
    return create_topology_registry_entry(
        {
            "project_id": project_id,
            "env_key": env_key,
            "topology_id": topology_id,
            "name": name,
        },
        actor=actor,
    )


def rename_topology(topology_id: str, name: str, actor: str = "admin") -> Dict[str, Any]:
    return update_topology_registry_entry(topology_id, {"name": name}, actor=actor)


def close_topology(topology_id: str) -> bool:
    return delete_topology_registry_entry(topology_id)


def place_preset_node(payload: Dict[str, Any]) -> Dict[str, Any]:
    body, status = add_node_from_preset(payload)
    if status >= 400 or not body.get("ok"):
        raise ValueError(body.get("message") or body.get("error") or "添加节点失败")
    return body


def connect_nodes(payload: Dict[str, Any]) -> Dict[str, Any]:
    body, status = upsert_edge(payload)
    if status >= 400 or not body.get("ok"):
        raise ValueError(body.get("message") or body.get("error") or "连线失败")
    return body


def remove_edge(payload: Dict[str, Any]) -> Dict[str, Any]:
    body, status = delete_edge(payload)
    if status >= 400 or not body.get("ok"):
        raise ValueError(body.get("message") or body.get("error") or "删除连线失败")
    return body


def remove_node(payload: Dict[str, Any]) -> Dict[str, Any]:
    body, status = delete_node(payload)
    if status >= 400 or not body.get("ok"):
        raise ValueError(body.get("message") or body.get("error") or "删除节点失败")
    return body


def start_server_deploy(project_id: str, topology_id: str, artifact_id: str, service_id: str, actor: str) -> Dict[str, Any]:
    release = create_server_release(
        project_id,
        {
            "topology_id": topology_id,
            "artifact_id": artifact_id,
            "target_services": [service_id],
            "env_key": "development",
        },
        actor,
    )
    return deploy_server_release(project_id, release["server_release_id"], actor)


def read_server_release(project_id: str, server_release_id: str) -> Dict[str, Any]:
    row = get_server_release(project_id, server_release_id)
    if not row:
        raise ValueError("服务端发布单不存在")
    return row
