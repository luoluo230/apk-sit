# -*- coding: utf-8 -*-
"""Completed Jenkins tasks that a release order can ship, plus matching server releases."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import get_channel_by_id, project_versions_db
from models.db import get_cursor, init_db
from services.release.env_registry import stage_to_env_key
from services.release.order_helpers import _decode

RELEASED_STATUSES = {"published", "verifying", "verified"}
ROLLED_STATUSES = {"rolled_back"}
SERVER_SHIPPABLE = {"ready", "deployed"}


def stamp_selected_build(record_payload: Dict[str, Any]) -> None:
    """Keep the shipped Jenkins build number on the order, and tie the server release."""
    bn = str(record_payload.get("selected_build_number") or "").strip()
    if bn.isdigit():
        record_payload["build_job_id"] = bn
    if "server_release_id" in record_payload:
        record_payload["deploy_server_with_client"] = bool(
            str(record_payload.get("server_release_id") or "").strip()
        )


def classify_release_mark(
    version_id: str,
    build_number: int,
    orders: List[Dict[str, Any]],
    *,
    is_newest_success: bool,
) -> str:
    """released / rolled_back / unreleased for one completed build."""
    vid = str(version_id or "").strip()
    bn = str(int(build_number or 0))
    exact = [row for row in orders if _order_matches_build(row, vid, bn)]
    if any(str(row.get("status") or "") in RELEASED_STATUSES for row in exact):
        return "released"
    if any(str(row.get("status") or "") in ROLLED_STATUSES for row in exact):
        return "rolled_back"
    if is_newest_success and any(
        str(row.get("version_id") or "") == vid
        and str(row.get("status") or "") in RELEASED_STATUSES
        and not _order_build_number(row)
        for row in orders
    ):
        return "released"
    return "unreleased"


def list_ship_choices(
    project_id: str,
    *,
    env_key: str = "",
    channel_id: str = "",
    platform: str = "",
    release_state: str = "",
) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    tasks = _completed_client_tasks(pid, env_key=env_key, channel_id=channel_id, platform=platform)
    state = str(release_state or "").strip()
    if state in {"released", "unreleased", "rolled_back"}:
        tasks = [row for row in tasks if row.get("release_mark") == state]
    return {
        "tasks": tasks,
        "server_releases": _server_releases(pid, env_key=env_key),
    }


def _completed_client_tasks(
    project_id: str,
    *,
    env_key: str,
    channel_id: str,
    platform: str,
) -> List[Dict[str, Any]]:
    from services.build_history_service import _resolve_build_status, list_records_for_project

    versions = {
        str(row.get("id") or ""): row
        for row in (project_versions_db.get(project_id) or [])
        if isinstance(row, dict)
    }
    orders = _load_orders(project_id)
    cache: dict = {}
    grouped: Dict[str, List[dict]] = {}
    for rec in list_records_for_project(project_id):
        item = _resolve_build_status(rec, cache, detail_mode=False)
        vid = str(item.get("version_id") or "")
        if not vid:
            continue
        grouped.setdefault(vid, []).append(item)

    want_env = stage_to_env_key(env_key) if env_key else ""
    want_channel = str(channel_id or "").strip()
    want_platform = str(platform or "").strip().lower()
    tasks: List[Dict[str, Any]] = []
    for vid, items in grouped.items():
        meta = versions.get(vid) or {}
        if not _scope_matches(meta, want_env, want_channel, want_platform, project_id):
            continue
        completed = [row for row in items if str(row.get("result") or "").upper() == "SUCCESS"]
        if not completed and _version_has_apk(project_id, meta):
            completed = items[:1]
        if not completed:
            continue
        completed.sort(key=lambda row: int(row.get("build_number") or 0), reverse=True)
        newest = int(completed[0].get("build_number") or 0)
        for row in completed:
            bn = int(row.get("build_number") or 0)
            mark = classify_release_mark(vid, bn, orders, is_newest_success=(bn == newest))
            tasks.append(_task_row(meta, row, mark, project_id))
    tasks.sort(key=_task_sort_key)
    return tasks


def _task_row(meta: dict, build: dict, mark: str, project_id: str) -> Dict[str, Any]:
    channel_id = str(meta.get("channel_id") or meta.get("channel") or "").strip()
    channel = get_channel_by_id(channel_id) or {}
    code = str(meta.get("version_code") or build.get("version_code") or "")
    return {
        "instance_id": str(build.get("instance_id") or ""),
        "build_number": int(build.get("build_number") or 0),
        "version_id": str(build.get("version_id") or meta.get("id") or ""),
        "version_name": str(meta.get("version_name") or build.get("version_name") or ""),
        "version_code": code,
        "env_key": stage_to_env_key(meta.get("env_key") or meta.get("stage") or ""),
        "channel_id": channel_id,
        "channel_name": str(channel.get("name") or channel_id),
        "platform": str(meta.get("platform") or "").strip().lower(),
        "triggered_by": str(build.get("triggered_by") or ""),
        "finished_at": str(build.get("ended_at") or build.get("started_at") or ""),
        "release_mark": mark,
        "release_label": {"released": "已发版", "rolled_back": "已回滚", "unreleased": "未发版"}.get(mark, "未发版"),
        "notes": str(meta.get("description") or meta.get("notes") or ""),
        "project_id": project_id,
    }


def _task_sort_key(row: Dict[str, Any]):
    code = str(row.get("version_code") or "")
    numeric = int(code) if code.isdigit() else -1
    return (-numeric, code, -int(row.get("build_number") or 0))


def _scope_matches(meta: dict, env_key: str, channel_id: str, platform: str, project_id: str) -> bool:
    if not meta:
        return False
    if env_key and stage_to_env_key(meta.get("env_key") or meta.get("stage") or "") != env_key:
        return False
    if platform and str(meta.get("platform") or "").strip().lower() != platform:
        return False
    if channel_id:
        raw = str(meta.get("channel_id") or meta.get("channel") or "").strip()
        from services.release.scope_ids import resolve_channel_id

        resolved = resolve_channel_id(project_id, raw) or raw
        want = resolve_channel_id(project_id, channel_id) or channel_id
        if resolved != want:
            return False
    return True


def _version_has_apk(project_id: str, meta: dict) -> bool:
    if not meta:
        return False
    try:
        from repositories.admin import versions_repo

        return bool(versions_repo.has_apk(project_id, meta))
    except Exception:
        return False


def _load_orders(project_id: str) -> List[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT version_id, status, payload FROM release_orders WHERE project_id=?",
            (project_id,),
        ).fetchall()
    out = []
    for row in rows:
        payload = _decode(row["payload"], {}) or {}
        out.append({
            "version_id": str(row["version_id"] or ""),
            "status": str(row["status"] or ""),
            "payload": payload if isinstance(payload, dict) else {},
        })
    return out


def _order_build_number(order: Dict[str, Any]) -> str:
    payload = order.get("payload") if isinstance(order.get("payload"), dict) else {}
    for key in ("selected_build_number", "build_job_id"):
        value = str(payload.get(key) or "").strip()
        if value.isdigit():
            return value
    return ""


def _order_matches_build(order: Dict[str, Any], version_id: str, build_number: str) -> bool:
    if str(order.get("version_id") or "") != version_id:
        return False
    return _order_build_number(order) == build_number


def _server_releases(project_id: str, *, env_key: str) -> List[Dict[str, Any]]:
    from services.release.server_artifact_service import get_artifact
    from services.release.server_release_service import list_server_releases

    want = stage_to_env_key(env_key) if env_key else ""
    rows = []
    for row in list_server_releases(project_id, env_key=want):
        status = str(row.get("status") or "")
        if status not in SERVER_SHIPPABLE:
            continue
        artifact = get_artifact(str(row.get("artifact_id") or "")) or {}
        label = str(artifact.get("version_label") or artifact.get("artifact_id") or "未命名制品")
        rows.append({
            "server_release_id": str(row.get("server_release_id") or ""),
            "env_key": str(row.get("env_key") or ""),
            "status": status,
            "status_label": "已部署" if status == "deployed" else "可部署",
            "version_label": label,
            "artifact_id": str(row.get("artifact_id") or ""),
        })
    return rows
