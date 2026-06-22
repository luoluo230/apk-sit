# -*- coding: utf-8 -*-
"""Release order state machine for the unified project delivery workflow."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from models.data import get_channel_by_id, get_channels_for_project, project_versions_db, projects_db
from models.db import _db_lock, _get_conn, get_cursor, init_db
from services.release.bundle_service import run_scope_precheck
from services.release.env_registry import CANONICAL_ENV_KEYS, normalize_release_env_key
from services.release.scope_resolver import resolve_network_profile, resolve_scope, resolve_topology_binding_for_scope

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
    "gray_ratio",
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
    for row in project_versions_db.get(project_id) or []:
        if not isinstance(row, dict):
            continue
        if version_id and str(row.get("id") or "") == version_id:
            return dict(row)
        if version_code and str(row.get("version_code") or "") == version_code:
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
    return [_order_from_row(row) for row in rows]


def get_release_order(project_id: str, order_id: str, *, include_details: bool = True) -> Dict[str, Any]:
    init_db()
    with _db_lock:
        row = _get_conn().execute(
            "SELECT * FROM release_orders WHERE project_id=? AND release_order_id=?",
            (project_id, order_id),
        ).fetchone()
        return _order_from_row(row, include_details=include_details) if row else {}


def create_release_order(project_id: str, payload: Dict[str, Any], actor: str) -> Dict[str, Any]:
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    env_key = normalize_release_env_key(payload.get("env_key"))
    channel_id = str(payload.get("channel_id") or "").strip()
    platform = str(payload.get("platform") or "").strip().lower()
    version_id = str(payload.get("version_id") or "").strip()
    version_code = str(payload.get("version_code") or "").strip()
    if not channel_id or platform not in {"android", "ios"}:
        raise ValueError("环境、渠道和平台必须精确选择")
    version = _find_version(project_id, version_id, version_code)
    if not version:
        raise ValueError("VersionCode 不存在")
    if str(version.get("platform") or "android").lower() != platform:
        raise ValueError("平台与 VersionCode 不一致")
    version_env_key = normalize_release_env_key(version.get("env_key") or version.get("stage") or version.get("env"))
    version_channel_id = str(version.get("channel_id") or version.get("channel") or "").strip()
    if version_env_key != env_key or version_channel_id != channel_id:
        raise ValueError("VersionCode 与发布单的环境或渠道不一致")
    order_id = _order_id()
    now = _now_iso()
    artifacts = _artifact_rows(version)
    has_artifacts = all(url or path for _, url, path in artifacts[:3])
    status = "artifacts_ready" if has_artifacts else "draft"
    scope = resolve_scope(project_id, env_key, channel_id, auto_create=True)
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
    configured_params = plan.get("jenkins_params")
    if isinstance(configured_params, str) and configured_params.strip():
        try:
            configured_params = json.loads(configured_params)
        except json.JSONDecodeError as exc:
            raise ValueError("发布单中的 Jenkins 构建参数不是有效 JSON") from exc
    params = dict(configured_params or version.get("jenkins_params") or {})
    instance_id = str(plan.get("jenkins_instance_id") or version.get("jenkins_instance_id") or "").strip()
    if not instance_id or not params:
        raise ValueError("当前 VersionCode 未配置 Jenkins 实例或构建参数，请先在版本管理中完成构建配置")
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
    payload.update({"build_job_id": str(build_number), "jenkins_instance_id": instance_id, "jenkins_params": params})
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


def precheck_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if not order:
        raise ValueError("发布单不存在")
    version = _find_version(project_id, order["version_id"], order["version_code"])
    scope = resolve_scope(project_id, order["env_key"], order["channel_id"], auto_create=False)
    if not scope:
        raise ValueError("发布作用域不存在")
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
    scope = resolve_scope(project_id, order["env_key"], order["channel_id"], auto_create=False)
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
    bundle = {
        "bundle_id": bundle_id,
        "release_order_id": order_id,
        "project_id": project_id,
        "scope_id": order["scope_id"],
        "env_key": order["env_key"],
        "channel_id": order["channel_id"],
        "client": {
            "version_id": order["version_id"],
            "version_name": order["version_name"],
            "version_code": order["version_code"],
            "platform": order["platform"],
            "apk_path": str(version.get("apk_path") or ""),
            "apk_url": str(version.get("apk_url") or ""),
            "resource_url": str(version.get("resource_url") or ""),
            "config_url": str(version.get("config_url") or ""),
            "code_url": str(version.get("code_url") or ""),
            "resource_path": str(version.get("resource_path") or ""),
            "config_path": str(version.get("config_path") or ""),
            "code_path": str(version.get("code_path") or ""),
            "artifacts": [
                {
                    "artifact_type": str(item.get("artifact_type") or ""),
                    "artifact_url": str(item.get("artifact_url") or ""),
                    "artifact_path": str(item.get("artifact_path") or ""),
                    "status": str(item.get("status") or ""),
                }
                for item in order.get("artifacts") or []
            ],
        },
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
            "SELECT bundle_id, payload FROM release_bundles WHERE scope_id=? AND publish_status='published' ORDER BY published_at DESC LIMIT 1",
            (order["scope_id"],),
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


def verify_release_order(project_id: str, order_id: str, actor: str, ok: bool = True) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if order.get("status") not in {"published", "verifying", "verify_failed"}:
        raise ValueError("只有已发布的发布单可以验证")
    return _transition(project_id, order_id, actor, "verified" if ok else "verify_failed", "verified", {"ok": ok})


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


def cancel_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = get_release_order(project_id, order_id, include_details=False)
    if order.get("status") in TERMINAL_STATUSES or order.get("status") == "published":
        raise ValueError("当前发布单不可取消")
    return _transition(project_id, order_id, actor, "cancelled", "cancelled")


def context_options(project_id: str) -> Dict[str, Any]:
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
    channels = [
        {"channel_id": str(row.get("id") or ""), "channel_name": str(row.get("name") or row.get("id") or "")}
        for row in get_channels_for_project(project_id)
    ]
    return {
        "project_id": project_id,
        "environments": [
            {"env_key": key, "label": {"development": "开发环境", "testing": "测试环境", "staging": "预发环境", "production": "生产环境"}[key]}
            for key in CANONICAL_ENV_KEYS
        ],
        "channels": channels,
        "platforms": [{"value": "android", "label": "Android"}, {"value": "ios", "label": "iOS"}],
        "versions": versions,
    }


def project_overview(project_id: str) -> Dict[str, Any]:
    init_db()
    cards = []
    for env_key in CANONICAL_ENV_KEYS:
        orders = list_release_orders(project_id, {"env_key": env_key})
        with _db_lock:
            bundles = _get_conn().execute(
                "SELECT * FROM release_bundles WHERE project_id=? AND env_key=? AND publish_status='published' ORDER BY published_at DESC",
                (project_id, env_key),
            ).fetchall()
        active = dict(bundles[0]) if bundles else {}
        pending = sum(1 for row in orders if row["status"] == "awaiting_approval")
        failed = sum(1 for row in orders if row["status"] in {"precheck_failed", "publish_failed", "verify_failed"})
        processing = sum(1 for row in orders if row["status"] in {"building", "prechecking", "publishing", "verifying"})
        health = "blocked" if failed else ("warning" if pending else ("processing" if processing else ("healthy" if active else "unconfigured")))
        cards.append(
            {
                "env_key": env_key,
                "env_label": {"development": "开发环境", "testing": "测试环境", "staging": "预发环境", "production": "生产环境"}[env_key],
                "health": health,
                "active_bundle_id": str(active.get("bundle_id") or ""),
                "version_name": str(active.get("version_name") or ""),
                "version_code": str(active.get("version_code") or ""),
                "topology_id": str(active.get("topology_id") or ""),
                "runtime_run_id": str(active.get("runtime_run_id") or ""),
                "release_order_count": len(orders),
                "pending_approval_count": pending,
                "failed_count": failed,
                "processing_count": processing,
                "channels": sorted({row["channel_name"] for row in orders}),
                "platforms": sorted({row["platform"] for row in orders}),
                "latest_orders": orders[:4],
            }
        )
    return {"project_id": project_id, "project": projects_db.get(project_id) or {}, "environments": cards}
