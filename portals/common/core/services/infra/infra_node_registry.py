# -*- coding: utf-8 -*-
"""Unified infra node registry: build agents + runtime cluster nodes."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from repositories import infra_nodes_repo
from services.build.build_grid import BUILD_ROLES, list_build_roles, normalize_build_platform

_CORE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_MIRROR_FILE = os.path.join(_CORE_ROOT, "data", "build_nodes.json")
_HEARTBEAT_TTL_SEC = 120
_RUNTIME_ROLE_PREFIX = "runtime-"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mirror_enabled() -> bool:
    return str(os.getenv("BUILD_NODES_JSON_MIRROR", "1")).strip().lower() not in ("0", "false", "no")


def _mirror_build_nodes_json(nodes: List[Dict[str, Any]]) -> None:
    if not _mirror_enabled():
        return
    os.makedirs(os.path.dirname(_MIRROR_FILE), exist_ok=True)
    payload = {"nodes": nodes, "updated_at": _now_iso(), "_mirror": True}
    with open(_MIRROR_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _build_row_to_legacy(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    out = {
        "id": row.get("node_id"),
        "node_id": row.get("node_id"),
        "role": row.get("role"),
        "hostname": row.get("host") or payload.get("hostname"),
        "host": row.get("host"),
        "agent_name": row.get("display_name") or payload.get("agent_name"),
        "display_name": row.get("display_name"),
        "os": payload.get("os") or "",
        "unity_version": payload.get("unity_version") or "",
        "unity_editor_path": payload.get("unity_editor_path") or "",
        "jenkins_master_url": payload.get("jenkins_master_url") or "",
        "labels": payload.get("labels") if isinstance(payload.get("labels"), list) else [],
        "capabilities": row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {},
        "last_heartbeat": row.get("last_heartbeat_at") or "",
        "last_heartbeat_at": row.get("last_heartbeat_at") or "",
        "status": row.get("status") or "unknown",
        "created_at": row.get("created_at") or "",
        "project_id": row.get("project_id") or "",
        "jenkins_label": row.get("jenkins_label") or "",
        "port": row.get("port") or 0,
        "agent_ws_url": row.get("agent_ws_url") or "",
    }
    return _enrich_node(out)


def _is_build_role(role: str) -> bool:
    return str(role or "") in BUILD_ROLES or str(role or "").startswith("build-")


def list_nodes(*, role: str = "", role_prefix: str = "", project_id: str = "", plane: str = "") -> List[Dict[str, Any]]:
    prefix = role_prefix
    if plane == "build":
        rows = infra_nodes_repo.list_nodes(role=role, project_id=project_id)
        return [_build_row_to_legacy(r) for r in rows if _is_build_role(str(r.get("role") or ""))]
    if plane == "runtime":
        prefix = prefix or _RUNTIME_ROLE_PREFIX
        rows = infra_nodes_repo.list_nodes(role_prefix=prefix, project_id=project_id)
        return [_runtime_row_view(r) for r in rows]
    rows = infra_nodes_repo.list_nodes(role=role, role_prefix=prefix, project_id=project_id)
    out: List[Dict[str, Any]] = []
    for row in rows:
        rk = str(row.get("role") or "")
        if rk.startswith(_RUNTIME_ROLE_PREFIX):
            out.append(_runtime_row_view(row))
        else:
            out.append(_build_row_to_legacy(row))
    return out


def get_node(node_id: str) -> Optional[Dict[str, Any]]:
    row = infra_nodes_repo.get_node(node_id)
    if not row:
        return None
    rk = str(row.get("role") or "")
    if rk.startswith(_RUNTIME_ROLE_PREFIX):
        return _runtime_row_view(row)
    return _build_row_to_legacy(row)


def register_or_heartbeat(payload: Dict[str, Any]) -> Dict[str, Any]:
    role = str(payload.get("role") or "").strip()
    if role not in BUILD_ROLES:
        raise ValueError(f"未知构建角色: {role}")
    hostname = str(payload.get("hostname") or payload.get("host") or "").strip()
    agent_name = str(payload.get("agent_name") or payload.get("jenkins_agent_name") or hostname).strip()
    node_id = str(payload.get("node_id") or payload.get("id") or "").strip()
    if not node_id:
        node_id = f"{role}-{uuid.uuid4().hex[:8]}"
    now = _now_iso()
    meta = BUILD_ROLES.get(role) or {}
    label = str(meta.get("label") or "")
    extra_payload = {
        "hostname": hostname or agent_name,
        "agent_name": agent_name,
        "os": str(payload.get("os") or "").strip().lower(),
        "unity_version": str(payload.get("unity_version") or "").strip(),
        "unity_editor_path": str(payload.get("unity_editor_path") or "").strip(),
        "jenkins_master_url": str(payload.get("jenkins_master_url") or "").strip(),
        "labels": payload.get("labels") if isinstance(payload.get("labels"), list) else ([label] if label else []),
    }
    existing = infra_nodes_repo.get_node(node_id)
    saved = infra_nodes_repo.upsert_node(
        {
            "node_id": node_id,
            "project_id": str(payload.get("project_id") or (existing or {}).get("project_id") or ""),
            "role": role,
            "display_name": agent_name,
            "host": hostname or agent_name,
            "jenkins_label": label,
            "jenkins_instance_id": str(payload.get("jenkins_instance_id") or "").strip(),
            "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {},
            "status": "online",
            "last_heartbeat_at": now,
            "created_at": (existing or {}).get("created_at") or now,
            "payload": extra_payload,
        }
    )
    _mirror_build_nodes_json(list_nodes(plane="build"))
    return _build_row_to_legacy(saved)


def upsert_runtime_node(project_id: str, server: Dict[str, Any]) -> Dict[str, Any]:
    srv_id = str(server.get("ServerId") or server.get("node_id") or "").strip()
    if not srv_id:
        raise ValueError("runtime node 缺少 ServerId")
    srv_type = str(server.get("Type") or server.get("server_type") or "runtime").strip().lower()
    role_key = str(server.get("Role") or srv_type or "runtime").strip().lower()
    role = f"{_RUNTIME_ROLE_PREFIX}{role_key}"
    host = str(server.get("ProbeHost") or server.get("Host") or server.get("host") or "127.0.0.1").strip()
    port = int(server.get("Port") or server.get("port") or 0)
    display_name = str(server.get("DisplayName") or server.get("display_name") or srv_id).strip()
    now = _now_iso()
    payload = {
        "server_type": srv_type,
        "node_id": srv_id,
        "category": str(server.get("Category") or ""),
        "registration_origin": str(server.get("registration_origin") or "cluster.sync"),
    }
    saved = infra_nodes_repo.upsert_node(
        {
            "node_id": srv_id,
            "project_id": str(project_id or server.get("project_id") or "").strip(),
            "role": role,
            "display_name": display_name,
            "host": host,
            "port": port,
            "agent_ws_url": str(server.get("agent_ws_url") or ""),
            "status": str(server.get("status") or "unknown").lower(),
            "last_heartbeat_at": str(server.get("last_heartbeat") or server.get("updated_at") or now),
            "capabilities": {"platforms": [], "actions": server.get("capabilities") or []},
            "payload": payload,
        }
    )
    return _runtime_row_view(saved)


def sync_runtime_nodes_from_cluster(project_id: str, servers: List[Dict[str, Any]]) -> Dict[str, Any]:
    synced = 0
    for srv in servers or []:
        if not isinstance(srv, dict):
            continue
        try:
            upsert_runtime_node(project_id, srv)
            synced += 1
        except ValueError:
            continue
    return {"synced": synced, "project_id": project_id}


def delete_node(node_id: str) -> bool:
    ok = infra_nodes_repo.delete_node(node_id)
    if ok:
        _mirror_build_nodes_json(list_nodes(plane="build"))
    return ok


def build_grid_summary() -> Dict[str, Any]:
    roles = list_build_roles()
    nodes = list_nodes(plane="build")
    by_role: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        rk = str(n.get("role") or "")
        by_role.setdefault(rk, []).append(n)
    role_rows = []
    for role in roles:
        rid = str(role.get("role_id") or "")
        online = [n for n in by_role.get(rid, []) if n.get("online")]
        role_rows.append(
            {
                "role_id": rid,
                "display_name": role.get("display_name"),
                "label": role.get("label"),
                "job_name": role.get("job_name"),
                "online_count": len(online),
                "total_count": len(by_role.get(rid, [])),
                "healthy": len(online) >= 1 if rid != "control" else True,
            }
        )
    runtime_nodes = list_nodes(plane="runtime")
    return {
        "roles": role_rows,
        "nodes": nodes,
        "runtime_nodes": runtime_nodes,
        "updated_at": _now_iso(),
    }


def resolve_online_build_node(platform: str) -> Optional[Dict[str, Any]]:
    from services.build.build_grid import resolve_build_role_for_platform

    role = resolve_build_role_for_platform(normalize_build_platform(platform))
    label = str((BUILD_ROLES.get(role) or {}).get("label") or "")
    online = [
        n
        for n in list_nodes(role=role, plane="build")
        if n.get("online") and (not label or str(n.get("jenkins_label") or n.get("expected_label") or "") == label)
    ]
    return online[0] if online else None


def recommended_build_node_for_platform(platform: str) -> Dict[str, Any]:
    node = resolve_online_build_node(platform)
    plat = normalize_build_platform(platform)
    role = str((node or {}).get("role") or "")
    meta = BUILD_ROLES.get(role) or {}
    if not node:
        return {
            "platform": plat,
            "available": False,
            "label": str(meta.get("label") or ""),
            "display_name": str(meta.get("display_name") or ""),
            "hint": "无在线构建节点，请先安装并启动对应 Agent",
        }
    return {
        "platform": plat,
        "available": True,
        "node_id": node.get("id") or node.get("node_id"),
        "display_name": node.get("agent_name") or node.get("display_name"),
        "hostname": node.get("hostname") or node.get("host"),
        "jenkins_label": node.get("jenkins_label") or node.get("expected_label") or meta.get("label"),
        "unity_version": node.get("unity_version") or "",
        "hint": "",
    }


def _enrich_node(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    hb = str(out.get("last_heartbeat") or out.get("last_heartbeat_at") or "")
    online = False
    if hb:
        try:
            dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            online = age <= _HEARTBEAT_TTL_SEC
        except Exception:
            online = False
    out["online"] = online
    if not online and str(out.get("status") or "").lower() == "online":
        out["status"] = "offline"
    role = str(out.get("role") or "")
    meta = BUILD_ROLES.get(role) or {}
    out["role_display_name"] = meta.get("display_name") or role
    out["expected_label"] = out.get("jenkins_label") or meta.get("label") or ""
    out["job_name"] = meta.get("job_name") or ""
    return out


def _runtime_row_view(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    role = str(row.get("role") or "")
    return {
        "id": row.get("node_id"),
        "node_id": row.get("node_id"),
        "role": role,
        "role_display_name": role.replace(_RUNTIME_ROLE_PREFIX, "").upper() or "Runtime",
        "display_name": row.get("display_name") or row.get("node_id"),
        "host": row.get("host") or "",
        "port": row.get("port") or 0,
        "status": row.get("status") or "unknown",
        "project_id": row.get("project_id") or "",
        "server_type": payload.get("server_type") or "",
        "last_heartbeat_at": row.get("last_heartbeat_at") or "",
        "plane": "runtime",
    }
