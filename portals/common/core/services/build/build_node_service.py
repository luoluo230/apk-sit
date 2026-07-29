# -*- coding: utf-8 -*-
"""Build node registry (JSON) + heartbeat + pre-build gates."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.build.build_grid import BUILD_ROLES, list_build_roles, normalize_build_platform

_CORE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DATA_FILE = os.path.join(_CORE_ROOT, "data", "build_nodes.json")
_HEARTBEAT_TTL_SEC = 120


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_store() -> None:
    os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
    if not os.path.isfile(_DATA_FILE):
        with open(_DATA_FILE, "w", encoding="utf-8") as fh:
            json.dump({"nodes": [], "updated_at": _now_iso()}, fh, ensure_ascii=False, indent=2)


def _load_raw() -> Dict[str, Any]:
    _ensure_store()
    with open(_DATA_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {"nodes": []}


def _save_raw(data: Dict[str, Any]) -> None:
    _ensure_store()
    data["updated_at"] = _now_iso()
    with open(_DATA_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def list_nodes(*, role: str = "") -> List[Dict[str, Any]]:
    rows = list(_load_raw().get("nodes") or [])
    if role:
        role_key = str(role).strip()
        rows = [r for r in rows if str(r.get("role") or "") == role_key]
    return [_enrich_node(dict(r)) for r in rows]


def get_node(node_id: str) -> Optional[Dict[str, Any]]:
    nid = str(node_id or "").strip()
    if not nid:
        return None
    for row in _load_raw().get("nodes") or []:
        if str(row.get("id") or "") == nid:
            return _enrich_node(dict(row))
    return None


def register_or_heartbeat(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _load_raw()
    nodes: List[Dict[str, Any]] = list(data.get("nodes") or [])
    role = str(payload.get("role") or "").strip()
    if role not in BUILD_ROLES:
        raise ValueError(f"未知构建角色: {role}")
    hostname = str(payload.get("hostname") or payload.get("host") or "").strip()
    agent_name = str(payload.get("agent_name") or payload.get("jenkins_agent_name") or hostname).strip()
    node_id = str(payload.get("node_id") or payload.get("id") or "").strip()
    if not node_id:
        node_id = f"{role}-{uuid.uuid4().hex[:8]}"

    now = _now_iso()
    existing = next((n for n in nodes if str(n.get("id") or "") == node_id), None)
    row = dict(existing or {})
    row.update({
        "id": node_id,
        "role": role,
        "hostname": hostname or row.get("hostname") or agent_name,
        "agent_name": agent_name,
        "os": str(payload.get("os") or row.get("os") or "").strip().lower(),
        "unity_version": str(payload.get("unity_version") or row.get("unity_version") or "").strip(),
        "unity_editor_path": str(payload.get("unity_editor_path") or row.get("unity_editor_path") or "").strip(),
        "jenkins_master_url": str(payload.get("jenkins_master_url") or row.get("jenkins_master_url") or "").strip(),
        "labels": payload.get("labels") if isinstance(payload.get("labels"), list) else [BUILD_ROLES[role]["label"]] if BUILD_ROLES[role].get("label") else [],
        "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {},
        "last_heartbeat": now,
        "status": "online",
    })
    if not existing:
        row["created_at"] = now
        nodes.append(row)
    else:
        idx = nodes.index(existing)
        nodes[idx] = row
    data["nodes"] = nodes
    _save_raw(data)
    return _enrich_node(row)


def delete_node(node_id: str) -> bool:
    data = _load_raw()
    nodes = list(data.get("nodes") or [])
    before = len(nodes)
    nodes = [n for n in nodes if str(n.get("id") or "") != str(node_id or "").strip()]
    if len(nodes) == before:
        return False
    data["nodes"] = nodes
    _save_raw(data)
    return True


def build_grid_summary() -> Dict[str, Any]:
    roles = list_build_roles()
    nodes = list_nodes()
    by_role: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        rk = str(n.get("role") or "")
        by_role.setdefault(rk, []).append(n)
    role_rows = []
    for role in roles:
        rid = str(role.get("role_id") or "")
        online = [n for n in by_role.get(rid, []) if n.get("online")]
        role_rows.append({
            "role_id": rid,
            "display_name": role.get("display_name"),
            "label": role.get("label"),
            "job_name": role.get("job_name"),
            "online_count": len(online),
            "total_count": len(by_role.get(rid, [])),
            "healthy": len(online) >= 1 if rid != "control" else True,
        })
    return {
        "roles": role_rows,
        "nodes": nodes,
        "updated_at": _load_raw().get("updated_at"),
    }


def assert_build_ready(platform: str, *, required_unity_version: str = "") -> None:
    """Raise ValueError when platform cannot build or no online agent."""
    from services.build.platform_capability import assert_platform_build_allowed

    assert_platform_build_allowed(platform)
    plat = normalize_build_platform(platform)
    from services.build.build_grid import resolve_build_role_for_platform

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
    mismatched = [n for n in online if str(n.get("unity_version") or "") and str(n.get("unity_version")) != req]
    if mismatched and not any(str(n.get("unity_version") or "") == req for n in online):
        raise ValueError(f"构建节点 Unity 版本与项目要求不一致：需要 {req}")


def _enrich_node(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    hb = str(out.get("last_heartbeat") or "")
    online = False
    if hb:
        try:
            dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            online = age <= _HEARTBEAT_TTL_SEC
        except Exception:
            online = False
    out["online"] = online
    if not online and out.get("status") == "online":
        out["status"] = "offline"
    role = str(out.get("role") or "")
    meta = BUILD_ROLES.get(role) or {}
    out["role_display_name"] = meta.get("display_name") or role
    out["expected_label"] = meta.get("label") or ""
    out["job_name"] = meta.get("job_name") or ""
    return out
