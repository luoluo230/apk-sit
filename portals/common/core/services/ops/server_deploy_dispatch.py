# -*- coding: utf-8 -*-
"""Dispatch deploy_server_artifact jobs to Ops Agent (P2-01 Step 3)."""

from __future__ import annotations

from typing import Any, Dict, List

from services.ops.agent_registry import _enqueue_agent_job


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
