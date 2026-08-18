# -*- coding: utf-8 -*-
"""Release Hub BFF — unified delivery cockpit aggregating actions, promotion, and observability."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import projects_db
from services.release.bundle_promotion_service import list_promotion_candidates
from services.release.server_artifact_promotion_service import list_server_promotion_candidates
from services.release.env_registry import get_project_env_defs, normalize_release_env_key, project_env_label
from services.release.overview_feed_service import build_release_health_summary
from services.release.release_order_service import list_release_orders, resolve_release_order_next_action
from services.release.release_policy_service import get_env_release_policy


def _module_cards(project_id: str) -> List[Dict[str, Any]]:
    return [
        {
            "id": "release-console",
            "title": "发版控制台",
            "desc": "批量勾选交付线，一次会话完成构建/预检/发布",
            "href": f"/admin/projects/{project_id}/release",
            "icon": "nav_release",
            "primary": True,
        },
        {
            "id": "versions",
            "title": "版本管理",
            "desc": "VersionCode、版本组与单线发版入口",
            "href": f"/admin/projects/{project_id}/versions",
            "icon": "nav_version",
        },
        {
            "id": "release-orders",
            "title": "发布单",
            "desc": "查看/编辑各环境发布单与审批状态",
            "href": f"/admin/projects/{project_id}/release-orders",
            "icon": "nav_release_order",
        },
        {
            "id": "build-history",
            "title": "构建与产物",
            "desc": "Jenkins 构建记录与产物下载",
            "href": f"/admin/projects/{project_id}/build-history?scoped=1&env_key=development",
            "icon": "nav_build_artifact",
        },
    ]


def _prod_wizard_steps(project_id: str) -> List[Dict[str, Any]]:
    policy = get_env_release_policy(project_id, "production")
    tiers = policy.get("approval_tiers") or []
    return [
        {"id": "scope", "label": "选择交付线", "desc": "确认渠道×平台与环境"},
        {"id": "artifacts", "label": "产物就绪", "desc": "构建完成或自低环境晋级"},
        {"id": "precheck", "label": "预检通过", "desc": "拓扑绑定、制品与验证计划"},
        {
            "id": "approval",
            "label": "审批" + (f"（{len(tiers)} 级）" if len(tiers) > 1 else ""),
            "desc": "QA + 发布负责人" if len(tiers) > 1 else "发布负责人确认",
        },
        {"id": "publish", "label": "发布上线", "desc": "Bundle 激活与灰度策略"},
        {"id": "verify", "label": "发布验证", "desc": "冒烟与 bootstrap 校验"},
    ]


def _coordinated_deploy_summary(order: Dict[str, Any]) -> Dict[str, Any] | None:
    plan = order.get("payload") if isinstance(order.get("payload"), dict) else {}
    if not plan.get("deploy_server_with_client"):
        return None
    deploy = plan.get("server_coordinated_deploy") if isinstance(plan.get("server_coordinated_deploy"), dict) else {}
    if deploy.get("skipped"):
        return None
    if deploy.get("error"):
        return {
            "state": "failed",
            "label": "服务端部署失败",
            "detail": str(deploy.get("error") or ""),
            "server_release_id": str(deploy.get("server_release_id") or plan.get("server_release_id") or ""),
        }
    status = str(deploy.get("deploy_status") or "").strip().lower()
    if status == "deploying":
        return {
            "state": "deploying",
            "label": "服务端部署中",
            "server_release_id": str(deploy.get("server_release_id") or plan.get("server_release_id") or ""),
        }
    if status == "deployed":
        return {
            "state": "ok",
            "label": "服务端已部署",
            "server_release_id": str(deploy.get("server_release_id") or plan.get("server_release_id") or ""),
        }
    if deploy.get("server_release_id"):
        return {
            "state": "ok" if status else "pending",
            "label": "服务端已触发部署" if status else "待服务端部署",
            "server_release_id": str(deploy.get("server_release_id") or ""),
            "deploy_status": status,
        }
    return {"state": "pending", "label": "待服务端部署", "server_release_id": ""}


def _coordinated_deploy_feed(project_id: str, *, limit: int = 12) -> List[Dict[str, Any]]:
    orders = list_release_orders(project_id, {})
    out: List[Dict[str, Any]] = []
    for order in orders:
        plan = order.get("payload") if isinstance(order.get("payload"), dict) else {}
        deploy_summary = _coordinated_deploy_summary(order)
        if deploy_summary:
            deploy = plan.get("server_coordinated_deploy") if isinstance(plan.get("server_coordinated_deploy"), dict) else {}
            out.append(
                {
                    "op_type": "deploy",
                    "release_order_id": order.get("release_order_id"),
                    "version_name": order.get("version_name"),
                    "version_code": order.get("version_code"),
                    "env_key": order.get("env_key"),
                    "env_label": project_env_label(project_id, str(order.get("env_key") or "")),
                    "channel_name": order.get("channel_name"),
                    "platform": order.get("platform"),
                    "published_at": order.get("published_at") or order.get("updated_at"),
                    "server_release_id": deploy_summary.get("server_release_id") or "",
                    "state": deploy_summary.get("state"),
                    "label": deploy_summary.get("label"),
                    "detail": deploy_summary.get("detail") or "",
                    "deploy_status": deploy.get("deploy_status") or "",
                    "deploy_jobs_count": len(deploy.get("deploy_jobs") or []),
                    "rollback_steps": [],
                    "order_href": f"/admin/projects/{project_id}/release-orders/{order.get('release_order_id')}",
                    "server_href": f"/admin/projects/{project_id}/server-management?env_key={order.get('env_key') or 'development'}",
                }
            )
        rollback = plan.get("server_coordinated_rollback") if isinstance(plan.get("server_coordinated_rollback"), dict) else {}
        if rollback and not rollback.get("skipped"):
            state = "ok" if rollback.get("ok") else "failed"
            label = "联合回滚成功" if rollback.get("ok") else "联合回滚失败"
            detail = str(rollback.get("error") or "")
            if not detail:
                failed = [s for s in rollback.get("steps") or [] if not s.get("ok")]
                if failed:
                    detail = str(failed[0].get("error") or "")
            out.append(
                {
                    "op_type": "rollback",
                    "release_order_id": order.get("release_order_id"),
                    "version_name": order.get("version_name"),
                    "version_code": order.get("version_code"),
                    "env_key": order.get("env_key"),
                    "env_label": project_env_label(project_id, str(order.get("env_key") or "")),
                    "channel_name": order.get("channel_name"),
                    "platform": order.get("platform"),
                    "published_at": order.get("published_at") or order.get("updated_at"),
                    "server_release_id": str(rollback.get("target_server_release_id") or ""),
                    "state": state,
                    "label": label,
                    "detail": detail,
                    "deploy_status": "",
                    "deploy_jobs_count": 0,
                    "rollback_steps": rollback.get("steps") or [],
                    "order_href": f"/admin/projects/{project_id}/release-orders/{order.get('release_order_id')}",
                    "server_href": f"/admin/projects/{project_id}/server-management?env_key={order.get('env_key') or 'development'}",
                }
            )
    out.sort(key=lambda row: str(row.get("published_at") or ""), reverse=True)
    return out[:limit]


def _pending_actions(project_id: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    orders = list_release_orders(project_id, {})
    pending_statuses = {
        "awaiting_approval",
        "precheck_failed",
        "artifacts_ready",
        "ready",
        "approved",
        "building",
        "published",
    }
    out: List[Dict[str, Any]] = []
    for order in orders:
        status = str(order.get("status") or "")
        if status not in pending_statuses:
            continue
        try:
            nxt = resolve_release_order_next_action(project_id, str(order.get("release_order_id") or ""))
        except ValueError:
            nxt = {}
        out.append(
            {
                "release_order_id": order.get("release_order_id"),
                "env_key": order.get("env_key"),
                "env_label": project_env_label(project_id, str(order.get("env_key") or "")),
                "channel_name": order.get("channel_name"),
                "platform": order.get("platform"),
                "version_name": order.get("version_name"),
                "version_code": order.get("version_code"),
                "status": status,
                "next_action": nxt,
                "coordinated_deploy": _coordinated_deploy_summary(order),
                "href": f"/admin/projects/{project_id}/release-orders/{order.get('release_order_id')}",
            }
        )
        if len(out) >= limit:
            break
    return out


def build_release_hub(project_id: str, *, env_key: str = "") -> Dict[str, Any]:
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    selected_env = normalize_release_env_key(env_key or "development", project_id=project_id) if env_key else "development"
    env_defs = []
    for row in get_project_env_defs(project_id):
        ek = str(row.get("env_key") or "")
        env_defs.append(
            {
                **row,
                "label": project_env_label(project_id, ek),
                "release_policy": get_env_release_policy(project_id, ek),
            }
        )
    health = build_release_health_summary(project_id, days=7)
    return {
        "project_id": project_id,
        "selected_env": selected_env,
        "env_defs": env_defs,
        "module_cards": _module_cards(project_id),
        "prod_wizard_steps": _prod_wizard_steps(project_id),
        "promotion_candidates": list_promotion_candidates(project_id),
        "server_promotion_candidates": list_server_promotion_candidates(project_id),
        "coordinated_deploy_feed": _coordinated_deploy_feed(project_id),
        "pending_actions": _pending_actions(project_id),
        "release_health": health,
        "quick_actions": {
            "dev_quick_publish": f"/api/projects/{project_id}/delivery-attempts/quick-publish",
            "release_console": f"/admin/projects/{project_id}/release?env_key={selected_env}",
            "prod_release": f"/admin/projects/{project_id}/release?env_key=production",
        },
    }
