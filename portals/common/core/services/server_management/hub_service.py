# -*- coding: utf-8 -*-
"""Server management hub — unified card aggregation for topology and BaaS."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from models.data import get_channels_for_project, projects_db
from services.baas.service_crud import list_all_services
from services.ops.runtime_service import _runtime_active_for_scope
from services.ops.storage import _load_runtime_runs
from services.ops.topology_registry import (
    _env_label,
    _list_topologies,
    _normalize_env_key,
    create_topology_registry_entry,
    delete_topology_registry_entry,
    update_topology_registry_entry,
)
from services.release.topology_binding_service import list_topology_bindings


def _parse_iso(ts: str) -> Optional[datetime]:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _uptime_seconds(started_at: str) -> int:
    dt = _parse_iso(started_at)
    if not dt:
        return 0
    try:
        delta = datetime.utcnow() - dt.replace(tzinfo=None)
        return max(0, int(delta.total_seconds()))
    except Exception:
        return 0


def _format_uptime(seconds: int) -> str:
    sec = max(0, int(seconds or 0))
    if sec < 60:
        return f"{sec}秒"
    mins = sec // 60
    if mins < 60:
        return f"{mins}分钟"
    hours = mins // 60
    if hours < 48:
        return f"{hours}小时{mins % 60}分"
    days = hours // 24
    return f"{days}天{hours % 24}小时"


def _project_meta(project_id: str) -> Dict[str, str]:
    pid = str(project_id or "").strip()
    row = (projects_db or {}).get(pid) or {}
    return {
        "id": pid,
        "name": str(row.get("name") or pid or "未知项目").strip(),
        "icon_url": str(row.get("icon") or "").strip() or "/static/project_ui/svg/nav_project_overview.svg",
    }


def _card_status_class(status: str, has_error: bool = False) -> str:
    st = str(status or "").strip().lower()
    if has_error or st in ("error", "failed", "degraded"):
        return "error"
    if st in ("disabled", "archived"):
        return "neutral"
    if st in ("running", "active", "validated", "healthy"):
        return "configured"
    return "unconfigured"


def _badge_class(card_class: str) -> str:
    return {"configured": "ready", "unconfigured": "pending", "error": "error", "neutral": "neutral"}.get(
        card_class, "neutral"
    )


def _status_label(status: str) -> str:
    return {
        "running": "运行中",
        "validated": "已验证",
        "draft": "草稿",
        "stopped": "已停止",
        "archived": "已归档",
        "disabled": "已禁用",
        "active": "运行中",
        "error": "异常",
        "failed": "失败",
        "idle": "空闲",
    }.get(str(status or "").strip().lower(), str(status or "未知"))


def _bindings_for_topology(topology_id: str, bindings_cache: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tid = str(topology_id or "").strip()
    out: List[Dict[str, Any]] = []
    channel_names: Dict[str, str] = {}
    for row in bindings_cache:
        if str(row.get("topology_id") or "").strip() != tid:
            continue
        pid = str(row.get("project_id") or "").strip()
        cid = str(row.get("channel_id") or "").strip()
        if cid and pid and cid not in channel_names:
            for ch in get_channels_for_project(pid) or []:
                ch_id = str(ch.get("id") or "").strip()
                if ch_id:
                    channel_names[ch_id] = str(ch.get("name") or ch_id).strip()
        out.append(
            {
                "platform": str(row.get("platform") or "").strip(),
                "channel_id": cid,
                "channel_name": channel_names.get(cid, cid or "全部"),
                "env_key": str(row.get("env_key") or "").strip(),
                "level_label": str(row.get("level_label") or "").strip(),
            }
        )
    return out


def _runtime_log_snippets(project_id: str, env_key: str, topology_id: str, limit: int = 3) -> List[Dict[str, str]]:
    pid = str(project_id or "").strip()
    env = _normalize_env_key(env_key)
    tid = str(topology_id or "").strip()
    snippets: List[Dict[str, str]] = []
    for row in _load_runtime_runs():
        if not isinstance(row, dict):
            continue
        if pid and str(row.get("project_id") or "") != pid:
            continue
        if env and _normalize_env_key(row.get("env_key") or "") != env:
            continue
        if tid and str(row.get("topology_id") or "") != tid:
            continue
        err = str(row.get("error") or "").strip()
        st = str(row.get("status") or "").strip().lower()
        if err:
            snippets.append(
                {
                    "level": "error",
                    "message": err[:160],
                    "at": str(row.get("updated_at") or row.get("created_at") or ""),
                    "source": str(row.get("op") or "runtime"),
                }
            )
        elif st in ("failed", "timeout", "canceled"):
            snippets.append(
                {
                    "level": "warn",
                    "message": f"运行 {row.get('op') or 'op'} 状态 {st}",
                    "at": str(row.get("updated_at") or row.get("created_at") or ""),
                    "source": "runtime",
                }
            )
        if len(snippets) >= limit:
            break
    return snippets[:limit]


def _topology_runtime(project_id: str, env_key: str, topology_id: str) -> Dict[str, Any]:
    info = _runtime_active_for_scope(project_id, env_key, topology_id)
    active = bool(info.get("active"))
    status = str(info.get("status") or "").strip().lower()
    reason = str(info.get("reason") or "").strip()
    has_error = status in ("failed", "timeout", "error") or reason in ("stop_failed",)
    started_at = ""
    for row in _load_runtime_runs():
        if not isinstance(row, dict):
            continue
        if str(row.get("topology_id") or "") != topology_id:
            continue
        if str(row.get("op") or "").lower() != "start":
            continue
        if active and str(row.get("status") or "").lower() in ("running", "queued"):
            started_at = str(row.get("updated_at") or row.get("created_at") or "")
            break
    display_status = "running" if active else (status or "stopped")
    if has_error:
        display_status = "error"
    uptime = _uptime_seconds(started_at) if active and started_at else 0
    return {
        "status": display_status,
        "active": active,
        "uptime_seconds": uptime,
        "uptime_label": _format_uptime(uptime) if uptime else "-",
        "has_error": has_error,
        "started_at": started_at,
        "run_id": str(info.get("run_id") or ""),
    }


def build_topology_card(row: Dict[str, Any], bindings_cache: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    bindings_cache = bindings_cache if bindings_cache is not None else []
    tid = str(row.get("topology_id") or "").strip()
    pid = str(row.get("project_id") or "").strip()
    env_key = str(row.get("env_key") or "").strip()
    disabled = bool(row.get("disabled"))
    registry_status = str(row.get("registry_status") or row.get("status") or "draft").strip().lower()
    runtime = _topology_runtime(pid, env_key, tid)
    if disabled:
        runtime = {
            "status": "disabled",
            "active": False,
            "uptime_seconds": 0,
            "uptime_label": "-",
            "has_error": False,
            "started_at": "",
            "run_id": "",
        }
    elif not disabled and registry_status == "draft" and not runtime.get("active"):
        runtime["status"] = "draft"
    log_snippets = [] if disabled else _runtime_log_snippets(pid, env_key, tid)
    card_class = _card_status_class(str(runtime.get("status") or registry_status), bool(runtime.get("has_error")))
    bindings = _bindings_for_topology(tid, bindings_cache)
    return {
        "id": tid,
        "kind": "topology",
        "name": str(row.get("name") or tid).strip(),
        "description": str(row.get("description") or "").strip(),
        "icon_url": str(row.get("icon_url") or "").strip() or "/static/project_ui/svg/nav_topology.svg",
        "project": _project_meta(pid),
        "env_key": env_key,
        "env_label": _env_label(env_key),
        "bindings": bindings,
        "runtime": runtime,
        "stats": {
            "node_count": int(row.get("node_count") or 0),
            "edge_count": int(row.get("edge_count") or 0),
        },
        "log_snippets": log_snippets,
        "card_class": card_class,
        "badge_class": _badge_class(card_class),
        "status_label": _status_label(runtime.get("status") or registry_status),
        "disabled": disabled,
        "actions": {
            "canvas_url": f"/admin/projects/{pid}/topologies/canvas?env_key={env_key}&topology_id={tid}",
            "binding_url": f"/admin/projects/{pid}/environments/{env_key}?open_topology_drawer=1&env_key={env_key}",
        },
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _baas_player_count(service_id: str) -> int:
    from models.db import get_cursor, init_db

    init_db()
    sid = str(service_id or "").strip()
    if not sid:
        return 0
    with get_cursor() as cur:
        row = cur.execute("SELECT COUNT(*) AS cnt FROM baas_players WHERE service_id=?", (sid,)).fetchone()
        return int(row["cnt"] or 0) if row else 0


def build_baas_card(row: Dict[str, Any]) -> Dict[str, Any]:
    sid = str(row.get("service_id") or "").strip()
    pid = str(row.get("project_id") or "").strip()
    env_key = str(row.get("env_key") or "development").strip()
    disabled = bool(row.get("disabled"))
    raw_status = str(row.get("status") or "active").strip().lower()
    display_status = "disabled" if disabled else raw_status
    has_error = raw_status in ("error", "failed")
    card_class = _card_status_class(display_status, has_error)
    player_count = _baas_player_count(sid)
    return {
        "id": sid,
        "kind": "baas",
        "name": str(row.get("name") or sid).strip(),
        "description": str(row.get("description") or "").strip(),
        "icon_url": str(row.get("icon_url") or "").strip() or "/static/project_ui/svg/nav_project_setting.svg",
        "project": _project_meta(pid),
        "env_key": env_key,
        "env_label": _env_label(env_key),
        "bindings": [{"platform": "", "channel_id": "", "channel_name": "Passport REST", "env_key": env_key, "level_label": "轻度服务"}],
        "runtime": {
            "status": display_status,
            "active": raw_status == "active" and not disabled,
            "uptime_seconds": 0,
            "uptime_label": "Portal 托管" if not disabled else "-",
            "has_error": has_error,
            "started_at": str(row.get("updated_at") or ""),
            "run_id": "",
        },
        "stats": {
            "config_version": int(row.get("config_version") or 0),
            "player_count": player_count,
        },
        "log_snippets": [],
        "card_class": card_class,
        "badge_class": _badge_class(card_class),
        "status_label": _status_label(display_status),
        "disabled": disabled,
        "actions": {
            "config_url": f"/admin/projects/{pid}/casual-services/{sid}?env_key={env_key}",
            "gm_url": f"/admin/projects/{pid}/baas-gm/{sid}",
        },
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def list_topology_cards(
    *,
    project_id: str = "",
    env_key: str = "",
    status: str = "",
    query: str = "",
) -> List[Dict[str, Any]]:
    pid = str(project_id or "").strip()
    env_filter = _normalize_env_key(env_key) if str(env_key or "").strip() else ""
    status_filter = str(status or "").strip().lower()
    q = str(query or "").strip().lower()
    rows = _list_topologies(pid or "", env_filter or None)
    bindings = list_topology_bindings(pid) if pid else list_topology_bindings("")
    cards = [build_topology_card(row, bindings) for row in rows]
    if status_filter:
        cards = [c for c in cards if str(c.get("runtime", {}).get("status") or "").lower() == status_filter or (status_filter == "disabled" and c.get("disabled"))]
    if q:
        cards = [
            c
            for c in cards
            if q in str(c.get("name") or "").lower()
            or q in str(c.get("id") or "").lower()
            or q in str(c.get("description") or "").lower()
        ]
    return cards


def list_baas_cards(
    *,
    project_id: str = "",
    env_key: str = "",
    status: str = "",
    query: str = "",
) -> List[Dict[str, Any]]:
    rows = list_all_services(str(project_id or "").strip(), str(env_key or "").strip())
    cards = [build_baas_card(row) for row in rows]
    status_filter = str(status or "").strip().lower()
    q = str(query or "").strip().lower()
    if status_filter:
        cards = [c for c in cards if str(c.get("runtime", {}).get("status") or "").lower() == status_filter]
    if q:
        cards = [
            c
            for c in cards
            if q in str(c.get("name") or "").lower()
            or q in str(c.get("id") or "").lower()
            or q in str(c.get("description") or "").lower()
        ]
    return cards


def topology_delete_guard(topology_id: str) -> Optional[str]:
    tid = str(topology_id or "").strip()
    if not tid:
        return "topology_id required"
    row = next((r for r in _list_topologies("", None) if str(r.get("topology_id") or "") == tid), None)
    if not row:
        return "拓扑不存在"
    bindings = [b for b in list_topology_bindings("") if str(b.get("topology_id") or "") == tid and str(b.get("status") or "") == "active"]
    if bindings:
        return "存在活跃绑定，请先解除绑定"
    pid = str(row.get("project_id") or "")
    env_key = str(row.get("env_key") or "")
    runtime = _runtime_active_for_scope(pid, env_key, tid)
    if runtime.get("active"):
        return "拓扑正在运行，请先停止"
    return None


def create_topology_card(payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    row = create_topology_registry_entry(payload, actor=actor)
    bindings = list_topology_bindings(str(row.get("project_id") or ""))
    return build_topology_card(row, bindings)
