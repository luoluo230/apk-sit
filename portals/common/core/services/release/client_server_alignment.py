# -*- coding: utf-8 -*-
"""Client ReleaseOrder × Server Release status alignment (P3-03 Wave E)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _parse_ts(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def assess_client_server_alignment(
    client_order: Dict[str, Any] | None,
    server_release: Dict[str, Any] | None,
    *,
    env_key: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return ok/warn/block matrix for dual-plane release status."""
    order = client_order if isinstance(client_order, dict) else {}
    server = server_release if isinstance(server_release, dict) else {}
    client_status = str(order.get("status") or "").strip().lower()
    server_status = str(server.get("status") or "").strip().lower()
    linked_id = str(
        order.get("linked_server_release_id")
        or (order.get("payload") or {}).get("linked_server_release_id")
        or (order.get("payload") or {}).get("server_release_id")
        or server.get("server_release_id")
        or ""
    ).strip()
    ek = str(env_key or order.get("env_key") or "").strip().lower()
    clock = now or datetime.now(timezone.utc)

    state = "ok"
    label = "双平面对齐"
    reasons = []

    if not linked_id and not server_status:
        if client_status in {"published", "verified", "publishing", "ready", "awaiting_approval"}:
            state = "warn"
            label = "未关联服务端发布"
            reasons.append("客户端发布单未关联 server_release")
        else:
            state = "ok"
            label = "服务端未要求"
    elif server_status in {"failed", "rolled_back", "cancelled"}:
        state = "block"
        label = "服务端平面异常"
        reasons.append(f"服务端状态={server_status}")
    elif server_status in {"deploying", "queued", "building"}:
        if client_status in {"publishing", "published", "verified"}:
            state = "warn" if ek != "production" else "block"
            label = "服务端仍在部署"
            reasons.append("客户端已推进但服务端未 deployed")
        else:
            state = "warn"
            label = "服务端部署中"
    elif server_status in {"deployed", "verified"}:
        state = "ok"
        label = "服务端已就绪"
    elif linked_id and not server_status:
        state = "warn"
        label = "服务端状态未知"
        reasons.append("有关联 id 但读不到服务端发布单")

    started = _parse_ts(
        str(server.get("deploy_started_at") or server.get("updated_at") or order.get("updated_at") or "")
    )
    sla_seconds = None
    if started:
        sla_seconds = max(0, int((clock - started.astimezone(timezone.utc)).total_seconds()))
        # Soft SLA: > 30 min deploying → escalate warn/block
        if server_status in {"deploying", "queued"} and sla_seconds > 1800:
            if state == "ok":
                state = "warn"
            if ek == "production":
                state = "block"
            reasons.append(f"服务端部署超过 SLA（{sla_seconds}s）")

    block_expand = state == "block"
    block_publish = state == "block" and ek == "production"

    return {
        "state": state,
        "label": label,
        "reasons": reasons,
        "client_status": client_status,
        "server_status": server_status,
        "linked_server_release_id": linked_id,
        "sla_seconds": sla_seconds,
        "block_gray_expand": block_expand,
        "block_publish": block_publish,
        "env_key": ek,
    }


def assert_alignment_allows_action(
    alignment: Dict[str, Any],
    *,
    action: str,
) -> None:
    """Raise when production actions must stop due to plane drift."""
    action_key = str(action or "").strip().lower()
    detail = "；".join(alignment.get("reasons") or []) or str(alignment.get("label") or "")
    if action_key in {"expand_gray", "gray_expand"} and alignment.get("block_gray_expand"):
        raise ValueError("服务端平面未对齐，禁止扩大灰度：" + detail)
    if action_key in {"publish", "production_publish"} and alignment.get("block_publish"):
        raise ValueError("服务端平面未对齐，禁止 production 发布：" + detail)
