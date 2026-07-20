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

TERMINAL_STATUSES = {"verified", "rolled_back", "cancelled"}
PUBLISHABLE_STATUSES = {"ready", "approved"}
EDITABLE_PLAN_FIELDS = (
    "owner",
    "release_window",
    "change_order",
    "related_requirements",
    "related_tasks",
    "release_description",
    "jenkins_instance_id",
    "jenkins_job",
    "jenkins_params",
    "target_topology_id",
    "release_strategy",
    "release_reason_type",
    "gray_strategy",
    "gray_ratio",
    "validation_items",
    "gray_duration",
    "gray_success_action",
    "target_audience",
    "validation_plan",
    "validation_task",
    "rollback_plan",
    "rollback_target",
    "rollback_condition",
    "rollback_method",
    "rollback_timeout_minutes",
)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _decode(value: str, default=None):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


def _order_id() -> str:
    return f"ro-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _bundle_id(scope_id: str) -> str:
    slug = str(scope_id or "scope").replace(":", "-")[:40]
    return f"rb-{datetime.now().strftime('%Y%m%d')}-{slug}-{uuid.uuid4().hex[:6]}"


def _event(cur, order_id: str, event_type: str, actor: str, from_status: str = "", to_status: str = "", payload=None):
    cur.execute(
        """
        INSERT INTO release_order_events (
            release_order_id, event_type, from_status, to_status, actor, payload, created_at
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (order_id, event_type, from_status, to_status, actor, _json(payload or {}), _now_iso()),
    )


def _find_version(project_id: str, version_id: str = "", version_code: str = "") -> Dict[str, Any]:
    rows = project_versions_db.get(project_id) or []
    vid = str(version_id or "").strip()
    vcode = str(version_code or "").strip()
    if vid:
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("id") or "") == vid:
                return dict(row)
        return {}
    if vcode:
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("version_code") or "") == vcode:
                return dict(row)
    return {}


def _artifact_rows(version: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    mapping = [
        ("apk", "apk_url", "apk_path"),
        ("resource", "resource_url", "resource_path"),
        ("config", "config_url", "config_path"),
        ("code", "code_url", "code_path"),
    ]
    rows = []
    for artifact_type, url_key, path_key in mapping:
        url = str(version.get(url_key) or "")
        path = str(version.get(path_key) or "")
        rows.append((artifact_type, url, path))
    return rows


def _channel_name(channel_id: str) -> str:
    row = get_channel_by_id(channel_id) or {}
    return str(row.get("name") or row.get("apk_subdir") or channel_id)


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


def _resolve_issue_fix(
    group_id: str,
    order: dict,
    pipeline_snapshot: Optional[dict] = None,
    *,
    precheck_payload: Optional[dict] = None,
    project_id: str = "",
) -> Dict[str, str]:
    if group_id == "runtime":
        return {
            "fix": "runtime",
            "fix_section": "",
            "fix_label": "启动运行态",
            "highlight_fields": ["runtime_topology"],
            "focus_reason": "目标环境尚未启动运行态，请在本页确认拓扑运行状态并启动 Runtime",
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
            }
        )

    if payload.get("topology_runtime_aligned") is False or payload.get("runtime_error"):
        runtime_hint = str(payload.get("runtime_error") or "").strip()
        if payload.get("topology_runtime_aligned") is False:
            topo_hint = f"设计拓扑 {payload.get('topology_id') or '-'}，运行拓扑 {payload.get('runtime_topology_id') or '-'}"
            runtime_hint = f"{runtime_hint}；{topo_hint}" if runtime_hint else topo_hint
        issues.append(
            {
                "id": "runtime",
                "label": "Runtime 运行态",
                "hint": runtime_hint or "目标拓扑未运行，需启动 Runtime",
                "fix": "runtime",
                "fix_section": "",
                "fix_label": "启动运行态",
                "highlight_fields": ["runtime_topology"],
                "focus_reason": "目标环境尚未启动运行态，请启动 Runtime 后返回发布单重新预检",
                "fields": ["runtime"],
            }
        )

    return issues


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
        order = find_release_order_for_version(project_id, vid)
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
    base = f"/admin/projects/{project_id}/environments/{ek}/channels/{cid}"
    qs = urlencode({"env_key": ek, "channel_id": cid})
    return {
        "build": f"{base}/build?{qs}",
        "release": f"{base}/release?{qs}",
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
    order = find_release_order_for_version(project_id, vid) if vid else None
    order_status = str(order.get("status") or "") if order else ""
    artifact_ready = bool(version and str(version.get("apk_status") or "") == "found") or order_status == "artifacts_ready"
    active_bundle = find_active_bundle(scope_id, platform=platform) if scope_id else {}
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
    order = find_release_order_for_version(project_id, vid)
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
    platforms = [{"value": str(l["platform"]), "label": str(l.get("platform_label") or l["platform"])} for l in lines]
    plat = str(platform or "").strip().lower()
    if not plat and platforms:
        plat = platforms[0]["value"]
    line = next((l for l in lines if str(l.get("platform") or "") == plat), lines[0] if lines else None)
    per_platform = {str(l["platform"]): _platform_state_for_journey(project_id, ek, l) for l in lines}
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
    sync_building_release_orders(project_id)
    if selected_vid:
        state = _enrich_state_from_version_id(project_id, state, selected_vid)
        order = find_release_order_for_version(project_id, selected_vid)
        if order:
            state = {**state, "order_status": order.get("status"), "release_order_id": order.get("release_order_id")}
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
        row for row in list_release_orders(project_id, {"env_key": ek, "channel_id": cid})
        if str(row.get("platform") or "").strip().lower() == plat
    ][:20]
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
            "build_entry": {"label": "进入构建流程", "href": urls["build"], "enabled": False, "reason": "渠道未配置"},
            "release_entry": {"label": "进入发版流程", "href": urls["release"], "enabled": False, "reason": "渠道未配置"},
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
            "label": "进入构建流程",
            "href": urls["build"],
            "enabled": True,
            "reason": "" if any_pipeline or platform_lines else "请先配置平台",
        },
        "release_entry": {
            "label": "进入发版流程",
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


def project_overview(project_id: str, filters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    init_db()
    filters = filters or {}
    filter_channel_global = str(filters.get("channel_id") or "").strip()
    cards: List[Dict[str, Any]] = []
    for env_key in list_project_env_keys(project_id):
        if filter_channel_global and not is_channel_allowed_for_env(project_id, env_key, filter_channel_global):
            continue
        orders = list_release_orders(project_id, {"env_key": env_key})
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
        cards.append(
            {
                "env_key": env_key,
                "env_label": project_env_label(project_id, env_key),
                "health": health,
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
    delivery_lines = [enrich_delivery_line_actions(project_id, line) for line in _delivery_lines_for_env(project_id, ek)]
    orders = list_release_orders(project_id, {"env_key": ek})
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
