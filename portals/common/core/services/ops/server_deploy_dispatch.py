# -*- coding: utf-8 -*-
"""Dispatch deploy_server_artifact jobs to Ops Agent (P2-01 Step 3)."""

from __future__ import annotations

from typing import Any, Dict, List

from services.ops.agent_registry import _enqueue_agent_job


def apply_deploy_job_report(job: Dict[str, Any], status: str, *, actor: str) -> Dict[str, Any] | None:
    """When an agent reports a server deploy job, update the server release."""
    action = str((job or {}).get("action_type") or "").strip().lower()
    if action != "deploy_server_artifact":
        return None
    normalized = str(status or "").strip().upper()
    if normalized not in {"SUCCESS", "FAILED"}:
        return None
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    project_id = str(payload.get("project_id") or "").strip()
    server_release_id = str(payload.get("server_release_id") or "").strip()
    service_id = str(payload.get("service_id") or job.get("target") or job.get("node_id") or "").strip()
    if not project_id or not server_release_id or not service_id:
        raise ValueError("部署回调缺少 project_id、server_release_id 或 service_id")
    from services.release.server_release_service import complete_deploy_server_release

    detail = job.get("result") if isinstance(job.get("result"), dict) else {}
    return complete_deploy_server_release(
        project_id,
        server_release_id,
        ok=normalized == "SUCCESS",
        actor=actor or "agent",
        detail=detail,
        service_id=service_id,
    )


def enqueue_deploy_server_artifact(
    *,
    project_id: str,
    server_release_id: str,
    topology_id: str,
    artifact: Dict[str, Any],
    target_services: List[str],
    actor: str,
) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    bundle_path = str(artifact.get("bundle_path") or "")
    artifact_id = str(artifact.get("artifact_id") or "")
    for service_id in target_services:
        node_id = str(service_id or "").strip()
        if not node_id:
            continue
        payload = {
            "command": "deploy_server_artifact",
            "project_id": project_id,
            "server_release_id": server_release_id,
            "topology_id": topology_id,
            "artifact_id": artifact_id,
            "bundle_path": bundle_path,
            "checksum": str(artifact.get("checksum") or ""),
            "protocol_version": str(artifact.get("protocol_version") or ""),
            "version_label": str(artifact.get("version_label") or ""),
            "service_id": node_id,
            "priority": 50,
        }
        job = _enqueue_agent_job(
            node_id,
            "deploy_server_artifact",
            node_id,
            payload,
            {
                "ticket_id": f"SRO-{server_release_id}",
                "reason": f"deploy server artifact {artifact_id} to {node_id}",
                "risk": "high",
                "require_approval": False,
                "approved": True,
            },
        )
        jobs.append(job)
    return jobs
