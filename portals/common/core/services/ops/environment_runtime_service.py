# -*- coding: utf-8 -*-
"""Environment runtime overview BFF (P16)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import has_request_context, session

from models.data import projects_db
from services.authz import has_scope
from services.release.env_registry import get_project_env_defs, normalize_release_env_key, project_env_label
from services.release.release_order_service import project_overview


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_service_healthy(status: str, probe_status: str = "") -> bool:
    st = str(status or "").upper()
    probe = str(probe_status or "").upper()
    if probe == "FAIL":
        return False
    if st in ("ONLINE", "RUNNING", "READY") and (not probe or probe == "PASS"):
        return True
    return st in ("ONLINE", "RUNNING", "READY")


def _is_agent_online(agent: Dict[str, Any]) -> bool:
    st = str(agent.get("effective_status") or agent.get("status") or "").upper()
    return st in ("ONLINE", "RUNNING", "READY")


def _format_time_short(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "--"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M")
    except Exception:
        if len(text) >= 16:
            return text[11:16]
        return text[:5] if len(text) >= 5 else text


def _severity_bucket(severity: str) -> str:
    sev = str(severity or "").lower()
    if sev in ("critical", "emergency", "error", "fatal"):
        return "critical"
    if sev in ("warning", "warn", "high"):
        return "warning"
    if sev in ("info", "notice", "low"):
        return "info"
    return "other"


def _service_display_name(service_id: str, topo_map: Dict[str, Dict[str, Any]]) -> str:
    sid = str(service_id or "").strip()
    if not sid:
        return "service"
    node = topo_map.get(sid) or {}
    label = str(node.get("name") or node.get("label") or "").strip()
    if label:
        return label
    return sid.replace("-", " ").replace("_", " ").title()


def _derive_alerts_from_services(services: List[Dict[str, Any]], topo_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for svc in services:
        if _is_service_healthy(svc.get("status"), svc.get("probe_status")):
            continue
        sid = str(svc.get("service_id") or "")
        name = _service_display_name(sid, topo_map)
        severity = "critical" if str(svc.get("status") or "").upper() in ("OFFLINE", "FAILED") else "warning"
        alerts.append(
            {
                "id": f"svc-{sid}",
                "severity": severity,
                "title": f"服务异常：{name}",
                "message": f"状态={svc.get('status') or 'UNKNOWN'}",
                "time": _now_iso(),
            }
        )
    return alerts


def _pct(part: int, whole: int) -> float:
    return round((part / whole * 100.0), 1) if whole else 0.0


def _build_distribution_donut(services: List[Dict[str, Any]], topo_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    normal = abnormal = maintenance = 0
    for svc in services:
        st = str(svc.get("status") or "").upper()
        if st in ("MAINTENANCE", "MAINTAINING"):
            maintenance += 1
        elif _is_service_healthy(svc.get("status"), svc.get("probe_status")):
            normal += 1
        else:
            abnormal += 1
    total = len(services)
    return {
        "title": "服务状态分布",
        "center_label": "全部服务",
        "center_value": total,
        "segments": [
            {"key": "normal", "label": "正常", "count": normal, "pct": _pct(normal, total), "color": "#52c41a"},
            {"key": "abnormal", "label": "异常", "count": abnormal, "pct": _pct(abnormal, total), "color": "#ff4d4f"},
            {"key": "maintenance", "label": "维护中", "count": maintenance, "pct": _pct(maintenance, total), "color": "#faad14"},
        ],
    }


def _build_instance_donut(service_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    healthy = unhealthy = unknown = 0
    for row in service_rows:
        pct = int(row.get("health_pct") or 0)
        if pct >= 90:
            healthy += 1
        elif pct > 0:
            unhealthy += 1
        else:
            unknown += 1
    total = len(service_rows)
    online = sum(int(row.get("instances_online") or 0) for row in service_rows)
    return {
        "title": "实例健康",
        "center_label": "实例",
        "center_value": f"{online}/{total}" if total else "0/0",
        "segments": [
            {"key": "healthy", "label": "健康", "count": healthy, "pct": _pct(healthy, total), "color": "#52c41a"},
            {"key": "unhealthy", "label": "不健康", "count": unhealthy, "pct": _pct(unhealthy, total), "color": "#ff4d4f"},
            {"key": "unknown", "label": "未知", "count": unknown, "pct": _pct(unknown, total), "color": "#d9d9d9"},
        ],
    }


def _aggregate_resource_trends(agents: List[Dict[str, Any]]) -> Dict[str, Any]:
    from services.ops.agent_registry import _realtime_metric_points

    agent_ids: List[str] = []
    for ag in agents:
        for aid in ag.get("member_agent_ids") or []:
            text = str(aid or "").strip()
            if text:
                agent_ids.append(text)
        primary = str(ag.get("agent_id") or "").strip()
        if primary and primary not in agent_ids:
            agent_ids.append(primary)
    points = _realtime_metric_points(list(dict.fromkeys(agent_ids)))

    def _series(key: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for point in points:
            val = _safe_float(point.get(key))
            if val is None:
                continue
            out.append({"time": str(point.get("time") or ""), "value": val})
        return out

    def _latest(key: str) -> Optional[float]:
        vals = [_safe_float(point.get(key)) for point in points]
        clean = [v for v in vals if v is not None]
        return round(sum(clean) / len(clean), 1) if clean else None

    def _delta(key: str) -> Optional[float]:
        vals = [_safe_float(point.get(key)) for point in points]
        clean = [v for v in vals if v is not None]
        if len(clean) < 2:
            return None
        return round(clean[-1] - clean[0], 1)

    return {
        "window_label": "最近 1 小时",
        "has_history": len(points) > 1,
        "cpu": {
            "label": "CPU 使用率",
            "value": _latest("cpu_percent"),
            "unit": "%",
            "delta": _delta("cpu_percent"),
            "series": _series("cpu_percent"),
        },
        "memory": {
            "label": "内存使用率",
            "value": _latest("mem_percent"),
            "unit": "%",
            "delta": _delta("mem_percent"),
            "series": _series("mem_percent"),
        },
        "qps": {
            "label": "QPS",
            "value": _latest("qps"),
            "unit": "",
            "delta": _delta("qps"),
            "series": _series("qps"),
        },
    }


def _change_tone(event_type: str) -> str:
    text = str(event_type or "").lower()
    if "release" in text or "publish" in text:
        return "release"
    if "script" in text or "action" in text:
        return "script"
    return "config"


def _change_type_label(event_type: str) -> str:
    tone = _change_tone(event_type)
    if tone == "release":
        return "发布变更"
    if tone == "script":
        return "脚本变更"
    return "配置变更"


def _recent_changes(project_id: str, env_key: str, limit: int = 5) -> List[Dict[str, Any]]:
    from services.ops.storage import _load_events

    rows: List[Dict[str, Any]] = []
    for ev in _load_events(50, project_id):
        if not isinstance(ev, dict):
            continue
        scope = str(ev.get("scope") or ev.get("env_key") or "").strip().lower()
        if scope and env_key not in scope and scope != env_key:
            continue
        event_type = str(ev.get("type") or ev.get("event_type") or "change")
        rows.append(
            {
                "id": str(ev.get("id") or len(rows)),
                "type_label": _change_type_label(event_type),
                "tone": _change_tone(event_type),
                "title": str(ev.get("message") or event_type),
                "time": _format_time_short(str(ev.get("created_at") or ev.get("timestamp") or "")),
                "actor": str(ev.get("actor") or ev.get("user") or "系统"),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _current_risks(
    service_rows: List[Dict[str, Any]],
    blockers: List[Dict[str, Any]],
    error_rate: Optional[float],
) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    high_cpu = [row for row in service_rows if (row.get("cpu") or 0) >= 80]
    if high_cpu:
        risks.append(
            {
                "severity": "warning",
                "title": f"{len(high_cpu)} 个服务 CPU 使用率偏高",
                "detail": "、".join(str(row.get("name") or "") for row in high_cpu[:3]),
            }
        )
    unhealthy = [row for row in service_rows if int(row.get("health_pct") or 0) < 90]
    if unhealthy:
        risks.append(
            {
                "severity": "critical",
                "title": f"{len(unhealthy)} 个服务实例不健康",
                "detail": f"覆盖 {len({row.get('service_id') for row in unhealthy})} 个服务",
            }
        )
    if error_rate is not None and error_rate >= 1:
        risks.append(
            {
                "severity": "warning",
                "title": "错误率升高",
                "detail": f"当前 {error_rate}%",
            }
        )
    for blocker in blockers[:2]:
        risks.append(
            {
                "severity": str(blocker.get("severity") or "warning"),
                "title": str(blocker.get("title") or "阻断项"),
                "detail": str(blocker.get("message") or ""),
                "href": str(blocker.get("href") or ""),
            }
        )
    return risks[:5]


def _kpi_trend_flat() -> Dict[str, str]:
    return {"trend_label": "持平 较昨日", "trend_dir": "flat"}


def _merge_topo_services(
    services: List[Dict[str, Any]],
    service_rows: List[Dict[str, Any]],
    topo_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_id = {str(row.get("service_id") or ""): row for row in service_rows if row.get("service_id")}
    linked_nodes = {str(row.get("node_id") or "").strip() for row in service_rows if row.get("node_id")}
    for sid, node in topo_map.items():
        if sid in by_id or sid in linked_nodes:
            continue
        name = str(node.get("name") or node.get("role") or sid)
        by_id[sid] = {
            "service_id": sid,
            "name": name,
            "cluster": name,
            "instances_online": 0,
            "instances_total": 1,
            "health_pct": 0,
            "cpu": None,
            "memory": None,
            "qps": None,
            "updated_at": "--",
            "agent_id": "",
            "node_id": sid,
            "status": "OFFLINE",
        }
    for row in service_rows:
        sid = str(row.get("service_id") or "")
        if sid:
            by_id[sid] = row
    return list(by_id.values())[:50]


def _service_health_bucket(pct: int) -> str:
    if pct >= 90:
        return "healthy"
    if pct >= 60:
        return "warn"
    return "bad"


def _service_run_bucket(status: str, run_state: str = "") -> str:
    state = str(run_state or status or "").upper()
    if state in ("RUNNING", "ONLINE", "READY"):
        return "running"
    if state in ("DEGRADED", "UNKNOWN", "WARNING"):
        return "degraded"
    return "offline"


def _query_runtime_services(
    rows: List[Dict[str, Any]],
    *,
    q: str = "",
    cluster: str = "",
    category: str = "",
    health: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    q_norm = str(q or "").strip().lower()
    cluster_norm = str(cluster or "").strip().lower()
    category_norm = str(category or "").strip().lower()
    health_norm = str(health or "").strip().lower()
    status_norm = str(status or "").strip().lower()
    page = max(1, int(page or 1))
    page_size = max(1, min(50, int(page_size or 10)))

    clusters = sorted({str(row.get("cluster") or "").strip() for row in rows if str(row.get("cluster") or "").strip()})
    categories = sorted({str(row.get("category") or "").strip() for row in rows if str(row.get("category") or "").strip()})

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if cluster_norm and cluster_norm != str(row.get("cluster") or "").strip().lower():
            continue
        if category_norm and category_norm != str(row.get("category") or "").strip().lower():
            continue
        if health_norm and health_norm != str(row.get("health_bucket") or ""):
            continue
        if status_norm and status_norm != str(row.get("run_bucket") or ""):
            continue
        if q_norm:
            hay = " ".join(
                [
                    str(row.get("name") or ""),
                    str(row.get("cluster") or ""),
                    str(row.get("category") or ""),
                    str(row.get("service_id") or ""),
                    str(row.get("agent_id") or ""),
                    str(row.get("device_id") or ""),
                    str(row.get("device_label") or ""),
                    str(row.get("host_ip") or ""),
                ]
            ).lower()
            if q_norm not in hay:
                continue
        filtered.append(row)

    total = len(filtered)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    items = filtered[start : start + page_size]
    running_total = sum(1 for row in rows if row.get("is_running"))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "live_total": len(rows),
        "running_total": running_total,
        "filter_options": {
            "clusters": clusters,
            "categories": categories,
        },
        "applied": {
            "q": q_norm,
            "cluster": cluster_norm,
            "category": category_norm,
            "health": health_norm,
            "status": status_norm,
        },
    }


def _resolve_on_call(env_def: Dict[str, Any], project_id: str = "") -> Dict[str, Any]:
    raw = env_def.get("on_call") if isinstance(env_def.get("on_call"), dict) else {}
    name = str(raw.get("name") or env_def.get("on_call_name") or "").strip()
    if name:
        return {
            "configured": True,
            "name": name,
            "role": str(raw.get("role") or env_def.get("on_call_role") or "研发工程师"),
            "phone": str(raw.get("phone") or env_def.get("on_call_phone") or ""),
            "shift": str(raw.get("shift") or env_def.get("on_call_shift") or ""),
            "is_default": False,
        }
    return {"configured": False, "name": "", "role": "", "phone": "", "shift": "", "is_default": False}


def _enrich_alerts(recent_alerts: List[Dict[str, Any]], env_label: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in recent_alerts:
        item = dict(row)
        if env_label:
            item["env_label"] = env_label
        out.append(item)
    return out


def _enrich_bundle(bundle: Dict[str, Any], latest_order: Dict[str, Any]) -> Dict[str, Any]:
    publisher = str(bundle.get("publisher") or latest_order.get("created_by") or latest_order.get("publisher") or "").strip()
    order_id = str(bundle.get("order_id") or latest_order.get("order_id") or latest_order.get("id") or "").strip()
    bundle = dict(bundle)
    if publisher:
        bundle["publisher"] = publisher
        bundle["publisher_initial"] = publisher[:1]
    else:
        bundle.pop("publisher", None)
        bundle.pop("publisher_initial", None)
    if order_id:
        bundle["order_id"] = order_id
    if not bundle.get("released_at"):
        bundle["released_at"] = str(latest_order.get("published_at") or latest_order.get("updated_at") or "")
    return bundle

def build_environment_runtime_overview(
    project_id: str,
    env_key: str,
    filters: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Aggregate ops + delivery context for P16 runtime dashboard (fast path, no live node probe)."""
    if project_id not in projects_db:
        raise ValueError("项目不存在")

    env = normalize_release_env_key(env_key, project_id=project_id)
    allowed = {str(row.get("env_key") or "").strip().lower() for row in get_project_env_defs(project_id)}
    if env not in allowed:
        raise ValueError("环境不存在")

    env_def = next((row for row in get_project_env_defs(project_id) if str(row.get("env_key") or "").lower() == env), {})
    if env_def.get("enabled") is False:
        raise ValueError("环境已禁用")

    filters = filters or {}
    channel_id = str(filters.get("channel_id") or "").strip()
    platform = str(filters.get("platform") or "").strip().lower()

    can_ops = has_scope("gm_ops") or has_scope("gm.ops.read") or has_scope("gm.ops.execute")

    delivery = project_overview(
        project_id,
        {"env_key": env, "channel_id": channel_id, "platform": platform},
    )
    delivery_card = next((row for row in (delivery.get("environments") or []) if row.get("env_key") == env), {})

    agents: List[Dict[str, Any]] = []
    services: List[Dict[str, Any]] = []
    runtime_info: Dict[str, Any] = {"active": False, "run_id": "", "topology_id": "", "topology_name": "", "reason": ""}
    topo_map: Dict[str, Dict[str, Any]] = {}
    probe_source = "unavailable"
    metrics_missing = True

    if can_ops:
        from services.ops import helpers as ops_helpers
        from services.release.scope_resolver import resolve_scope, resolve_topology_binding_for_scope

        agents = ops_helpers._logical_agents_for_project(project_id, env)
        services = ops_helpers._services_for_project(project_id, env)
        topology_id_override = ""
        if channel_id and platform:
            scope = resolve_scope(project_id, env, channel_id, platform=platform, auto_create=False)
            if scope:
                binding = resolve_topology_binding_for_scope(scope, "")
                topology_id_override = str(binding.get("topology_id") or "").strip()
        ctx = ops_helpers._resolve_topology_context(project_id, env, topology_id_override)
        topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
        for item in topo.get("nodes") or []:
            if isinstance(item, dict):
                nid = str(item.get("id") or "").strip()
                if nid:
                    topo_map[nid] = item
        topology_id = str(topo.get("id") or topo.get("topology_id") or "").strip()
        runtime_info = ops_helpers._runtime_active_for_scope(project_id, env, topology_id)
        runtime_info["topology_id"] = topology_id
        runtime_info["topology_name"] = str(topo.get("name") or topology_id or "")
        probe_source = "agent-registry" if agents else "ops-empty"
        metrics_missing = not bool(agents)

    if platform:
        services = [
            svc
            for svc in services
            if platform in str(svc.get("service_type") or svc.get("node_id") or "").lower()
            or platform in str(svc.get("service_id") or "").lower()
        ]

    healthy_services = sum(1 for svc in services if _is_service_healthy(svc.get("status"), svc.get("probe_status")))
    total_services = len(services)
    service_health_pct = round((healthy_services / total_services * 100.0), 1) if total_services else None

    online_agents = sum(1 for ag in agents if _is_agent_online(ag))
    total_agents = len(agents)
    running_services = sum(
        1
        for svc in services
        if str(svc.get("run_state") or svc.get("status") or "").upper() in ("RUNNING", "ONLINE", "READY")
    )

    alerts = _derive_alerts_from_services(services, topo_map)
    alert_counts = {"critical": 0, "warning": 0, "info": 0, "other": 0}
    for alert in alerts:
        bucket = _severity_bucket(str(alert.get("severity") or ""))
        alert_counts[bucket] = alert_counts.get(bucket, 0) + 1

    latency_samples: List[float] = []
    for svc in services:
        rtt = _safe_float(svc.get("probe_rtt_ms"))
        if rtt is not None and rtt > 0:
            latency_samples.append(rtt)
    for ag in agents:
        rtt = _safe_float(ag.get("probe_rtt_ms"))
        if rtt is not None and rtt > 0:
            latency_samples.append(rtt)
    avg_latency = round(sum(latency_samples) / len(latency_samples), 1) if latency_samples else None

    error_rates: List[float] = []
    for ag in agents:
        metrics = ag.get("metrics") if isinstance(ag.get("metrics"), dict) else {}
        business = metrics.get("business") if isinstance(metrics.get("business"), dict) else metrics
        err = _safe_float(business.get("error_rate") if isinstance(business, dict) else None)
        if err is not None:
            error_rates.append(err)
    error_rate = round(sum(error_rates) / len(error_rates), 2) if error_rates else None

    service_rows: List[Dict[str, Any]] = []
    agent_by_id = {str(a.get("agent_id") or ""): a for a in agents if isinstance(a, dict)}
    for svc in services:
        sid = str(svc.get("service_id") or "")
        node_id = str(svc.get("node_id") or sid)
        node = topo_map.get(node_id) or {}
        metrics = svc.get("metrics") if isinstance(svc.get("metrics"), dict) else {}
        cpu = _safe_float(metrics.get("cpu_percent"))
        mem = _safe_float(metrics.get("mem_percent"))
        qps = _safe_float(metrics.get("qps"))
        healthy = _is_service_healthy(svc.get("status"), svc.get("probe_status"))
        health_pct = 100 if healthy else (50 if str(svc.get("status") or "").upper() in ("DEGRADED", "UNKNOWN") else 0)
        display_name = str(node.get("name") or node.get("role") or _service_display_name(sid, topo_map))
        run_state = str(svc.get("run_state") or svc.get("status") or "")
        cluster = str(node.get("name") or node.get("role") or node_id or "—")
        category = str(node.get("role") or svc.get("service_type") or cluster or "default")
        is_running = _service_run_bucket(str(svc.get("status") or ""), run_state) == "running" and bool(
            str(svc.get("agent_id") or "").strip()
        )
        ag = agent_by_id.get(str(svc.get("agent_id") or ""), {})
        device_id = str(svc.get("device_id") or ag.get("device_id") or "")
        device_label = str(ag.get("device_id") or ag.get("host_name") or device_id or "—")
        host_ip = str(ag.get("host_ip") or ag.get("host_name") or "")
        service_rows.append(
            {
                "service_id": sid,
                "name": display_name,
                "cluster": cluster,
                "category": category,
                "device_id": device_id,
                "device_label": device_label,
                "host_ip": host_ip,
                "agent_id": str(svc.get("agent_id") or ""),
                "instances_online": 1 if healthy and is_running else 0,
                "instances_total": 1,
                "health_pct": health_pct,
                "health_bucket": _service_health_bucket(int(health_pct)),
                "run_bucket": _service_run_bucket(str(svc.get("status") or ""), run_state),
                "run_state": run_state or str(svc.get("status") or "UNKNOWN"),
                "cpu": cpu,
                "memory": mem,
                "qps": qps,
                "updated_at": _format_time_short(str(svc.get("updated_at") or "")),
                "node_id": node_id,
                "status": str(svc.get("status") or "UNKNOWN"),
                "is_live": True,
                "is_running": is_running,
                "source": str(svc.get("source") or "agent-registry"),
            }
        )

    healthy_services = sum(1 for row in service_rows if int(row.get("health_pct") or 0) >= 90)
    total_services = len(service_rows)
    service_health_pct = round((healthy_services / total_services * 100.0), 1) if total_services else None
    running_services = sum(int(row.get("instances_online") or 0) for row in service_rows)

    blockers: List[Dict[str, Any]] = []
    hint = str(delivery_card.get("blocker_hint") or "").strip()
    if hint:
        blockers.append(
            {
                "id": "delivery-scope",
                "severity": "warning",
                "title": "交付范围未完整配置",
                "message": hint,
                "href": f"/admin/projects/{project_id}/overview?tab=environments",
            }
        )
    if delivery_card.get("failed_count"):
        blockers.append(
            {
                "id": "release-failed",
                "severity": "critical",
                "title": "存在失败发布单",
                "message": f"{delivery_card.get('failed_count')} 个发布单失败",
                "href": f"/admin/projects/{project_id}/release-orders?scoped=1&env_key={env}&status=failed",
            }
        )
    if can_ops and not runtime_info.get("active") and runtime_info.get("topology_id"):
        blockers.append(
            {
                "id": "runtime-inactive",
                "severity": "warning",
                "title": "Runtime 未运行",
                "message": str(runtime_info.get("reason") or "topology runtime inactive"),
                "href": f"/admin/projects/{project_id}/topologies?env_key={env}",
            }
        )
    if can_ops and not agents:
        blockers.append(
            {
                "id": "metrics-missing",
                "severity": "info",
                "title": "运行指标不可用",
                "message": "Agent 未上报或未配置 ops 探针",
                "href": f"/admin/projects/{project_id}/agents?env_key={env}",
            }
        )

    recent_alerts = [
        {
            "id": str(row.get("id") or ""),
            "severity": _severity_bucket(str(row.get("severity") or "")),
            "title": str(row.get("title") or "告警"),
            "message": str(row.get("message") or ""),
            "time": _format_time_short(str(row.get("time") or "")),
        }
        for row in alerts[:8]
    ]

    latest_orders = delivery_card.get("latest_orders") or []
    latest_order = latest_orders[0] if latest_orders else {}
    bundle_version = str(latest_order.get("version_name") or latest_order.get("version_code") or latest_order.get("version_id") or "")
    bundle_code = str(latest_order.get("version_code") or "")
    bundle_label = f"{bundle_version} ({bundle_code})" if bundle_version and bundle_code and bundle_version != bundle_code else (bundle_version or bundle_code)

    delivery_health = str(delivery_card.get("health") or "unconfigured")
    runtime_badge = "running" if runtime_info.get("active") else ("stopped" if can_ops else delivery_health)

    resource_trends = _aggregate_resource_trends(agents) if can_ops and agents else {
        "window_label": "最近 1 小时",
        "has_history": False,
        "cpu": {"label": "CPU 使用率", "value": None, "unit": "%", "delta": None, "series": []},
        "memory": {"label": "内存使用率", "value": None, "unit": "%", "delta": None, "series": []},
        "qps": {"label": "QPS", "value": None, "unit": "", "delta": None, "series": []},
    }
    env_label = project_env_label(project_id, env)
    recent_alerts = _enrich_alerts(recent_alerts, env_label)
    bundle = _enrich_bundle(
        {
            "version": bundle_label,
            "version_name": str(latest_order.get("version_name") or ""),
            "version_code": bundle_code,
            "order_id": str(latest_order.get("order_id") or latest_order.get("id") or ""),
            "released_at": str(latest_order.get("published_at") or latest_order.get("updated_at") or ""),
            "publisher": str(latest_order.get("created_by") or latest_order.get("publisher") or ""),
            "link": f"/admin/projects/{project_id}/release-orders?scoped=1&env_key={env}",
            "link_text": "查看发布详情",
        },
        latest_order if isinstance(latest_order, dict) else {},
    )
    primary_agent = agents[0] if agents else {}
    data_quality_extra = {
        "sparse_metrics": bool(service_rows)
        and not any(row.get("cpu") is not None or row.get("memory") is not None or row.get("qps") is not None for row in service_rows),
        "primary_agent_id": str(primary_agent.get("agent_id") or ""),
        "primary_device_id": str(primary_agent.get("device_id") or ""),
        "primary_host": str(primary_agent.get("host_ip") or primary_agent.get("host_name") or ""),
    }
    if not can_ops:
        probe_source = "no-permission"
    services_page = _query_runtime_services(
        service_rows,
        q=str(filters.get("service_q") or ""),
        cluster=str(filters.get("service_cluster") or ""),
        category=str(filters.get("service_category") or ""),
        health=str(filters.get("service_health") or ""),
        status=str(filters.get("service_status") or ""),
        page=int(filters.get("service_page") or 1),
        page_size=int(filters.get("service_page_size") or 5),
    )
    dashboard = {
        "service_distribution": _build_distribution_donut(services, topo_map),
        "instance_health": _build_instance_donut(service_rows),
        "agent_online": {
            "online": online_agents,
            "offline": max(total_agents - online_agents, 0),
            "total": total_agents,
            "rate_pct": round((online_agents / total_agents * 100.0), 1) if total_agents else None,
            "link": f"/admin/projects/{project_id}/agents?env_key={env}",
            "link_text": "查看 Agent 列表",
        },
        "resource_trends": resource_trends,
        "recent_changes": _recent_changes(project_id, env),
        "risks": _current_risks(service_rows, blockers, error_rate),
    }
    trend = _kpi_trend_flat()
    payload: Dict[str, Any] = {
        "context": {
            "project_id": project_id,
            "project_name": str((projects_db.get(project_id) or {}).get("name") or project_id),
            "env_key": env,
            "env_label": env_label,
            "channel_id": channel_id,
            "platform": platform,
            "updated_at": _now_iso(),
        },
        "kpis": {
            "service_health": {
                "value": service_health_pct,
                "unit": "%",
                "label": "服务健康度",
                "link": f"/admin/projects/{project_id}/diagnostics?env_key={env}",
                "link_text": "健康概览",
                **trend,
            },
            "online_instances": {
                "value": running_services if total_services else online_agents,
                "total": total_services or total_agents,
                "label": "在线实例",
                "link": f"/admin/projects/{project_id}/agents?env_key={env}",
                "link_text": "实例列表",
                **trend,
            },
            "alerts_today": {
                "value": len(alerts),
                "label": "今日告警",
                "link": f"/admin/projects/{project_id}/diagnostics?env_key={env}",
                "link_text": "告警详情",
                **trend,
            },
            "avg_latency_ms": {
                "value": avg_latency,
                "unit": "ms",
                "label": "平均响应",
                "link": f"/admin/projects/{project_id}/diagnostics?env_key={env}",
                "link_text": "性能诊断",
                **trend,
            },
            "error_rate": {
                "value": error_rate,
                "unit": "%",
                "label": "错误率",
                "link": f"/admin/projects/{project_id}/diagnostics?env_key={env}",
                "link_text": "错误分析",
                **trend,
            },
        },
        "runtime": {
            "active": bool(runtime_info.get("active")),
            "run_id": str(runtime_info.get("run_id") or ""),
            "topology_id": str(runtime_info.get("topology_id") or ""),
            "topology_name": str(runtime_info.get("topology_name") or ""),
            "badge": runtime_badge,
            "delivery_health": delivery_health,
        },
        "bundle": bundle,
        "dashboard": dashboard,
        "services": services_page.get("items") or [],
        "services_page": services_page,
        "services_all": service_rows,
        "sidebar": {
            "on_call": _resolve_on_call(env_def if isinstance(env_def, dict) else {}, project_id),
            "alerts": {
                "counts_by_severity": alert_counts,
                "recent": recent_alerts,
            },
            "quick_links": [
                {
                    "label": "查看拓扑",
                    "href": f"/admin/projects/{project_id}/topologies?env_key={env}",
                    "icon": "nav_topology",
                },
                {
                    "label": "查看日志",
                    "href": f"/admin/projects/{project_id}/diagnostics?env_key={env}",
                    "icon": "nav_execute",
                },
                {
                    "label": "进入发布单",
                    "href": f"/admin/projects/{project_id}/release-orders?scoped=1&env_key={env}",
                    "icon": "nav_release_order",
                },
                {
                    "label": "创建变更",
                    "href": f"/admin/projects/{project_id}/change-governance?env_key={env}",
                    "icon": "nav_change_governance",
                },
            ],
        },
        "filter_options": {
            "environment_options": delivery.get("environment_options") or [],
            "channel_options": delivery.get("channel_options") or [],
            "platform_options": delivery.get("platform_options") or [],
        },
        "data_quality": {
            "can_ops": can_ops,
            "probe_source": probe_source,
            "live_agents": online_agents,
            "total_agents": total_agents,
            "metrics_missing": metrics_missing and can_ops,
            "presentation_mode": "live",
            **data_quality_extra,
        },
    }
    scope_id = ""
    if channel_id and platform:
        from services.release.scope_resolver import resolve_scope

        scope = resolve_scope(project_id, env, channel_id, platform=platform, auto_create=False)
        scope_id = str((scope or {}).get("scope_id") or "")
    elif latest_order:
        scope_id = str(latest_order.get("scope_id") or "")
    from services.release.client_health_service import build_client_health_panel

    payload["client_health"] = build_client_health_panel(scope_id=scope_id)
    return payload
