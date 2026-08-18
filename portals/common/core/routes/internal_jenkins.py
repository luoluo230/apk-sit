# -*- coding: utf-8 -*-
"""Internal Jenkins callbacks (build-complete webhook). Plan: P0-01."""

from __future__ import annotations

import base64
import json
import os
import tempfile
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from services.security.webhook_auth import assert_internal_webhook_request

bp = Blueprint("internal_jenkins", __name__)


def _parse_payload(raw_body: bytes) -> Dict[str, Any]:
    if not raw_body:
        return {}
    data = json.loads(raw_body.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _signature_header() -> str:
    return (
        request.headers.get("X-Signature-SHA256")
        or request.headers.get("X-Jenkins-Signature")
        or request.headers.get("X-Webhook-Signature")
        or ""
    )


@bp.route("/api/internal/jenkins/build-complete", methods=["POST"])
def jenkins_build_complete():
    """Jenkins post-build hook: HMAC body + instance_id/build_number → sync release order."""
    raw_body = request.get_data(cache=True) or b""
    auth_error = assert_internal_webhook_request(
        request,
        raw_body,
        _signature_header(),
        "JENKINS_BUILD_WEBHOOK_SECRET",
    )
    if auth_error:
        return jsonify({"ok": False, "error": auth_error}), 401

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


@bp.route("/api/internal/jenkins/server-artifact", methods=["POST"])
def jenkins_server_artifact():
    """Jenkins gameserver build hook: register server artifact zip with Portal."""
    raw_body = request.get_data(cache=True) or b""
    auth_error = assert_internal_webhook_request(
        request,
        raw_body,
        _signature_header(),
        "JENKINS_BUILD_WEBHOOK_SECRET",
    )
    if auth_error:
        return jsonify({"ok": False, "error": auth_error}), 401

    try:
        payload = _parse_payload(raw_body)
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "invalid json"}), 400

    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        return jsonify({"ok": False, "error": "project_id required"}), 400

    from services.release import server_artifact_service as sas

    extra: Dict[str, Any] = {}
    if payload.get("build_number") is not None:
        extra["build_number"] = payload.get("build_number")
    if payload.get("jenkins_instance_id"):
        extra["jenkins_instance_id"] = payload.get("jenkins_instance_id")
    body: Dict[str, Any] = {
        "artifact_id": str(payload.get("artifact_id") or "").strip(),
        "version_label": str(payload.get("version_label") or payload.get("version") or "").strip(),
        "protocol_version": str(payload.get("protocol_version") or "v1").strip(),
        "checksum": str(payload.get("checksum") or "").strip(),
        "bundle_path": str(payload.get("bundle_path") or payload.get("artifact_path") or "").strip(),
    }
    if payload.get("oss_url"):
        body["oss_url"] = str(payload.get("oss_url"))
    if extra:
        body["payload"] = extra

    source_path = str(payload.get("source_path") or "").strip()
    artifact_b64 = str(payload.get("artifact_b64") or "").strip()
    temp_path = ""
    if artifact_b64:
        fd, temp_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        with open(temp_path, "wb") as fh:
            fh.write(base64.b64decode(artifact_b64))
        source_path = temp_path
    try:
        row = sas.register_artifact(project_id, body, source_path=source_path)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        if temp_path and os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    result: Dict[str, Any] = {"artifact": row}
    topology_id = str(payload.get("topology_id") or "").strip()
    target_services = payload.get("target_services")
    env_key = str(payload.get("env_key") or "development").strip()
    if topology_id and isinstance(target_services, list) and target_services:
        from services.release import server_release_service as srs

        sro = srs.create_server_release(
            project_id,
            {
                "artifact_id": row.get("artifact_id"),
                "topology_id": topology_id,
                "env_key": env_key,
                "target_services": target_services,
                "payload": {
                    "jenkins_build_number": payload.get("build_number"),
                    "jenkins_instance_id": payload.get("jenkins_instance_id"),
                },
            },
            actor="jenkins-webhook",
        )
        result["server_release"] = sro

    return jsonify({"ok": True, **result}), 201
