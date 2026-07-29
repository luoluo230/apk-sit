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
from services.release.order_helpers import (
    _artifact_rows,
    _channel_name,
    _decode,
    _event,
    _find_version,
    _json,
    _now_iso,
    _order_id,
    _bundle_id,
)

def _build_pipeline_snapshot(project_id: str, version_id: str, channel_id: str = "") -> Dict[str, Any]:
    vid = str(version_id or "").strip()
    if not vid:
        return {}
    version = _find_version(project_id, vid, "")
    if not version:
        return {}
    from services.admin.version_service import (
        _get_group_meta,
        _version_row_env_key,
        _version_row_platform,
        resolve_effective_jenkins,
        resolve_effective_pipeline,
    )
    from services.release.release_policy_service import assess_pipeline_readiness, build_config_href

    vn = str(version.get("version_name") or "").strip()
    env_key = _version_row_env_key(version, project_id)
    platform = _version_row_platform(version)
    meta = _get_group_meta(project_id, vn, env_key, platform) if vn else {}
    jenkins = resolve_effective_jenkins(project_id, version)
    pipeline = resolve_effective_pipeline(project_id, version)
    readiness = assess_pipeline_readiness(version, meta, channel_id or str(version.get("channel") or ""), project_id=project_id)
    return {
        "jenkins": jenkins,
        "effective_pipeline": pipeline,
        "readiness": readiness,
        "build_config_href": build_config_href(project_id, version, entry_from="release-order"),
    }


def _pipeline_step_enabled(pipeline_snapshot: Optional[dict], step_key: str) -> bool:
    pipeline = (pipeline_snapshot or {}).get("effective_pipeline") or {}
    block = pipeline.get(step_key) or {}
    return isinstance(block, dict) and bool(block.get("enabled"))


def _pipeline_build_ready(pipeline_snapshot: Optional[dict]) -> bool:
    readiness = (pipeline_snapshot or {}).get("readiness") or {}
    return bool(readiness.get("ready"))


def _highlight_fields_for_section(section: str) -> List[str]:
    mapping = {
        "jenkins": ["jenkins_instance_id", "jenkins_job_id"],
        "config_export": ["config_export_enabled"],
        "resource_build": ["resource_build_enabled"],
        "hot_release": ["hot_release_enabled", "code_enabled"],
        "artifact": ["apk_build_enabled"],
        "client_policy": ["resource_server_url"],
    }
    return list(mapping.get(str(section or "").strip(), []))


def _bootstrap_configured(project_id: str, order: dict, payload: Optional[dict] = None) -> bool:
    version = _find_version(project_id, str(order.get("version_id") or ""), str(order.get("version_code") or ""))
    if not version:
        return False
    from services.admin.version_service import resolve_effective_bootstrap_fields

    boot = resolve_effective_bootstrap_fields(project_id, version)
    if str(boot.get("resource_server_url") or "").strip():
        return True
    targets = (payload or {}).get("artifact_targets") or {}
    return bool(str(targets.get("catalog_url") or targets.get("config_manifest_url") or "").strip())


def _artifact_url_unreachable(group_id: str, payload: Optional[dict]) -> bool:
    payload = payload if isinstance(payload, dict) else {}
    key_map = {
        "apk": ("apk_url", "catalog_url"),
        "resource": ("resource_url", "catalog_url"),
        "config": ("config_url", "config_manifest_url"),
        "code": ("code_manifest_url",),
    }
    checks = payload.get("artifact_checks") or {}
    targets = payload.get("artifact_targets") or {}
    keys = key_map.get(str(group_id or "").strip(), ())
    outcomes: list[bool] = []
    for key in keys:
        url = str(targets.get(key) or "").strip()
        if not url:
            continue
        check = checks.get(key) or {}
        outcomes.append(bool(check.get("ok")))
    if not outcomes:
        return False
    return not any(outcomes)


_URL_CLIENT_KEYS = frozenset(
    {
        "apk_url",
        "resource_url",
        "config_url",
        "code_url",
        "apk_version",
        "resource_version",
        "config_version",
    }
)


def _refresh_diagnostic_payload(project_id: str, order: dict, payload: Optional[dict]) -> dict:
    """Merge live bootstrap/URL state so stale precheck snapshots do not mislead the UI."""
    payload = dict(payload or {})
    pid = str(project_id or order.get("project_id") or "").strip()
    if not pid:
        return payload
    version = _find_version(pid, str(order.get("version_id") or ""), str(order.get("version_code") or ""))
    if not version:
        return payload
    if not _bootstrap_configured(pid, order, payload):
        return payload
    payload["missing_client_fields"] = [
        k for k in (payload.get("missing_client_fields") or []) if k not in _URL_CLIENT_KEYS
    ]
    try:
        from services.admin.version_service import enrich_version_client_urls
        from services.release.bundle_service import _artifact_probe_targets, _evaluate_artifact_checks
        from services.release.scope_resolver import resolve_scope

        enriched = enrich_version_client_urls(pid, version)
        scope = resolve_scope(
            pid,
            str(order.get("env_key") or ""),
            str(order.get("channel_id") or ""),
            platform=str(order.get("platform") or ""),
            auto_create=False,
        )
        if not scope:
            return payload
        targets = _artifact_probe_targets(scope, enriched)
        checks, missing = _evaluate_artifact_checks(targets, enriched)
        payload["artifact_targets"] = targets
        payload["artifact_checks"] = checks
        payload["missing_artifact_fields"] = missing
    except Exception:
        pass
    return payload


def _resolve_runtime_start_node(project_id: str, env_key: str, topology_id: str) -> str:
    tid = str(topology_id or "").strip()
    if not tid:
        return ""
    try:
        from services.ops.topology_registry import _load_topology_scoped

        topo = _load_topology_scoped(str(project_id or ""), str(env_key or ""), tid)
        nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
        preferred_roles = ("gateway", "auth", "business", "game", "ops")
        for role in preferred_roles:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_role = str(node.get("role") or "").strip().lower()
                if node_role == role or str(node.get("id") or "").startswith(f"{role}-"):
                    return str(node.get("id") or node.get("server_id") or "").strip()
        for node in nodes:
            if isinstance(node, dict):
                nid = str(node.get("id") or node.get("server_id") or "").strip()
                if nid:
                    return nid
    except Exception:
        return ""
    return ""


def _resolve_issue_fix(
    group_id: str,
    order: dict,
    pipeline_snapshot: Optional[dict] = None,
    *,
    precheck_payload: Optional[dict] = None,
    project_id: str = "",
) -> Dict[str, str]:
    if group_id == "runtime":
        pid = str(project_id or order.get("project_id") or "").strip()
        env_key = str(order.get("env_key") or "").strip()
        topology_id = str((precheck_payload or {}).get("topology_id") or order.get("topology_id") or "").strip()
        node_id = _resolve_runtime_start_node(pid, env_key, topology_id)
        return {
            "fix": "runtime",
            "fix_action": "start_runtime",
            "fix_section": "",
            "fix_label": "启动运行态",
            "highlight_fields": ["runtime_topology"],
            "focus_reason": "目标环境尚未启动运行态，请在本页确认拓扑运行状态并启动 Runtime",
            "runtime_action": {
                "project_id": pid,
                "env_key": env_key,
                "topology_id": topology_id,
                "node_id": node_id,
            },
        }
    if group_id == "network":
        return {
            "fix": "network",
            "fix_section": "",
            "fix_label": "配置网络接入",
            "highlight_fields": ["gateway_ws", "login_http", "game_ws", "ops_http"],
            "focus_reason": "环境网络接入字段未配置完整，请补充下列高亮项",
        }
    if group_id == "scope":
        return {
            "fix": "edit",
            "fix_section": "",
            "fix_label": "编辑发布计划",
            "highlight_fields": [],
            "focus_reason": "发布单与 VersionCode 交付范围不一致，请核对并保存",
        }

    art = _artifact_row(order.get("artifacts") or [], group_id)
    status = str(art.get("status") or "").lower()
    has_path = bool(str(art.get("artifact_path") or "").strip())

    step_map = {
        "code": ("hot_release", "开启热更发布", "请开启热更发布并保存，然后返回发布单触发 Jenkins 构建"),
        "apk": ("artifact", "配置安装包步骤", "请启用安装包打包步骤并保存，然后返回发布单触发构建"),
        "resource": ("resource_build", "配置资源打包", "请启用资源打包步骤并保存，然后返回发布单触发构建"),
        "config": ("config_export", "配置导出步骤", "请启用配置导出步骤并保存，然后返回发布单触发构建"),
    }
    step_key, config_label, config_reason = step_map.get(group_id, ("client_policy", "配置管线", "请完成管线配置"))

    if status == "missing" or not has_path:
        if _pipeline_step_enabled(pipeline_snapshot, step_key) and _pipeline_build_ready(pipeline_snapshot):
            return {
                "fix": "trigger_build",
                "fix_section": "",
                "fix_label": "触发 Jenkins 构建",
                "highlight_fields": [],
                "focus_reason": "",
            }
        return {
            "fix": "buildConfig",
            "fix_section": step_key,
            "fix_label": config_label,
            "highlight_fields": _highlight_fields_for_section(step_key),
            "focus_reason": config_reason,
        }

    pid = str(project_id or order.get("project_id") or "").strip()
    if pid and _bootstrap_configured(pid, order, precheck_payload):
        if group_id == "code" and _pipeline_step_enabled(pipeline_snapshot, "hot_release") and _pipeline_build_ready(pipeline_snapshot):
            return {
                "fix": "trigger_build",
                "fix_section": "",
                "fix_label": "触发 Jenkins 构建",
                "highlight_fields": [],
                "focus_reason": "客户端策略已配置，需完成 code 包构建并 upload 到 OSS",
            }
        return {
            "fix": "buildHistory",
            "fix_section": "",
            "fix_label": "查看构建历史",
            "highlight_fields": [],
            "focus_reason": "下载地址已生成，但 OSS 上产物不可达，需 Jenkins 构建并 upload",
        }

    return {
        "fix": "buildConfig",
        "fix_section": "client_policy",
        "fix_label": "补充下载地址",
        "highlight_fields": ["resource_server_url"],
        "focus_reason": "产物路径已登记，请填写资源服务器 URL 并保存，以生成对外下载地址",
    }


_DIAGNOSTIC_GROUPS: List[Dict[str, Any]] = [
    {
        "id": "code",
        "keys": frozenset({"code"}),
        "label": "代码热更包",
        "hint_ready_path": "代码产物路径已登记，需在「客户端策略」补充 resource_server_url 等下载地址",
        "hint_unreachable": "下载地址已配置，但 code manifest 不可达（404），需 Jenkins 构建并 upload",
        "hint_missing": "需开启热更发布步骤、完成构建并登记 code 包",
        "priority": 1,
    },
    {
        "id": "apk",
        "keys": frozenset({"apk"}),
        "label": "APK 安装包",
        "hint_ready_path": "安装包路径已登记，需在「客户端策略」补充 resource_server_url / catalog 等对外下载地址",
        "hint_unreachable": "下载地址已配置，但 OSS 远程产物不可达（404），需 Jenkins 构建并 upload",
        "hint_missing": "需完成安装包构建并登记 APK 与 Catalog",
        "priority": 2,
    },
    {
        "id": "resource",
        "keys": frozenset({"resource"}),
        "label": "资源包",
        "hint_ready_path": "资源路径已登记，需在「客户端策略」补充 resource_server_url 与 resource_version",
        "hint_unreachable": "下载地址已配置，但 OSS 远程产物不可达（404），需 Jenkins 构建并 upload",
        "hint_missing": "需完成资源打包并登记资源包 URL",
        "priority": 3,
    },
    {
        "id": "config",
        "keys": frozenset({"config"}),
        "label": "配置包",
        "hint_ready_path": "配置路径已登记，需在「客户端策略」补充下载基址与 manifest 对外地址",
        "hint_unreachable": "下载地址已配置，但 OSS manifest 不可达（404），需 Jenkins 构建并 upload",
        "hint_missing": "需完成配置导出并登记配置包 URL",
        "priority": 4,
    },
    {
        "id": "network",
        "keys": frozenset({"network"}),
        "label": "网络接入配置",
        "hint_missing": "环境网络接入字段未配置完整",
        "fix": "network",
        "priority": 10,
    },
    {
        "id": "scope",
        "keys": frozenset({"scope"}),
        "label": "交付范围对齐",
        "hint_missing": "VersionCode 与发布单环境/渠道/Scope 不一致",
        "fix": "edit",
        "priority": 11,
    },
]


def _canonical_failing_key(key: str) -> str:
    k = str(key or "").strip().lower()
    if not k:
        return k
    if k in {"code", "code_url", "code_manifest_url"} or "code_manifest" in k:
        return "code"
    if k in {"apk", "apk_url", "apk_version", "catalog", "catalog_url"} or k.startswith("apk"):
        return "apk"
    if k in {"resource", "resource_url", "resource_version"} or "resource" in k:
        return "resource"
    if k in {"config", "config_url", "config_version", "config_manifest_url"} or "config" in k:
        return "config"
    if k in {"gateway_ws", "login_http", "game_ws", "ops_http"}:
        return "network"
    if k in {"scope_id", "env_key", "channel_id"}:
        return "scope"
    return k


def _artifact_row(artifacts: List[dict], artifact_type: str) -> dict:
    want = str(artifact_type or "").strip().lower()
    for row in artifacts or []:
        if str(row.get("artifact_type") or "").strip().lower() == want:
            return dict(row)
    return {}


def summarize_order_diagnostic_issues(
    order: dict,
    payload: Optional[dict] = None,
    *,
    pipeline_snapshot: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Collapse raw precheck field lists into a small set of actionable issues."""
    if str(order.get("status") or "") in {"published", "completed", "rolled_back"}:
        return []
    payload = _refresh_diagnostic_payload(str(order.get("project_id") or ""), order, payload if isinstance(payload, dict) else {})
    failing: set = set()
    for key in payload.get("missing_client_fields") or []:
        failing.add(_canonical_failing_key(key))
    for key in payload.get("missing_profile_fields") or []:
        failing.add(_canonical_failing_key(key))
    for key in payload.get("missing_artifact_fields") or []:
        failing.add(_canonical_failing_key(key))
    for key in payload.get("alignment_errors") or []:
        failing.add(_canonical_failing_key(key))
    artifacts = order.get("artifacts") or []
    for row in artifacts:
        status = str(row.get("status") or "").lower()
        if status in {"missing", "unreachable", "invalid"}:
            failing.add(_canonical_failing_key(str(row.get("artifact_type") or "")))
    failing.discard("")

    issues: List[Dict[str, Any]] = []
    consumed: set = set()

    def _has_registered_path(group_id: str) -> bool:
        art = _artifact_row(artifacts, group_id)
        return bool(str(art.get("artifact_path") or art.get("artifact_url") or "").strip())

    for group in sorted(_DIAGNOSTIC_GROUPS, key=lambda item: int(item.get("priority") or 99)):
        matched = failing & set(group["keys"])
        if not matched:
            continue
        consumed |= matched
        if group["id"] in {"apk", "resource", "config", "code"} and _has_registered_path(group["id"]):
            pid = str(order.get("project_id") or "").strip()
            if pid and _bootstrap_configured(pid, order, payload):
                hint = str(group.get("hint_unreachable") or group.get("hint_missing") or "")
            else:
                hint = str(group.get("hint_ready_path") or group.get("hint_missing") or "")
        elif group["id"] == "network":
            fields = ", ".join(sorted(payload.get("missing_profile_fields") or []))
            hint = f"缺少：{fields}" if fields else str(group.get("hint_missing") or "")
        elif group["id"] == "scope":
            fields = ", ".join(sorted(payload.get("alignment_errors") or []))
            hint = f"不一致项：{fields}" if fields else str(group.get("hint_missing") or "")
        else:
            hint = str(group.get("hint_missing") or "预检未通过")
        fix_meta = _resolve_issue_fix(
            group["id"],
            order,
            pipeline_snapshot,
            precheck_payload=payload,
            project_id=str(order.get("project_id") or ""),
        )
        issues.append(
            {
                "id": group["id"],
                "label": group["label"],
                "hint": hint,
                "fix": fix_meta.get("fix") or "edit",
                "fix_section": fix_meta.get("fix_section") or "",
                "fix_label": fix_meta.get("fix_label") or "去处理",
                "highlight_fields": fix_meta.get("highlight_fields") or [],
                "focus_reason": fix_meta.get("focus_reason") or "",
                "fields": sorted(matched),
                "runtime_action": fix_meta.get("runtime_action") or {},
            }
        )

    if payload.get("topology_runtime_aligned") is False or payload.get("runtime_error"):
        runtime_hint = str(payload.get("runtime_error") or "").strip()
        if payload.get("topology_runtime_aligned") is False:
            topo_hint = f"设计拓扑 {payload.get('topology_id') or '-'}，运行拓扑 {payload.get('runtime_topology_id') or '-'}"
            runtime_hint = f"{runtime_hint}；{topo_hint}" if runtime_hint else topo_hint
        pid = str(order.get("project_id") or "").strip()
        env_key = str(order.get("env_key") or "").strip()
        topology_id = str(payload.get("topology_id") or order.get("topology_id") or "").strip()
        node_id = _resolve_runtime_start_node(pid, env_key, topology_id)
        issues.append(
            {
                "id": "runtime",
                "label": "Runtime 运行态",
                "hint": runtime_hint or "目标拓扑未运行，需启动 Runtime",
                "fix": "runtime",
                "fix_action": "start_runtime",
                "fix_section": "",
                "fix_label": "启动运行态",
                "highlight_fields": ["runtime_topology"],
                "focus_reason": "目标环境尚未启动运行态，请启动 Runtime 后返回发布单重新预检",
                "fields": ["runtime"],
                "runtime_action": {
                    "project_id": pid,
                    "env_key": env_key,
                    "topology_id": topology_id,
                    "node_id": node_id,
                },
            }
        )

    return issues
