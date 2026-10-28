# -*- coding: utf-8 -*-
"""Version-page delivery-line matrix: env × channel × platform inventory."""

from __future__ import annotations

from typing import Any, Dict, List

from data.delivery_scope import get_channels_for_env, get_platform_defs_for_env
from services.admin.version_group_repo import _version_row_env_key, _version_row_platform
from services.admin.version_group_service import list_version_groups
from services.release.env_registry import normalize_release_env_key, project_env_label

STATUS_LABELS = {
    "live": "线上",
    "built": "有构建未发布",
    "no_vc": "无该渠道构建",
    "empty": "未配管线",
}


def _channel_id_of(row: Dict[str, Any]) -> str:
    return str(row.get("channel_id") or row.get("channel") or "").strip()


def _cell_status(
    *,
    bundle_id: str,
    version_name: str,
    version_code: str,
    has_group: bool,
    channel_vc_count: int,
    artifact_ready: bool,
) -> Dict[str, str]:
    if bundle_id:
        label = " / ".join(part for part in (version_name, version_code) if part) or "已激活"
        return {"status": "live", "label": label}
    if artifact_ready:
        return {"status": "built", "label": STATUS_LABELS["built"]}
    if has_group and channel_vc_count <= 0:
        return {"status": "no_vc", "label": STATUS_LABELS["no_vc"]}
    if has_group:
        return {"status": "built", "label": "有大版本"}
    return {"status": "empty", "label": STATUS_LABELS["empty"]}


def build_version_delivery_matrix(
    project_id: str,
    username: str,
    env_key: str,
) -> Dict[str, Any]:
    ek = normalize_release_env_key(env_key or "development", project_id=project_id)
    channels = [
        {
            "channel_id": str(row.get("id") or ""),
            "channel_name": str(row.get("name") or row.get("id") or ""),
        }
        for row in get_channels_for_env(project_id, ek)
        if str(row.get("id") or "").strip()
    ]
    platforms = get_platform_defs_for_env(project_id, ek)
    groups_payload, status = list_version_groups(project_id, username, env_key=ek)
    if status >= 400:
        return groups_payload
    groups = groups_payload.get("version_groups") or []
    from services.admin.version_download_service import list_versions

    versions_payload, vstatus = list_versions(project_id, username)
    versions = versions_payload.get("versions") or [] if vstatus < 400 else []
    env_versions = [row for row in versions if _version_row_env_key(row, project_id) == ek]

    try:
        from services.release.channel_journey_bff import _delivery_lines_for_env

        lines = _delivery_lines_for_env(project_id, ek)
    except Exception:
        lines = []
    line_map = {
        (str(row.get("channel_id") or ""), str(row.get("platform") or "")): row
        for row in lines
    }

    cells: List[Dict[str, Any]] = []
    for channel in channels:
        cid = channel["channel_id"]
        for plat in platforms:
            pk = str(plat.get("value") or "")
            line = line_map.get((cid, pk)) or {}
            platform_groups = [
                g for g in groups if str(g.get("platform") or "") in {"", pk}
            ]
            channel_vcs = [
                row
                for row in env_versions
                if _channel_id_of(row) == cid and _version_row_platform(row) == pk
            ]
            artifact_ready = any(str(row.get("apk_status") or "") == "found" for row in channel_vcs)
            cell = _cell_status(
                bundle_id=str(line.get("bundle_id") or ""),
                version_name=str(line.get("version_name") or ""),
                version_code=str(line.get("version_code") or ""),
                has_group=bool(platform_groups),
                channel_vc_count=len(channel_vcs),
                artifact_ready=artifact_ready,
            )
            cells.append(
                {
                    "channel_id": cid,
                    "channel_name": channel["channel_name"],
                    "platform": pk,
                    "platform_label": plat.get("label") or pk,
                    "bundle_id": str(line.get("bundle_id") or ""),
                    "group_count": len(platform_groups),
                    "vc_count": len(channel_vcs),
                    "pipeline_ready": any(bool(g.get("pipeline_ready")) for g in platform_groups),
                    **cell,
                    "href": (
                        f"/admin/projects/{project_id}/versions"
                        f"?env_key={ek}&channel_id={cid}&platform={pk}"
                    ),
                }
            )

    return {
        "env_key": ek,
        "env_label": project_env_label(project_id, ek),
        "channels": channels,
        "platforms": platforms,
        "cells": cells,
        "hint": "格子是交付线。点选后下面列出该平台的大版本（管线），并只显示该渠道的构建。",
    }
