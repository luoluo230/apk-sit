# -*- coding: utf-8 -*-
"""Release order submodule (extracted from release_order_service)."""

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
from services.release.storage import find_manifest

from services.release.order_constants import EDITABLE_PLAN_FIELDS, PUBLISHABLE_STATUSES, TERMINAL_STATUSES
from services.release.order_helpers import _find_version, _decode
from services.release.overview_feed_service import build_overview_activities, build_overview_kpis


def _core():
    """Lazy import to avoid circular load with release_order_service."""
    import services.release.release_order_service as mod

    return mod

def _version_id_for_delivery_line(
    project_id: str,
    env_key: str,
    channel_id: str,
    platform: str,
    version_name: str,
    version_code: str,
) -> str:
    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = resolve_channel_id(project_id, channel_id) or str(channel_id or "").strip()
    plat = str(platform or "").strip().lower()
    vn = str(version_name or "").strip()
    vc = str(version_code or "").strip()
    for source in project_versions_db.get(project_id) or []:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        row_env = normalize_release_env_key(row.get("env_key") or row.get("stage") or row.get("env"), project_id=project_id)
        row_channel = resolve_channel_id(project_id, str(row.get("channel_id") or row.get("channel") or "")) or str(
            row.get("channel_id") or row.get("channel") or ""
        ).strip()
        row_plat = str(row.get("platform") or "android").strip().lower()
        if row_env != ek or row_channel != cid or row_plat != plat:
            continue
        if vn and str(row.get("version_name") or "").strip() != vn:
            continue
        if vc and str(row.get("version_code") or "").strip() != vc:
            continue
        vid = str(row.get("id") or "").strip()
        if vid:
            return vid
    return ""


BUILD_JOURNEY_STEPS = [
    {"id": "platform", "label": "选择平台", "index": 0},
    {"id": "pipeline", "label": "检查管线", "index": 1},
    {"id": "version", "label": "选择 VersionCode", "index": 2},
    {"id": "trigger", "label": "触发构建", "index": 3},
    {"id": "monitor", "label": "监控构建", "index": 4},
    {"id": "verify", "label": "产物验收", "index": 5},
]

RELEASE_JOURNEY_STEPS = [
    {"id": "platform", "label": "选择平台", "index": 0},
    {"id": "target", "label": "选择目标版本", "index": 1},
    {"id": "plan", "label": "发版计划", "index": 2},
    {"id": "precheck", "label": "预检", "index": 3},
    {"id": "publish", "label": "发布操作", "index": 4},
    {"id": "verify", "label": "验证", "index": 5},
    {"id": "ops", "label": "回滚与下线", "index": 6},
]


def _lines_for_channel(project_id: str, env_key: str, channel_id: str) -> List[Dict[str, Any]]:
    cid = str(channel_id or "").strip()
    return [
        line
        for line in _delivery_lines_for_env(project_id, env_key)
        if str(line.get("channel_id") or "").strip() == cid
    ]


def _versions_for_channel_platform(project_id: str, env_key: str, channel_id: str, platform: str) -> List[Dict[str, Any]]:
    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = resolve_channel_id(project_id, channel_id) or str(channel_id or "").strip()
    plat = str(platform or "android").strip().lower()
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for source in project_versions_db.get(project_id) or []:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        row_env = normalize_release_env_key(row.get("env_key") or row.get("stage") or row.get("env"))
        if row_env != ek:
            continue
        row_cid = resolve_channel_id(project_id, str(row.get("channel_id") or row.get("channel") or "")) or str(row.get("channel_id") or row.get("channel") or "").strip()
        if row_cid != cid:
            continue
        row_plat = str(row.get("platform") or "android").strip().lower()
        if row_plat != plat:
            continue
        vid = str(row.get("id") or "").strip()
        if not vid or vid in seen:
            continue
        seen.add(vid)
        order = _core().find_release_order_for_version(project_id, vid)
        out.append({
            "version_id": vid,
            "version_name": str(row.get("version_name") or ""),
            "version_code": str(row.get("version_code") or ""),
            "apk_status": str(row.get("apk_status") or ""),
            "release_order_id": str(order.get("release_order_id") or "") if order else "",
            "release_order_status": str(order.get("status") or "") if order else "",
            "artifacts_ready": str(row.get("apk_status") or "") == "found" or (order and order.get("status") == "artifacts_ready"),
        })
    out.sort(key=lambda r: (r.get("version_name") or "", r.get("version_code") or ""), reverse=True)
    return out


def _channel_entry_urls(project_id: str, env_key: str, channel_id: str) -> Dict[str, str]:
    from urllib.parse import urlencode

    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = str(channel_id or "").strip()
    base = f"/admin/projects/{project_id}/versions"
    qs = urlencode({"env_key": ek, "channel_id": cid})
    qs_release = urlencode({"env_key": ek, "channel_id": cid, "action": "edit_release"})
    return {
        "build": f"{base}?{qs}",
        "release": f"{base}?{qs_release}",
    }


def _gray_rollout_view(order: Dict[str, Any] | None, active_bundle: Dict[str, Any] | None) -> Dict[str, Any]:
    from datetime import datetime, timedelta

    order = order if isinstance(order, dict) else {}
    bundle = active_bundle if isinstance(active_bundle, dict) else {}
    plan = dict(order.get("payload") or {})
    client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
    strategy = str(plan.get("release_strategy") or bundle.get("release_strategy") or "standard").strip().lower()
    try:
        rollout = int(
            client.get("rollout_percentage")
            if client.get("rollout_percentage") is not None
            else bundle.get("rollout_percentage")
            if bundle.get("rollout_percentage") is not None
            else plan.get("gray_ratio")
            if plan.get("gray_ratio") not in (None, "")
            else 100
        )
    except (TypeError, ValueError):
        rollout = 100
    rollout = max(0, min(100, rollout))
    gray_status = str(bundle.get("gray_status") or ("active" if strategy == "gray" and rollout < 100 else "full"))
    success_action = str(plan.get("gray_success_action") or bundle.get("gray_success_action") or "manual").strip().lower()
    duration_raw = plan.get("gray_duration") or bundle.get("gray_duration") or ""
    try:
        gray_minutes = max(1, int(duration_raw))
    except (TypeError, ValueError):
        gray_minutes = 30
    published_at_raw = str(order.get("published_at") or bundle.get("published_at") or "").strip()
    auto_expand_due_at = ""
    auto_expand_pending = (
        success_action == "automatic"
        and str(order.get("status") or "") == "published"
        and rollout < 100
    )
    if auto_expand_pending and published_at_raw:
        try:
            published_at = datetime.fromisoformat(published_at_raw.replace("Z", "+00:00").replace("+00:00", ""))
            auto_expand_due_at = (published_at + timedelta(minutes=gray_minutes)).isoformat(timespec="seconds")
        except ValueError:
            auto_expand_due_at = ""
    action_labels = {"manual": "手动放量", "automatic": "自动放量", "hold": "保持比例"}
    return {
        "release_strategy": strategy,
        "gray_strategy": str(plan.get("gray_strategy") or bundle.get("gray_strategy") or "ratio"),
        "gray_ratio": str(plan.get("gray_ratio") or bundle.get("gray_ratio") or rollout),
        "gray_duration": str(plan.get("gray_duration") or bundle.get("gray_duration") or ""),
        "gray_success_action": success_action,
        "gray_success_action_label": action_labels.get(success_action, success_action),
        "rollout_percentage": rollout,
        "gray_status": gray_status,
        "is_gray_active": strategy == "gray" and rollout < 100 and gray_status != "full",
        "can_expand_gray": bool(order.get("release_order_id"))
        and str(order.get("status") or "") == "published"
        and rollout < 100
        and success_action != "hold",
        "gray_auto_expand_scheduled": auto_expand_pending,
        "gray_auto_expand_due_at": auto_expand_due_at,
        "gray_auto_expand_minutes": gray_minutes if auto_expand_pending else None,
        "gray_expanded_at": str(bundle.get("gray_expanded_at") or ""),
        "gray_expanded_by": str(bundle.get("gray_expanded_by") or ""),
    }


def _platform_state_for_journey(project_id: str, env_key: str, line: Dict[str, Any]) -> Dict[str, Any]:
    from services.release.release_policy_service import assess_delivery_readiness, build_config_href

    vid = str(line.get("version_id") or "").strip()
    platform = str(line.get("platform") or "android").strip().lower()
    cid = str(line.get("channel_id") or "").strip()
    scope_id = str(line.get("scope_id") or "")
    version = _find_version(project_id, vid) if vid else None
    readiness = assess_delivery_readiness(project_id, version or {}, env_key, cid, platform) if version else {"pipeline_ready": False}
    pipeline_ready = bool(readiness.get("pipeline_ready"))
    order = _core().find_release_order_for_version(project_id, vid) if vid else None
    order_status = str(order.get("status") or "") if order else ""
    artifact_ready = bool(version and str(version.get("apk_status") or "") == "found") or order_status == "artifacts_ready"
    active_bundle = find_active_bundle(scope_id, platform=platform) if scope_id else {}
    order_full = None
    if order and order.get("release_order_id"):
        order_full = _core().get_release_order(project_id, str(order.get("release_order_id") or ""))
    gray = _gray_rollout_view(order_full or order, active_bundle)
    return {
        "platform": platform,
        "platform_label": line.get("platform_label") or platform,
        "scope_id": scope_id,
        "version_id": vid,
        "version_name": line.get("version_name") or "",
        "version_code": line.get("version_code") or "",
        "configured": bool(line.get("configured")),
        "pipeline_ready": pipeline_ready,
        "artifact_ready": artifact_ready,
        "order_status": order_status,
        "release_order_id": str(order.get("release_order_id") or "") if order else "",
        "active_bundle_id": str(active_bundle.get("bundle_id") or line.get("bundle_id") or ""),
        "topology_id": str(line.get("topology_id") or ""),
        "build_config_href": build_config_href(project_id, version) if version else "",
        "versions": _versions_for_channel_platform(project_id, env_key, cid, platform),
        "publishable_bundles": list_publishable_bundles(scope_id, platform=platform) if scope_id else [],
        **gray,
    }


def _resolve_build_current_step(platform: str, state: Dict[str, Any]) -> int:
    if not platform:
        return 0
    if not state.get("pipeline_ready"):
        return 1
    if not state.get("version_id"):
        return 2
    status = str(state.get("order_status") or "")
    if status == "building":
        return 4
    if state.get("artifact_ready") or status == "artifacts_ready":
        return 5
    return 3


def _resolve_release_current_step(platform: str, state: Dict[str, Any], *, has_target: bool = False) -> int:
    if not platform:
        return 0
    if not has_target and not state.get("artifact_ready") and not state.get("publishable_bundles"):
        return 1
    if not has_target:
        return 1
    status = str(state.get("order_status") or "")
    if status in {"draft", "artifacts_ready", "precheck_failed"}:
        return 3
    if status in {"prechecking", "ready", "awaiting_approval", "approved"}:
        return 4
    if status == "published":
        return 5
    if status in {"verified", "verify_failed"}:
        return 6
    return 2


def _enrich_state_from_version_id(project_id: str, state: Dict[str, Any], version_id: str) -> Dict[str, Any]:
    vid = str(version_id or "").strip()
    if not vid:
        return state
    version = _find_version(project_id, vid)
    if not version:
        return {**state, "version_id": vid}
    order = _core().find_release_order_for_version(project_id, vid)
    order_status = str(order.get("status") or "") if order else ""
    artifact_ready = str(version.get("apk_status") or "") == "found" or order_status == "artifacts_ready"
    for row in state.get("versions") or []:
        if str(row.get("version_id") or "") == vid:
            order_status = str(row.get("release_order_status") or order_status)
            artifact_ready = artifact_ready or bool(row.get("artifacts_ready"))
            break
    return {
        **state,
        "version_id": vid,
        "version_name": str(version.get("version_name") or state.get("version_name") or ""),
        "version_code": str(version.get("version_code") or state.get("version_code") or ""),
        "order_status": order_status,
        "release_order_id": str(order.get("release_order_id") or "") if order else str(state.get("release_order_id") or ""),
        "artifact_ready": artifact_ready,
    }


def _jenkins_progress_pct(build: Dict[str, Any]) -> int:
    if not isinstance(build, dict):
        return 0
    if build.get("building"):
        st = str(build.get("status") or build.get("result") or "BUILDING").upper()
        if st in {"QUEUED", "WAITING"}:
            return 12
        return 55
    st = str(build.get("status") or build.get("result") or "").upper()
    if st == "SUCCESS":
        return 100
    if st in {"FAILURE", "ABORTED", "UNSTABLE"}:
        return 100
    return 38


def resolve_channel_build_journey(
    project_id: str,
    env_key: str,
    channel_id: str,
    *,
    platform: str = "",
    version_id: str = "",
) -> Dict[str, Any]:
    from urllib.parse import urlencode

    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = str(channel_id or "").strip()
    lines = _lines_for_channel(project_id, ek, cid)
    if not lines:
        raise ValueError("该环境下未配置此渠道")
    channel_name = str(lines[0].get("channel_name") or cid)
    from services.build.platform_capability import can_build

    platforms = [
        {"value": str(l["platform"]), "label": str(l.get("platform_label") or l["platform"])}
        for l in lines
        if can_build(str(l.get("platform") or ""))
    ]
    plat = str(platform or "").strip().lower()
    if not plat and platforms:
        plat = platforms[0]["value"]
    line = next((l for l in lines if str(l.get("platform") or "") == plat), None)
    if not line and lines:
        line = next((l for l in lines if can_build(str(l.get("platform") or ""))), lines[0])
    if not platforms and line:
        platforms = [{"value": str(line["platform"]), "label": str(line.get("platform_label") or line["platform"])}]
    per_platform = {
        str(l["platform"]): _platform_state_for_journey(project_id, ek, l)
        for l in lines
        if can_build(str(l.get("platform") or ""))
    }
    state = per_platform.get(plat) or {}
    selected_vid = str(version_id or state.get("version_id") or "").strip()
    if selected_vid:
        state = _enrich_state_from_version_id(project_id, state, selected_vid)
        per_platform = dict(per_platform)
        per_platform[plat] = state
    latest_build: Dict[str, Any] = {}
    if selected_vid:
        try:
            from services.build_history_service import latest_build_for_version

            latest_build = latest_build_for_version(selected_vid, project_id) or {}
        except Exception:
            latest_build = {}
    if latest_build:
        latest_build = dict(latest_build)
        latest_build["progress_pct"] = _jenkins_progress_pct(latest_build)
        state = dict(state)
        state["latest_build"] = latest_build
        per_platform = dict(per_platform)
        per_platform[plat] = state
    current_step = _resolve_build_current_step(plat, state)
    urls = _channel_entry_urls(project_id, ek, cid)
    scope_qs = urlencode({"env_key": ek, "channel_id": cid, "platform": plat, "version_id": state.get("version_id") or ""})
    return {
        "project_id": project_id,
        "env_key": ek,
        "env_label": project_env_label(project_id, ek),
        "channel_id": cid,
        "channel_name": channel_name,
        "platform": plat,
        "platforms": platforms,
        "steps": BUILD_JOURNEY_STEPS,
        "current_step": current_step,
        "per_platform": per_platform,
        "selected_version_id": str(selected_vid or state.get("version_id") or ""),
        "links": {
            "build_journey": urls["build"],
            "release_journey": urls["release"],
            "build_history": f"/admin/projects/{project_id}/build-history?{scope_qs}&scoped=1",
            "versions": f"/admin/projects/{project_id}/versions?{scope_qs}",
        },
    }


def resolve_channel_release_journey(
    project_id: str,
    env_key: str,
    channel_id: str,
    *,
    platform: str = "",
    version_id: str = "",
    bundle_id: str = "",
) -> Dict[str, Any]:
    from urllib.parse import urlencode
    from services.release.release_policy_service import get_env_release_policy

    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = str(channel_id or "").strip()
    lines = _lines_for_channel(project_id, ek, cid)
    if not lines:
        raise ValueError("该环境下未配置此渠道")
    channel_name = str(lines[0].get("channel_name") or cid)
    platforms = [{"value": str(l["platform"]), "label": str(l.get("platform_label") or l["platform"])} for l in lines]
    plat = str(platform or "").strip().lower()
    if not plat and platforms:
        plat = platforms[0]["value"]
    per_platform = {str(l["platform"]): _platform_state_for_journey(project_id, ek, l) for l in lines}
    state = per_platform.get(plat) or {}
    selected_vid = str(version_id or state.get("version_id") or "").strip()
    selected_bundle = str(bundle_id or "").strip()
    _core().sync_building_release_orders(project_id)
    if selected_vid:
        state = _enrich_state_from_version_id(project_id, state, selected_vid)
        order = _core().find_release_order_for_version(project_id, selected_vid)
        if order:
            enriched = {**state, "order_status": order.get("status"), "release_order_id": order.get("release_order_id")}
            full = _core().get_release_order(project_id, str(order.get("release_order_id") or ""))
            if full:
                enriched.update(_gray_rollout_view(full, find_active_bundle(str(state.get("scope_id") or ""), platform=plat)))
            if str(order.get("status") or "") == "precheck_failed":
                if full:
                    from services.release.order_diagnostics import summarize_order_diagnostic_issues

                    payload = ((full.get("latest_precheck") or {}).get("payload") or {})
                    enriched["diagnostic_issues"] = summarize_order_diagnostic_issues(full, payload)
            state = enriched
        else:
            start_qs = urlencode(
                {
                    "env_key": ek,
                    "channel_id": cid,
                    "platform": plat,
                    "version_id": selected_vid,
                }
            )
            state = {
                **state,
                "create_order_href": f"/admin/projects/{project_id}/release-orders/start?{start_qs}",
                "ensure_order_api": f"/api/projects/{project_id}/versions/{selected_vid}/ensure-release-order",
            }
        per_platform = dict(per_platform)
        per_platform[plat] = state
    has_target = bool(selected_vid or selected_bundle or state.get("active_bundle_id"))
    policy = get_env_release_policy(project_id, ek)
    current_step = _resolve_release_current_step(plat, state, has_target=has_target)
    urls = _channel_entry_urls(project_id, ek, cid)
    scope_qs = urlencode({"env_key": ek, "channel_id": cid, "platform": plat})
    orders = [
        row for row in _core().list_release_orders(project_id, {"env_key": ek, "channel_id": cid})
        if str(row.get("platform") or "").strip().lower() == plat
    ][:20]
    recommended_build_node = {}
    if plat:
        try:
            from services.infra.infra_node_registry import recommended_build_node_for_platform

            recommended_build_node = recommended_build_node_for_platform(plat)
        except Exception:
            recommended_build_node = {}
    return {
        "project_id": project_id,
        "env_key": ek,
        "env_label": project_env_label(project_id, ek),
        "channel_id": cid,
        "channel_name": channel_name,
        "platform": plat,
        "platforms": platforms,
        "steps": RELEASE_JOURNEY_STEPS,
        "current_step": current_step,
        "form_depth": str(policy.get("form_depth") or ""),
        "per_platform": per_platform,
        "selected_version_id": selected_vid,
        "selected_bundle_id": selected_bundle,
        "release_orders": orders,
        "recommended_build_node": recommended_build_node,
        "links": {
            "build_journey": urls["build"],
            "release_journey": urls["release"],
            "environment_detail": f"/admin/projects/{project_id}/environments/{ek}",
        },
    }


def resolve_channel_journey_entries(project_id: str, env_key: str, channel_id: str) -> Dict[str, Any]:
    """Channel-level dual entry buttons for environment matrix."""
    ek = normalize_release_env_key(env_key, project_id=project_id)
    cid = str(channel_id or "").strip()
    lines = _lines_for_channel(project_id, ek, cid)
    urls = _channel_entry_urls(project_id, ek, cid)
    if not lines:
        return {
            "channel_id": cid,
            "channel_name": cid,
            "build_entry": {"label": "版本管理", "href": urls["build"], "enabled": False, "reason": "渠道未配置"},
            "release_entry": {"label": "版本管理", "href": urls["release"], "enabled": False, "reason": "渠道未配置"},
            "platform_lines": [],
        }
    channel_name = str(lines[0].get("channel_name") or cid)
    platform_lines = []
    any_artifact = False
    any_pipeline = False
    for line in lines:
        st = _platform_state_for_journey(project_id, ek, line)
        platform_lines.append(st)
        any_artifact = any_artifact or st.get("artifact_ready")
        any_pipeline = any_pipeline or st.get("pipeline_ready")
    return {
        "channel_id": cid,
        "channel_name": channel_name,
        "build_entry": {
            "label": "版本管理",
            "href": urls["build"],
            "enabled": True,
            "reason": "" if any_pipeline or platform_lines else "请先配置平台",
        },
        "release_entry": {
            "label": "版本管理",
            "href": urls["release"],
            "enabled": True,
            "reason": "" if any_artifact or any(st.get("publishable_bundles") for st in platform_lines) else "暂无产物或线上版本",
        },
        "platform_lines": platform_lines,
    }


def _delivery_lines_for_env(project_id: str, env_key: str) -> List[Dict[str, Any]]:
    ek = normalize_release_env_key(env_key, project_id=project_id)
    channels = [
        {"channel_id": str(row.get("id") or ""), "channel_name": str(row.get("name") or row.get("id") or "")}
        for row in get_channels_for_env(project_id, ek)
    ]
    platforms = get_platform_defs_for_env(project_id, ek)
    lines: List[Dict[str, Any]] = []
    for channel in channels:
        cid = str(channel.get("channel_id") or "").strip()
        if not cid:
            continue
        for plat in platforms:
            plat_value = str(plat["value"])
            scope = resolve_scope(project_id, env_key, cid, platform=plat_value, auto_create=False)
            scope_id = str(scope.get("scope_id") or build_scope_id(project_slug(project_id), env_key, cid, plat_value))
            bundle = find_active_bundle(scope_id) if scope else {}
            client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
            server = bundle.get("server") if isinstance(bundle.get("server"), dict) else {}
            version_name = str(client.get("version_name") or bundle.get("version_name") or "")
            binding = resolve_topology_binding_for_scope(scope or {}, version_name) if scope else {}
            topology_id = str(binding.get("topology_id") or server.get("topology_id") or "")
            from services.release.topology_binding_service import _topology_name_map

            topo_names = _topology_name_map(project_id)
            configured = bool(scope and (bundle or version_name))
            line_version_code = str(client.get("version_code") or bundle.get("version_code") or "")
            lines.append(
                {
                    "channel_id": cid,
                    "channel_name": channel.get("channel_name") or cid,
                    "platform": plat_value,
                    "platform_label": plat["label"],
                    "scope_id": scope_id,
                    "configured": configured,
                    "version_name": version_name,
                    "version_code": line_version_code,
                    "version_id": _version_id_for_delivery_line(
                        project_id, env_key, cid, plat_value, version_name, line_version_code
                    ),
                    "topology_id": topology_id,
                    "topology_name": topo_names.get(topology_id, topology_id or "-"),
                    "binding_source": str(binding.get("binding_source") or ""),
                    "binding_source_label": str(binding.get("binding_source_label") or ""),
                    "bundle_id": str(bundle.get("bundle_id") or ""),
                    "runtime_run_id": str(server.get("runtime_run_id") or ""),
                }
            )
    return lines


from services.release.channel_journey_overview import (  # noqa: F401
    environment_detail,
    project_overview,
)
