# -*- coding: utf-8 -*-
"""Server deploy outcome notifications (P3)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.notify.outbound_webhook import (
    EVENT_SERVER_DEPLOY_COMPLETED,
    EVENT_SERVER_DEPLOY_FAILED,
    notify_release_event,
)


def _base_fields(project_id: str, row: Dict[str, Any], *, actor: str = "", error: str = "") -> Dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    artifact_id = str(row.get("artifact_id") or "")
    version_label = ""
    if artifact_id:
        try:
            from services.release.server_artifact_service import get_artifact

            art = get_artifact(artifact_id) or {}
            version_label = str(art.get("version_label") or "")
        except Exception:
            pass
    return {
        "project_id": project_id,
        "server_release_id": str(row.get("server_release_id") or ""),
        "env_key": str(row.get("env_key") or ""),
        "topology_id": str(row.get("topology_id") or ""),
        "artifact_id": artifact_id,
        "server_version_label": version_label,
        "target_services": row.get("target_services") or [],
        "status": str(row.get("status") or ""),
        "linked_release_order_id": str(payload.get("linked_release_order_id") or "").strip(),
        "actor": actor,
        "error": error,
        "deploy_results": payload.get("deploy_results") or {},
    }


def notify_server_deploy_transition(
    project_id: str,
    row: Dict[str, Any],
    target_status: str,
    actor: str,
    *,
    detail: Optional[dict] = None,
    error: str = "",
) -> None:
    """Fire webhook when SRO reaches deployed or failed."""
    status = str(target_status or "").strip().lower()
    if status not in {"deployed", "failed"}:
        return
    fields = _base_fields(project_id, row, actor=actor, error=error)
    if isinstance(detail, dict):
        if detail.get("service_id"):
            fields["service_id"] = detail.get("service_id")
        if detail.get("deploy_results"):
            fields["deploy_results"] = detail.get("deploy_results")
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    linked = str(payload.get("linked_release_order_id") or fields.get("linked_release_order_id") or "").strip()
    if linked:
        fields["linked_release_order_id"] = linked
        fields["release_order_id"] = linked

    if status == "deployed":
        event = EVENT_SERVER_DEPLOY_COMPLETED
        title = "服务端部署完成"
        summary = (
            f"project={project_id}\n"
            f"server_release={fields.get('server_release_id')}\n"
            f"env={fields.get('env_key')}\n"
            f"topology={fields.get('topology_id')}\n"
            f"artifact={fields.get('artifact_id')}\n"
            f"targets={fields.get('target_services')}\n"
            f"linked_order={fields.get('linked_release_order_id') or '-'}"
        )
    else:
        event = EVENT_SERVER_DEPLOY_FAILED
        title = "服务端部署失败"
        err = error or str((detail or {}).get("error") or "")
        summary = (
            f"project={project_id}\n"
            f"server_release={fields.get('server_release_id')}\n"
            f"env={fields.get('env_key')}\n"
            f"artifact={fields.get('artifact_id')}\n"
            f"targets={fields.get('target_services')}\n"
            f"error={err or 'deploy failed'}"
        )
        fields["error"] = err or "deploy failed"

    notify_release_event(event, fields, title=title, summary=summary)


def notify_coordinated_server_deploy(
    project_id: str,
    release_order_id: str,
    deploy_result: Dict[str, Any],
    *,
    actor: str = "",
    error: str = "",
) -> None:
    """Notify when coordinated server deploy fails at publish time (success via SRO transition)."""
    if deploy_result.get("skipped"):
        return
    if not error and deploy_result.get("ok") is not False:
        status = str(deploy_result.get("deploy_status") or "").lower()
        if status != "failed":
            return
    sro_id = str(deploy_result.get("server_release_id") or "").strip()
    from services.release.server_release_service import get_server_release

    row = get_server_release(project_id, sro_id) if sro_id else {}
    row = row or {
        "server_release_id": sro_id or "unknown",
        "status": "failed",
        "payload": {"linked_release_order_id": release_order_id},
    }
    notify_server_deploy_transition(
        project_id,
        row,
        "failed",
        actor,
        detail={"error": error or deploy_result.get("error")},
        error=error or str(deploy_result.get("error") or "coordinated deploy failed"),
    )
