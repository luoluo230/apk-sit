# -*- coding: utf-8 -*-
"""ReleaseBatch orchestration — multi-line release sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from models.data import projects_db
from models.db import _get_conn, get_cursor, init_db
from services.release.env_registry import normalize_release_env_key
from services.release.order_constants import TERMINAL_STATUSES
from services.release.order_helpers import _decode, _find_version, _json, _now_iso

BATCH_EDITABLE_STATUSES = {"draft", "artifacts_ready", "precheck_failed", "partial_failed", "ready"}

STATUS_RANK: Dict[str, int] = {
    "partial_failed": 0,
    "publish_failed": 1,
    "verify_failed": 2,
    "precheck_failed": 3,
    "cancelled": 4,
    "building": 5,
    "prechecking": 6,
    "publishing": 7,
    "verifying": 8,
    "awaiting_approval": 9,
    "approved": 10,
    "draft": 11,
    "artifacts_ready": 12,
    "ready": 13,
    "published": 14,
    "verified": 15,
    "completed": 16,
}

SHARED_PLAN_KEYS = (
    "owner",
    "release_reason_type",
    "release_window",
    "change_order",
    "related_requirements",
    "related_tasks",
    "release_description",
    "target_topology_id",
    "release_strategy",
    "gray_strategy",
    "gray_ratio",
    "gray_duration",
    "gray_success_action",
    "validation_plan",
    "rollback_plan",
    "server_release_id",
    "linked_server_release_id",
    "server_artifact_id",
    "target_services",
    "min_server_version",
    "waive_server_release_check",
    "deploy_server_with_client",
    "rollback_with_server",
    "skip_failed_lines_on_publish",
)


def _batch_id() -> str:
    return f"rbatch-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _batch_event(cur, batch_id: str, event_type: str, actor: str, from_status: str = "", to_status: str = "", payload=None):
    cur.execute(
        """
        INSERT INTO release_batch_events (
            batch_id, event_type, from_status, to_status, actor, payload, created_at
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (batch_id, event_type, from_status, to_status, actor, _json(payload or {}), _now_iso()),
    )


def _batch_from_row(row, *, include_events: bool = False) -> Dict[str, Any]:
    result = {
        "batch_id": row["batch_id"],
        "project_id": row["project_id"],
        "env_key": row["env_key"],
        "status": row["status"],
        "shared_plan": _decode(row["shared_plan"], {}) or {},
        "line_targets": _decode(row["line_targets"], []) or [],
        "announcement": _decode(row["announcement"], {}) or {},
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_events:
        conn = _get_conn()
        result["events"] = [
            {**dict(ev), "payload": _decode(ev["payload"], {}) or {}}
            for ev in conn.execute(
                "SELECT * FROM release_batch_events WHERE batch_id=? ORDER BY id DESC LIMIT 50",
                (row["batch_id"],),
            ).fetchall()
        ]
    return result


def _orders_for_batch(project_id: str, batch_id: str) -> List[Dict[str, Any]]:
    from services.release.order_crud import _order_from_row

    init_db()
    rows = _get_conn().execute(
        "SELECT * FROM release_orders WHERE project_id=? AND batch_id=? ORDER BY channel_id, platform",
        (project_id, batch_id),
    ).fetchall()
    return [_order_from_row(row) for row in rows]


def _aggregate_batch_status(orders: List[Dict[str, Any]]) -> str:
    if not orders:
        return "draft"
    statuses = [str(o.get("status") or "draft") for o in orders]
    failed = [s for s in statuses if s in {"precheck_failed", "publish_failed", "verify_failed"}]
    okish = [s for s in statuses if s not in {"precheck_failed", "publish_failed", "verify_failed", "cancelled"}]
    if failed and okish:
        return "partial_failed"
    if all(s in TERMINAL_STATUSES or s in {"verified", "published"} for s in statuses):
        if all(s == "verified" for s in statuses):
            return "completed"
        if all(s in {"verified", "published"} for s in statuses):
            return "published"
    worst = min(statuses, key=lambda s: STATUS_RANK.get(s, 50))
    return worst


def _sync_batch_status(project_id: str, batch_id: str, actor: str = "system") -> str:
    batch = get_release_batch(project_id, batch_id)
    if not batch:
        return ""
    orders = _orders_for_batch(project_id, batch_id)
    new_status = _aggregate_batch_status(orders)
    old_status = str(batch.get("status") or "")
    if new_status != old_status:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE release_batches SET status=?, updated_at=? WHERE project_id=? AND batch_id=?",
                (new_status, _now_iso(), project_id, batch_id),
            )
            _batch_event(cur, batch_id, "status_synced", actor, old_status, new_status, {"order_count": len(orders)})
    return new_status


def list_release_batches(project_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    init_db()
    rows = _get_conn().execute(
        "SELECT * FROM release_batches WHERE project_id=? ORDER BY updated_at DESC LIMIT ?",
        (project_id, max(1, min(limit, 100))),
    ).fetchall()
    out = []
    for row in rows:
        item = _batch_from_row(row)
        item["order_count"] = len(_orders_for_batch(project_id, item["batch_id"]))
        out.append(item)
    return out


def get_release_batch(project_id: str, batch_id: str, *, include_events: bool = False) -> Dict[str, Any]:
    init_db()
    row = _get_conn().execute(
        "SELECT * FROM release_batches WHERE project_id=? AND batch_id=?",
        (project_id, batch_id),
    ).fetchone()
    if not row:
        return {}
    result = _batch_from_row(row, include_events=include_events)
    result["orders"] = _orders_for_batch(project_id, batch_id)
    return result


def _merge_shared_into_order_payload(shared: Dict[str, Any], line_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for key in SHARED_PLAN_KEYS:
        if key in shared and shared.get(key) not in (None, ""):
            payload[key] = shared[key]
    if line_overrides:
        for key, val in line_overrides.items():
            if val not in (None, ""):
                payload[key] = val
    return payload


def create_release_batch(project_id: str, payload: Dict[str, Any], actor: str) -> Dict[str, Any]:
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    env_key = normalize_release_env_key(payload.get("env_key"), project_id=project_id)
    line_targets = payload.get("line_targets") if isinstance(payload.get("line_targets"), list) else []
    if not line_targets:
        raise ValueError("请至少选择一条交付线")
    shared_plan = dict(payload.get("shared_plan") or {})
    announcement = dict(payload.get("announcement") or {})
    if not str(shared_plan.get("owner") or actor).strip():
        shared_plan["owner"] = actor
    batch_id = _batch_id()
    now = _now_iso()
    init_db()
    from services.release.order_crud import create_release_order

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO release_batches (
                batch_id, project_id, env_key, status, shared_plan, line_targets,
                announcement, created_by, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                batch_id,
                project_id,
                env_key,
                "draft",
                _json(shared_plan),
                _json(line_targets),
                _json(announcement),
                actor,
                now,
                now,
            ),
        )
        _batch_event(cur, batch_id, "created", actor, "", "draft", {"line_count": len(line_targets)})
    for line in line_targets:
        if not isinstance(line, dict):
            continue
        channel_id = str(line.get("channel_id") or "").strip()
        platform = str(line.get("platform") or "android").strip().lower()
        version_id = str(line.get("version_id") or "").strip()
        if not channel_id or not version_id:
            raise ValueError("每条交付线需指定 channel_id 与 version_id")
        version = _find_version(project_id, version_id)
        if not version:
            raise ValueError(f"VersionCode 不存在: {version_id}")
        order_payload = {
            "env_key": env_key,
            "channel_id": channel_id,
            "platform": platform,
            "version_id": version_id,
            "version_code": str(version.get("version_code") or ""),
            "reason": str(shared_plan.get("release_description") or shared_plan.get("reason") or "发版控制台批量创建"),
            "owner": str(shared_plan.get("owner") or actor),
            "batch_id": batch_id,
            **_merge_shared_into_order_payload(shared_plan, line.get("overrides") if isinstance(line.get("overrides"), dict) else None),
        }
        create_release_order(project_id, order_payload, actor)
    return get_release_batch(project_id, batch_id)


def update_release_batch(project_id: str, batch_id: str, payload: Dict[str, Any], actor: str) -> Dict[str, Any]:
    batch = get_release_batch(project_id, batch_id)
    if not batch:
        raise ValueError("发版批次不存在")
    if str(batch.get("status") or "") not in BATCH_EDITABLE_STATUSES:
        raise ValueError("当前批次状态不可编辑")
    shared_plan = dict(batch.get("shared_plan") or {})
    announcement = dict(batch.get("announcement") or {})
    line_targets = list(batch.get("line_targets") or [])
    if isinstance(payload.get("shared_plan"), dict):
        for key in SHARED_PLAN_KEYS:
            if key in payload["shared_plan"]:
                shared_plan[key] = payload["shared_plan"][key]
    if isinstance(payload.get("announcement"), dict):
        announcement.update(payload["announcement"])
    if isinstance(payload.get("line_targets"), list) and payload["line_targets"]:
        line_targets = payload["line_targets"]
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE release_batches
            SET shared_plan=?, line_targets=?, announcement=?, updated_at=?
            WHERE project_id=? AND batch_id=?
            """,
            (_json(shared_plan), _json(line_targets), _json(announcement), now, project_id, batch_id),
        )
        _batch_event(cur, batch_id, "plan_updated", actor, batch["status"], batch["status"], {"keys": sorted(payload.keys())})
    orders = _orders_for_batch(project_id, batch_id)
    if orders and shared_plan:
        from services.release.order_crud import update_release_order

        order_patch = _merge_shared_into_order_payload(shared_plan)
        for order in orders:
            if str(order.get("status") or "") in {"draft", "artifacts_ready", "precheck_failed"}:
                try:
                    update_release_order(project_id, order["release_order_id"], order_patch, actor)
                except ValueError:
                    pass
    return get_release_batch(project_id, batch_id)


def batch_readiness(project_id: str, batch_id: str) -> Dict[str, Any]:
    batch = get_release_batch(project_id, batch_id)
    if not batch:
        raise ValueError("发版批次不存在")
    from services.release.release_console_bff import line_readiness_for_batch

    return line_readiness_for_batch(project_id, batch)


def _run_batch_action(
    project_id: str,
    batch_id: str,
    actor: str,
    action: str,
    *,
    order_filter=None,
    extra_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    batch = get_release_batch(project_id, batch_id)
    if not batch:
        raise ValueError("发版批次不存在")
    from services.release.release_order_service import (
        cancel_release_order,
        precheck_release_order,
        publish_release_order,
        request_build,
        verify_release_order,
    )

    handlers = {
        "build": request_build,
        "precheck": precheck_release_order,
        "publish": publish_release_order,
        "verify": verify_release_order,
        "cancel": cancel_release_order,
    }
    handler = handlers.get(action)
    if not handler:
        raise ValueError(f"未知批量动作: {action}")
    extra_kwargs = extra_kwargs or {}
    results: List[Dict[str, Any]] = []
    orders = _orders_for_batch(project_id, batch_id)
    for order in orders:
        oid = str(order.get("release_order_id") or "")
        if order_filter and not order_filter(order):
            continue
        entry = {"release_order_id": oid, "channel_id": order.get("channel_id"), "platform": order.get("platform"), "ok": False}
        try:
            if action == "precheck":
                row = handler(project_id, oid, actor, auto_ensure_runtime=bool(extra_kwargs.get("auto_ensure_runtime")))
            elif action == "verify":
                row = handler(project_id, oid, actor, ok=bool(extra_kwargs.get("ok", True)))
            else:
                row = handler(project_id, oid, actor)
            entry["ok"] = True
            entry["status"] = row.get("status")
        except ValueError as exc:
            entry["error"] = str(exc)
        except Exception as exc:
            entry["error"] = str(exc)
        results.append(entry)
    with get_cursor() as cur:
        _batch_event(cur, batch_id, f"batch_{action}", actor, batch["status"], batch["status"], {"results": results})
    new_status = _sync_batch_status(project_id, batch_id, actor)
    if action == "publish":
        from services.release.release_announcement_service import maybe_sync_batch_announcement

        ann_result = maybe_sync_batch_announcement(project_id, batch_id, actor)
        return {
            "batch_id": batch_id,
            "status": new_status,
            "results": results,
            "announcement_sync": ann_result,
        }
    return {"batch_id": batch_id, "status": new_status, "results": results}


def batch_build(project_id: str, batch_id: str, actor: str, *, retry_failed_only: bool = False) -> Dict[str, Any]:
    def _filter(order: Dict[str, Any]) -> bool:
        status = str(order.get("status") or "")
        if retry_failed_only:
            return status in {"draft", "precheck_failed", "publish_failed"}
        return status in {"draft", "artifacts_ready", "precheck_failed"}

    with get_cursor() as cur:
        _batch_event(cur, batch_id, "batch_build_started", actor, "", "building", {})
    _get_conn().execute(
        "UPDATE release_batches SET status=?, updated_at=? WHERE project_id=? AND batch_id=?",
        ("building", _now_iso(), project_id, batch_id),
    )
    return _run_batch_action(project_id, batch_id, actor, "build", order_filter=_filter)


def batch_precheck(project_id: str, batch_id: str, actor: str, *, auto_ensure_runtime: bool = False) -> Dict[str, Any]:
    def _filter(order: Dict[str, Any]) -> bool:
        return str(order.get("status") or "") in {"artifacts_ready", "precheck_failed", "ready"}

    with get_cursor() as cur:
        _batch_event(cur, batch_id, "batch_precheck_started", actor, "", "prechecking", {})
    _get_conn().execute(
        "UPDATE release_batches SET status=?, updated_at=? WHERE project_id=? AND batch_id=?",
        ("prechecking", _now_iso(), project_id, batch_id),
    )
    return _run_batch_action(
        project_id,
        batch_id,
        actor,
        "precheck",
        order_filter=_filter,
        extra_kwargs={"auto_ensure_runtime": auto_ensure_runtime},
    )


def batch_publish(
    project_id: str,
    batch_id: str,
    actor: str,
    *,
    skip_failed_lines: bool = False,
    confirm_production: bool = False,
) -> Dict[str, Any]:
    batch = get_release_batch(project_id, batch_id)
    if not batch:
        raise ValueError("发版批次不存在")
    env_key = str(batch.get("env_key") or "")
    from services.release.release_policy_service import get_env_release_policy

    policy = get_env_release_policy(project_id, env_key)
    if policy.get("require_approval") and env_key in ("production", "staging"):
        pending = [o for o in batch.get("orders") or [] if str(o.get("status") or "") not in {"ready", "approved"}]
        if pending:
            raise ValueError("存在未就绪或未审批的发布单，无法批量发布")
    if env_key == "production" and not confirm_production:
        raise ValueError("生产发布需二次确认（confirm_production=true）")
    shared = batch.get("shared_plan") or {}
    if skip_failed_lines or shared.get("skip_failed_lines_on_publish"):
        def _filter(order: Dict[str, Any]) -> bool:
            return str(order.get("status") or "") in {"ready", "approved"}
    else:
        failed = [o for o in batch.get("orders") or [] if str(o.get("status") or "") == "precheck_failed"]
        if failed:
            raise ValueError("存在预检失败的线，默认阻塞发布；可勾选跳过失败线并留痕")

        def _filter(order: Dict[str, Any]) -> bool:
            return str(order.get("status") or "") in {"ready", "approved"}

    with get_cursor() as cur:
        _batch_event(
            cur,
            batch_id,
            "batch_publish_started",
            actor,
            batch["status"],
            "publishing",
            {"skip_failed_lines": skip_failed_lines},
        )
    _get_conn().execute(
        "UPDATE release_batches SET status=?, updated_at=? WHERE project_id=? AND batch_id=?",
        ("publishing", _now_iso(), project_id, batch_id),
    )
    return _run_batch_action(project_id, batch_id, actor, "publish", order_filter=_filter)


def batch_verify(project_id: str, batch_id: str, actor: str, *, ok: bool = True) -> Dict[str, Any]:
    def _filter(order: Dict[str, Any]) -> bool:
        return str(order.get("status") or "") in {"published", "verifying", "verify_failed"}

    with get_cursor() as cur:
        _batch_event(cur, batch_id, "batch_verify_started", actor, "", "verifying", {})
    return _run_batch_action(project_id, batch_id, actor, "verify", order_filter=_filter, extra_kwargs={"ok": ok})


def batch_rollback(
    project_id: str,
    batch_id: str,
    actor: str,
    *,
    skip_failed_lines: bool = False,
) -> Dict[str, Any]:
    from services.release.incident_loop_service import find_rollback_target_order
    from services.release.order_publish_lifecycle import rollback_release_order

    batch = get_release_batch(project_id, batch_id)
    if not batch:
        raise ValueError("发版批次不存在")

    def _eligible(order: Dict[str, Any]) -> bool:
        return str(order.get("status") or "") in {"published", "verify_failed", "verified"}

    results: List[Dict[str, Any]] = []
    orders = _orders_for_batch(project_id, batch_id)
    for order in orders:
        oid = str(order.get("release_order_id") or "")
        if not _eligible(order):
            continue
        entry: Dict[str, Any] = {
            "release_order_id": oid,
            "channel_id": order.get("channel_id"),
            "platform": order.get("platform"),
            "ok": False,
        }
        target = find_rollback_target_order(project_id, str(order.get("scope_id") or ""), oid)
        if not target:
            entry["error"] = "无可回滚的上一个 Bundle"
            results.append(entry)
            continue
        try:
            row = rollback_release_order(project_id, target["release_order_id"], actor)
            entry["ok"] = True
            entry["target_order_id"] = target["release_order_id"]
            entry["status"] = row.get("status")
        except ValueError as exc:
            entry["error"] = str(exc)
            if not skip_failed_lines:
                pass
        except Exception as exc:
            entry["error"] = str(exc)
        results.append(entry)

    with get_cursor() as cur:
        _batch_event(
            cur,
            batch_id,
            "batch_rollback",
            actor,
            batch["status"],
            batch["status"],
            {"results": results, "skip_failed_lines": skip_failed_lines},
        )
    new_status = _sync_batch_status(project_id, batch_id, actor)
    return {"batch_id": batch_id, "status": new_status, "results": results}


def batch_cancel(project_id: str, batch_id: str, actor: str) -> Dict[str, Any]:
    def _filter(order: Dict[str, Any]) -> bool:
        return str(order.get("status") or "") not in TERMINAL_STATUSES

    result = _run_batch_action(project_id, batch_id, actor, "cancel", order_filter=_filter)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE release_batches SET status=?, updated_at=? WHERE project_id=? AND batch_id=?",
            ("cancelled", _now_iso(), project_id, batch_id),
        )
        _batch_event(cur, batch_id, "cancelled", actor, result.get("status") or "", "cancelled", {})
    result["status"] = "cancelled"
    return result


def resolve_batch_next_action(project_id: str, batch_id: str) -> Dict[str, Any]:
    batch = get_release_batch(project_id, batch_id)
    if not batch:
        raise ValueError("发版批次不存在")
    status = str(batch.get("status") or "draft")
    orders = batch.get("orders") or []
    base_api = f"/api/projects/{project_id}/release-batches/{batch_id}"
    more: List[Dict[str, Any]] = []

    def _primary(action: str, label: str, *, api_action: str = "", disabled: bool = False, reason: str = ""):
        return {
            "action": action,
            "label": label,
            "api_action": api_action,
            "api_path": f"{base_api}/{api_action}" if api_action else "",
            "disabled": disabled,
            "reason": reason,
        }

    if not orders:
        primary = _primary("select_lines", "下一步：选择交付线", disabled=True, reason="未选择交付线")
    elif status in ("draft", "precheck_failed", "partial_failed"):
        building = [o for o in orders if str(o.get("status") or "") == "building"]
        if building:
            primary = _primary("wait_build", "下一步：等待构建完成", disabled=True, reason="构建进行中")
        else:
            primary = _primary("build", "构建全部", api_action="build")
        more.extend([
            {"action": "precheck", "label": "预检全部", "api_action": "precheck"},
            {"action": "cancel", "label": "取消批次", "api_action": "cancel"},
        ])
    elif status == "building":
        primary = _primary("wait_build", "下一步：等待构建完成", disabled=True, reason="构建进行中")
    elif status == "artifacts_ready":
        primary = _primary("precheck", "预检全部", api_action="precheck")
        more.append({"action": "build", "label": "重新构建", "api_action": "build"})
    elif status in ("prechecking", "ready", "awaiting_approval", "approved"):
        primary = _primary("publish", "发布全部", api_action="publish")
        more.extend([
            {"action": "precheck", "label": "重新预检", "api_action": "precheck"},
            {"action": "build", "label": "重新构建", "api_action": "build"},
        ])
    elif status == "publishing":
        primary = _primary("wait_publish", "发布进行中…", disabled=True)
    elif status == "published":
        primary = _primary("verify", "验证全部", api_action="verify")
        more.append({"action": "rollback", "label": "批次联合回滚", "api_action": "rollback"})
    elif status in ("verified", "completed"):
        primary = _primary("done", "批次已完成", disabled=True)
        more.append({"action": "rollback", "label": "批次联合回滚", "api_action": "rollback"})
    elif status == "verify_failed":
        primary = _primary("rollback", "批次联合回滚", api_action="rollback")
        more.append({"action": "verify", "label": "重新验证", "api_action": "verify"})
    else:
        primary = _primary("review", "查看批次详情", disabled=False)

    failed_lines = [
        {
            "release_order_id": o.get("release_order_id"),
            "channel_id": o.get("channel_id"),
            "platform": o.get("platform"),
            "status": o.get("status"),
        }
        for o in orders
        if str(o.get("status") or "") in {"precheck_failed", "publish_failed", "verify_failed", "building"}
    ]
    return {
        "batch_id": batch_id,
        "status": status,
        "primary": primary,
        "more_actions": more,
        "failed_lines": failed_lines,
        "order_count": len(orders),
    }
