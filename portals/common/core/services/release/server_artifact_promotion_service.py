# -*- coding: utf-8 -*-
"""Cross-environment server artifact promotion — clone deployed SRO to higher env."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from models.data import projects_db
from services.release.env_registry import get_project_env_defs, normalize_release_env_key, project_env_label
from services.release.order_helpers import _now_iso
from services.release.release_policy_service import requires_promotion_approval
from services.release.scope_resolver import resolve_scope, resolve_topology_binding_for_scope
from services.release.server_artifact_service import get_artifact

_ENV_RANK = {
    "development": 10,
    "testing": 20,
    "staging": 30,
    "production": 40,
}


def _env_rank(env_key: str) -> int:
    return int(_ENV_RANK.get(normalize_release_env_key(env_key), 0))


def _next_env_keys(project_id: str, source_env: str) -> List[str]:
    src_rank = _env_rank(source_env)
    out: List[str] = []
    for row in get_project_env_defs(project_id):
        ek = str(row.get("env_key") or "").strip()
        if _env_rank(ek) > src_rank:
            out.append(ek)
    return sorted(out, key=_env_rank)


def _new_sro_id() -> str:
    return f"sro-{uuid.uuid4().hex[:12]}"


def list_server_promotion_candidates(project_id: str) -> List[Dict[str, Any]]:
    """Deployed server releases that can advance to a higher environment."""
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    from services.release import server_release_service as srs

    rows = srs.list_server_releases(project_id, env_key="")
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("status") or "") not in {"deployed", "deploying"}:
            continue
        artifact_id = str(row.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        ek = normalize_release_env_key(str(row.get("env_key") or ""), project_id=project_id)
        artifact = get_artifact(artifact_id) or {}
        version_label = str(artifact.get("version_label") or "")
        key = f"{ek}:{artifact_id}:{version_label}"
        if key in seen:
            continue
        seen.add(key)
        targets = _next_env_keys(project_id, ek)
        if not targets:
            continue
        target_rows = []
        for target_env in targets:
            existing = [
                r
                for r in rows
                if normalize_release_env_key(str(r.get("env_key") or ""), project_id=project_id) == target_env
                and str(r.get("artifact_id") or "") == artifact_id
                and str(r.get("status") or "") in {"ready", "deploying", "deployed"}
            ]
            target_rows.append(
                {
                    "env_key": target_env,
                    "env_label": project_env_label(project_id, target_env),
                    "already_promoted": bool(existing),
                    "existing_server_release_id": str(existing[0].get("server_release_id") or "") if existing else "",
                    "requires_promotion_approval": requires_promotion_approval(project_id, target_env),
                }
            )
        out.append(
            {
                "server_release_id": str(row.get("server_release_id") or ""),
                "source_env_key": ek,
                "source_env_label": project_env_label(project_id, ek),
                "artifact_id": artifact_id,
                "version_label": version_label,
                "protocol_version": str(artifact.get("protocol_version") or ""),
                "topology_id": str(row.get("topology_id") or ""),
                "target_services": list(row.get("target_services") or []),
                "deploy_status": str(row.get("status") or ""),
                "updated_at": str(row.get("updated_at") or ""),
                "target_envs": target_rows,
            }
        )
    return out


def promote_server_artifact_to_env(
    project_id: str,
    source_server_release_id: str,
    target_env_key: str,
    actor: str,
    *,
    note: str = "",
    channel_id: str = "",
    platform: str = "android",
) -> Dict[str, Any]:
    """Create a ready server release order in target env from a deployed source SRO."""
    if project_id not in projects_db:
        raise ValueError("项目不存在")
    from services.release import server_release_service as srs

    source = srs.get_server_release(project_id, str(source_server_release_id or "").strip())
    if not source:
        raise ValueError("源服务端发布单不存在")
    if str(source.get("status") or "") not in {"deployed", "deploying"}:
        raise ValueError("仅已部署的服务端发布单可晋级")
    artifact_id = str(source.get("artifact_id") or "").strip()
    if not artifact_id or not get_artifact(artifact_id):
        raise ValueError("源发布单缺少有效制品")

    source_env = normalize_release_env_key(str(source.get("env_key") or ""), project_id=project_id)
    target_env = normalize_release_env_key(target_env_key, project_id=project_id)
    if _env_rank(target_env) <= _env_rank(source_env):
        raise ValueError("目标环境必须高于源环境")

    cid = str(channel_id or "common").strip() or "common"
    plat = str(platform or "android").lower()
    scope = resolve_scope(project_id, target_env, cid, platform=plat, auto_create=True)
    binding = resolve_topology_binding_for_scope(scope, "")
    topology_id = str(source.get("topology_id") or binding.get("topology_id") or "").strip()
    if not topology_id:
        raise ValueError("目标环境缺少拓扑绑定")

    targets = list(source.get("target_services") or [])
    if not targets:
        raise ValueError("源发布单缺少 target_services")

    now = _now_iso()
    needs_approval = requires_promotion_approval(project_id, target_env)
    promotion_meta = {
        "promoted_from_server_release_id": str(source.get("server_release_id") or ""),
        "promoted_from_env_key": source_env,
        "promoted_from_artifact_id": artifact_id,
        "promotion_note": str(note or "").strip(),
        "promoted_at": now,
        "promoted_by": actor,
    }
    row = srs.create_server_release(
        project_id,
        {
            "server_release_id": _new_sro_id(),
            "artifact_id": artifact_id,
            "topology_id": topology_id,
            "env_key": target_env,
            "target_services": targets,
            "status": "awaiting_approval" if needs_approval else "ready",
            "payload": {"promotion": promotion_meta},
        },
        actor,
    )
    return {
        "server_release_id": row.get("server_release_id"),
        "server_release": row,
        "promotion": promotion_meta,
        "next_action": "approval" if needs_approval else "deploy",
        "requires_promotion_approval": needs_approval,
        "target_env_key": target_env,
        "target_env_label": project_env_label(project_id, target_env),
    }


def approve_server_promotion(
    project_id: str,
    server_release_id: str,
    actor: str,
    *,
    note: str = "",
) -> Dict[str, Any]:
    """QA sign-off for a promoted server release — transitions awaiting_approval → ready."""
    from services.release import server_release_service as srs

    row = srs.get_server_release(project_id, str(server_release_id or "").strip())
    if not row:
        raise ValueError("服务端发布单不存在")
    if str(row.get("status") or "") != "awaiting_approval":
        raise ValueError("当前服务端发布单不在待审批状态")
    promotion = (row.get("payload") or {}).get("promotion") or {}
    if not promotion.get("promoted_from_server_release_id"):
        raise ValueError("非晋级服务端发布单")
    approved = srs.update_server_release(
        project_id,
        str(row.get("server_release_id") or ""),
        {
            "payload": {
                "promotion_approval": {
                    "approved_by": actor,
                    "note": str(note or "").strip(),
                    "approved_at": _now_iso(),
                }
            }
        },
        actor,
    )
    return srs.transition_server_release(
        project_id,
        str(row.get("server_release_id") or ""),
        "ready",
        actor,
        detail={"promotion_approved": True, "note": note},
    ) or approved
