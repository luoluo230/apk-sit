"""Version module — multi-channel version create."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Tuple

from data.delivery_scope import get_channels_for_env, is_channel_allowed_for_env, is_platform_allowed_for_env
from data.platforms import is_valid_platform_id
from repositories.admin import versions_repo
from services.admin.version_group_repo import _ensure_version_group_meta
from services.admin.version_row_helpers import _format_version_output
from services.build.platform_capability import assert_buildable_delivery_platform
from services.release.env_registry import normalize_release_env_key

def create_version_all_channels(
    project_id: str, username: str, data: Dict[str, Any]
) -> Tuple[Dict[str, Any], int]:
    env_key = normalize_release_env_key(data.get("env_key") or "development", project_id=project_id)
    platform = (data.get("platform") or "").strip().lower()
    if not is_valid_platform_id(platform):
        return {"error": "平台无效或不支持"}, 400
    try:
        assert_buildable_delivery_platform(platform)
    except ValueError as exc:
        return {"error": str(exc)}, 400
    if not is_platform_allowed_for_env(project_id, env_key, platform):
        return {"error": "所选平台不在该环境的交付范围内"}, 400

    channel_ids = [
        str(row.get("id") or "").strip()
        for row in get_channels_for_env(project_id, env_key)
        if str(row.get("id") or "").strip()
    ]
    if not channel_ids:
        return {"error": "该环境未配置可用渠道"}, 400

    versions = versions_repo.list_versions(project_id)
    created_rows: list = []
    skipped_channels: list = []
    ch_text = (data.get("changelog") or "").strip()
    ch_rec = bool(data.get("changelog_recommended"))

    from services.admin.version_crud_service import _build_new_version_row

    for channel_id in channel_ids:
        if not is_channel_allowed_for_env(project_id, env_key, channel_id):
            continue
        single_data = dict(data)
        single_data.pop("apply_all_channels", None)
        single_data["channel_id"] = channel_id
        row, error, status = _build_new_version_row(project_id, username, single_data, versions)
        if error:
            if status == 409:
                skipped_channels.append(channel_id)
                continue
            return {"error": error}, status
        versions.append(row)
        created_rows.append(row)
        vid = str(row.get("id") or "").strip()
        if ch_text or ch_rec:
            versions_repo.save_changelog_item(
                "version:" + project_id + ":" + vid, {"text": ch_text, "recommended": ch_rec}
            )
        versions_repo.audit("create_project_version", "%s %s" % (project_id, vid))

    if not created_rows:
        return {"error": "所有渠道下均已存在该 VersionCode，或没有可创建的交付线"}, 409

    versions_repo.save_versions(project_id, versions)
    vn = str((created_rows[0] or {}).get("version_name") or "").strip()
    if vn:
        _ensure_version_group_meta(
            project_id,
            vn,
            username,
            created_rows[0].get("version_mode"),
            created_rows[0].get("notes"),
            env_key=env_key,
            platform=platform,
        )

    out_versions = [_format_version_output(project_id, row, platform, ch_text, ch_rec) for row in created_rows]
    return {
        "versions": out_versions,
        "version": out_versions[0],
        "created_count": len(out_versions),
        "skipped_count": len(skipped_channels),
    }, 200
