# -*- coding: utf-8 -*-
"""Release order submodule."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from models.data import get_channel_by_id, get_channels_for_project, project_versions_db, projects_db
from data.delivery_scope import get_channels_for_env, get_platform_defs_for_env, is_channel_allowed_for_env
from data.platforms import get_platform_defs_for_project, is_platform_enabled_for_project, is_valid_platform_id
from models.db import _db_lock, _get_conn, get_cursor, init_db
from services.release.bundle_service import find_active_bundle, list_publishable_bundles, run_scope_precheck
from services.release.env_registry import list_project_env_keys, normalize_release_env_key, project_env_label
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.scope_resolver import resolve_network_profile, resolve_scope, resolve_topology_binding_for_scope
from services.release.topology_binding_service import resolve_topology_binding, upsert_topology_binding
from services.release.storage import find_manifest
from services.release.order_constants import EDITABLE_PLAN_FIELDS, PUBLISHABLE_STATUSES, TERMINAL_STATUSES
from services.release.order_diagnostics import _build_pipeline_snapshot, _pipeline_build_ready, summarize_order_diagnostic_issues
from services.release.order_helpers import (
    _artifact_rows,
    _bundle_id,
    _channel_name,
    _decode,
    _event,
    _find_version,
    _json,
    _now_iso,
    _order_id,
)


def _order_build_sync():
    import services.release.order_build_sync as mod
    return mod
def _order_from_row(row, *, include_details: bool = False) -> Dict[str, Any]:
    payload = _decode(row["payload"], {}) or {}
    scope_row = _get_conn().execute(
        "SELECT active_bundle_id FROM release_scopes WHERE scope_id=?",
        (row["scope_id"],),
    ).fetchone()
    result = {
        "release_order_id": row["release_order_id"],
        "project_id": row["project_id"],
        "env_key": row["env_key"],
        "channel_id": row["channel_id"],
        "channel_name": _channel_name(row["channel_id"]),
        "platform": row["platform"],
        "version_id": row["version_id"],
        "version_name": row["version_name"],
        "version_code": row["version_code"],
        "scope_id": row["scope_id"],
        "topology_id": row["topology_id"],
        "topology_binding_source": row["topology_binding_source"],
        "runtime_run_id": row["runtime_run_id"],
        "bundle_id": row["bundle_id"],
        "active_bundle_id": str(scope_row["active_bundle_id"] or "") if scope_row else "",
        "status": row["status"],
        "reason": row["reason"],
        "created_by": row["created_by"],
        "approved_by": row["approved_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "published_at": row["published_at"],
        "payload": payload,
    }
    if include_details:
        order_id = row["release_order_id"]
        conn = _get_conn()
        result["events"] = [
            {
                **dict(event),
                "payload": _decode(event["payload"], {}) or {},
            }
            for event in conn.execute(
                "SELECT * FROM release_order_events WHERE release_order_id=? ORDER BY id DESC", (order_id,)
            ).fetchall()
        ]
        result["artifacts"] = [
            {**dict(item), "payload": _decode(item["payload"], {}) or {}}
            for item in conn.execute(
                "SELECT * FROM release_order_artifacts WHERE release_order_id=? ORDER BY id", (order_id,)
            ).fetchall()
        ]
        precheck = conn.execute(
            "SELECT * FROM release_order_prechecks WHERE release_order_id=? ORDER BY id DESC LIMIT 1", (order_id,)
        ).fetchone()
        result["latest_precheck"] = (
            {"ok": bool(precheck["ok"]), "payload": _decode(precheck["payload"], {}) or {}, "created_at": precheck["created_at"]}
            if precheck
            else {}
        )
        result["approvals"] = [dict(item) for item in conn.execute(
            "SELECT * FROM release_approvals WHERE release_order_id=? ORDER BY created_at DESC", (order_id,)
        ).fetchall()]
        precheck_payload = (result.get("latest_precheck") or {}).get("payload") or {}
        pipeline_snapshot = _build_pipeline_snapshot(
            str(row["project_id"]),
            str(row["version_id"] or ""),
            str(row["channel_id"] or ""),
        )
        if pipeline_snapshot:
            result["pipeline_snapshot"] = pipeline_snapshot
        result["diagnostic_issues"] = summarize_order_diagnostic_issues(
            result,
            precheck_payload,
            pipeline_snapshot=pipeline_snapshot,
        )
    return result




def list_release_orders(project_id: str, filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    init_db()
    filters = filters or {}
    sql = "SELECT * FROM release_orders WHERE project_id=?"
    params: List[str] = [project_id]
    for key in ("env_key", "channel_id", "platform", "version_name", "version_code", "status"):
        value = str(filters.get(key) or "").strip()
        if value and value != "all":
            sql += f" AND {key}=?"
            params.append(value)
    sql += " ORDER BY updated_at DESC"
    with _db_lock:
        rows = _get_conn().execute(sql, params).fetchall()
    _order_build_sync().sync_building_release_orders(project_id)
    with _db_lock:
        rows = _get_conn().execute(sql, params).fetchall()
    return [_order_from_row(row) for row in rows]


def get_release_order(project_id: str, order_id: str, *, include_details: bool = True) -> Dict[str, Any]:
    init_db()
    with _db_lock:
        row = _get_conn().execute(
            "SELECT * FROM release_orders WHERE project_id=? AND release_order_id=?",
            (project_id, order_id),
        ).fetchone()
    if not row:
        return {}
    if str(row["status"] or "") == "building":
        _order_build_sync().sync_release_order_build_status(project_id, order_id)
        with _db_lock:
            row = _get_conn().execute(
                "SELECT * FROM release_orders WHERE project_id=? AND release_order_id=?",
                (project_id, order_id),
            ).fetchone()
    return _order_from_row(row, include_details=include_details) if row else {}


def find_draft_release_order(project_id: str, version_id: str) -> Optional[Dict[str, Any]]:
    vid = str(version_id or "").strip()
    if not vid:
        return None
    for row in list_release_orders(project_id):
        if str(row.get("version_id") or "") != vid:
            continue
        if str(row.get("status") or "") in {"draft", "artifacts_ready", "precheck_failed"}:
            return row
    return None


def ensure_draft_release_order(
    project_id: str,
    version_id: str,
    actor: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Return an existing editable draft for `version_id`, or auto-create one.

    Build entry points (workspace, release-order page) use this so users always
    arrive at a draft order whose build params come from the version group.
    """
    existing = find_draft_release_order(project_id, version_id)
    if existing:
        return existing
    vrow = _find_version(project_id, version_id)
    if not vrow:
        raise ValueError("VersionCode 不存在")
    env_key = normalize_release_env_key(
        vrow.get("env_key") or vrow.get("stage") or "development",
        project_id=project_id,
    )
    channel_id = resolve_channel_id(project_id, str(vrow.get("channel") or vrow.get("channel_id") or "")) or str(
        vrow.get("channel") or vrow.get("channel_id") or ""
    )
    payload = {
        "env_key": env_key,
        "channel_id": channel_id,
        "platform": str(vrow.get("platform") or "android").strip().lower(),
        "version_id": str(vrow.get("id") or ""),
        "version_code": str(vrow.get("version_code") or ""),
        "reason": reason or f"快速构建 - {vrow.get('version_name') or ''} {vrow.get('version_code') or ''}",
        "owner": actor,
    }
    return create_release_order(project_id, payload, actor)


def create_release_order(project_id: str, payload: Dict[str, Any], actor: str) -> Dict[str, Any]:
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    env_key = normalize_release_env_key(payload.get("env_key"), project_id=project_id)
    channel_id = str(payload.get("channel_id") or "").strip()
    platform = str(payload.get("platform") or "").strip().lower()
    version_id = str(payload.get("version_id") or "").strip()
    version_code = str(payload.get("version_code") or "").strip()
    if not channel_id or not is_platform_enabled_for_project(project_id, platform):
        raise ValueError("环境、渠道和平台必须精确选择")
    version = _find_version(project_id, version_id, version_code)
    if not version:
        raise ValueError("VersionCode 不存在")
    if str(version.get("platform") or "android").lower() != platform:
        raise ValueError("平台与 VersionCode 不一致")
    version_env_key = normalize_release_env_key(
        version.get("env_key") or version.get("stage") or version.get("env"),
        project_id=project_id,
    )
    version_channel_raw = str(version.get("channel_id") or version.get("channel") or "").strip()
    version_channel_id = resolve_channel_id(project_id, version_channel_raw) or version_channel_raw
    order_channel_id = resolve_channel_id(project_id, channel_id) or channel_id
    if version_env_key != env_key or version_channel_id != order_channel_id:
        raise ValueError("VersionCode 与发布单的环境或渠道不一致")
    from services.release.release_policy_service import apply_release_defaults_to_payload

    payload = apply_release_defaults_to_payload(project_id, env_key, dict(payload or {}))
    order_id = _order_id()
    now = _now_iso()
    artifacts = _artifact_rows(version)
    has_artifacts = all(url or path for _, url, path in artifacts[:3])
    status = "artifacts_ready" if has_artifacts else "draft"
    scope = resolve_scope(project_id, env_key, channel_id, platform=platform, auto_create=True)
    binding = resolve_topology_binding_for_scope(scope, str(version.get("version_name") or ""))
    record_payload = {
        "reason": str(payload.get("reason") or ""),
        "version_snapshot": version,
        "topology_binding_snapshot": binding,
        "build_job_id": str(version.get("jenkins_job_id") or ""),
    }
    for key in EDITABLE_PLAN_FIELDS:
        if key in payload:
            record_payload[key] = payload.get(key)
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO release_orders (
                release_order_id, project_id, env_key, channel_id, platform, version_id,
                version_name, version_code, scope_id, topology_id, topology_binding_source,
                runtime_run_id, bundle_id, status, reason, payload, created_by, approved_by,
                created_at, updated_at, published_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                order_id, project_id, env_key, channel_id, platform, str(version.get("id") or ""),
                str(version.get("version_name") or ""), str(version.get("version_code") or ""),
                str(scope.get("scope_id") or ""), str(binding.get("topology_id") or ""),
                str(binding.get("binding_source") or ""), "", "", status, str(payload.get("reason") or ""),
                _json(record_payload), actor, "", now, now, "",
            ),
        )
        for artifact_type, url, path in artifacts:
            cur.execute(
                """
                INSERT INTO release_order_artifacts (
                    release_order_id, artifact_type, artifact_url, artifact_path, status, payload, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (order_id, artifact_type, url, path, "registered" if url or path else "missing", "{}", now, now),
            )
        _event(cur, order_id, "created", actor, "", status, {"scope_id": scope.get("scope_id"), "topology_id": binding.get("topology_id")})
    return get_release_order(project_id, order_id)


def _transition(project_id: str, order_id: str, actor: str, to_status: str, event_type: str, payload=None, **fields) -> Dict[str, Any]:
    current = get_release_order(project_id, order_id, include_details=False)
    if not current:
        raise ValueError("发布单不存在")
    sets = ["status=?", "updated_at=?"]
    params: List[Any] = [to_status, _now_iso()]
    for key, value in fields.items():
        if key not in {"scope_id", "topology_id", "topology_binding_source", "runtime_run_id", "bundle_id", "approved_by", "published_at"}:
            continue
        sets.append(f"{key}=?")
        params.append(value)
    params.extend([project_id, order_id])
    with get_cursor() as cur:
        cur.execute(f"UPDATE release_orders SET {', '.join(sets)} WHERE project_id=? AND release_order_id=?", params)
        _event(cur, order_id, event_type, actor, current["status"], to_status, payload)
    return get_release_order(project_id, order_id)


def update_release_order(project_id: str, order_id: str, payload: Dict[str, Any], actor: str) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        raise ValueError("发布单不存在")
    if order["status"] not in {"draft", "artifacts_ready", "precheck_failed"}:
        raise ValueError("发布单进入预检或执行阶段后不可编辑")
    from services.release.release_policy_service import apply_release_defaults_to_payload

    env_key = str(order.get("env_key") or "").strip()
    payload = apply_release_defaults_to_payload(project_id, env_key, dict(payload or {}))
    reason = str(payload.get("reason") if "reason" in payload else order.get("reason") or "").strip()
    record_payload = dict(order.get("payload") or {})
    for key in EDITABLE_PLAN_FIELDS:
        if key in payload:
            record_payload[key] = payload.get(key)
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute(
            "UPDATE release_orders SET reason=?, payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (reason, _json(record_payload), now, project_id, order_id),
        )
        cur.execute("DELETE FROM release_order_prechecks WHERE release_order_id=?", (order_id,))
        cur.execute(
            "UPDATE release_approvals SET status='invalidated', updated_at=? WHERE release_order_id=? AND status='pending'",
            (now, order_id),
        )
        _event(cur, order_id, "draft_updated", actor, order["status"], order["status"], {"changed_fields": sorted(payload.keys())})
    return get_release_order(project_id, order_id)

def find_release_order_for_version(project_id: str, version_id: str) -> Optional[Dict[str, Any]]:
    """Latest non-terminal release order for a VersionCode (for hub/matrix actions)."""
    vid = str(version_id or "").strip()
    if not vid:
        return None
    terminal = TERMINAL_STATUSES | {"cancelled"}
    candidates = [
        row
        for row in list_release_orders(project_id)
        if str(row.get("version_id") or "") == vid and str(row.get("status") or "") not in terminal
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""))

def cancel_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if order.get("status") in TERMINAL_STATUSES or order.get("status") == "published":
        raise ValueError("当前发布单不可取消")
    return _transition(project_id, order_id, actor, "cancelled", "cancelled")


def context_options(project_id: str, env_key: str = "") -> Dict[str, Any]:
    versions = []
    seen_versions = set()
    for source in project_versions_db.get(project_id) or []:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        row["env_key"] = normalize_release_env_key(row.get("env_key") or row.get("stage") or row.get("env"))
        row["channel_id"] = str(row.get("channel_id") or row.get("channel") or "").strip()
        row["platform"] = str(row.get("platform") or "android").strip().lower()
        identity = (
            row["env_key"],
            row["channel_id"],
            row["platform"],
            str(row.get("version_name") or ""),
            str(row.get("version_code") or ""),
        )
        if identity in seen_versions:
            continue
        seen_versions.add(identity)
        versions.append(row)
    ek = normalize_release_env_key(env_key, project_id=project_id) if env_key else ""
    if ek:
        channels = [
            {"channel_id": str(row.get("id") or ""), "channel_name": str(row.get("name") or row.get("id") or "")}
            for row in get_channels_for_env(project_id, ek)
        ]
        platforms = get_platform_defs_for_env(project_id, ek)
    else:
        channels = [
            {"channel_id": str(row.get("id") or ""), "channel_name": str(row.get("name") or row.get("id") or "")}
            for row in get_channels_for_project(project_id)
        ]
        platforms = get_platform_defs_for_project(project_id)
    return {
        "project_id": project_id,
        "env_key": ek,
        "environments": [
            {"env_key": key, "label": project_env_label(project_id, key)}
        for key in list_project_env_keys(project_id)
        ],
        "channels": channels,
        "platforms": platforms,
        "versions": versions,
    }
