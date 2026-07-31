# -*- coding: utf-8 -*-
"""Release console BFF — aggregates env matrix, policies, and batch readiness."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import projects_db
from services.release.channel_journey_bff import _delivery_lines_for_env
from services.release.env_registry import get_project_env_defs, normalize_release_env_key, project_env_label
from services.release.release_batch_service import get_release_batch, list_release_batches
from services.release.release_policy_service import get_env_release_policy, get_required_plan_fields
from services.release.order_diagnostics import _build_pipeline_snapshot, _pipeline_build_ready


def build_release_console(project_id: str, *, env_key: str = "", batch_id: str = "") -> Dict[str, Any]:
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    env_defs = []
    for row in get_project_env_defs(project_id):
        ek = str(row.get("env_key") or "")
        policy = get_env_release_policy(project_id, ek)
        env_defs.append(
            {
                **row,
                "label": project_env_label(project_id, ek),
                "release_policy": policy,
                "required_fields": get_required_plan_fields(project_id, ek),
            }
        )
    selected_env = normalize_release_env_key(env_key or "development", project_id=project_id) if env_key else ""
    delivery_matrix: List[Dict[str, Any]] = []
    if selected_env:
        delivery_matrix = _enrich_delivery_matrix(project_id, selected_env)
    recent_batches = list_release_batches(project_id, limit=10)
    active_batch = {}
    if batch_id:
        active_batch = get_release_batch(project_id, batch_id)
    elif recent_batches:
        draft_batches = [b for b in recent_batches if str(b.get("status") or "") in {"draft", "building", "artifacts_ready", "precheck_failed", "partial_failed", "ready"}]
        if draft_batches:
            active_batch = get_release_batch(project_id, draft_batches[0]["batch_id"])
    return {
        "project_id": project_id,
        "env_defs": env_defs,
        "selected_env": selected_env,
        "delivery_matrix": delivery_matrix,
        "recent_batches": recent_batches,
        "active_batch": active_batch,
        "console_url": f"/admin/projects/{project_id}/release",
    }


def _enrich_delivery_matrix(project_id: str, env_key: str) -> List[Dict[str, Any]]:
    lines = _delivery_lines_for_env(project_id, env_key)
    out: List[Dict[str, Any]] = []
    for line in lines:
        cid = str(line.get("channel_id") or "")
        plat = str(line.get("platform") or "android")
        pipeline = _build_pipeline_snapshot(project_id, "", cid)
        pipeline_ready = _pipeline_build_ready(pipeline)
        readiness = "ready" if line.get("configured") and line.get("version_code") else "empty"
        if not pipeline_ready:
            readiness = "blocked"
        out.append(
            {
                **line,
                "line_key": f"{cid}:{plat}",
                "pipeline_ready": pipeline_ready,
                "readiness": readiness,
                "recommended_version_id": _recommended_version_id(project_id, env_key, cid, plat),
            }
        )
    return out


def _recommended_version_id(project_id: str, env_key: str, channel_id: str, platform: str) -> str:
    from services.release.channel_journey_bff import _versions_for_channel_platform

    versions = _versions_for_channel_platform(project_id, env_key, channel_id, platform)
    for row in versions:
        if str(row.get("artifact_ready") or row.get("artifacts_ready") or "").lower() in ("1", "true", "yes"):
            return str(row.get("version_id") or "")
        if row.get("status") == "artifacts_ready":
            return str(row.get("version_id") or "")
    if versions:
        return str(versions[0].get("version_id") or "")
    return ""


def line_readiness_for_batch(project_id: str, batch: Dict[str, Any]) -> Dict[str, Any]:
    env_key = str(batch.get("env_key") or "")
    orders = batch.get("orders") or []
    lines: List[Dict[str, Any]] = []
    all_ready = True
    for order in orders:
        vid = str(order.get("version_id") or "")
        pipeline = _build_pipeline_snapshot(project_id, vid, str(order.get("channel_id") or ""))
        pipeline_ready = _pipeline_build_ready(pipeline)
        status = str(order.get("status") or "draft")
        issues: List[str] = []
        if not pipeline_ready:
            issues.append("构建管线未就绪")
            all_ready = False
        if status == "draft":
            issues.append("尚未构建产物")
            all_ready = False
        elif status == "precheck_failed":
            issues.append("预检未通过")
            all_ready = False
        lines.append(
            {
                "release_order_id": order.get("release_order_id"),
                "channel_id": order.get("channel_id"),
                "channel_name": order.get("channel_name"),
                "platform": order.get("platform"),
                "version_id": vid,
                "version_code": order.get("version_code"),
                "status": status,
                "pipeline_ready": pipeline_ready,
                "issues": issues,
                "ready": not issues,
            }
        )
    policy = get_env_release_policy(project_id, env_key)
    shared = batch.get("shared_plan") or {}
    missing_fields: List[str] = []
    for field in get_required_plan_fields(project_id, env_key):
        val = shared.get(field) if field != "reason" else batch.get("reason") or shared.get("release_description")
        if not str(val or "").strip():
            missing_fields.append(field)
    return {
        "batch_id": batch.get("batch_id"),
        "env_key": env_key,
        "policy": policy,
        "lines": lines,
        "all_lines_ready": all_ready and bool(lines),
        "missing_plan_fields": missing_fields,
        "plan_complete": not missing_fields,
    }
