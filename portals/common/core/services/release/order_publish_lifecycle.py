# -*- coding: utf-8 -*-
"""Post-publish release order lifecycle."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.release.env_registry import normalize_release_env_key
from services.release.order_helpers import _decode, _event, _json, _now_iso


def _order_crud():
    import services.release.order_crud as mod
    return mod


def pause_gray_rollout_for_order(
    project_id: str,
    order: Dict[str, Any],
    actor: str,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    """Hold gray rollout after verify failure or metric incident."""
    order_id = str(order.get("release_order_id") or "")
    if not order_id:
        return {"ok": False, "reason": "missing_order_id"}
    if str(order.get("status") or "") not in {"published", "verify_failed", "verified"}:
        return {"ok": False, "reason": "invalid_status"}
    bundle_id = str(order.get("bundle_id") or "").strip()
    if not bundle_id:
        return {"ok": False, "reason": "missing_bundle"}
    plan = dict(order.get("payload") or {})
    strategy = str(plan.get("release_strategy") or "standard").strip().lower()
    if strategy != "gray":
        return {"ok": False, "reason": "not_gray", "skipped": True}
    if str(plan.get("gray_success_action") or "").strip().lower() == "hold":
        return {"ok": True, "already_paused": True, "release_order_id": order_id}
    now = _now_iso()
    pause_reason = str(reason or "verify_failed")[:500]
    init_db()
    with get_cursor() as cur:
        bundle_row = cur.execute("SELECT payload FROM release_bundles WHERE bundle_id=?", (bundle_id,)).fetchone()
        if not bundle_row:
            return {"ok": False, "reason": "bundle_not_found"}
        bundle = _decode(bundle_row["payload"], {}) or {}
        bundle["gray_success_action"] = "hold"
        bundle["gray_paused_at"] = now
        bundle["gray_paused_reason"] = pause_reason
        bundle["gray_paused_by"] = actor
        bundle["updated_at"] = now
        cur.execute(
            "UPDATE release_bundles SET payload=?, updated_at=? WHERE bundle_id=?",
            (_json(bundle), now, bundle_id),
        )
        plan["gray_success_action"] = "hold"
        plan["gray_paused_at"] = now
        plan["gray_paused_reason"] = pause_reason
        cur.execute(
            "UPDATE release_orders SET payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (_json(plan), now, project_id, order_id),
        )
        _event(
            cur,
            order_id,
            "gray_rollout_paused",
            actor,
            str(order.get("status") or "published"),
            str(order.get("status") or "published"),
            {"bundle_id": bundle_id, "reason": pause_reason},
        )
    try:
        from services.notify.outbound_webhook import EVENT_GRAY_ROLLOUT_PAUSED, notify_release_event

        notify_release_event(
            EVENT_GRAY_ROLLOUT_PAUSED,
            {
                "project_id": project_id,
                "release_order_id": order_id,
                "bundle_id": bundle_id,
                "reason": pause_reason,
                "actor": actor,
            },
        )
    except Exception:
        pass
    return {"ok": True, "release_order_id": order_id, "gray_success_action": "hold", "reason": pause_reason}


def expand_gray_rollout(
    project_id: str,
    order_id: str,
    actor: str,
    *,
    target_ratio: int = 100,
) -> Dict[str, Any]:
    order = _order_crud().get_release_order(project_id, order_id, include_details=True)
    if not order:
        raise ValueError("发布单不存在")
    if str(order.get("status") or "") != "published":
        raise ValueError("仅已发布订单可扩大灰度")
    bundle_id = str(order.get("bundle_id") or "").strip()
    if not bundle_id:
        raise ValueError("发布单缺少 bundle")
    plan = dict(order.get("payload") or {})
    hold_action = str(plan.get("gray_success_action") or "manual").strip().lower()
    if hold_action == "hold":
        raise ValueError("灰度策略为保持当前比例，不可扩大放量")
    try:
        ratio = max(1, min(100, int(target_ratio)))
    except (TypeError, ValueError):
        ratio = 100
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        row = cur.execute("SELECT payload FROM release_bundles WHERE bundle_id=?", (bundle_id,)).fetchone()
        if not row:
            raise ValueError("Bundle 不存在")
        bundle = _decode(row["payload"], {}) or {}
        client = dict(bundle.get("client") or {})
        client["rollout_percentage"] = ratio
        bundle["client"] = client
        bundle["rollout_percentage"] = ratio
        bundle["gray_ratio"] = str(ratio)
        bundle["gray_status"] = "full" if ratio >= 100 else "active"
        bundle["gray_expanded_at"] = now
        bundle["gray_expanded_by"] = actor
        bundle["updated_at"] = now
        cur.execute(
            "UPDATE release_bundles SET payload=?, updated_at=? WHERE bundle_id=?",
            (_json(bundle), now, bundle_id),
        )
        plan = dict(order.get("payload") or {})
        plan["gray_ratio"] = str(ratio)
        if ratio >= 100:
            plan["release_strategy"] = "standard"
        cur.execute(
            "UPDATE release_orders SET payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (_json(plan), now, project_id, order_id),
        )
        _event(cur, order_id, "gray_expanded", actor, "published", "published", {"bundle_id": bundle_id, "rollout_percentage": ratio})
    return _order_crud().get_release_order(project_id, order_id)


def run_bootstrap_smoke_for_order(project_id: str, order_id: str) -> Dict[str, Any]:
    """HTTP smoke against active bundle fields after publish (internal validation)."""
    order = _order_crud().get_release_order(project_id, order_id, include_details=False)
    if not order:
        raise ValueError("发布单不存在")
    scope_id = str(order.get("scope_id") or "").strip()
    bundle_id = str(order.get("bundle_id") or "").strip()
    if not scope_id or not bundle_id:
        return {"ok": False, "error": "发布单缺少 scope 或 bundle", "checks": []}
    from services.release.bundle_service import _check_remote_artifact, find_active_bundle

    bundle = find_active_bundle(scope_id, platform=str(order.get("platform") or ""))
    if not bundle or str(bundle.get("bundle_id") or "") != bundle_id:
        return {"ok": False, "error": "active bundle 与发布单不一致", "checks": []}
    client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
    checks: List[Dict[str, Any]] = []
    probe_keys = ("catalog_url", "config_manifest_url", "code_manifest_url")
    for key in probe_keys:
        val = str(client.get(key) or "").strip()
        probe = _check_remote_artifact(val) if val else {"ok": False, "status": 0, "error": "missing url"}
        checks.append(
            {
                "key": key,
                "ok": bool(probe.get("ok")),
                "value": val[:120] if val else "",
                "probe": probe,
            }
        )
    if str(order.get("platform") or "").lower() == "android":
        apk_url = str(client.get("apk_url") or client.get("catalog_url") or "").strip()
        probe = _check_remote_artifact(apk_url) if apk_url else {"ok": False, "status": 0, "error": "missing url"}
        checks.append(
            {
                "key": "apk_url",
                "ok": bool(probe.get("ok")),
                "value": apk_url[:120] if apk_url else "",
                "probe": probe,
            }
        )
    ok = all(item.get("ok") for item in checks)
    return {"ok": ok, "bundle_id": bundle_id, "scope_id": scope_id, "checks": checks}


def verify_release_order(project_id: str, order_id: str, actor: str, ok: bool = True) -> Dict[str, Any]:
    order = _order_crud().get_release_order(project_id, order_id, include_details=False)
    if order.get("status") not in {"published", "verifying", "verify_failed"}:
        raise ValueError("只有已发布的发布单可以验证")
    _order_crud()._transition(project_id, order_id, actor, "verifying", "verify_started", {})
    smoke_ok = ok
    smoke_report: Dict[str, Any] = {}
    if ok:
        smoke_report = run_bootstrap_smoke_for_order(project_id, order_id)
        smoke_ok = bool(smoke_report.get("ok"))
        try:
            from services.release.bootstrap_hotupdate_regression import run_hotupdate_regression_for_order

            regression = run_hotupdate_regression_for_order(project_id, order_id)
            smoke_report["hotupdate_regression"] = regression
            smoke_ok = smoke_ok and bool(regression.get("ok"))
        except Exception as exc:
            smoke_report["hotupdate_regression"] = {"ok": False, "error": str(exc)}
            smoke_ok = False
    from services.release.validation_plan_runner import run_validation_plan

    validation = run_validation_plan({**order, "project_id": project_id, "release_order_id": order_id}, phase="verify")
    smoke_ok = smoke_ok and bool(validation.get("ok", True))
    target = "verified" if smoke_ok else "verify_failed"
    result = _order_crud()._transition(
        project_id,
        order_id,
        actor,
        target,
        "verified" if smoke_ok else "verify_failed",
        {"ok": smoke_ok, "smoke": smoke_report, "validation_plan": validation},
    )
    if not smoke_ok:
        try:
            from services.release.incident_loop_service import handle_verify_failure

            handle_verify_failure(
                project_id,
                result,
                actor,
                smoke_report=smoke_report,
                validation=validation,
            )
        except Exception:
            pass
    return result


def rollback_release_order(project_id: str, order_id: str, actor: str) -> Dict[str, Any]:
    from services.release.order_state_machine import assert_transition

    target = _order_crud().get_release_order(project_id, order_id, include_details=False)
    if not target or not target.get("bundle_id"):
        raise ValueError("目标发布单没有可回滚 Bundle")
    now = _now_iso()
    superseded_order = None
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
        assert_transition(str(target.get("status") or "published"), "published")
        cur.execute(
            "UPDATE release_orders SET status='published', published_at=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (now, now, project_id, order_id),
        )
        if current and str(current["release_order_id"] or ""):
            superseded_oid = str(current["release_order_id"])
            superseded_order = _order_crud().get_release_order(project_id, superseded_oid, include_details=False)
            assert_transition(str(superseded_order.get("status") or "published"), "rolled_back")
            cur.execute(
                "UPDATE release_orders SET status='rolled_back', updated_at=? WHERE project_id=? AND release_order_id=?",
                (now, project_id, superseded_oid),
            )
        cur.execute(
            "UPDATE release_scopes SET active_bundle_id=?, updated_at=? WHERE scope_id=?",
            (target["bundle_id"], now, target["scope_id"]),
        )
        _event(cur, order_id, "rollback_restored", actor, target["status"], "published", {"bundle_id": target["bundle_id"]})
    result = _order_crud().get_release_order(project_id, order_id)
    try:
        from services.release.server_coordinated_rollback import maybe_coordinated_server_rollback

        server_rb = maybe_coordinated_server_rollback(project_id, result, superseded_order, actor)
        result = _order_crud().get_release_order(project_id, order_id)
        if isinstance(result.get("payload"), dict):
            result["payload"]["server_coordinated_rollback"] = server_rb
    except ValueError as exc:
        result = _order_crud().get_release_order(project_id, order_id)
        if isinstance(result.get("payload"), dict):
            result["payload"]["server_coordinated_rollback"] = {"ok": False, "error": str(exc)}
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
    release_order_id: str = "",
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
    mode_key = str(mode or "full").strip().lower()
    order_id = str(release_order_id or "").strip()
    if mode_key not in {"rollback"} and not order_id:
        raise ValueError("Scope 直发必须绑定发布单 release_order_id")
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
        if order_id:
            target_bundle["release_order_id"] = order_id
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

