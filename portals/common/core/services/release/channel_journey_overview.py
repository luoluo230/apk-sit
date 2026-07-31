# -*- coding: utf-8 -*-
"""Project/environment overview BFF."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from models.data import get_channel_by_id, get_channels_for_project, project_versions_db, projects_db
from data.delivery_scope import is_channel_allowed_for_env
from data.platforms import get_platform_defs_for_project
from models.db import init_db
from services.release.env_registry import list_project_env_keys, normalize_release_env_key, project_env_label
from services.release.overview_feed_service import build_overview_activities, build_overview_kpis
from services.release.storage import find_manifest


def _core():
    import services.release.release_order_service as mod
    return mod


def _delivery_lines_for_env(project_id: str, env_key: str):
    from services.release.channel_journey_bff import _delivery_lines_for_env as fn

    return fn(project_id, env_key)


def resolve_channel_journey_entries(project_id: str, env_key: str, channel_id: str):
    from services.release.channel_journey_bff import resolve_channel_journey_entries as fn

    return fn(project_id, env_key, channel_id)


_EVENT_KIND_LABELS: Dict[str, Tuple[str, str]] = {
    "build_requested": ("build", "构建"),
    "build_completed": ("build", "构建"),
    "build_failed": ("build", "构建"),
    "build_finalize_failed": ("build", "构建"),
    "published": ("release", "发布"),
    "rollback_restored": ("release", "发布"),
    "publish_started": ("release", "发布"),
    "verify_started": ("release", "发布"),
    "precheck_started": ("release", "发布"),
    "prechecked": ("release", "发布"),
    "approved": ("approval", "审批"),
    "created": ("change", "变更"),
    "draft_updated": ("change", "变更"),
    "cancelled": ("change", "变更"),
}


def _activity_title(event_type: str, order_id: str, env_key: str, version_name: str, version_code: str, payload: Dict[str, Any]) -> str:
    base = f"{version_name} / {version_code}".strip(" /")
    env = env_key or "—"
    oid = order_id or "—"
    if event_type == "build_requested":
        bn = payload.get("build_number") or payload.get("build_job_id") or "—"
        return f"触发 Jenkins 构建 #{bn} · {base} · {env}"
    if event_type == "build_completed":
        bn = payload.get("build_number") or "—"
        return f"Jenkins 构建 #{bn} 成功 · {base} · {env}"
    if event_type in {"build_failed", "build_finalize_failed"}:
        hint = str(payload.get("failure_summary") or payload.get("error") or "失败")[:80]
        return f"Jenkins 构建失败 · {oid} · {hint}"
    if event_type == "published":
        return f"发布单 {oid} 已发布到 {env} · {base}"
    if event_type == "rollback_restored":
        return f"发布单 {oid} 已回滚恢复 · {env} · {base}"
    if event_type == "approved":
        return f"发布单 {oid} 审批通过 · {env} · {base}"
    if event_type == "prechecked":
        return f"发布单 {oid} 预检通过 · {env} · {base}"
    if event_type in {"precheck_started", "publish_started", "verify_started"}:
        label = {"precheck_started": "预检中", "publish_started": "发布中", "verify_started": "验收中"}.get(event_type, event_type)
        return f"发布单 {oid} {label} · {env} · {base}"
    if event_type == "created":
        return f"发布单 {oid} 已创建 · {env} · {base}"
    if event_type == "draft_updated":
        return f"发布单 {oid} 计划已更新 · {env} · {base}"
    if event_type == "cancelled":
        return f"发布单 {oid} 已取消 · {env}"
    return f"发布单 {oid} · {event_type} · {env} · {base}"


def _overview_activities(project_id: str, filters: Optional[Dict[str, str]] = None, *, limit: int = 40) -> List[Dict[str, Any]]:
    return build_overview_activities(project_id, filters, limit=limit)


def project_overview(project_id: str, filters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    init_db()
    filters = filters or {}
    filter_channel_global = str(filters.get("channel_id") or "").strip()
    cards: List[Dict[str, Any]] = []
    for env_key in list_project_env_keys(project_id):
        if filter_channel_global and not is_channel_allowed_for_env(project_id, env_key, filter_channel_global):
            continue
        orders = _core().list_release_orders(project_id, {"env_key": env_key})
        delivery_lines_all = _delivery_lines_for_env(project_id, env_key)
        delivery_lines = delivery_lines_all
        if filter_channel_global:
            delivery_lines = [
                line
                for line in delivery_lines_all
                if str(line.get("channel_id") or "").strip() == filter_channel_global
            ]
        configured_lines = [line for line in delivery_lines if line.get("configured")]
        unconfigured_count = sum(1 for line in delivery_lines if not line.get("configured"))
        pending = sum(1 for row in orders if row["status"] == "awaiting_approval")
        failed = sum(1 for row in orders if row["status"] in {"precheck_failed", "publish_failed", "verify_failed"})
        processing = sum(1 for row in orders if row["status"] in {"building", "prechecking", "publishing", "verifying"})
        blocker = next((line for line in delivery_lines if not line.get("configured")), None)
        health = "blocked" if failed else (
            "warning" if pending else (
                "processing" if processing else (
                    "healthy" if configured_lines else "unconfigured"
                )
            )
        )
        channel_ids = sorted(
            {str(line.get("channel_id") or "").strip() for line in delivery_lines_all if str(line.get("channel_id") or "").strip()}
        )
        platforms = sorted(
            {str(line.get("platform") or "").strip().lower() for line in delivery_lines_all if str(line.get("platform") or "").strip()}
        )
        channel_platform_labels: List[str] = []
        if filter_channel_global:
            seen_platform_labels: set[str] = set()
            for line in delivery_lines:
                label = str(line.get("platform_label") or line.get("platform") or "").strip()
                if label and label not in seen_platform_labels:
                    seen_platform_labels.add(label)
                    channel_platform_labels.append(label)
        runtime_status = ""
        runtime_label = ""
        if configured_lines:
            try:
                from services.ops.runtime_service import _runtime_active_for_scope
                from services.release.scope_resolver import resolve_scope, resolve_topology_binding_for_scope

                probe_line = configured_lines[0]
                scope = resolve_scope(
                    project_id,
                    env_key,
                    str(probe_line.get("channel_id") or ""),
                    platform=str(probe_line.get("platform") or "android"),
                    auto_create=False,
                )
                tid = ""
                if scope:
                    binding = resolve_topology_binding_for_scope(scope, "")
                    tid = str(binding.get("topology_id") or "")
                if tid:
                    rt = _runtime_active_for_scope(project_id, env_key, tid)
                    runtime_status = "running" if rt.get("active") else "stopped"
                    runtime_label = "运行中" if rt.get("active") else "已停止"
            except Exception:
                runtime_status = ""
                runtime_label = ""
        cards.append(
            {
                "env_key": env_key,
                "env_label": project_env_label(project_id, env_key),
                "health": health,
                "runtime_status": runtime_status,
                "runtime_label": runtime_label,
                "delivery_line_count": len(delivery_lines),
                "configured_line_count": len(configured_lines),
                "unconfigured_line_count": unconfigured_count,
                "channel_ids": channel_ids,
                "platforms": platforms,
                "channel_platform_labels": channel_platform_labels,
                "blocker_hint": (
                    f"{blocker.get('channel_name')} / {blocker.get('platform_label')} 未配置"
                    if blocker else ""
                ),
                "release_order_count": len(orders),
                "pending_approval_count": pending,
                "failed_count": failed,
                "processing_count": processing,
                "latest_orders": orders[:4],
            }
        )
    filter_env = str(filters.get("env_key") or "").strip().lower()
    filter_platform = str(filters.get("platform") or "").strip().lower()
    filter_health = str(filters.get("health") or "").strip().lower()
    if filter_env:
        cards = [row for row in cards if row["env_key"] == filter_env]
    if filter_platform:
        cards = [row for row in cards if filter_platform in row.get("platforms") or []]
    if filter_health:
        cards = [row for row in cards if row.get("health") == filter_health]
    enabled_channels = [
        {"channel_id": str(row.get("id") or ""), "channel_name": str(row.get("name") or row.get("id") or "")}
        for row in get_channels_for_project(project_id)
    ]
    return {
        "project_id": project_id,
        "project": projects_db.get(project_id) or {},
        "environments": cards,
        "activities": _overview_activities(project_id, filters),
        "kpis": build_overview_kpis(project_id, filters, cards),
        "environment_options": [
            {"env_key": key, "env_label": project_env_label(project_id, key)}
            for key in list_project_env_keys(project_id)
        ],
        "channel_options": enabled_channels,
        "platform_options": get_platform_defs_for_project(project_id),
        "health_options": [
            {"value": "healthy", "label": "运行中"},
            {"value": "blocked", "label": "存在阻断"},
            {"value": "warning", "label": "待处理"},
            {"value": "processing", "label": "处理中"},
            {"value": "unconfigured", "label": "未配置"},
        ],
    }


def environment_detail(project_id: str, env_key: str) -> Dict[str, Any]:
    ek = normalize_release_env_key(env_key, project_id=project_id)
    delivery_lines = [_core().enrich_delivery_line_actions(project_id, line) for line in _delivery_lines_for_env(project_id, ek)]
    orders = _core().list_release_orders(project_id, {"env_key": ek})
    versions = []
    seen = set()
    for source in project_versions_db.get(project_id) or []:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        row_env = normalize_release_env_key(row.get("env_key") or row.get("stage") or row.get("env"))
        if row_env != ek:
            continue
        row["env_key"] = row_env
        row["channel_id"] = str(row.get("channel_id") or row.get("channel") or "").strip()
        row["platform"] = str(row.get("platform") or "android").strip().lower()
        identity = (row["channel_id"], row["platform"], str(row.get("version_name") or ""), str(row.get("version_code") or ""))
        if identity in seen:
            continue
        seen.add(identity)
        channel_row = get_channel_by_id(row["channel_id"]) or {}
        row["channel_name"] = str(channel_row.get("name") or row["channel_id"])
        versions.append(row)
    pending = sum(1 for row in orders if row["status"] == "awaiting_approval")
    failed = sum(1 for row in orders if row["status"] in {"precheck_failed", "publish_failed", "verify_failed"})
    processing = sum(1 for row in orders if row["status"] in {"building", "prechecking", "publishing", "verifying"})
    unconfigured = sum(1 for line in delivery_lines if not line.get("configured"))
    manifest = find_manifest(project_id)
    channel_ids = sorted({str(line.get("channel_id") or "").strip() for line in delivery_lines if str(line.get("channel_id") or "").strip()})
    channel_journeys = [resolve_channel_journey_entries(project_id, ek, cid) for cid in channel_ids]
    return {
        "project_id": project_id,
        "project": projects_db.get(project_id) or {},
        "env_key": ek,
        "env_label": project_env_label(project_id, ek),
        "delivery_lines": delivery_lines,
        "channel_journeys": channel_journeys,
        "versions": versions,
        "release_orders": orders[:20],
        "summary": {
            "delivery_line_count": len(delivery_lines),
            "configured_line_count": sum(1 for line in delivery_lines if line.get("configured")),
            "unconfigured_line_count": unconfigured,
            "pending_approval_count": pending,
            "failed_count": failed,
            "processing_count": processing,
            "release_order_count": len(orders),
        },
        "manifest": manifest,
    }
