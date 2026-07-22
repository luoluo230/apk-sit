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


def _order_crud():
    import services.release.order_crud as mod
    return mod
def precheck_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = _order_crud().get_release_order(project_id, order_id, include_details=False)
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
    return _order_crud().get_release_order(project_id, order_id)


def approve_release_order(project_id: str, order_id: str, actor: str, note: str = "") -> Dict[str, Any]:
    order = _order_crud().get_release_order(project_id, order_id, include_details=False)
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
    return _order_crud().get_release_order(project_id, order_id)


def publish_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    order = _order_crud().get_release_order(project_id, order_id, include_details=True)
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
    published = _order_crud().get_release_order(project_id, order_id)
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
    order = _order_crud().get_release_order(project_id, order_id, include_details=False)
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
    order = _order_crud().get_release_order(project_id, order_id, include_details=False)
    if order.get("status") not in {"published", "verifying", "verify_failed"}:
        raise ValueError("只有已发布的发布单可以验证")
    smoke_ok = ok
    smoke_report: Dict[str, Any] = {}
    if ok:
        smoke_report = run_bootstrap_smoke_for_order(project_id, order_id)
        smoke_ok = bool(smoke_report.get("ok"))
    target = "verified" if smoke_ok else "verify_failed"
    return _order_crud()._transition(
        project_id,
        order_id,
        actor,
        target,
        "verified",
        {"ok": smoke_ok, "smoke": smoke_report},
    )


def rollback_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    target = _order_crud().get_release_order(project_id, order_id, include_details=False)
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
    result = _order_crud().get_release_order(project_id, order_id)
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

