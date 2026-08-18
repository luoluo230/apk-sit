# -*- coding: utf-8 -*-
"""Coordinated client+server rollback orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.release.order_helpers import _decode, _event, _json, _now_iso


def _sro_id_from_plan(plan: Dict[str, Any]) -> str:
    return str(plan.get("server_release_id") or plan.get("linked_server_release_id") or "").strip()


def _artifact_id_for_sro(project_id: str, server_release_id: str) -> str:
    if not server_release_id:
        return ""
    from services.release import server_release_service as srs

    row = srs.get_server_release(project_id, server_release_id)
    if not row:
        return ""
    return str(row.get("artifact_id") or "").strip()


def _should_coordinate_server_rollback(
    target_order: Dict[str, Any],
    superseded_order: Optional[Dict[str, Any]],
) -> bool:
    target_plan = dict(target_order.get("payload") or {})
    if target_plan.get("rollback_with_server") is False:
        return False
    if _sro_id_from_plan(target_plan):
        return True
    if not superseded_order:
        return False
    superseded_plan = dict(superseded_order.get("payload") or {})
    if superseded_plan.get("deploy_server_with_client"):
        return True
    if _sro_id_from_plan(superseded_plan):
        return True
    return bool(str(target_plan.get("rollback_target") or "").strip().startswith("server:"))


def _resolve_target_artifact_id(
    project_id: str,
    target_order: Dict[str, Any],
    superseded_order: Optional[Dict[str, Any]],
) -> str:
    target_plan = dict(target_order.get("payload") or {})
    explicit = str(target_plan.get("server_artifact_id") or "").strip()
    if explicit:
        return explicit
    rollback_target = str(target_plan.get("rollback_target") or "").strip()
    if rollback_target.startswith("artifact:"):
        return rollback_target.split(":", 1)[1].strip()
    target_sro = _sro_id_from_plan(target_plan)
    artifact = _artifact_id_for_sro(project_id, target_sro)
    if artifact:
        return artifact
    if superseded_order:
        deploy = dict((superseded_order.get("payload") or {}).get("server_coordinated_deploy") or {})
        prev = str(deploy.get("previous_artifact_id") or "").strip()
        if prev:
            return prev
    return ""


def maybe_coordinated_server_rollback(
    project_id: str,
    target_order: Dict[str, Any],
    superseded_order: Optional[Dict[str, Any]],
    actor: str,
) -> Dict[str, Any]:
    """After client bundle rollback to target_order, restore server plane in sync."""
    if not _should_coordinate_server_rollback(target_order, superseded_order):
        return {"skipped": True, "reason": "server_rollback_not_requested"}

    from services.release import server_release_service as srs

    target_plan = dict(target_order.get("payload") or {})
    target_sro = _sro_id_from_plan(target_plan)
    target_artifact = _resolve_target_artifact_id(project_id, target_order, superseded_order)
    steps: List[Dict[str, Any]] = []

    superseded_plan = dict((superseded_order or {}).get("payload") or {})
    superseded_sro = _sro_id_from_plan(superseded_plan)

    if superseded_sro and target_artifact and superseded_sro != target_sro:
        try:
            row = srs.rollback_server_release(
                project_id,
                superseded_sro,
                actor,
                previous_artifact_id=target_artifact,
            )
            steps.append(
                {
                    "action": "rollback_superseded_sro",
                    "ok": True,
                    "server_release_id": superseded_sro,
                    "artifact_id": target_artifact,
                    "status": str(row.get("status") or ""),
                }
            )
        except ValueError as exc:
            steps.append(
                {
                    "action": "rollback_superseded_sro",
                    "ok": False,
                    "server_release_id": superseded_sro,
                    "error": str(exc),
                }
            )

    if target_sro and target_artifact:
        target_row = srs.get_server_release(project_id, target_sro)
        if target_row:
            current_artifact = str(target_row.get("artifact_id") or "").strip()
            status = str(target_row.get("status") or "")
            try:
                if current_artifact != target_artifact:
                    row = srs.rollback_server_release(
                        project_id,
                        target_sro,
                        actor,
                        previous_artifact_id=target_artifact,
                    )
                    steps.append(
                        {
                            "action": "restore_target_sro",
                            "ok": True,
                            "server_release_id": target_sro,
                            "artifact_id": target_artifact,
                            "status": str(row.get("status") or ""),
                        }
                    )
                elif status not in {"deployed", "deploying"}:
                    row = srs.deploy_server_release(project_id, target_sro, actor)
                    steps.append(
                        {
                            "action": "deploy_target_sro",
                            "ok": True,
                            "server_release_id": target_sro,
                            "status": str(row.get("status") or ""),
                        }
                    )
                else:
                    steps.append(
                        {
                            "action": "target_sro_already_active",
                            "ok": True,
                            "server_release_id": target_sro,
                            "status": status,
                        }
                    )
            except ValueError as exc:
                steps.append(
                    {
                        "action": "restore_target_sro",
                        "ok": False,
                        "server_release_id": target_sro,
                        "error": str(exc),
                    }
                )

    ok = all(step.get("ok") for step in steps) if steps else False
    result = {
        "skipped": False,
        "ok": ok,
        "target_server_release_id": target_sro,
        "target_artifact_id": target_artifact,
        "superseded_server_release_id": superseded_sro,
        "steps": steps,
    }

    order_id = str(target_order.get("release_order_id") or "").strip()
    if order_id:
        now = _now_iso()
        init_db()
        with get_cursor() as cur:
            cur.execute(
                "SELECT payload FROM release_orders WHERE project_id=? AND release_order_id=?",
                (project_id, order_id),
            )
            fetched = cur.fetchone()
            merged = dict(target_plan)
            if fetched:
                stored = _decode(fetched["payload"], {}) or {}
                if isinstance(stored, dict):
                    merged = {**stored, **merged}
            merged["server_coordinated_rollback"] = result
            cur.execute(
                "UPDATE release_orders SET payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
                (_json(merged), now, project_id, order_id),
            )
            _event(
                cur,
                order_id,
                "server_coordinated_rollback",
                actor,
                str(target_order.get("status") or "published"),
                str(target_order.get("status") or "published"),
                result,
            )
        if superseded_order and str(superseded_order.get("release_order_id") or "").strip():
            sid = str(superseded_order["release_order_id"])
            with get_cursor() as cur:
                cur.execute(
                    "SELECT payload FROM release_orders WHERE project_id=? AND release_order_id=?",
                    (project_id, sid),
                )
                fetched = cur.fetchone()
                merged = dict(superseded_plan)
                if fetched:
                    stored = _decode(fetched["payload"], {}) or {}
                    if isinstance(stored, dict):
                        merged = {**stored, **merged}
                merged["server_coordinated_rollback"] = {**result, "role": "superseded"}
                cur.execute(
                    "UPDATE release_orders SET payload=?, updated_at=? WHERE project_id=? AND release_order_id=?",
                    (_json(merged), now, project_id, sid),
                )

    return result
