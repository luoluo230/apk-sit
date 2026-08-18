# -*- coding: utf-8 -*-
"""Link Android client Jenkins builds with GameServer artifacts / SRO."""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.db import get_cursor, init_db
from services.release.order_helpers import _decode, _json, _now_iso


def link_server_artifact_to_client_build(
    project_id: str,
    artifact_id: str,
    *,
    client_instance_id: str,
    client_build_number: str | int,
    release_order_id: str = "",
    server_build_number: str | int = "",
) -> Dict[str, Any]:
    """Persist client↔server build linkage on artifact and optional release order."""
    from services.release import server_artifact_service as sas

    pid = str(project_id or "").strip()
    aid = str(artifact_id or "").strip()
    iid = str(client_instance_id or "").strip()
    bn = str(client_build_number or "").strip()
    if not pid or not aid or not iid or not bn:
        raise ValueError("project_id、artifact_id、client_instance_id、client_build_number 必填")

    row = sas.get_artifact(aid)
    if not row or str(row.get("project_id") or "") != pid:
        raise ValueError("服务端制品不存在")

    payload = dict(row.get("payload") or {})
    payload.update({
        "client_jenkins_instance_id": iid,
        "client_build_number": bn,
        "linked_release_order_id": str(release_order_id or payload.get("linked_release_order_id") or "").strip(),
        "server_build_number": str(server_build_number or payload.get("build_number") or bn).strip(),
        "build_linkage_version": "v1",
    })
    updated = sas.register_artifact(pid, {**row, "payload": payload})

    oid = str(release_order_id or "").strip()
    if oid:
        _attach_artifact_to_release_order(pid, oid, aid, iid, bn)
    return updated


def _attach_artifact_to_release_order(
    project_id: str,
    release_order_id: str,
    artifact_id: str,
    client_instance_id: str,
    client_build_number: str,
) -> None:
    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT payload FROM release_orders WHERE project_id=? AND release_order_id=?",
            (project_id, release_order_id),
        ).fetchone()
        if not row:
            return
        plan = _decode(row["payload"], {}) or {}
        if not isinstance(plan, dict):
            plan = {}
        plan["server_artifact_id"] = artifact_id
        plan["linked_server_artifact_id"] = artifact_id
        plan["client_build_linkage"] = {
            "jenkins_instance_id": client_instance_id,
            "build_number": client_build_number,
            "artifact_id": artifact_id,
        }
        cur.execute(
            "UPDATE release_orders SET payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (_json(plan), now, project_id, release_order_id),
        )


def find_server_artifact_for_client_build(
    project_id: str,
    client_instance_id: str,
    client_build_number: str | int,
) -> Optional[Dict[str, Any]]:
    from services.release import server_artifact_service as sas

    iid = str(client_instance_id or "").strip()
    bn = str(client_build_number or "").strip()
    if not iid or not bn:
        return None
    for row in sas.list_artifacts(project_id, limit=200):
        payload = row.get("payload") or {}
        if str(payload.get("client_jenkins_instance_id") or "").strip() != iid:
            continue
        if str(payload.get("client_build_number") or "").strip() != bn:
            continue
        return row
    return None


def resolve_server_artifact_for_order(project_id: str, order: Dict[str, Any]) -> Optional[str]:
    plan = order.get("payload") or {}
    if not isinstance(plan, dict):
        return None
    explicit = str(plan.get("server_artifact_id") or plan.get("linked_server_artifact_id") or "").strip()
    if explicit:
        return explicit
    linkage = plan.get("client_build_linkage") or {}
    if isinstance(linkage, dict):
        linked = str(linkage.get("artifact_id") or "").strip()
        if linked:
            return linked
    build_number = str(plan.get("build_job_id") or "").strip()
    instance_id = str(plan.get("jenkins_instance_id") or "").strip()
    if build_number and instance_id:
        row = find_server_artifact_for_client_build(project_id, instance_id, build_number)
        if row:
            return str(row.get("artifact_id") or "").strip()
    return None


def maybe_attach_linked_server_artifact(project_id: str, order_id: str) -> Optional[str]:
    """After client build completes, attach server artifact matched by BUILD_NUMBER."""
    from services.release import order_crud as oc

    order = oc.get_release_order(project_id, order_id, include_details=False)
    if not order:
        return None
    artifact_id = resolve_server_artifact_for_order(project_id, order)
    if not artifact_id:
        return None
    plan = dict(order.get("payload") or {})
    if str(plan.get("server_artifact_id") or "").strip():
        return artifact_id
    plan["server_artifact_id"] = artifact_id
    plan["linked_server_artifact_id"] = artifact_id
    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute(
            "UPDATE release_orders SET payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (_json(plan), now, project_id, order_id),
        )
    return artifact_id
