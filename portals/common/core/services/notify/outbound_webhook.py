# -*- coding: utf-8 -*-
"""Unified outbound webhooks for release incidents and approvals (P2-03 Step 1)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

EVENT_VERIFY_FAILED = "verify_failed"
EVENT_PUBLISH_FAILED = "publish_failed"
EVENT_BOOTSTRAP_SMOKE_FAILED = "bootstrap_smoke_failed"
EVENT_APPROVAL_SLA_TIMEOUT = "approval_sla_timeout"
EVENT_AUTO_ROLLBACK_EXECUTED = "auto_rollback_executed"
EVENT_GRAY_ROLLOUT_PAUSED = "gray_rollout_paused"
EVENT_SERVER_DEPLOY_COMPLETED = "server_deploy_completed"
EVENT_SERVER_DEPLOY_FAILED = "server_deploy_failed"

INCIDENT_EVENTS = {
    EVENT_VERIFY_FAILED,
    EVENT_PUBLISH_FAILED,
    EVENT_BOOTSTRAP_SMOKE_FAILED,
    EVENT_APPROVAL_SLA_TIMEOUT,
    EVENT_AUTO_ROLLBACK_EXECUTED,
    EVENT_GRAY_ROLLOUT_PAUSED,
    EVENT_SERVER_DEPLOY_FAILED,
}

SERVER_DEPLOY_EVENTS = {
    EVENT_SERVER_DEPLOY_COMPLETED,
    EVENT_SERVER_DEPLOY_FAILED,
}


def _resolve_notify_url(explicit: str = "") -> str:
    url = str(explicit or os.getenv("NOTIFY_WEBHOOK_URL") or "").strip()
    if url.startswith("http"):
        return url
    try:
        from models.data import get_system_config

        return str(get_system_config("webhook_url") or "").strip()
    except Exception:
        return ""


def _resolve_signing_secret() -> str:
    from services.security.webhook_auth import resolve_webhook_secret

    return resolve_webhook_secret("NOTIFY_SIGNING_SECRET", "JENKINS_BUILD_WEBHOOK_SECRET")


def _sign_payload(body: bytes, secret: str) -> str:
    ts = str(int(datetime.now().timestamp()))
    digest = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("utf-8") + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def _post_signed_json(url: str, payload: dict, *, secret: str = "") -> bool:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    signing_secret = str(secret or _resolve_signing_secret() or "").strip()
    if signing_secret:
        headers["X-Signature-SHA256"] = _sign_payload(body, signing_secret)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("notify webhook ok: %s status=%s", payload.get("event"), resp.status)
            return True
    except Exception as exc:
        logger.warning("notify webhook failed: %s", exc)
        return False


def build_release_event_payload(event_type: str, fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = dict(fields or {})
    return {
        "event": str(event_type or "").strip(),
        "timestamp": datetime.now().isoformat(),
        "payload": data,
    }


def notify_release_event(
    event_type: str,
    fields: Optional[Dict[str, Any]] = None,
    *,
    title: str = "",
    summary: str = "",
    notify_url: str = "",
) -> None:
    """Async notify: signed generic webhook + Feishu/DingTalk for incident events."""
    payload = build_release_event_payload(event_type, fields)

    def _send() -> None:
        url = _resolve_notify_url(notify_url)
        if url.startswith("http"):
            _post_signed_json(url, payload)
        try:
            from services.webhook import fire_dingtalk, fire_feishu, fire_webhook

            fire_webhook(event_type, fields or {})
        except Exception:
            pass
        if event_type in INCIDENT_EVENTS or event_type in SERVER_DEPLOY_EVENTS or event_type == "release_awaiting_approval":
            heading = title or _default_title(event_type)
            body = summary or _default_summary(event_type, fields or {})
            try:
                from services.webhook import fire_dingtalk, fire_feishu

                fire_feishu(heading, body)
                fire_dingtalk(heading, body)
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()


def _default_title(event_type: str) -> str:
    mapping = {
        EVENT_VERIFY_FAILED: "发布验证失败",
        EVENT_PUBLISH_FAILED: "发布失败",
        EVENT_BOOTSTRAP_SMOKE_FAILED: "Bootstrap Smoke 失败",
        EVENT_APPROVAL_SLA_TIMEOUT: "审批 SLA 超时",
        EVENT_AUTO_ROLLBACK_EXECUTED: "自动回滚已执行",
        EVENT_GRAY_ROLLOUT_PAUSED: "灰度放量已暂停",
        EVENT_SERVER_DEPLOY_COMPLETED: "服务端部署完成",
        EVENT_SERVER_DEPLOY_FAILED: "服务端部署失败",
        "release_awaiting_approval": "发布单待审批",
    }
    return mapping.get(event_type, "发布通知")


def _default_summary(event_type: str, fields: Dict[str, Any]) -> str:
    lines = [
        f"event={event_type}",
        f"project={fields.get('project_id') or '-'}",
        f"order={fields.get('release_order_id') or '-'}",
        f"env={fields.get('env_key') or '-'}",
        f"version={fields.get('version_name') or '-'}/{fields.get('version_code') or '-'}",
        f"platform={fields.get('platform') or '-'}",
    ]
    if fields.get("error"):
        lines.append(f"error={fields.get('error')}")
    if fields.get("rollback_target_order"):
        lines.append(f"rollback_target={fields.get('rollback_target_order')}")
    if fields.get("server_release_id"):
        lines.append(f"server_release={fields.get('server_release_id')}")
    if fields.get("linked_release_order_id"):
        lines.append(f"linked_order={fields.get('linked_release_order_id')}")
    return "\n".join(lines)
