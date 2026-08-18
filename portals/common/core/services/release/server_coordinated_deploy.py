# -*- coding: utf-8 -*-
"""Coordinated client+server publish — deploy_server_with_client orchestration."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.release.env_registry import normalize_release_env_key
from services.release.order_helpers import _event, _json, _now_iso


def _normalize_targets(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        val = str(item or "").strip()
        if val and val not in out:
            out.append(val)
    return out


def _resolve_topology_target_services(project_id: str, topology_id: str, env_key: str) -> List[str]:
    """Best-effort service IDs from topology node bindings for deploy targets."""
    tid = str(topology_id or "").strip()
    if not tid:
        return []
    try:
        from routes.ops import deps as ops_helpers

        ek = normalize_release_env_key(str(env_key or "development"), project_id=project_id)
        scoped = ops_helpers._load_topology_scoped(project_id, ek, tid)
        service_bindings = ops_helpers._resolve_scope_service_bindings_for_scope(
            tid, project_id, ek, set(
                str(x.get("id") or "")
                for x in (scoped.get("nodes") or [])
                if isinstance(x, dict)
            ),
        )
        valid_services = set(
            str(x.get("service_id") or "").strip()
            for x in ops_helpers._services_for_project(project_id)
            if isinstance(x, dict)
        )
        out: List[str] = []
        for sid in service_bindings.values():
            s = str(sid or "").strip()
            if s and (not valid_services or s in valid_services) and s not in out:
                out.append(s)
        return out
    except Exception:
        return []


def maybe_deploy_server_with_client(
    project_id: str,
    order_id: str,
    order: Dict[str, Any],
    plan: Dict[str, Any],
    *,
    topology_id: str,
    actor: str,
) -> Dict[str, Any]:
    """After client publish, deploy linked server release when plan requests it."""
    if not plan.get("deploy_server_with_client"):
        return {"skipped": True, "reason": "not_requested"}

    from services.release import server_release_service as srs

    server_release_id = str(
        plan.get("server_release_id") or plan.get("linked_server_release_id") or ""
    ).strip()
    server_artifact_id = str(plan.get("server_artifact_id") or "").strip()
    plan_targets = _normalize_targets(plan.get("target_services"))
    env_key = str(order.get("env_key") or "development").strip()
    topo_id = str(topology_id or plan.get("target_topology_id") or "").strip()

    if not server_release_id:
        if not server_artifact_id:
            from services.release.jenkins_build_linkage_service import resolve_server_artifact_for_order

            server_artifact_id = str(resolve_server_artifact_for_order(project_id, order) or "").strip()
        if not server_artifact_id:
            raise ValueError("与客户端同批发布需要指定 server_release_id 或 server_artifact_id")
        targets = plan_targets or _resolve_topology_target_services(project_id, topo_id, env_key)
        if not targets:
            raise ValueError("与客户端同批发布需要 target_services 或已绑定的拓扑服务")
        if not topo_id:
            raise ValueError("与客户端同批发布需要拓扑 ID")
        created = srs.create_server_release(
            project_id,
            {
                "artifact_id": server_artifact_id,
                "topology_id": topo_id,
                "env_key": env_key,
                "target_services": targets,
                "payload": {"linked_release_order_id": order_id, "coordinated_client_publish": True},
            },
            actor,
        )
        server_release_id = str(created.get("server_release_id") or "")

    row = srs.get_server_release(project_id, server_release_id)
    if not row:
        raise ValueError("服务端发布单不存在")

    previous_artifact_id = str(row.get("artifact_id") or "").strip()
    patch: Dict[str, Any] = {}
    if server_artifact_id and not str(row.get("artifact_id") or "").strip():
        patch["artifact_id"] = server_artifact_id
    if topo_id and not str(row.get("topology_id") or "").strip():
        patch["topology_id"] = topo_id
    targets = _normalize_targets(row.get("target_services"))
    if not targets:
        resolved = plan_targets or _resolve_topology_target_services(
            project_id, str(row.get("topology_id") or topo_id), env_key
        )
        if resolved:
            patch["target_services"] = resolved
        else:
            raise ValueError("服务端发布单缺少 target_services")
    if patch:
        row = srs.update_server_release(project_id, server_release_id, patch, actor)

    deployed = srs.deploy_server_release(project_id, server_release_id, actor)
    result = {
        "skipped": False,
        "server_release_id": server_release_id,
        "deploy_status": str(deployed.get("status") or ""),
        "artifact_id": str(deployed.get("artifact_id") or ""),
        "previous_artifact_id": previous_artifact_id,
        "deploy_jobs": (deployed.get("payload") or {}).get("deploy_jobs") or [],
    }

    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            "SELECT payload FROM release_orders WHERE project_id=? AND release_order_id=?",
            (project_id, order_id),
        )
        fetched = cur.fetchone()
        merged_plan = dict(plan)
        if fetched:
            from services.release.order_helpers import _decode

            stored = _decode(fetched["payload"], {}) or {}
            if isinstance(stored, dict):
                merged_plan = {**stored, **merged_plan}
        merged_plan["linked_server_release_id"] = server_release_id
        merged_plan["server_release_id"] = server_release_id
        merged_plan["server_coordinated_deploy"] = result
        cur.execute(
            "UPDATE release_orders SET payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
            (_json(merged_plan), now, project_id, order_id),
        )
        _event(
            cur,
            order_id,
            "server_coordinated_deploy",
            actor,
            "published",
            "published",
            result,
        )
    return result
