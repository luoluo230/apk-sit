# -*- coding: utf-8 -*-
"""Project-owned topology binding matrix backed by SQLite."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.db import _db_lock, _get_conn, get_cursor, init_db
from services.release.env_registry import normalize_release_env_key


def _now_iso() -> str:
    return datetime.now().isoformat()


def _binding_level(env_key: str, channel_id: str, platform: str, version_name: str) -> str:
    if version_name:
        return "version"
    if env_key and channel_id and platform:
        return "env_channel_platform"
    if env_key and channel_id:
        return "env_channel"
    return "project_default"


def _level_label(level: str) -> str:
    return {
        "project_default": "项目默认",
        "env_channel": "环境 / 渠道",
        "env_channel_platform": "环境 / 渠道 / 平台",
        "version": "大版本覆盖",
    }.get(str(level or "").strip(), "未定义")


def _status_label(status: str) -> str:
    return {
        "running": "运行中",
        "validated": "已验证",
        "draft": "草稿",
        "stopped": "已停止",
        "archived": "已归档",
    }.get(str(status or "").strip().lower(), str(status or "").strip() or "未知")


def normalize_binding_row(payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    row = dict(payload or {})
    env_key = normalize_release_env_key(row.get("env_key") or "") if row.get("env_key") else ""
    channel_id = str(row.get("channel_id") or "").strip()
    platform = str(row.get("platform") or "").strip().lower()
    version_name = str(row.get("version_name") or "").strip()
    level = _binding_level(env_key, channel_id, platform, version_name)
    return {
        "binding_id": str(row.get("binding_id") or f"tb-{uuid.uuid4().hex[:10]}").strip(),
        "project_id": str(row.get("project_id") or "").strip(),
        "env_key": env_key,
        "channel_id": channel_id,
        "platform": platform,
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


def _row_from_db(row) -> Dict[str, Any]:
    keys = row.keys() if hasattr(row, "keys") else []
    platform = str(row["platform"] if "platform" in keys else "").strip().lower()
    level = str(row["level"] or "").strip()
    if level == "env_channel" and platform:
        level = "env_channel_platform"
    return {
        "binding_id": row["binding_id"],
        "project_id": row["project_id"],
        "env_key": row["env_key"],
        "channel_id": row["channel_id"],
        "platform": platform,
        "version_name": row["version_name"],
        "topology_id": row["topology_id"],
        "level": level,
        "level_label": _level_label(level),
        "status": row["status"],
        "note": row["note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
    }


def list_topology_bindings(project_id: str = "") -> List[Dict[str, Any]]:
    init_db()
    sql = "SELECT * FROM topology_bindings"
    params: List[str] = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(str(project_id).strip())
    sql += """
        ORDER BY CASE level
            WHEN 'project_default' THEN 0
            WHEN 'env_channel' THEN 1
            WHEN 'env_channel_platform' THEN 1
            ELSE 2 END,
        env_key, channel_id, platform, version_name, updated_at DESC
    """
    with _db_lock:
        rows = _get_conn().execute(sql, params).fetchall()
    return [_row_from_db(row) for row in rows]


def upsert_topology_binding(payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    row = normalize_binding_row(payload, actor=actor)
    if not row["project_id"]:
        raise ValueError("project_id required")
    if not row["topology_id"]:
        raise ValueError("topology_id required")
    if row["level"] == "env_channel_platform" and (not row["env_key"] or not row["channel_id"] or not row["platform"]):
        raise ValueError("env_channel_platform binding requires env_key, channel_id and platform")
    if row["level"] == "env_channel" and (not row["env_key"] or not row["channel_id"]):
        raise ValueError("env_channel binding requires env_key and channel_id")
    if row["level"] == "version" and (not row["env_key"] or not row["channel_id"] or not row["version_name"]):
        raise ValueError("version binding requires env_key, channel_id and version_name")
    init_db()
    with get_cursor() as cur:
        existing = cur.execute(
            """
            SELECT binding_id, created_at FROM topology_bindings
            WHERE project_id=? AND env_key=? AND channel_id=? AND platform=? AND version_name=?
            """,
            (row["project_id"], row["env_key"], row["channel_id"], row["platform"], row["version_name"]),
        ).fetchone()
        if existing:
            row["binding_id"] = existing["binding_id"]
            row["created_at"] = existing["created_at"]
        cur.execute(
            """
            INSERT INTO topology_bindings (
                binding_id, project_id, env_key, channel_id, platform, version_name, topology_id,
                level, status, note, payload, created_at, updated_at, updated_by
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(binding_id) DO UPDATE SET
                topology_id=excluded.topology_id, level=excluded.level, status=excluded.status,
                note=excluded.note, payload=excluded.payload, updated_at=excluded.updated_at,
                updated_by=excluded.updated_by, platform=excluded.platform
            """,
            (
                row["binding_id"], row["project_id"], row["env_key"], row["channel_id"], row["platform"],
                row["version_name"], row["topology_id"], row["level"], row["status"],
                row["note"], json.dumps(row, ensure_ascii=False), row["created_at"],
                row["updated_at"], row["updated_by"],
            ),
        )
    return row


def delete_topology_binding(binding_id: str, *, actor: str = "") -> bool:
    del actor
    init_db()
    with get_cursor() as cur:
        cur.execute("DELETE FROM topology_bindings WHERE binding_id=?", (str(binding_id or "").strip(),))
        return cur.rowcount > 0


def delete_topology_binding_for_scope(
    project_id: str,
    env_key: str,
    channel_id: str,
    *,
    platform: str = "",
    version_name: str = "",
) -> bool:
    ek = normalize_release_env_key(env_key) if env_key else ""
    cid = str(channel_id or "").strip()
    plat = str(platform or "").strip().lower()
    vname = str(version_name or "").strip()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            DELETE FROM topology_bindings
            WHERE project_id=? AND env_key=? AND channel_id=? AND platform=? AND version_name=?
            """,
            (str(project_id or "").strip(), ek, cid, plat, vname),
        )
        return cur.rowcount > 0


def resolve_topology_binding(
    project_id: str,
    env_key: str,
    channel_id: str,
    *,
    platform: str = "",
    version_name: str = "",
    fallback_topology_id: str = "",
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    ek = normalize_release_env_key(env_key) if env_key else ""
    cid = str(channel_id or "").strip()
    plat = str(platform or "").strip().lower()
    vname = str(version_name or "").strip()
    rows = [row for row in list_topology_bindings(pid) if row.get("status") == "active"]

    def _match(level: str) -> Optional[Dict[str, Any]]:
        for row in rows:
            row_level = str(row.get("level") or "").strip()
            if row_level != level:
                continue
            if level == "project_default":
                return row
            if level == "env_channel_platform":
                if row.get("env_key") == ek and row.get("channel_id") == cid and row.get("platform") == plat:
                    return row
            elif level == "env_channel":
                if row.get("env_key") == ek and row.get("channel_id") == cid and not str(row.get("platform") or "").strip():
                    return row
            elif level == "version":
                row_plat = str(row.get("platform") or "").strip().lower()
                plat_ok = (not row_plat) or (row_plat == plat)
                if row.get("env_key") == ek and row.get("channel_id") == cid and row.get("version_name") == vname and plat_ok:
                    return row
        return None

    matched = None
    if vname:
        matched = _match("version")
    if not matched and plat:
        matched = _match("env_channel_platform")
    if not matched:
        matched = _match("env_channel")
    if not matched:
        matched = _match("project_default")
    if matched:
        return {
            "topology_id": matched["topology_id"],
            "binding_source": matched["level"],
            "binding_source_label": matched["level_label"],
            "binding": matched,
        }
    if fallback_topology_id:
        return {
            "topology_id": str(fallback_topology_id).strip(),
            "binding_source": "scope_default",
            "binding_source_label": "Scope 默认",
            "binding": {},
        }
    return {"topology_id": "", "binding_source": "", "binding_source_label": "", "binding": {}}


def _topology_name_map(project_id: str) -> Dict[str, str]:
    from services.ops.helpers import _list_topologies

    out: Dict[str, str] = {}
    for item in _list_topologies(project_id, None):
        tid = str(item.get("topology_id") or "").strip()
        if tid:
            out[tid] = str(item.get("name") or tid).strip()
    return out


def _binding_scope_label(binding: Dict[str, Any], channel_names: Dict[str, str]) -> str:
    env_labels = {"development": "开发", "testing": "测试", "staging": "预发", "production": "生产"}
    parts: List[str] = []
    env_key = str(binding.get("env_key") or "").strip()
    channel_id = str(binding.get("channel_id") or "").strip()
    platform = str(binding.get("platform") or "").strip()
    version_name = str(binding.get("version_name") or "").strip()
    if env_key:
        parts.append(env_labels.get(env_key, env_key))
    else:
        parts.append("全部环境")
    if channel_id:
        parts.append(channel_names.get(channel_id, channel_id))
    else:
        parts.append("全部渠道")
    if platform:
        parts.append(platform.upper())
    if version_name:
        parts.append(version_name)
    return " / ".join(parts)


def build_topology_binding_picker(
    project_id: str,
    env_key: str,
    channel_id: str,
    *,
    platform: str = "",
    version_name: str = "",
) -> Dict[str, Any]:
    from models.data import get_channels_for_project
    from services.ops.helpers import _env_label, _list_topologies, _runtime_active_for_scope
    from services.release.scope_resolver import resolve_scope, resolve_topology_binding_for_scope

    pid = str(project_id or "").strip()
    ek = normalize_release_env_key(env_key) if env_key else ""
    cid = str(channel_id or "").strip()
    plat = str(platform or "").strip().lower()
    vname = str(version_name or "").strip()
    scope = resolve_scope(pid, ek, cid, platform=plat, auto_create=False)
    resolved_raw = resolve_topology_binding_for_scope(scope or {}, vname) if scope else resolve_topology_binding(
        pid, ek, cid, platform=plat, version_name=vname
    )
    resolved_tid = str(resolved_raw.get("topology_id") or "").strip()
    name_map = _topology_name_map(pid)
    channel_names = {
        str(item.get("id") or "").strip(): str(item.get("name") or item.get("id") or "").strip()
        for item in (get_channels_for_project(pid) or [])
        if str(item.get("id") or "").strip()
    }
    bindings = list_topology_bindings(pid)
    refs_by_topology: Dict[str, List[Dict[str, Any]]] = {}
    for binding in bindings:
        tid = str(binding.get("topology_id") or "").strip()
        if not tid:
            continue
        refs_by_topology.setdefault(tid, []).append(
            {
                "binding_id": binding.get("binding_id"),
                "level": binding.get("level"),
                "level_label": binding.get("level_label"),
                "env_key": binding.get("env_key"),
                "channel_id": binding.get("channel_id"),
                "platform": binding.get("platform"),
                "version_name": binding.get("version_name"),
                "scope_label": _binding_scope_label(binding, channel_names),
            }
        )
    topologies_out: List[Dict[str, Any]] = []
    env_seen = set()
    status_seen = set()
    for topo in _list_topologies(pid, None):
        tid = str(topo.get("topology_id") or "").strip()
        if not tid:
            continue
        topo_env = str(topo.get("env_key") or "").strip()
        status = str(topo.get("status") or "draft").strip().lower()
        env_seen.add(topo_env)
        status_seen.add(status)
        runtime_env = topo_env or ek
        runtime = _runtime_active_for_scope(pid, runtime_env, tid)
        binding_refs = refs_by_topology.get(tid, [])
        is_current_hit = tid == resolved_tid
        is_same_env = bool(topo_env and ek and topo_env == ek)
        node_count = int(topo.get("node_count") or 0)
        selectable = status != "archived"
        topologies_out.append(
            {
                "topology_id": tid,
                "name": str(topo.get("name") or tid).strip(),
                "env_key": topo_env,
                "env_label": str(topo.get("env_label") or _env_label(topo_env)).strip(),
                "status": status,
                "status_label": _status_label(status),
                "is_default": bool(topo.get("is_default")),
                "node_count": node_count,
                "edge_count": int(topo.get("edge_count") or 0),
                "updated_at": str(topo.get("updated_at") or "").strip(),
                "owner": str(topo.get("owner") or "").strip(),
                "runtime": {
                    "active": bool(runtime.get("active")),
                    "run_id": str(runtime.get("run_id") or "").strip(),
                    "reason": str(runtime.get("reason") or "").strip(),
                },
                "binding_refs": binding_refs,
                "binding_ref_count": len(binding_refs),
                "bundle_ref_count": 0,
                "flags": {
                    "is_current_hit": is_current_hit,
                    "is_same_env": is_same_env,
                    "selectable": selectable,
                    "warn_empty_nodes": node_count <= 0,
                },
            }
        )

    def _sort_key(item: Dict[str, Any]) -> tuple:
        flags = item.get("flags") if isinstance(item.get("flags"), dict) else {}
        runtime = item.get("runtime") if isinstance(item.get("runtime"), dict) else {}
        return (
            0 if flags.get("is_current_hit") else 1,
            0 if flags.get("is_same_env") else 1,
            0 if runtime.get("active") else 1,
            item.get("binding_ref_count") or 0,
            str(item.get("updated_at") or ""),
        )

    topologies_out.sort(key=_sort_key)
    resolved_binding = resolved_raw.get("binding") if isinstance(resolved_raw.get("binding"), dict) else {}
    return {
        "scope": {
            "project_id": pid,
            "env_key": ek,
            "channel_id": cid,
            "platform": plat,
            "scope_id": str(scope.get("scope_id") or "").strip() if scope else "",
            "channel_name": channel_names.get(cid, cid),
        },
        "resolved": {
            "topology_id": resolved_tid,
            "topology_name": name_map.get(resolved_tid, resolved_tid),
            "binding_source": str(resolved_raw.get("binding_source") or "").strip(),
            "binding_source_label": str(resolved_raw.get("binding_source_label") or "").strip(),
            "binding_id": str(resolved_binding.get("binding_id") or "").strip(),
        },
        "topologies": topologies_out,
        "filters": {
            "environments": sorted(
                [{"env_key": key, "label": _env_label(key)} for key in env_seen if key],
                key=lambda x: x["env_key"],
            ),
            "statuses": sorted(
                [{"value": key, "label": _status_label(key)} for key in status_seen if key],
                key=lambda x: x["value"],
            ),
        },
    }
