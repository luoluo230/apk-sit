# -*- coding: utf-8 -*-
"""Internal Jenkins callbacks (build-complete webhook)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from config import Config

bp = Blueprint("internal_jenkins", __name__)


def _webhook_secret() -> str:
    secret = (os.getenv("JENKINS_BUILD_WEBHOOK_SECRET") or "").strip()
    if secret:
        return secret
    return Config.get_secret_key()


def _verify_signature(raw_body: bytes, signature: str) -> bool:
    sig = (signature or "").strip()
    if not sig:
        return False
    if sig.lower().startswith("sha256="):
        sig = sig.split("=", 1)[1].strip()
    expected = hmac.new(_webhook_secret().encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _parse_payload(raw_body: bytes) -> Dict[str, Any]:
    if not raw_body:
        return {}
    data = json.loads(raw_body.decode("utf-8"))
    return data if isinstance(data, dict) else {}


@bp.route("/api/internal/jenkins/build-complete", methods=["POST"])
def jenkins_build_complete():
    """Jenkins post-build hook: HMAC body + instance_id/build_number → sync release order."""
    raw_body = request.get_data(cache=True) or b""
    signature = (
        request.headers.get("X-Jenkins-Signature")
        or request.headers.get("X-Webhook-Signature")
        or ""
    )
    if not _verify_signature(raw_body, signature):
        return jsonify({"ok": False, "error": "invalid signature"}), 401

    try:
        payload = _parse_payload(raw_body)
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "invalid json"}), 400

    instance_id = str(payload.get("instance_id") or "").strip()
    build_number_raw = payload.get("build_number")
    project_id = str(payload.get("project_id") or "").strip()
    release_order_id = str(payload.get("release_order_id") or "").strip()

    try:
        build_number = int(build_number_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "build_number required"}), 400
    if not instance_id:
        return jsonify({"ok": False, "error": "instance_id required"}), 400

    from services.release.order_build_sync import find_release_order_for_build, sync_release_order_build_status

    resolved: Optional[Tuple[str, str]] = None
    if project_id and release_order_id:
        resolved = (project_id, release_order_id)
    else:
        resolved = find_release_order_for_build(instance_id, build_number, project_id=project_id)

    if not resolved:
        return jsonify(
            {
                "ok": True,
                "synced": False,
                "reason": "no matching building release order",
                "instance_id": instance_id,
                "build_number": build_number,
            }
        ), 200

    pid, oid = resolved
    order = sync_release_order_build_status(pid, oid, actor="jenkins-webhook")
    return jsonify(
        {
            "ok": True,
            "synced": True,
            "project_id": pid,
            "release_order_id": oid,
            "status": str(order.get("status") or ""),
            "instance_id": instance_id,
            "build_number": build_number,
        }
    ), 200
