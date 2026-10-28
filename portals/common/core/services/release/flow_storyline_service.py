# -*- coding: utf-8 -*-
"""Human-facing release storyline: map order status to one pipeline, expose live Runtime."""

from __future__ import annotations

from typing import Any, Dict, List

from services.release.env_registry import project_env_label

PIPELINE_STAGES: List[Dict[str, str]] = [
    {"id": "build", "label": "构建", "desc": "出制品，不直接上线"},
    {"id": "artifacts", "label": "制品就绪", "desc": "APK / 热更 / 配置可追溯"},
    {"id": "precheck", "label": "预检", "desc": "兼容、产物、拓扑门禁"},
    {"id": "approval", "label": "审批", "desc": "生产按策略确认"},
    {"id": "publish", "label": "发布", "desc": "激活 Bundle 或灰度"},
    {"id": "verify", "label": "验证", "desc": "冒烟与启动校验"},
    {"id": "live", "label": "线上生效", "desc": "客户端实际加载的版本"},
]

_STATUS_TO_STAGE = {
    "draft": "build",
    "building": "build",
    "build_failed": "build",
    "cancelled": "build",
    "artifacts_ready": "artifacts",
    "prechecking": "precheck",
    "precheck_failed": "precheck",
    "ready": "precheck",
    "awaiting_approval": "approval",
    "approved": "approval",
    "publishing": "publish",
    "publish_failed": "publish",
    "published": "publish",
    "verifying": "verify",
    "verify_failed": "verify",
    "verified": "live",
    "rolled_back": "live",
}

STATUS_LABELS = {
    "draft": "草稿",
    "building": "构建中",
    "build_failed": "构建失败",
    "artifacts_ready": "制品就绪",
    "prechecking": "预检中",
    "precheck_failed": "预检未通过",
    "ready": "待发布",
    "awaiting_approval": "待审批",
    "approved": "已批准",
    "publishing": "发布中",
    "publish_failed": "发布失败",
    "published": "已发布（待验证）",
    "verifying": "验证中",
    "verify_failed": "验证失败",
    "verified": "已在线上",
    "rolled_back": "已回滚",
    "cancelled": "已取消",
}

_IN_FLIGHT = {
    "draft",
    "building",
    "build_failed",
    "artifacts_ready",
    "prechecking",
    "precheck_failed",
    "ready",
    "awaiting_approval",
    "approved",
    "publishing",
    "publish_failed",
    "published",
    "verifying",
    "verify_failed",
}


def stage_id_for_status(status: str) -> str:
    return _STATUS_TO_STAGE.get(str(status or "").strip().lower(), "build")


def status_label(status: str) -> str:
    key = str(status or "").strip().lower()
    return STATUS_LABELS.get(key, key or "未知")


def pipeline_steps(current_stage: str = "") -> List[Dict[str, Any]]:
    current = str(current_stage or "")
    ids = [row["id"] for row in PIPELINE_STAGES]
    current_idx = ids.index(current) if current in ids else -1
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(PIPELINE_STAGES):
        if current_idx < 0:
            state = "todo"
        elif idx < current_idx:
            state = "done"
        elif idx == current_idx:
            state = "current"
        else:
            state = "todo"
        out.append({**row, "state": state})
    return out


def build_runtime_snapshot(project_id: str, env_key: str) -> Dict[str, Any]:
    ek = str(env_key or "development")
    try:
        from services.release.channel_journey_bff import _delivery_lines_for_env

        lines = _delivery_lines_for_env(project_id, ek)
    except Exception:
        lines = []
    live_rows: List[Dict[str, Any]] = []
    empty_rows: List[Dict[str, Any]] = []
    for line in lines:
        row = {
            "channel_id": line.get("channel_id"),
            "channel_name": line.get("channel_name"),
            "platform": line.get("platform"),
            "platform_label": line.get("platform_label"),
            "scope_id": line.get("scope_id"),
            "bundle_id": line.get("bundle_id") or "",
            "version_name": line.get("version_name") or "",
            "version_code": line.get("version_code") or "",
            "topology_name": line.get("topology_name") or "",
            "href": (
                f"/admin/projects/{project_id}/release"
                f"?env_key={ek}&channel={line.get('channel_id')}&platform={line.get('platform')}"
            ),
        }
        if row["bundle_id"]:
            live_rows.append(row)
        else:
            empty_rows.append(row)
    return {
        "env_key": ek,
        "env_label": project_env_label(project_id, ek),
        "live_count": len(live_rows),
        "empty_count": len(empty_rows),
        "lines": live_rows + empty_rows,
        "summary": (
            f"{len(live_rows)} 条交付线已有线上 Bundle"
            if live_rows
            else "当前环境还没有已激活的线上 Bundle"
        ),
    }


def build_storyline(
    project_id: str,
    env_key: str,
    pending_actions: List[Dict[str, Any]],
    *,
    release_href: str,
) -> Dict[str, Any]:
    ek = str(env_key or "")
    current = None
    for row in pending_actions or []:
        if ek and str(row.get("env_key") or "") != ek:
            continue
        current = row
        break
    if current is None and pending_actions:
        current = pending_actions[0]

    if not current:
        steps = pipeline_steps("build")
        return {
            "has_in_flight": False,
            "current_stage": "build",
            "status": "",
            "status_label": "",
            "title": "当前没有进行中的发版",
            "detail": "从发版工作台勾选交付线开始；生产请走预检与审批，不要直接覆盖线上。",
            "steps": steps,
            "primary": {
                "label": "去发版",
                "href": release_href,
            },
        }

    status = str(current.get("status") or "")
    stage = stage_id_for_status(status)
    nxt = current.get("next_action") if isinstance(current.get("next_action"), dict) else {}
    href = str(nxt.get("href") or current.get("href") or release_href)
    label = str(nxt.get("label") or "继续发版")
    return {
        "has_in_flight": status in _IN_FLIGHT,
        "current_stage": stage,
        "status": status,
        "status_label": status_label(status),
        "title": f"{current.get('version_name') or ''} / {current.get('version_code') or ''}".strip(" /")
        or "进行中的发版",
        "detail": (
            f"{current.get('env_label') or current.get('env_key') or ''} · "
            f"{current.get('channel_name') or ''} · {current.get('platform') or ''} · "
            f"{status_label(status)}"
        ).strip(" ·"),
        "release_order_id": current.get("release_order_id"),
        "steps": pipeline_steps(stage),
        "primary": {"label": label, "href": href},
    }
