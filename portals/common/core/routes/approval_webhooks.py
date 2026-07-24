# -*- coding: utf-8 -*-
"""Inbound external approval webhooks (Feishu / DingTalk / generic)."""

from __future__ import annotations

import json
from typing import Any, Dict

from flask import jsonify, request

from models.db import get_cursor, init_db
from services.release.order_publish_flow import approve_release_order, scan_approval_sla_timeouts

approval_webhook_view = None


def verify_approval_signature(provider: str, body: bytes, headers: Dict[str, str]) -> bool:
    from services.security.webhook_auth import resolve_webhook_secret, verify_hmac_signature, webhook_auth_disabled

    if webhook_auth_disabled():
        return True
    secret = resolve_webhook_secret(
        f"APPROVAL_WEBHOOK_SECRET_{str(provider or '').strip().upper()}",
        "APPROVAL_WEBHOOK_SECRET",
    )
    if not secret:
        return False
    supplied = (
        str(headers.get("X-Signature-SHA256") or "").strip()
        or str(headers.get("X-Approval-Signature") or headers.get("X-Signature") or "").strip()
        or str(headers.get("X-Hub-Signature-256") or "").strip()
        or str(request.args.get("sign") or request.args.get("signature") or "").strip()
    )
    if not supplied:
        return False
    return verify_hmac_signature(body, supplied, secret)


def _find_order_for_approval(approval_id: str, release_order_id: str) -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        if approval_id:
            row = cur.execute(
                """
                SELECT a.approval_id, a.release_order_id, a.status, o.project_id
                FROM release_approvals a
                JOIN release_orders o ON o.release_order_id = a.release_order_id
                WHERE a.approval_id=?
                """,
                (approval_id,),
            ).fetchone()
            if row:
                return dict(row)
        if release_order_id:
            row = cur.execute(
                """
                SELECT a.approval_id, a.release_order_id, a.status, o.project_id
                FROM release_approvals a
                JOIN release_orders o ON o.release_order_id = a.release_order_id
                WHERE a.release_order_id=? AND a.status='pending'
                ORDER BY a.created_at DESC LIMIT 1
                """,
                (release_order_id,),
            ).fetchone()
            if row:
                return dict(row)
    return {}


def handle_external_approval(provider: str, payload: Dict[str, Any], *, actor: str = "external-webhook") -> Dict[str, Any]:
    approval_id = str(payload.get("approval_id") or "").strip()
    release_order_id = str(payload.get("release_order_id") or payload.get("order_id") or "").strip()
    action = str(payload.get("action") or "approve").strip().lower()
    note = str(payload.get("note") or payload.get("comment") or f"approved via {provider}").strip()
    row = _find_order_for_approval(approval_id, release_order_id)
    if not row:
        raise ValueError("approval record not found")
    approval_id = str(row.get("approval_id") or approval_id)
    project_id = str(row.get("project_id") or payload.get("project_id") or "").strip()
    order_id = str(row.get("release_order_id") or release_order_id)
    if str(row.get("status") or "") == "approved":
        return {"status": "already_processed", "approval_id": approval_id, "release_order_id": order_id}
    if action not in {"approve", "approved", "pass", "accept"}:
        raise ValueError(f"unsupported action: {action}")
    if not project_id:
        raise ValueError("project_id required")
    order = approve_release_order(project_id, order_id, actor, note=note)
    return {"status": "approved", "approval_id": approval_id, "release_order_id": order_id, "order": order}


def register_approval_webhook_routes(bp) -> None:
    global approval_webhook_view

    @bp.route("/api/webhooks/approval/<provider>", methods=["POST"])
    def approval_webhook(provider: str):
        scan_approval_sla_timeouts()
        body = request.get_data(cache=False) or b""
        headers = {k: v for k, v in request.headers.items()}
        if not verify_approval_signature(provider, body, headers):
            return jsonify({"ok": False, "error": "invalid signature"}), 401
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                payload = {}
        actor = str(payload.get("approved_by") or payload.get("actor") or f"{provider}-webhook").strip()
        try:
            result = handle_external_approval(provider, payload, actor=actor)
            return jsonify({"ok": True, "data": result})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    approval_webhook_view = approval_webhook
