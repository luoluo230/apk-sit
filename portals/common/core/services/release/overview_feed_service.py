# -*- coding: utf-8 -*-
"""Project overview activity feed and KPI aggregation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import DATA_DIR
from data.tasks import project_tasks_db
from models.data import projects_db
from models.db import _db_lock, _get_conn, get_audit_log_from_db, init_db
from services.release.env_registry import list_project_env_keys, project_env_label
from services.release.order_helpers import _decode

TASK_STATUS_LABELS = {
    "not_started": "未开始",
    "in_progress": "进行中",
    "pending_review": "待审核",
    "done": "已完成",
    "abandoned": "已放弃",
}

DOC_ACTION_PREFIXES = ("doc_", "docs_", "changelog_")


def _activity_row(
    *,
    kind: str,
    type_label: str,
    title: str,
    actor: str,
    created_at: str,
    href: str,
    event_type: str = "",
) -> Dict[str, Any]:
    ts = str(created_at or "")
    return {
        "kind": kind,
        "type_label": type_label,
        "title": title,
        "actor": str(actor or "系统"),
        "time": ts,
        "time_short": ts[11:16] if len(ts) >= 16 else ts[:16],
        "href": href or "#",
        "event_type": event_type,
    }


def _service_is_healthy(status: Any, probe_status: Any = None) -> bool:
    st = str(status or "").upper()
    probe = str(probe_status or "").upper()
    if st in ("OFFLINE", "FAILED", "ERROR", "DEGRADED", "STOPPED"):
        return False
    if probe in ("FAIL", "FAILED", "DOWN", "ERROR"):
        return False
    if st in ("ONLINE", "RUNNING", "READY", "HEALTHY"):
        return True
    if probe in ("OK", "UP", "PASS", "HEALTHY"):
        return True
    return st in ("", "UNKNOWN") and probe in ("", "UNKNOWN")


def _derive_service_alerts(
    services: List[Dict[str, Any]], topo_map: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for svc in services:
        if _service_is_healthy(svc.get("status"), svc.get("probe_status")):
            continue
        sid = str(svc.get("service_id") or "")
        node = topo_map.get(sid) or {}
        name = str(node.get("name") or node.get("label") or sid or "服务").strip()
        severity = "critical" if str(svc.get("status") or "").upper() in ("OFFLINE", "FAILED") else "warning"
        alerts.append(
            {
                "id": f"svc-{sid}",
                "severity": severity,
                "title": f"服务异常：{name}",
                "message": f"状态={svc.get('status') or 'UNKNOWN'}",
                "time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            }
        )
    return alerts


def _load_project_documents(project_id: str) -> List[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, "documents.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw if isinstance(raw, list) else raw.get("documents") if isinstance(raw, dict) else []
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("project_id") or row.get("project") or "").strip()
        if pid and pid != project_id:
            continue
        out.append(row)
    return out


def _project_member_count(project_id: str) -> int:
    proj = projects_db.get(project_id) or {}
    roles = proj.get("member_roles") if isinstance(proj.get("member_roles"), dict) else {}
    seen: set[str] = set()
    created_by = str(proj.get("created_by") or "").strip()
    if created_by:
        seen.add(created_by)
    for username in list(proj.get("editors") or []) + list(proj.get("viewers") or []):
        user = str(username or "").strip()
        if user:
            seen.add(user)
    for username in roles:
        user = str(username or "").strip()
        if user:
            seen.add(user)
    return len(seen)


def _release_order_activities(
    project_id: str,
    filters: Dict[str, str],
    *,
    fetch_limit: int,
) -> List[Dict[str, Any]]:
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

    def _activity_title(
        event_type: str,
        order_id: str,
        env_key: str,
        version_name: str,
        version_code: str,
        payload: Dict[str, Any],
    ) -> str:
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
            label = {"precheck_started": "预检中", "publish_started": "发布中", "verify_started": "验收中"}.get(
                event_type, event_type
            )
            return f"发布单 {oid} {label} · {env} · {base}"
        if event_type == "created":
            return f"发布单 {oid} 已创建 · {env} · {base}"
        if event_type == "draft_updated":
            return f"发布单 {oid} 计划已更新 · {env} · {base}"
        if event_type == "cancelled":
            return f"发布单 {oid} 已取消 · {env}"
        return f"发布单 {oid} · {event_type} · {env} · {base}"

    filter_env = str(filters.get("env_key") or "").strip().lower()
    filter_channel = str(filters.get("channel_id") or "").strip()
    filter_platform = str(filters.get("platform") or "").strip().lower()
    sql = """
        SELECT e.event_type, e.actor, e.payload, e.created_at,
               o.release_order_id, o.env_key, o.channel_id, o.platform,
               o.version_name, o.version_code
        FROM release_order_events e
        INNER JOIN release_orders o ON o.release_order_id = e.release_order_id
        WHERE o.project_id=?
        ORDER BY e.created_at DESC
        LIMIT ?
    """
    init_db()
    with _db_lock:
        rows = _get_conn().execute(sql, (project_id, fetch_limit)).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        env_key = str(row["env_key"] or "").strip()
        channel_id = str(row["channel_id"] or "").strip()
        platform = str(row["platform"] or "").strip().lower()
        if filter_env and env_key.lower() != filter_env:
            continue
        if filter_channel and channel_id != filter_channel:
            continue
        if filter_platform and platform != filter_platform:
            continue
        event_type = str(row["event_type"] or "").strip()
        kind, type_label = _EVENT_KIND_LABELS.get(event_type, ("release", "发布"))
        payload = _decode(row["payload"], {}) or {}
        order_id = str(row["release_order_id"] or "")
        out.append(
            _activity_row(
                kind=kind,
                type_label=type_label,
                title=_activity_title(
                    event_type,
                    order_id,
                    env_key,
                    str(row["version_name"] or ""),
                    str(row["version_code"] or ""),
                    payload if isinstance(payload, dict) else {},
                ),
                actor=str(row["actor"] or "系统"),
                created_at=str(row["created_at"] or ""),
                href=f"/admin/projects/{project_id}/release-orders/{order_id}",
                event_type=event_type,
            )
        )
    return out


def _task_activities(project_id: str, *, fetch_limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    tasks = project_tasks_db.get(project_id) or []
    if not isinstance(tasks, list):
        return out
    sorted_tasks = sorted(
        [t for t in tasks if isinstance(t, dict)],
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )
    for task in sorted_tasks[:fetch_limit]:
        task_id = str(task.get("id") or "").strip()
        title = str(task.get("title") or "未命名任务").strip()
        status = TASK_STATUS_LABELS.get(str(task.get("status") or ""), str(task.get("status") or "未知"))
        actor = str(task.get("current_assignee") or task.get("created_by") or "系统")
        ts = str(task.get("updated_at") or task.get("created_at") or "")
        out.append(
            _activity_row(
                kind="task",
                type_label="任务",
                title=f"任务「{title}」· {status}",
                actor=actor,
                created_at=ts,
                href=f"/admin/projects/{project_id}/tasks",
                event_type="task_updated",
            )
        )
        flow_log = task.get("flow_log") if isinstance(task.get("flow_log"), list) else []
        for entry in reversed(flow_log[-3:]):
            if not isinstance(entry, dict):
                continue
            out.append(
                _activity_row(
                    kind="task",
                    type_label="任务",
                    title=f"任务「{title}」流转 · {entry.get('from_user') or ''} → {entry.get('to_user') or ''}",
                    actor=str(entry.get("from_user") or actor),
                    created_at=str(entry.get("at") or ts),
                    href=f"/admin/projects/{project_id}/tasks",
                    event_type="task_flow",
                )
            )
    return out


def _alert_activities(project_id: str, filters: Dict[str, str], *, fetch_limit: int) -> List[Dict[str, Any]]:
    from services.ops import helpers as ops_helpers
    from services.ops.constants import OPS_ALERT_SNAPSHOT_KEY

    filter_env = str(filters.get("env_key") or "").strip().lower()
    out: List[Dict[str, Any]] = []

    snapshot = ops_helpers._load_json_config(OPS_ALERT_SNAPSHOT_KEY, {})
    snapshot_alerts = snapshot.get("alerts") if isinstance(snapshot, dict) else []
    if isinstance(snapshot_alerts, list):
        for item in snapshot_alerts:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("project_id") or "").strip()
            if pid and pid != project_id:
                continue
            env_key = str(item.get("env_key") or "").strip().lower()
            if filter_env and env_key and env_key != filter_env:
                continue
            title = str(item.get("title") or item.get("message") or "运维告警").strip()
            out.append(
                _activity_row(
                    kind="alert",
                    type_label="告警",
                    title=title,
                    actor=str(item.get("actor") or "Ops"),
                    created_at=str(item.get("time") or item.get("created_at") or ""),
                    href=f"/admin/projects/{project_id}/environments/{env_key or 'production'}/runtime",
                    event_type="ops_alert",
                )
            )

    for env_key in list_project_env_keys(project_id):
        if filter_env and env_key.lower() != filter_env:
            continue
        services = ops_helpers._services_for_project(project_id, env_key)
        if not services:
            continue
        ctx = ops_helpers._resolve_topology_context(project_id, env_key, "")
        topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
        topo_map: Dict[str, Dict[str, Any]] = {}
        for node in topo.get("nodes") or []:
            if isinstance(node, dict):
                nid = str(node.get("id") or "").strip()
                if nid:
                    topo_map[nid] = node
        for alert in _derive_service_alerts(services, topo_map):
            out.append(
                _activity_row(
                    kind="alert",
                    type_label="告警",
                    title=str(alert.get("title") or "服务告警"),
                    actor="Ops",
                    created_at=str(alert.get("time") or ""),
                    href=f"/admin/projects/{project_id}/environments/{env_key}/runtime",
                    event_type="service_alert",
                )
            )
    out.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return out[:fetch_limit]


def _doc_activities(project_id: str, *, fetch_limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for doc in _load_project_documents(project_id):
        doc_id = str(doc.get("id") or doc.get("doc_id") or "").strip()
        title = str(doc.get("title") or "未命名文档").strip()
        actor = str(doc.get("updated_by") or doc.get("created_by") or "系统")
        ts = str(doc.get("updated_at") or doc.get("created_at") or "")
        href = f"/docs/{doc_id}" if doc_id else f"/admin/projects/{project_id}/docs"
        out.append(
            _activity_row(
                kind="doc",
                type_label="文档",
                title=f"文档「{title}」已更新",
                actor=actor,
                created_at=ts,
                href=href,
                event_type="doc_updated",
            )
        )

    try:
        audit_rows = get_audit_log_from_db(limit=80, action_filter=None)
    except Exception:
        audit_rows = []
    project_token = str(project_id or "").strip()
    for row in audit_rows or []:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or "")
        if not any(action.startswith(prefix) for prefix in DOC_ACTION_PREFIXES):
            continue
        details = str(row.get("details") or "")
        if project_token and project_token not in details and f"project={project_token}" not in details:
            if not details.startswith("doc") and project_token not in action:
                continue
        out.append(
            _activity_row(
                kind="doc",
                type_label="文档",
                title=f"文档操作 · {action.replace('_', ' ')}",
                actor=str(row.get("user") or "系统"),
                created_at=str(row.get("timestamp") or ""),
                href=f"/admin/projects/{project_id}/docs",
                event_type=action,
            )
        )
    out.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return out[:fetch_limit]


def build_overview_activities(
    project_id: str,
    filters: Optional[Dict[str, str]] = None,
    *,
    limit: int = 40,
    kind: str = "",
) -> List[Dict[str, Any]]:
    filters = filters or {}
    kind_filter = str(kind or filters.get("kind") or "").strip().lower()
    per_source = max(limit, 20)
    merged: List[Dict[str, Any]] = []
    merged.extend(_release_order_activities(project_id, filters, fetch_limit=per_source * 2))
    merged.extend(_task_activities(project_id, fetch_limit=per_source))
    merged.extend(_alert_activities(project_id, filters, fetch_limit=per_source))
    merged.extend(_doc_activities(project_id, fetch_limit=per_source))
    merged.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    if kind_filter and kind_filter != "all":
        merged = [item for item in merged if str(item.get("kind") or "").strip().lower() == kind_filter]
    return merged[:limit]


def build_release_health_summary(project_id: str, *, days: int = 7) -> Dict[str, Any]:
    from services.monitor.release_metrics import build_release_health_summary as _summary

    return _summary(project_id, days=days)


def build_overview_kpis(
    project_id: str,
    filters: Optional[Dict[str, str]],
    cards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    filters = filters or {}
    filter_env = str(filters.get("env_key") or "").strip().lower()
    init_db()

    today_prefix = datetime.now().strftime("%Y-%m-%d")
    with _db_lock:
        row = _get_conn().execute(
            """
            SELECT COUNT(*) FROM release_order_events e
            INNER JOIN release_orders o ON o.release_order_id = e.release_order_id
            WHERE o.project_id=?
              AND e.event_type IN ('build_requested', 'build_completed', 'build_failed', 'build_finalize_failed')
              AND substr(e.created_at, 1, 10) = ?
            """,
            (project_id, today_prefix),
        ).fetchone()
    today_build_count = int(row[0] if row else 0)

    pending_changes = sum(int(card.get("failed_count") or 0) + int(card.get("pending_approval_count") or 0) for card in cards)

    current_version = "—"
    current_version_code = ""
    for card in cards:
        for order in card.get("latest_orders") or []:
            if str(order.get("status") or "") in ("published", "verified"):
                current_version = str(order.get("version_name") or current_version)
                current_version_code = str(order.get("version_code") or "")
                break
        if current_version != "—":
            break
    if current_version == "—":
        for card in cards:
            orders = card.get("latest_orders") or []
            if orders:
                current_version = str(orders[0].get("version_name") or "—")
                current_version_code = str(orders[0].get("version_code") or "")
                break

    service_health_pct: Optional[float] = None
    health_source = "delivery"
    try:
        from services.ops import helpers as ops_helpers

        healthy = 0
        total = 0
        for env_key in list_project_env_keys(project_id):
            if filter_env and env_key.lower() != filter_env:
                continue
            services = ops_helpers._services_for_project(project_id, env_key)
            for svc in services:
                total += 1
                if _service_is_healthy(svc.get("status"), svc.get("probe_status")):
                    healthy += 1
        if total:
            service_health_pct = round((healthy / total) * 100.0, 1)
            health_source = "ops"
    except Exception:
        service_health_pct = None

    if service_health_pct is None and cards:
        healthy_cards = sum(1 for card in cards if card.get("health") in ("healthy", "processing"))
        service_health_pct = round((healthy_cards / len(cards)) * 100.0, 1)

    member_count = _project_member_count(project_id)
    env_for_link = filter_env or "production"
    release_health = build_release_health_summary(project_id, days=7)
    return {
        "current_version": current_version,
        "current_version_code": current_version_code,
        "service_health_pct": service_health_pct,
        "service_health_source": health_source,
        "today_build_count": today_build_count,
        "pending_changes": pending_changes,
        "member_count": member_count,
        "release_health": release_health,
        "links": {
            "version": f"/admin/projects/{project_id}/versions?env_key={env_for_link}",
            "health": f"/admin/projects/{project_id}/environments/{env_for_link}/runtime",
            "builds": f"/admin/projects/{project_id}/build-history",
            "changes": f"/admin/projects/{project_id}/release-orders?status=awaiting_approval",
            "members": f"/admin/projects/{project_id}/settings?tab=members",
            "activities": f"/admin/projects/{project_id}/activities?env_key={env_for_link}",
        },
    }
