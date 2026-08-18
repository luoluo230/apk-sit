# -*- coding: utf-8 -*-
"""Server release order state machine + deploy dispatch (P2-01)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from repositories import server_release_repo
from services.release.env_registry import normalize_release_env_key
from services.release.server_artifact_service import get_artifact

TERMINAL_STATUSES = {"deployed", "failed", "rolled_back", "cancelled"}
DEPLOYABLE_STATUSES = {"ready", "deployed"}

_ALLOWED_TRANSITIONS: Dict[str, set] = {
    "draft": {"ready", "cancelled", "awaiting_approval"},
    "building": {"ready", "failed", "cancelled"},
    "ready": {"deploying", "cancelled"},
    "awaiting_approval": {"ready", "cancelled"},
    "deploying": {"deployed", "failed"},
    "deployed": {"deploying", "rolled_back"},
    "failed": {"ready", "deploying", "cancelled"},
    "rolled_back": {"ready", "deploying"},
    "cancelled": set(),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return f"sro-{uuid.uuid4().hex[:12]}"


def _normalize_targets(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        val = str(item or "").strip()
        if val and val not in out:
            out.append(val)
    return out


def create_server_release(project_id: str, payload: Dict[str, Any], actor: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    body = dict(payload or {})
    env_key = normalize_release_env_key(str(body.get("env_key") or "development"), project_id=pid)
    topology_id = str(body.get("topology_id") or "").strip()
    artifact_id = str(body.get("artifact_id") or "").strip()
    if not topology_id:
        raise ValueError("topology_id 必填")
    now = _now_iso()
    explicit_status = str(body.get("status") or "").strip().lower()
    if explicit_status == "awaiting_approval" and artifact_id:
        status = "awaiting_approval"
    elif artifact_id:
        status = "ready"
    else:
        status = "draft"
    if artifact_id and not get_artifact(artifact_id):
        raise ValueError("服务端制品不存在")
    row = server_release_repo.upsert_release(
        {
            "server_release_id": str(body.get("server_release_id") or _new_id()),
            "project_id": pid,
            "env_key": env_key,
            "topology_id": topology_id,
            "artifact_id": artifact_id,
            "status": status,
            "target_services": _normalize_targets(body.get("target_services")),
            "payload": body.get("payload") if isinstance(body.get("payload"), dict) else {},
            "created_by": str(actor or "system"),
            "created_at": now,
            "updated_at": now,
        }
    )
    return row


def get_server_release(project_id: str, server_release_id: str) -> Optional[Dict[str, Any]]:
    row = server_release_repo.get_release(server_release_id)
    if not row or str(row.get("project_id") or "") != str(project_id or "").strip():
        return None
    return row


def list_server_releases(project_id: str, *, env_key: str = "") -> List[Dict[str, Any]]:
    ek = normalize_release_env_key(env_key, project_id=project_id) if env_key else ""
    return server_release_repo.list_releases(project_id, env_key=ek)


def update_server_release(project_id: str, server_release_id: str, patch: Dict[str, Any], actor: str) -> Dict[str, Any]:
    row = get_server_release(project_id, server_release_id)
    if not row:
        raise ValueError("服务端发布单不存在")
    fields: Dict[str, Any] = {"updated_at": _now_iso()}
    if "artifact_id" in patch:
        aid = str(patch.get("artifact_id") or "").strip()
        if aid and not get_artifact(aid):
            raise ValueError("服务端制品不存在")
        fields["artifact_id"] = aid
    if "topology_id" in patch:
        fields["topology_id"] = str(patch.get("topology_id") or "").strip()
    if "target_services" in patch:
        fields["target_services"] = _normalize_targets(patch.get("target_services"))
    if "payload" in patch and isinstance(patch.get("payload"), dict):
        merged = dict(row.get("payload") or {})
        merged.update(patch["payload"])
        fields["payload"] = merged
    updated = server_release_repo.update_release_fields(server_release_id, **fields)
    if not updated:
        raise ValueError("更新失败")
    if updated.get("artifact_id") and str(updated.get("status") or "") == "draft":
        updated = server_release_repo.update_release_fields(
            server_release_id, status="ready", updated_at=_now_iso()
        ) or updated
    updated = updated or row
    updated["updated_by"] = actor
    return updated


def transition_server_release(
    project_id: str,
    server_release_id: str,
    target_status: str,
    actor: str,
    *,
    detail: Optional[dict] = None,
) -> Dict[str, Any]:
    row = get_server_release(project_id, server_release_id)
    if not row:
        raise ValueError("服务端发布单不存在")
    current = str(row.get("status") or "draft")
    target = str(target_status or "").strip().lower()
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(f"不允许从 {current} 转到 {target}")
    payload = dict(row.get("payload") or {})
    if detail:
        payload.setdefault("events", []).append({"at": _now_iso(), "from": current, "to": target, "detail": detail, "actor": actor})
    updated = server_release_repo.update_release_fields(
        server_release_id,
        status=target,
        payload=payload,
        updated_at=_now_iso(),
    )
    result = updated or row
    if target in {"deployed", "failed"}:
        try:
            from services.release.server_deploy_notify import notify_server_deploy_transition

            notify_server_deploy_transition(
                project_id,
                result,
                target,
                actor,
                detail=detail if isinstance(detail, dict) else {},
                error=str((detail or {}).get("error") or "") if isinstance(detail, dict) else "",
            )
        except Exception:
            pass
    return result


def deploy_server_release(project_id: str, server_release_id: str, actor: str) -> Dict[str, Any]:
    row = get_server_release(project_id, server_release_id)
    if not row:
        raise ValueError("服务端发布单不存在")
    status = str(row.get("status") or "")
    if status not in DEPLOYABLE_STATUSES:
        raise ValueError(f"当前状态 {status} 不可部署")
    artifact_id = str(row.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("未绑定服务端制品")
    artifact = get_artifact(artifact_id)
    if not artifact:
        raise ValueError("服务端制品不存在")
    targets = _normalize_targets(row.get("target_services"))
    if not targets:
        raise ValueError("target_services 为空")

    row = transition_server_release(project_id, server_release_id, "deploying", actor)
    from services.ops.server_deploy_dispatch import enqueue_deploy_server_artifact

    jobs = enqueue_deploy_server_artifact(
        project_id=project_id,
        server_release_id=server_release_id,
        topology_id=str(row.get("topology_id") or ""),
        artifact=artifact,
        target_services=targets,
        actor=actor,
    )
    payload = dict(row.get("payload") or {})
    payload["deploy_jobs"] = jobs
    payload["last_deploy_at"] = _now_iso()
    payload["last_deploy_by"] = actor
    updated = server_release_repo.update_release_fields(
        server_release_id, payload=payload, updated_at=_now_iso()
    )
    return updated or row


def record_agent_deploy_result(
    project_id: str,
    server_release_id: str,
    *,
    service_id: str,
    ok: bool,
    actor: str = "system",
    detail: Optional[dict] = None,
) -> Dict[str, Any]:
    """Record per-service deploy callback; finalize release when all targets report."""
    row = get_server_release(project_id, server_release_id)
    if not row:
        raise ValueError("服务端发布单不存在")
    sid = str(service_id or "").strip()
    if not sid:
        raise ValueError("service_id 必填")

    payload = dict(row.get("payload") or {})
    results = dict(payload.get("deploy_results") or {})
    results[sid] = {
        "ok": bool(ok),
        "detail": detail or {},
        "at": _now_iso(),
        "actor": actor,
    }
    payload["deploy_results"] = results
    row = server_release_repo.update_release_fields(
        server_release_id, payload=payload, updated_at=_now_iso()
    ) or row

    targets = _normalize_targets(row.get("target_services"))
    if not targets:
        jobs = payload.get("deploy_jobs") if isinstance(payload.get("deploy_jobs"), list) else []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            val = str(job.get("target") or job.get("node_id") or "").strip()
            if val and val not in targets:
                targets.append(val)

    if not targets or any(t not in results for t in targets):
        return row

    all_ok = all(bool((results.get(t) or {}).get("ok")) for t in targets)
    current = str(row.get("status") or "")
    if current != "deploying":
        return row
    return transition_server_release(
        project_id,
        server_release_id,
        "deployed" if all_ok else "failed",
        actor,
        detail={"deploy_results": results, "service_id": sid},
    )


def complete_deploy_server_release(
    project_id: str,
    server_release_id: str,
    *,
    ok: bool,
    actor: str = "system",
    detail: Optional[dict] = None,
    service_id: str = "",
) -> Dict[str, Any]:
    sid = str(service_id or "").strip()
    if sid:
        return record_agent_deploy_result(
            project_id,
            server_release_id,
            service_id=sid,
            ok=ok,
            actor=actor,
            detail=detail,
        )
    target = "deployed" if ok else "failed"
    return transition_server_release(project_id, server_release_id, target, actor, detail=detail or {})


def rollback_server_release(project_id: str, server_release_id: str, actor: str, *, previous_artifact_id: str = "") -> Dict[str, Any]:
    row = get_server_release(project_id, server_release_id)
    if not row:
        raise ValueError("服务端发布单不存在")
    payload = dict(row.get("payload") or {})
    prev = str(previous_artifact_id or payload.get("previous_artifact_id") or "").strip()
    if prev:
        payload["rollback_artifact_id"] = prev
        server_release_repo.update_release_fields(server_release_id, artifact_id=prev, payload=payload, updated_at=_now_iso())
        return deploy_server_release(project_id, server_release_id, actor)
    return transition_server_release(project_id, server_release_id, "rolled_back", actor)


def assess_server_release_for_precheck(
    project_id: str,
    server_release_id: str,
    *,
    min_server_version: str = "",
    waive: bool = False,
) -> Dict[str, Any]:
    if waive:
        return {"ok": True, "waived": True, "reason": "explicit_waive"}
    row = get_server_release(project_id, server_release_id)
    if not row:
        return {"ok": False, "reason": "server_release_not_found"}
    status = str(row.get("status") or "")
    artifact_id = str(row.get("artifact_id") or "")
    artifact = get_artifact(artifact_id) if artifact_id else None
    version_label = str((artifact or {}).get("version_label") or "")
    protocol_version = str((artifact or {}).get("protocol_version") or "")
    min_ver = str(min_server_version or "").strip()
    if status not in {"deployed", "deploying"}:
        return {
            "ok": False,
            "reason": "server_not_deployed",
            "status": status,
            "server_release_id": server_release_id,
            "version_label": version_label,
            "hint": "关联的服务端发布单尚未部署完成",
        }
    if min_ver and version_label and version_label < min_ver:
        return {
            "ok": False,
            "reason": "server_version_below_min",
            "version_label": version_label,
            "min_server_version": min_ver,
            "hint": f"服务端版本 {version_label} 低于要求的 {min_ver}",
        }
    return {
        "ok": True,
        "status": status,
        "server_release_id": server_release_id,
        "version_label": version_label,
        "protocol_version": protocol_version,
    }
