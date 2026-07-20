# -*- coding: utf-8 -*-
"""Release order state machine for the unified project delivery workflow."""

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
    sync_building_release_orders(project_id)
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
        sync_release_order_build_status(project_id, order_id)
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


def quick_build_version(project_id: str, version_id: str, actor: str, *, force: bool = False) -> Dict[str, Any]:
    """Ensure a draft release order and trigger Jenkins (Dev fast path).

    Returns the updated order. If artifacts are already ready, returns the draft
    without re-triggering unless ``force=True``.
    """
    draft = ensure_draft_release_order(
        project_id,
        version_id,
        actor,
        reason=f"快速构建 - {actor}",
    )
    status = str(draft.get("status") or "")
    order_id = str(draft.get("release_order_id") or "")
    if status == "building":
        return get_release_order(project_id, order_id) or draft
    if status in TERMINAL_STATUSES:
        raise ValueError("当前发布单已结束，请从版本代码发起新的交付尝试")
    if status == "artifacts_ready" and not force:
        return draft
    if status == "artifacts_ready" and force:
        return request_build(project_id, order_id, actor)
    env_key = normalize_release_env_key(draft.get("env_key") or "development", project_id=project_id)
    from services.release.release_policy_service import (
        FORM_DEPTH_MINIMAL,
        get_env_release_policy,
        get_required_plan_fields,
    )

    policy = get_env_release_policy(project_id, env_key)
    if str(policy.get("form_depth") or "") != FORM_DEPTH_MINIMAL:
        payload = dict(draft.get("payload") or {})
        missing: List[str] = []
        for field in get_required_plan_fields(project_id, env_key):
            if field in {"reason", "owner"}:
                val = draft.get("reason") if field == "reason" else payload.get("owner") or draft.get("created_by")
            else:
                val = payload.get(field)
            if not str(val or "").strip():
                missing.append(field)
        if missing:
            raise ValueError("请先完善发布计划后再触发构建")
    return request_build(project_id, order_id, actor)


def quick_publish_delivery(
    project_id: str,
    env_key: str,
    channel_id: str,
    platform: str,
    version_id: str,
    actor: str,
    *,
    skip_build: bool = False,
    force_build: bool = False,
    auto_verify: bool = True,
) -> Dict[str, Any]:
    """Dev/prod unified shortcut: ensure order → (optional) build → precheck → publish → verify.

    Returns early with ``phase`` when waiting on build or production approval.
    """
    vid = str(version_id or "").strip()
    plat = str(platform or "").strip().lower()
    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = str(channel_id or "").strip()
    if not vid or not plat or not cid:
        raise ValueError("env_key、channel_id、platform、version_id 必填")
    order = ensure_draft_release_order(project_id, vid, actor, reason="一键发版")
    order_id = str(order.get("release_order_id") or "")
    status = str(order.get("status") or "")
    if status == "building":
        return {"phase": "building", "release_order_id": order_id, "order": order}
    if status == "build_failed":
        if skip_build:
            raise ValueError("构建已失败，请重新触发构建")
        order = request_build(project_id, order_id, actor)
        return {"phase": "building", "release_order_id": order_id, "order": order}
    if status in {"draft", "precheck_failed"} and not skip_build:
        order = quick_build_version(project_id, vid, actor, force=force_build)
        status = str(order.get("status") or "")
        order_id = str(order.get("release_order_id") or order_id)
        if status == "building":
            return {"phase": "building", "release_order_id": order_id, "order": order}
    if status not in {"artifacts_ready", "ready", "approved", "awaiting_approval", "precheck_failed", "published"}:
        if status == "draft" and skip_build:
            raise ValueError("产物未就绪，无法跳过构建直接发布")
    order = get_release_order(project_id, order_id) or order
    status = str(order.get("status") or "")
    if status in {"draft", "artifacts_ready", "precheck_failed"}:
        order = precheck_release_order(project_id, order_id, actor)
        status = str(order.get("status") or "")
    if status == "awaiting_approval":
        return {"phase": "awaiting_approval", "release_order_id": order_id, "order": order}
    if status in {"ready", "approved"}:
        order = publish_release_order(project_id, order_id, actor)
        status = str(order.get("status") or "")
    if status == "published" and auto_verify:
        order = verify_release_order(project_id, order_id, actor, ok=True)
    return {"phase": str(order.get("status") or status), "release_order_id": order_id, "order": order}


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


def request_build(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        raise ValueError("发布单不存在")
    if order.get("status") in TERMINAL_STATUSES:
        raise ValueError("当前发布单不可重新构建")
    version = _find_version(project_id, order["version_id"], order["version_code"])
    plan = dict(order.get("payload") or {})
    from services.admin.version_service import (
        resolve_effective_pipeline,
        resolve_effective_jenkins,
    )

    effective_pipeline = resolve_effective_pipeline(project_id, version)
    if not effective_pipeline:
        raise ValueError("版本组管线模板尚未配置；请前往版本组「配置管线」完成 Jenkins 实例、Job 与四步流水线后再触发构建。")
    version_for_build = dict(version)
    version_for_build["pipeline"] = effective_pipeline
    from services.commercial_release_plan import plan_defaults_from_pipeline, plan_to_jenkins_params

    plan_defaults = plan_defaults_from_pipeline(version_for_build, project_id=project_id)
    plan_filepath = str(plan.get("release_plan_file") or "release_order_inline.json")
    params, _ = plan_to_jenkins_params(plan_defaults, plan_filepath, version_for_build, project_id=project_id)
    if not params:
        raise ValueError("无法从版本组管线推导 Jenkins 构建参数；请检查管线配置是否完整。")
    jenkins_binding = resolve_effective_jenkins(project_id, version_for_build)
    instance_id = jenkins_binding.get("jenkins_instance_id") or ""
    if not instance_id:
        raise ValueError("当前版本组未配置 Jenkins 实例。请在「配置管线」选择 Jenkins 实例后再触发构建。")
    resolved_job = jenkins_binding.get("jenkins_job_id") or ""
    params["VERSION_NAME"] = str(order["version_name"])
    params["VERSION_CODE"] = str(order["version_code"])
    params["CHANNEL"] = str(order["channel_name"])
    from services import jenkins as jenkins_svc
    from services import jenkins_manager as jm
    ok, prep_error = jm.prepare_instance_for_project_build(
        instance_id,
        project_id,
        git_branch=str(params.get("GIT_BRANCH") or ""),
    )
    if not ok:
        raise ValueError(prep_error or "同步项目构建配置到 Jenkins 失败")
    base_url = jm.get_jenkins_url_for_instance(instance_id=instance_id)
    builds_dir = jm.get_builds_dir_for_instance(instance_id=instance_id)
    success, build_number, error = jenkins_svc.trigger_build(
        params,
        base_url=base_url,
        builds_dir=builds_dir,
        instance_id=instance_id,
    )
    if not success:
        raise ValueError(error or "触发 Jenkins 构建失败")
    from models.data import record_build_version
    record_build_version(instance_id, int(build_number), order["version_id"], project_id)
    payload = dict(order.get("payload") or {})
    payload.update({
        "build_job_id": str(build_number),
        "jenkins_instance_id": instance_id,
        "jenkins_job": resolved_job,
        "jenkins_params": params,
        "pipeline_source": "version_group",
    })
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute(
            "UPDATE release_orders SET status='building', payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (_json(payload), now, project_id, order_id),
        )
        _event(
            cur,
            order_id,
            "build_requested",
            actor,
            order["status"],
            "building",
            {"build_number": build_number, "jenkins_instance_id": instance_id},
        )
    return get_release_order(project_id, order_id)


def sync_release_order_build_status(project_id: str, order_id: str, *, actor: str = "system") -> Dict[str, Any]:
    """When Jenkins build finishes, advance building → artifacts_ready and refresh artifacts."""
    init_db()
    with _db_lock:
        row = _get_conn().execute(
            "SELECT * FROM release_orders WHERE project_id=? AND release_order_id=?",
            (project_id, order_id),
        ).fetchone()
    if not row or str(row["status"] or "") != "building":
        return _order_from_row(row, include_details=False) if row else {}
    order = _order_from_row(row, include_details=False)
    payload = dict(order.get("payload") or {})
    build_number = str(payload.get("build_job_id") or "").strip()
    instance_id = str(payload.get("jenkins_instance_id") or "").strip()
    if not build_number or not instance_id:
        return order
    try:
        from services import jenkins as jenkins_svc
        from services import jenkins_manager as jm

        base_url = jm.get_jenkins_url_for_instance(instance_id=instance_id)
        builds_dir = jm.get_builds_dir_for_instance(instance_id=instance_id)
        st = jenkins_svc.get_build_status(
            int(build_number),
            base_url=base_url,
            builds_dir=builds_dir,
            instance_id=instance_id,
        )
    except Exception:
        return order
    if st.get("building"):
        return order
    result = str(st.get("status") or "").upper()
    if result != "SUCCESS":
        fail_status = "build_failed"
        fail_payload = {
            "build_number": build_number,
            "jenkins_result": result,
            "failure_summary": str(st.get("error") or result or "BUILD_FAILED"),
        }
        now = _now_iso()
        with get_cursor() as cur:
            cur.execute(
                "UPDATE release_orders SET status=?, updated_at=? WHERE project_id=? AND release_order_id=?",
                (fail_status, now, project_id, order_id),
            )
            _event(cur, order_id, "build_failed", actor, "building", fail_status, fail_payload)
        return get_release_order(project_id, order_id, include_details=False)
    try:
        from services.apk_artifact_service import finalize_apk_from_jenkins_build

        finalize_apk_from_jenkins_build(instance_id, int(build_number))
    except Exception:
        pass
    version = _find_version(project_id, order["version_id"], order["version_code"])
    if not version:
        return order
    artifacts = _artifact_rows(version)
    now = _now_iso()
    with get_cursor() as cur:
        for artifact_type, url, path in artifacts:
            cur.execute(
                """
                UPDATE release_order_artifacts
                SET artifact_url=?, artifact_path=?, status=?, updated_at=?
                WHERE release_order_id=? AND artifact_type=?
                """,
                (
                    url,
                    path,
                    "registered" if url or path else "missing",
                    now,
                    order_id,
                    artifact_type,
                ),
            )
        cur.execute(
            "UPDATE release_orders SET status='artifacts_ready', updated_at=? WHERE project_id=? AND release_order_id=?",
            (now, project_id, order_id),
        )
        _event(cur, order_id, "build_completed", actor, "building", "artifacts_ready", {"build_number": build_number})
    return get_release_order(project_id, order_id, include_details=False)


def sync_building_release_orders(project_id: str = "", *, actor: str = "system") -> List[Dict[str, Any]]:
    """Poll Jenkins for all in-flight release-order builds (proactive sync)."""
    init_db()
    sql = "SELECT project_id, release_order_id FROM release_orders WHERE status='building'"
    params: List[str] = []
    if project_id:
        sql += " AND project_id=?"
        params.append(str(project_id).strip())
    with _db_lock:
        rows = _get_conn().execute(sql, params).fetchall()
    updated: List[Dict[str, Any]] = []
    for row in rows:
        pid = str(row["project_id"] or "")
        oid = str(row["release_order_id"] or "")
        if not pid or not oid:
            continue
        synced = sync_release_order_build_status(pid, oid, actor=actor)
        if synced:
            updated.append(synced)
    return updated


def _scope_query_suffix(order: Dict[str, Any]) -> str:
    from urllib.parse import urlencode

    params = {
        key: str(order.get(key) or "").strip()
        for key in ("env_key", "channel_id", "platform", "version_id", "version_name", "version_code", "release_order_id")
        if str(order.get(key) or "").strip()
    }
    qs = urlencode(params)
    return f"?{qs}" if qs else ""


def _order_needs_jenkins_build(order: Dict[str, Any]) -> bool:
    for row in order.get("artifacts") or []:
        status = str(row.get("status") or "").lower()
        if status in {"missing", "unreachable", "invalid"}:
            return True
        if not str(row.get("artifact_path") or row.get("artifact_url") or "").strip():
            artifact_type = str(row.get("artifact_type") or "").lower()
            if artifact_type in {"code", "apk", "resource", "config"}:
                return True
    return False


def resolve_release_order_next_action(project_id: str, order_id: str) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=True)
    if not order:
        raise ValueError("发布单不存在")
    status = str(order.get("status") or "")
    ctx = _scope_query_suffix(order)
    base = f"/admin/projects/{project_id}/release-orders/{order_id}"
    edit_href = f"{base}/edit{ctx}"
    build_history_href = (
        f"/admin/projects/{project_id}/build-history"
        f"?env_key={order.get('env_key')}&channel_id={order.get('channel_id')}"
        f"&platform={order.get('platform')}&version_id={order.get('version_id')}&scoped=1"
    )
    phase_map = {
        "draft": 0,
        "cancelled": 0,
        "building": 1,
        "artifacts_ready": 1,
        "prechecking": 2,
        "precheck_failed": 2,
        "ready": 2,
        "awaiting_approval": 2,
        "approved": 2,
        "publishing": 2,
        "published": 2,
        "verifying": 2,
        "verified": 2,
        "verify_failed": 2,
        "rolled_back": 2,
        "publish_failed": 2,
    }
    phase_index = phase_map.get(status, 0)
    more: List[Dict[str, Any]] = []
    terminal = status in TERMINAL_STATUSES or status in {"published", "verified", "cancelled"}

    def _primary(action: str, label: str, *, api_action: str = "", href: str = "", disabled: bool = False, reason: str = ""):
        return {
            "action": action,
            "label": label,
            "api_action": api_action,
            "href": href,
            "disabled": disabled,
            "reason": reason,
        }

    if status == "draft":
        primary = _primary("build", "下一步：触发构建", api_action="build")
        more.extend([
            {"action": "edit", "label": "编辑计划", "href": edit_href},
            {"action": "cancel", "label": "取消发布单", "api_action": "cancel"},
        ])
    elif status == "artifacts_ready":
        primary = _primary("precheck", "下一步：继续发版", api_action="precheck")
        more.extend([
            {"action": "build", "label": "重新构建", "api_action": "build"},
            {"action": "edit", "label": "编辑计划", "href": edit_href},
            {"action": "cancel", "label": "取消发布单", "api_action": "cancel"},
        ])
    elif status == "building":
        primary = _primary("view_build", "下一步：查看构建日志", href=build_history_href)
        more.append({"action": "cancel", "label": "取消发布单", "api_action": "cancel"})
    elif status == "precheck_failed":
        pipeline_snapshot = _build_pipeline_snapshot(project_id, str(order.get("version_id") or ""), str(order.get("channel_id") or ""))
        if _order_needs_jenkins_build(order) and _pipeline_build_ready(pipeline_snapshot):
            primary = _primary("build", "下一步：触发构建", api_action="build")
        else:
            primary = _primary("edit", "下一步：编辑计划", href=edit_href)
        more.extend([
            {"action": "precheck", "label": "重新预检", "api_action": "precheck"},
            {"action": "cancel", "label": "取消发布单", "api_action": "cancel"},
        ])
    elif status in {"ready", "approved"}:
        primary = _primary("publish", "下一步：执行发布", api_action="publish")
        more.extend([
            {"action": "precheck", "label": "重新预检", "api_action": "precheck"},
            {"action": "cancel", "label": "取消发布单", "api_action": "cancel"},
        ])
    elif status == "awaiting_approval":
        primary = _primary("approve", "下一步：审批通过", api_action="approve")
        more.append({"action": "cancel", "label": "取消发布单", "api_action": "cancel"})
    elif status == "published":
        primary = _primary("verify", "下一步：执行验证", api_action="verify")
        more.append({"action": "rollback", "label": "回滚", "api_action": "rollback"})
    elif status == "verify_failed":
        primary = _primary("verify", "下一步：重新验证", api_action="verify")
        if order.get("bundle_id") and order.get("active_bundle_id") and order.get("bundle_id") != order.get("active_bundle_id"):
            more.append({"action": "rollback", "label": "回滚", "api_action": "rollback"})
    elif status == "verified":
        primary = _primary("view", "已完成", disabled=True, reason="发布与验证已完成")
        if order.get("bundle_id") and order.get("active_bundle_id") and order.get("bundle_id") != order.get("active_bundle_id"):
            more.append({"action": "rollback", "label": "回滚", "api_action": "rollback"})
    elif status == "prechecking":
        primary = _primary("wait", "预检进行中…", disabled=True, reason="请等待预检完成")
    elif status == "publishing":
        primary = _primary("wait", "发布执行中…", disabled=True, reason="请等待发布完成")
    elif status == "verifying":
        primary = _primary("wait", "验证进行中…", disabled=True, reason="请等待验证完成")
    elif status == "cancelled":
        primary = _primary("view", "已取消", disabled=True, reason="发布单已取消")
    elif status == "rolled_back":
        primary = _primary("view", "已回滚", disabled=True, reason="已回滚到上一 Bundle")
    else:
        primary = _primary("view", "查看详情", disabled=True)

    if status in {"draft", "artifacts_ready", "precheck_failed", "ready"} and not terminal:
        more.insert(0, {"action": "precheck", "label": "执行预检", "api_action": "precheck"})

    return {
        "release_order_id": order_id,
        "status": status,
        "phase_index": phase_index,
        "phases": ["准备", "构建", "发版"],
        "primary": primary,
        "more": [item for item in more if item.get("action") != primary.get("action")],
    }


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


def resolve_delivery_actions(project_id: str, version_id: str) -> Dict[str, Any]:
    """BFF: primary/secondary actions for a VersionCode (versions hub + env matrix)."""
    from urllib.parse import urlencode
    from services.release.release_policy_service import (
        FORM_DEPTH_FULL,
        FORM_DEPTH_MINIMAL,
        assess_delivery_readiness,
        build_config_href,
        get_env_release_policy,
    )

    version = _find_version(project_id, version_id)
    if not version:
        raise ValueError("VersionCode 不存在")
    env_key = normalize_release_env_key(
        version.get("env_key") or version.get("stage") or "development",
        project_id=project_id,
    )
    ch_raw = str(version.get("channel_id") or version.get("channel") or "").strip()
    channel_id = resolve_channel_id(project_id, ch_raw) or ch_raw
    platform = str(version.get("platform") or "android").strip().lower()
    version_name = str(version.get("version_name") or "")
    version_code = str(version.get("version_code") or "")

    policy = get_env_release_policy(project_id, env_key)
    form_depth = str(policy.get("form_depth") or "")
    readiness = assess_delivery_readiness(project_id, version, env_key, channel_id, platform)
    pipeline_ready = bool(readiness.get("pipeline_ready"))
    artifact_ready = str(version.get("apk_status") or "") == "found"

    order = find_release_order_for_version(project_id, version_id) or find_draft_release_order(project_id, version_id)
    order_status = str(order.get("status") or "") if order else ""
    order_id = str(order.get("release_order_id") or "") if order else ""

    scope_params = {
        "env_key": env_key,
        "channel_id": channel_id,
        "platform": platform,
        "version_id": version_id,
        "version_name": version_name,
        "version_code": version_code,
    }
    if order_id:
        scope_params["release_order_id"] = order_id
    scope_qs = urlencode({k: v for k, v in scope_params.items() if v})

    pipeline_config_href = build_config_href(project_id, version)
    build_history_href = (
        f"/admin/projects/{project_id}/build-history?"
        f"{urlencode({'env_key': env_key, 'channel_id': channel_id, 'platform': platform, 'version_id': version_id, 'scoped': '1'})}"
    )
    detail_href = f"/admin/projects/{project_id}/release-orders/{order_id}?{scope_qs}" if order_id else ""
    edit_href = (
        f"/admin/projects/{project_id}/release-orders/{order_id}/edit?{scope_qs}"
        if order_id
        else f"/admin/projects/{project_id}/release-orders/start?{urlencode({**scope_params, 'intent': 'release'})}"
    )
    versions_href = f"/admin/projects/{project_id}/versions?{urlencode({'env_key': env_key, 'channel_id': channel_id, 'platform': platform})}"

    release_continue_statuses = {
        "artifacts_ready",
        "precheck_failed",
        "ready",
        "awaiting_approval",
        "approved",
        "published",
        "prechecking",
        "publishing",
        "verifying",
        "verify_failed",
        "publish_failed",
    }

    def _action(action: str, label: str, **extra: Any) -> Dict[str, Any]:
        row = {"action": action, "label": label}
        row.update({k: v for k, v in extra.items() if v is not None and v != ""})
        return row

    primary: Dict[str, Any]
    secondary: List[Dict[str, Any]] = []
    status_hint = ""

    if order_status == "building":
        primary = _action("view_build", "查看构建", href=detail_href or build_history_href)
        status_hint = "构建进行中 · 查看日志"
        secondary = [
            _action("build_history", "构建日志", href=build_history_href),
            _action("rebuild", "重新构建", api_action="rebuild", release_order_id=order_id, version_id=version_id),
        ]
    elif artifact_ready or order_status in release_continue_statuses:
        primary = _action(
            "continue_release",
            "继续发版",
            href=detail_href or f"/admin/projects/{project_id}/release-orders/start?{urlencode({**scope_params, 'intent': 'release'})}",
        )
        status_hint = "产物就绪 · 可继续发版"
        secondary = [
            _action("rebuild", "重新构建", api_action="rebuild", release_order_id=order_id, version_id=version_id),
            _action("build_history", "构建日志", href=build_history_href),
        ]
    elif not pipeline_ready:
        primary = _action("configure_pipeline", "配置管线", href=pipeline_config_href)
        status_hint = "管线未配置 · 先配置管线"
        secondary = [_action("versions", "版本代码", href=versions_href)]
    elif form_depth == FORM_DEPTH_FULL:
        primary = _action("edit_plan", "填写计划", href=edit_href)
        status_hint = "生产环境 · 请先填写发布计划"
        secondary = [_action("build_history", "构建产物", href=build_history_href)]
    elif form_depth == FORM_DEPTH_MINIMAL or pipeline_ready:
        primary = _action("trigger_build", "触发构建", api_action="quick_build", version_id=version_id)
        status_hint = "管线就绪 · 可触发构建"
        secondary = [
            _action("build_history", "构建产物", href=build_history_href),
            _action("versions", "版本代码", href=versions_href),
        ]
    else:
        primary = _action("edit_plan", "填写计划", href=edit_href)
        status_hint = "请先填写发布计划"
        secondary = [_action("build_history", "构建产物", href=build_history_href)]

    return {
        "version_id": version_id,
        "release_order_id": order_id,
        "release_order_status": order_status,
        "pipeline_ready": pipeline_ready,
        "artifact_ready": artifact_ready,
        "form_depth": form_depth,
        "status_hint": status_hint,
        "primary": primary,
        "secondary": secondary,
        "build_entry": {
            "label": "进入构建流程",
            "href": f"/admin/projects/{project_id}/environments/{env_key}/channels/{channel_id}/build?{urlencode({**scope_params, 'platform': platform})}",
            "enabled": True,
        },
        "release_entry": {
            "label": "进入发版流程",
            "href": f"/admin/projects/{project_id}/environments/{env_key}/channels/{channel_id}/release?{urlencode({**scope_params, 'platform': platform})}",
            "enabled": bool(artifact_ready or order_status in release_continue_statuses or order_id),
        },
        "scope": scope_params,
        "links": {
            "detail": detail_href,
            "edit": edit_href,
            "build_history": build_history_href,
            "build_config": pipeline_config_href,
            "versions": versions_href,
        },
    }


def enrich_delivery_line_actions(project_id: str, line: Dict[str, Any]) -> Dict[str, Any]:
    """Attach delivery action BFF payload to an environment delivery line."""
    out = dict(line or {})
    version_id = str(out.get("version_id") or "").strip()
    if not version_id:
        status_hint = "未配置 VersionCode · 请先新建 VC"
        out.update({
            "release_order_id": "",
            "release_order_status": "",
            "pipeline_ready": False,
            "artifact_ready": False,
            "status_hint": status_hint,
            "delivery_actions": {
                "primary": {"action": "create_vc", "label": "新建 VC", "href": ""},
                "secondary": [],
                "status_hint": status_hint,
            },
        })
        return out
    try:
        actions = resolve_delivery_actions(project_id, version_id)
    except ValueError:
        actions = {
            "release_order_id": "",
            "release_order_status": "",
            "pipeline_ready": False,
            "artifact_ready": False,
            "status_hint": "交付动作暂不可用",
            "primary": {"action": "versions", "label": "去版本代码", "href": ""},
            "secondary": [],
        }
    out["release_order_id"] = actions.get("release_order_id") or ""
    out["release_order_status"] = actions.get("release_order_status") or ""
    out["pipeline_ready"] = bool(actions.get("pipeline_ready"))
    out["artifact_ready"] = bool(actions.get("artifact_ready"))
    out["status_hint"] = actions.get("status_hint") or ""
    out["delivery_actions"] = {
        "primary": actions.get("primary") or {},
        "secondary": actions.get("secondary") or [],
        "status_hint": out["status_hint"],
        "scope": actions.get("scope") or {},
        "links": actions.get("links") or {},
    }
    return out


def precheck_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        raise ValueError("发布单不存在")
    version = _find_version(project_id, order["version_id"], order["version_code"])
    from services.admin.version_service import enrich_version_client_urls

    version = enrich_version_client_urls(project_id, version)
    scope = resolve_scope(project_id, order["env_key"], order["channel_id"], platform=order["platform"], auto_create=False)
    if not scope:
        raise ValueError("发布作用域不存在")
    plan = dict(order.get("payload") or {})
    target_topology_id = str(plan.get("target_topology_id") or "").strip()
    if target_topology_id:
        binding = {
            "topology_id": target_topology_id,
            "binding_source": "release_order_override",
            "binding_source_label": "发布单指定拓扑",
            "binding": {},
        }
        result = run_scope_precheck(scope, version, validate_artifacts=True)
        result["topology_id"] = target_topology_id
        result["binding_source"] = binding["binding_source"]
    else:
        binding = resolve_topology_binding_for_scope(scope, str(version.get("version_name") or ""))
        result = run_scope_precheck(scope, version, validate_artifacts=True)
    runtime_run_id = ""
    try:
        from services.ops.helpers import _runtime_active_for_scope
        runtime = _runtime_active_for_scope(project_id, order["env_key"], str(result.get("topology_id") or ""))
        if runtime.get("active"):
            runtime_run_id = str(runtime.get("run_id") or "")
    except Exception:
        runtime_run_id = ""
    result["runtime_run_id"] = runtime_run_id
    result["runtime_active"] = bool(runtime_run_id)
    if not runtime_run_id:
        result["ok"] = False
        result["runtime_error"] = "目标拓扑没有运行中的 runtime"
    target = "awaiting_approval" if result.get("ok") and order["env_key"] == "production" else ("ready" if result.get("ok") else "precheck_failed")
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO release_order_prechecks (release_order_id, ok, payload, created_at) VALUES (?,?,?,?)",
            (order_id, 1 if result.get("ok") else 0, _json(result), now),
        )
        cur.execute(
            """
            UPDATE release_orders SET status=?, scope_id=?, topology_id=?, topology_binding_source=?, runtime_run_id=?,
            updated_at=? WHERE project_id=? AND release_order_id=?
            """,
            (
                target, str(result.get("scope_id") or ""), str(result.get("topology_id") or ""),
                str(result.get("binding_source") or ""), runtime_run_id, now, project_id, order_id,
            ),
        )
        _event(cur, order_id, "prechecked", actor, order["status"], target, result)
        if target == "awaiting_approval":
            cur.execute(
                """
                INSERT INTO release_approvals (
                    approval_id, release_order_id, status, requested_by, approved_by, note, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (f"ra-{uuid.uuid4().hex[:12]}", order_id, "pending", actor, "", "", now, now),
            )
    return get_release_order(project_id, order_id)


def approve_release_order(project_id: str, order_id: str, actor: str, note: str = "") -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if order.get("status") != "awaiting_approval":
        raise ValueError("当前发布单不在待审批状态")
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute(
            "UPDATE release_approvals SET status='approved', approved_by=?, note=?, updated_at=? WHERE release_order_id=? AND status='pending'",
            (actor, note, now, order_id),
        )
        cur.execute(
            "UPDATE release_orders SET status='approved', approved_by=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (actor, now, project_id, order_id),
        )
        _event(cur, order_id, "approved", actor, order["status"], "approved", {"note": note})
    return get_release_order(project_id, order_id)


def publish_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=True)
    if order.get("status") not in PUBLISHABLE_STATUSES:
        raise ValueError("发布单必须先通过预检和审批")
    if order["env_key"] == "production" and order.get("status") != "approved":
        raise ValueError("生产环境发布必须审批")
    version = _find_version(project_id, order["version_id"], order["version_code"])
    scope = resolve_scope(project_id, order["env_key"], order["channel_id"], platform=order["platform"], auto_create=False)
    if not scope:
        raise ValueError("发布作用域不存在")
    plan = dict(order.get("payload") or {})
    target_topology_id = str(plan.get("target_topology_id") or "").strip()
    if target_topology_id:
        topology_id = target_topology_id
        binding = {
            "topology_id": topology_id,
            "binding_source": "release_order_override",
            "binding_source_label": "发布单指定拓扑",
            "binding": {},
        }
        upsert_topology_binding(
            {
                "project_id": project_id,
                "env_key": order["env_key"],
                "channel_id": order["channel_id"],
                "platform": str(order.get("platform") or "").strip().lower(),
                "version_name": order["version_name"],
                "topology_id": topology_id,
            },
            actor=actor,
        )
    else:
        binding = resolve_topology_binding_for_scope(scope, order["version_name"])
        topology_id = str(binding.get("topology_id") or "")
    if not topology_id:
        raise ValueError("未命中拓扑绑定")
    profile, profile_source = resolve_network_profile(scope, order["version_name"])
    runtime_run_id = ""
    try:
        from services.ops.helpers import _runtime_active_for_scope
        runtime = _runtime_active_for_scope(project_id, order["env_key"], topology_id)
        runtime_run_id = str(runtime.get("run_id") or "") if runtime.get("active") else ""
    except Exception:
        runtime_run_id = ""
    if not runtime_run_id:
        raise ValueError("目标拓扑没有运行中的 runtime")
    now = _now_iso()
    bundle_id = _bundle_id(order["scope_id"])
    from services.release.bundle_service import build_client_bootstrap_snapshot

    client_snapshot = build_client_bootstrap_snapshot(version, scope)
    client_snapshot["artifacts"] = [
        {
            "artifact_type": str(item.get("artifact_type") or ""),
            "artifact_url": str(item.get("artifact_url") or ""),
            "artifact_path": str(item.get("artifact_path") or ""),
            "status": str(item.get("status") or ""),
        }
        for item in order.get("artifacts") or []
    ]
    bundle = {
        "bundle_id": bundle_id,
        "release_order_id": order_id,
        "project_id": project_id,
        "scope_id": order["scope_id"],
        "env_key": order["env_key"],
        "channel_id": order["channel_id"],
        "client": client_snapshot,
        "server": {
            "topology_id": topology_id,
            "runtime_run_id": runtime_run_id,
            "network_profile_snapshot": profile,
            "profile_source": profile_source,
            "binding_source": binding.get("binding_source"),
        },
        "publish_status": "published",
        "published_at": now,
        "published_by": actor,
        "created_at": now,
        "updated_at": now,
    }
    init_db()
    with get_cursor() as cur:
        active = cur.execute(
            "SELECT bundle_id, payload FROM release_bundles WHERE scope_id=? AND publish_status='published' AND platform=? ORDER BY published_at DESC LIMIT 1",
            (order["scope_id"], order["platform"]),
        ).fetchone()
        if active:
            previous = _decode(active["payload"], {}) or {}
            previous["publish_status"] = "superseded"
            previous["updated_at"] = now
            cur.execute(
                "UPDATE release_bundles SET publish_status='superseded', payload=?, updated_at=? WHERE bundle_id=?",
                (_json(previous), now, active["bundle_id"]),
            )
            bundle["supersedes_bundle_id"] = active["bundle_id"]
        else:
            bundle["supersedes_bundle_id"] = ""
        cur.execute(
            """
            INSERT INTO release_bundles (
                bundle_id, release_order_id, project_id, scope_id, env_key, channel_id,
                publish_status, topology_id, runtime_run_id, version_name, version_code,
                platform, payload, published_at, published_by, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                bundle_id, order_id, project_id, order["scope_id"], order["env_key"], order["channel_id"],
                "published", topology_id, runtime_run_id, order["version_name"], order["version_code"],
                order["platform"], _json(bundle), now, actor, now, now,
            ),
        )
        cur.execute(
            """
            UPDATE release_orders SET status='published', bundle_id=?, topology_id=?, runtime_run_id=?,
            topology_binding_source=?, published_at=?, updated_at=? WHERE project_id=? AND release_order_id=?
            """,
            (bundle_id, topology_id, runtime_run_id, str(binding.get("binding_source") or ""), now, now, project_id, order_id),
        )
        cur.execute(
            "UPDATE release_scopes SET active_bundle_id=?, updated_at=? WHERE scope_id=?",
            (bundle_id, now, order["scope_id"]),
        )
        _event(cur, order_id, "published", actor, order["status"], "published", {"bundle_id": bundle_id, "topology_id": topology_id, "runtime_run_id": runtime_run_id})
    published = get_release_order(project_id, order_id)
    if str(os.getenv("RELEASE_FEISHU_NOTIFY", "true")).lower() in ("true", "1", "yes"):
        try:
            from services.webhook import fire_feishu

            fire_feishu(
                "发布单已发布",
                (
                    f"project={project_id}\n"
                    f"order={order_id}\n"
                    f"version={published.get('version_name')}\n"
                    f"env={published.get('env_key')}\n"
                    f"actor={actor}\n"
                    f"bundle={published.get('bundle_id')}"
                ),
            )
        except Exception:
            pass
    return published


def run_bootstrap_smoke_for_order(project_id: str, order_id: str) -> Dict[str, Any]:
    """HTTP smoke against active bundle fields after publish (internal validation)."""
    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        raise ValueError("发布单不存在")
    scope_id = str(order.get("scope_id") or "").strip()
    bundle_id = str(order.get("bundle_id") or "").strip()
    if not scope_id or not bundle_id:
        return {"ok": False, "error": "发布单缺少 scope 或 bundle", "checks": []}
    from services.release.bundle_service import find_active_bundle

    bundle = find_active_bundle(scope_id, platform=str(order.get("platform") or ""))
    if not bundle or str(bundle.get("bundle_id") or "") != bundle_id:
        return {"ok": False, "error": "active bundle 与发布单不一致", "checks": []}
    client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
    checks: List[Dict[str, Any]] = []
    for key in ("catalog_url", "config_manifest_url", "code_manifest_url", "resource_server_url"):
        val = str(client.get(key) or "").strip()
        checks.append({"key": key, "ok": bool(val), "value": val[:120] if val else ""})
    apk_url = str(client.get("apk_url") or client.get("catalog_url") or "").strip()
    if str(order.get("platform") or "").lower() == "android":
        checks.append({"key": "apk_url", "ok": bool(apk_url), "value": apk_url[:120] if apk_url else ""})
    ok = all(item.get("ok") for item in checks if item.get("key") != "resource_server_url") and any(
        item.get("ok") for item in checks
    )
    return {"ok": ok, "bundle_id": bundle_id, "scope_id": scope_id, "checks": checks}


def verify_release_order(project_id: str, order_id: str, actor: str, ok: bool = True) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if order.get("status") not in {"published", "verifying", "verify_failed"}:
        raise ValueError("只有已发布的发布单可以验证")
    smoke_ok = ok
    smoke_report: Dict[str, Any] = {}
    if ok:
        smoke_report = run_bootstrap_smoke_for_order(project_id, order_id)
        smoke_ok = bool(smoke_report.get("ok"))
    target = "verified" if smoke_ok else "verify_failed"
    return _transition(
        project_id,
        order_id,
        actor,
        target,
        "verified",
        {"ok": smoke_ok, "smoke": smoke_report},
    )


def rollback_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    target = get_release_order(project_id, order_id, include_details=False)
    if not target or not target.get("bundle_id"):
        raise ValueError("目标发布单没有可回滚 Bundle")
    now = _now_iso()
    with get_cursor() as cur:
        target_bundle_row = cur.execute("SELECT payload FROM release_bundles WHERE bundle_id=?", (target["bundle_id"],)).fetchone()
        if not target_bundle_row:
            raise ValueError("目标 Bundle 不存在")
        target_bundle = _decode(target_bundle_row["payload"], {}) or {}
        current = cur.execute(
            "SELECT bundle_id, release_order_id, payload FROM release_bundles WHERE scope_id=? AND publish_status='published' ORDER BY published_at DESC LIMIT 1",
            (target["scope_id"],),
        ).fetchone()
        if current and current["bundle_id"] == target["bundle_id"]:
            raise ValueError("目标 Bundle 已经是当前生效版本，无需回滚")
        if current and current["bundle_id"] != target["bundle_id"]:
            current_payload = _decode(current["payload"], {}) or {}
            current_payload["publish_status"] = "superseded"
            current_payload["updated_at"] = now
            cur.execute(
                "UPDATE release_bundles SET publish_status='superseded', payload=?, updated_at=? WHERE bundle_id=?",
                (_json(current_payload), now, current["bundle_id"]),
            )
        target_bundle["publish_status"] = "published"
        target_bundle["rollback_of_bundle_id"] = current["bundle_id"] if current else ""
        target_bundle["published_at"] = now
        target_bundle["published_by"] = actor
        target_bundle["updated_at"] = now
        cur.execute(
            "UPDATE release_bundles SET publish_status='published', payload=?, published_at=?, published_by=?, updated_at=? WHERE bundle_id=?",
            (_json(target_bundle), now, actor, now, target["bundle_id"]),
        )
        cur.execute(
            "UPDATE release_orders SET status='published', published_at=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (now, now, project_id, order_id),
        )
        if current and str(current["release_order_id"] or ""):
            cur.execute(
                "UPDATE release_orders SET status='rolled_back', updated_at=? WHERE project_id=? AND release_order_id=?",
                (now, project_id, str(current["release_order_id"])),
            )
        cur.execute(
            "UPDATE release_scopes SET active_bundle_id=?, updated_at=? WHERE scope_id=?",
            (target["bundle_id"], now, target["scope_id"]),
        )
        _event(cur, order_id, "rollback_restored", actor, target["status"], "published", {"bundle_id": target["bundle_id"]})
    result = get_release_order(project_id, order_id)
    if os.environ.get("RELEASE_FEISHU_NOTIFY", "1").strip().lower() not in ("0", "false", "no"):
        try:
            from services.webhook import fire_feishu

            fire_feishu(
                "发布回滚",
                f"项目 {project_id} 订单 {order_id} 已回滚至 bundle {target.get('bundle_id')}（操作人 {actor}）",
            )
        except Exception:
            pass
    return result


def activate_bundle_on_scope(
    project_id: str,
    scope_id: str,
    bundle_id: str,
    actor: str,
    *,
    mode: str = "full",
    gray_ratio: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    """Activate an existing bundle as the live bundle for a scope (publish specified)."""
    sid = str(scope_id or "").strip()
    bid = str(bundle_id or "").strip()
    if not sid or not bid:
        raise ValueError("scope_id 与 bundle_id 必填")
    from services.release.storage import find_scope

    scope_row = find_scope(sid) or {}
    env_key = normalize_release_env_key(str(scope_row.get("env_key") or ""), project_id=project_id)
    if env_key == "production" and str(os.environ.get("ALLOW_SCOPE_PUBLISH_PRODUCTION", "")).strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        raise ValueError("生产环境禁止 Scope 直发 Bundle，请通过发布单审批发布")
    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        target_row = cur.execute("SELECT payload FROM release_bundles WHERE bundle_id=?", (bid,)).fetchone()
        if not target_row:
            raise ValueError("目标 Bundle 不存在")
        target_bundle = _decode(target_row["payload"], {}) or {}
        if str(target_bundle.get("scope_id") or "") != sid:
            raise ValueError("Bundle 不属于该交付线 Scope")
        current = cur.execute(
            "SELECT bundle_id, payload FROM release_bundles WHERE scope_id=? AND publish_status='published' ORDER BY published_at DESC LIMIT 1",
            (sid,),
        ).fetchone()
        if current and current["bundle_id"] == bid:
            return {"scope_id": sid, "bundle_id": bid, "status": "already_active", "bundle": target_bundle}
        if current:
            current_payload = _decode(current["payload"], {}) or {}
            current_payload["publish_status"] = "superseded"
            current_payload["updated_at"] = now
            cur.execute(
                "UPDATE release_bundles SET publish_status='superseded', payload=?, updated_at=? WHERE bundle_id=?",
                (_json(current_payload), now, current["bundle_id"]),
            )
        target_bundle["publish_status"] = "published"
        target_bundle["publish_mode"] = str(mode or "full")
        if gray_ratio:
            target_bundle["gray_ratio"] = str(gray_ratio)
        if reason:
            target_bundle["publish_reason"] = reason
        target_bundle["published_at"] = now
        target_bundle["published_by"] = actor
        target_bundle["updated_at"] = now
        target_bundle["supersedes_bundle_id"] = str(current["bundle_id"]) if current else ""
        cur.execute(
            "UPDATE release_bundles SET publish_status='published', payload=?, published_at=?, published_by=?, updated_at=? WHERE bundle_id=?",
            (_json(target_bundle), now, actor, now, bid),
        )
        cur.execute(
            "UPDATE release_scopes SET active_bundle_id=?, updated_at=? WHERE scope_id=?",
            (bid, now, sid),
        )
    return {"scope_id": sid, "bundle_id": bid, "status": "published", "bundle": target_bundle}


def unpublish_scope(project_id: str, scope_id: str, actor: str, *, reason: str = "") -> Dict[str, Any]:
    """Withdraw live bundle from scope (not rollback to another version)."""
    sid = str(scope_id or "").strip()
    if not sid:
        raise ValueError("scope_id 必填")
    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        current = cur.execute(
            "SELECT bundle_id, payload FROM release_bundles WHERE scope_id=? AND publish_status='published' ORDER BY published_at DESC LIMIT 1",
            (sid,),
        ).fetchone()
        if not current:
            raise ValueError("当前 Scope 没有线上生效 Bundle")
        payload = _decode(current["payload"], {}) or {}
        payload["publish_status"] = "revoked"
        payload["revoked_at"] = now
        payload["revoked_by"] = actor
        if reason:
            payload["revoke_reason"] = reason
        payload["updated_at"] = now
        cur.execute(
            "UPDATE release_bundles SET publish_status='revoked', payload=?, updated_at=? WHERE bundle_id=?",
            (_json(payload), now, current["bundle_id"]),
        )
        cur.execute(
            "UPDATE release_scopes SET active_bundle_id='', updated_at=? WHERE scope_id=?",
            (now, sid),
        )
    return {"scope_id": sid, "revoked_bundle_id": current["bundle_id"], "status": "revoked"}


def rollback_scope_to_bundle(
    project_id: str,
    scope_id: str,
    target_bundle_id: str,
    actor: str,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    """Rollback scope to a specific historical bundle."""
    result = activate_bundle_on_scope(
        project_id,
        scope_id,
        target_bundle_id,
        actor,
        mode="rollback",
        reason=reason or "scope rollback",
    )
    result["status"] = "rolled_back"
    return result


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




# --- Extracted modules (re-export for backward compatibility) ---
from services.release.channel_journey_bff import (  # noqa: E402
    BUILD_JOURNEY_STEPS,
    RELEASE_JOURNEY_STEPS,
    _channel_entry_urls,
    _delivery_lines_for_env,
    _enrich_state_from_version_id,
    _jenkins_progress_pct,
    _lines_for_channel,
    _platform_state_for_journey,
    _resolve_build_current_step,
    _resolve_release_current_step,
    _version_id_for_delivery_line,
    _versions_for_channel_platform,
    environment_detail,
    project_overview,
    resolve_channel_build_journey,
    resolve_channel_journey_entries,
    resolve_channel_release_journey,
)
