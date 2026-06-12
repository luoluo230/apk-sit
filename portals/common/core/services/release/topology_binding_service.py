# -*- coding: utf-8 -*-
"""Project-owned topology binding matrix for release/runtime resolution."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.data import get_system_config, set_system_config
from services.release.env_registry import normalize_release_env_key

TOPOLOGY_BINDINGS_KEY = "RELEASE_TOPOLOGY_BINDINGS_V1"


def _now_iso() -> str:
    return datetime.now().isoformat()


def _load_rows() -> List[Dict[str, Any]]:
    raw = get_system_config(TOPOLOGY_BINDINGS_KEY, [])
    return raw if isinstance(raw, list) else []


def _save_rows(rows: List[Dict[str, Any]], *, actor: str = "") -> None:
    set_system_config(
        TOPOLOGY_BINDINGS_KEY,
        rows if isinstance(rows, list) else [],
        value_type="json",
        description="项目拓扑绑定矩阵",
        username=str(actor or "system").strip() or "system",
    )


def _binding_level(env_key: str, channel_id: str, version_name: str) -> str:
    if version_name:
        return "version"
    if env_key and channel_id:
        return "env_channel"
    return "project_default"


def _level_label(level: str) -> str:
    mapping = {
        "project_default": "项目默认",
        "env_channel": "环境/渠道",
        "version": "大版本覆盖",
    }
    return mapping.get(str(level or "").strip(), "未定义")


def normalize_binding_row(payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    row = dict(payload or {})
    env_key = normalize_release_env_key(row.get("env_key") or "") if row.get("env_key") else ""
    channel_id = str(row.get("channel_id") or "").strip()
    version_name = str(row.get("version_name") or "").strip()
    level = _binding_level(env_key, channel_id, version_name)
    return {
        "binding_id": str(row.get("binding_id") or f"tb-{uuid.uuid4().hex[:10]}").strip(),
        "project_id": str(row.get("project_id") or "").strip(),
        "env_key": env_key,
        "channel_id": channel_id,
        "version_name": version_name,
        "topology_id": str(row.get("topology_id") or "").strip(),
        "level": level,
        "level_label": _level_label(level),
        "status": str(row.get("status") or "active").strip() or "active",
        "note": str(row.get("note") or "").strip(),
        "created_at": str(row.get("created_at") or _now_iso()),
        "updated_at": _now_iso(),
        "updated_by": str(actor or row.get("updated_by") or "system").strip() or "system",
    }


def list_topology_bindings(project_id: str = "") -> List[Dict[str, Any]]:
    pid = str(project_id or "").strip()
    rows = []
    for item in _load_rows():
        if not isinstance(item, dict):
            continue
        row = normalize_binding_row(item, actor=str(item.get("updated_by") or "system"))
        if pid and row["project_id"] != pid:
            continue
        rows.append(row)
    order = {"project_default": 0, "env_channel": 1, "version": 2}
    rows.sort(
        key=lambda row: (
            order.get(str(row.get("level") or ""), 9),
            str(row.get("env_key") or ""),
            str(row.get("channel_id") or ""),
            str(row.get("version_name") or ""),
            str(row.get("updated_at") or ""),
        )
    )
    return rows


def upsert_topology_binding(payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    row = normalize_binding_row(payload, actor=actor)
    if not row["project_id"]:
        raise ValueError("project_id required")
    if not row["topology_id"]:
        raise ValueError("topology_id required")
    if row["level"] == "env_channel" and (not row["env_key"] or not row["channel_id"]):
        raise ValueError("env_channel binding requires env_key and channel_id")
    if row["level"] == "version" and (not row["env_key"] or not row["channel_id"] or not row["version_name"]):
        raise ValueError("version binding requires env_key, channel_id and version_name")

    rows = _load_rows()
    hit = -1
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        current = normalize_binding_row(item, actor=str(item.get("updated_by") or "system"))
        same_key = (
            current["project_id"] == row["project_id"]
            and current["env_key"] == row["env_key"]
            and current["channel_id"] == row["channel_id"]
            and current["version_name"] == row["version_name"]
        )
        if current["binding_id"] == row["binding_id"] or same_key:
            hit = index
            row["binding_id"] = current["binding_id"]
            row["created_at"] = str(current.get("created_at") or row["created_at"])
            break
    if hit >= 0:
        rows[hit] = row
    else:
        rows.append(row)
    _save_rows(rows, actor=actor)
    return row


def delete_topology_binding(binding_id: str, *, actor: str = "") -> bool:
    bid = str(binding_id or "").strip()
    if not bid:
        return False
    rows = _load_rows()
    next_rows = [row for row in rows if not (isinstance(row, dict) and str(row.get("binding_id") or "").strip() == bid)]
    if len(next_rows) == len(rows):
        return False
    _save_rows(next_rows, actor=actor)
    return True


def resolve_topology_binding(
    project_id: str,
    env_key: str,
    channel_id: str,
    *,
    version_name: str = "",
    fallback_topology_id: str = "",
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    ek = normalize_release_env_key(env_key) if env_key else ""
    cid = str(channel_id or "").strip()
    vname = str(version_name or "").strip()
    rows = [row for row in list_topology_bindings(pid) if str(row.get("status") or "active") == "active"]

    def _match(level: str) -> Optional[Dict[str, Any]]:
        for row in rows:
            if row.get("level") != level:
                continue
            if level == "project_default":
                return row
            if level == "env_channel" and row.get("env_key") == ek and row.get("channel_id") == cid:
                return row
            if level == "version" and row.get("env_key") == ek and row.get("channel_id") == cid and row.get("version_name") == vname:
                return row
        return None

    matched = _match("version") if vname else None
    if not matched:
        matched = _match("env_channel")
    if not matched:
        matched = _match("project_default")
    if matched:
        return {
            "topology_id": str(matched.get("topology_id") or "").strip(),
            "binding_source": str(matched.get("level") or ""),
            "binding_source_label": str(matched.get("level_label") or _level_label(str(matched.get("level") or ""))),
            "binding": matched,
        }

    fallback = str(fallback_topology_id or "").strip()
    if fallback:
        return {
            "topology_id": fallback,
            "binding_source": "scope_default",
            "binding_source_label": "Scope 默认",
            "binding": {},
        }
    return {"topology_id": "", "binding_source": "", "binding_source_label": "", "binding": {}}
