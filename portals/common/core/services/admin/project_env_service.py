"""Project release environment configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from repositories.admin import projects_repo
from data.delivery_scope import get_env_delivery_scope
from services.admin.envelope import attach_legacy_error, fail, ok
from services.release.env_registry import (
    CANONICAL_ENV_KEYS,
    get_project_env_defs,
    is_valid_custom_env_key,
)


def _save_env_defs(project_id: str, defs: List[Dict[str, Any]]) -> None:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return
    proj["release_environments"] = defs
    projects_repo.save_projects_repo()


def _env_row_with_scope(project_id: str, row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    key = str(row.get("env_key") or "").strip().lower()
    scope = get_env_delivery_scope(project_id, key)
    enabled_channels = [c for c in scope.get("assigned_channels", []) if c.get("enabled")]
    enabled_platforms = [p for p in scope.get("assigned_platforms", []) if p.get("enabled")]
    inherits_channels = bool(scope.get("inherits_project_channels"))
    inherits_platforms = bool(scope.get("inherits_project_platforms"))
    out["delivery_scope"] = {
        "inherits_project_channels": inherits_channels,
        "inherits_project_platforms": inherits_platforms,
        "inherits_project": inherits_channels and inherits_platforms,
        "enabled_channel_count": len(enabled_channels),
        "enabled_platform_count": len(enabled_platforms),
        "delivery_line_count": len(enabled_channels) * len(enabled_platforms),
        "channel_labels": [str(c.get("channel_name") or c.get("channel_id") or "") for c in enabled_channels],
        "platform_labels": [str(p.get("platform_name") or p.get("platform_id") or "") for p in enabled_platforms],
    }
    return out


def list_environments(project_id: str) -> Tuple[Dict[str, Any], int]:
    if not projects_repo.get_project(project_id):
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    envs = [_env_row_with_scope(project_id, row) for row in get_project_env_defs(project_id)]
    return ok({"environments": envs}), 200


def add_environment(project_id: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    env_key = str(data.get("env_key") or "").strip().lower()
    label = str(data.get("label") or "").strip()
    if not is_valid_custom_env_key(env_key):
        return attach_legacy_error(fail("环境 key 无效（小写字母开头，仅字母数字下划线）", code="validation_error")), 400
    if not label:
        return attach_legacy_error(fail("环境名称不能为空", code="validation_error")), 400
    defs = get_project_env_defs(project_id)
    if any(str(row.get("env_key") or "").lower() == env_key for row in defs):
        return attach_legacy_error(fail("环境 key 已存在", code="conflict")), 409
    order = int(data.get("order") or 50)
    defs.append({"env_key": env_key, "label": label, "builtin": False, "enabled": True, "order": order})
    _save_env_defs(project_id, defs)
    projects_repo.audit("project_add_environment", f"{project_id} {env_key}")
    envs = [_env_row_with_scope(project_id, row) for row in get_project_env_defs(project_id)]
    return ok({"environments": envs}), 201


def update_environment(project_id: str, env_key: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    key = str(env_key or "").strip().lower()
    defs = get_project_env_defs(project_id)
    hit = next((row for row in defs if str(row.get("env_key") or "").lower() == key), None)
    if not hit:
        return attach_legacy_error(fail("环境不存在", code="not_found")), 404
    if "label" in data and str(data.get("label") or "").strip():
        hit["label"] = str(data.get("label") or "").strip()
    if "enabled" in data:
        hit["enabled"] = bool(data.get("enabled"))
    if "order" in data:
        hit["order"] = int(data.get("order") or hit.get("order") or 50)
    if "release_policy" in data and isinstance(data.get("release_policy"), dict):
        hit["release_policy"] = dict(data.get("release_policy") or {})
    _save_env_defs(project_id, defs)
    projects_repo.audit("project_update_environment", f"{project_id} {key}")
    envs = [_env_row_with_scope(project_id, row) for row in get_project_env_defs(project_id)]
    return ok({"environments": envs}), 200


def delete_environment(project_id: str, env_key: str) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    key = str(env_key or "").strip().lower()
    if key in CANONICAL_ENV_KEYS:
        return attach_legacy_error(fail("内置环境不可删除，可改为禁用", code="validation_error")), 400
    defs = get_project_env_defs(project_id)
    if not any(str(row.get("env_key") or "").lower() == key and not row.get("builtin") for row in defs):
        return attach_legacy_error(fail("自定义环境不存在", code="not_found")), 404
    defs = [row for row in defs if str(row.get("env_key") or "").lower() != key]
    _save_env_defs(project_id, defs)
    projects_repo.audit("project_delete_environment", f"{project_id} {key}")
    envs = [_env_row_with_scope(project_id, row) for row in get_project_env_defs(project_id)]
    return ok({"environments": envs}), 200


def get_delivery_scope(project_id: str, env_key: str) -> Tuple[Dict[str, Any], int]:
    if not projects_repo.get_project(project_id):
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    key = str(env_key or "").strip().lower()
    if not any(str(row.get("env_key") or "").lower() == key for row in get_project_env_defs(project_id)):
        return attach_legacy_error(fail("环境不存在", code="not_found")), 404
    return ok(get_env_delivery_scope(project_id, key)), 200


def update_delivery_scope(project_id: str, env_key: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    proj = projects_repo.get_project(project_id)
    if not proj:
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    key = str(env_key or "").strip().lower()
    defs = get_project_env_defs(project_id)
    hit = next((row for row in defs if str(row.get("env_key") or "").lower() == key), None)
    if not hit:
        return attach_legacy_error(fail("环境不存在", code="not_found")), 404

    scope_preview = get_env_delivery_scope(project_id, key)
    project_channel_ids = {row["channel_id"] for row in scope_preview.get("project_channel_catalog") or []}
    project_platform_ids = {row["platform_id"] for row in scope_preview.get("project_platform_catalog") or []}

    if "channels" in data:
        raw = data.get("channels")
        if raw is None:
            hit.pop("channels", None)
        elif isinstance(raw, list):
            channels = [str(x).strip() for x in raw if str(x).strip() in project_channel_ids]
            hit["channels"] = channels
        else:
            return attach_legacy_error(fail("channels 必须是数组", code="validation_error")), 400

    if "platforms" in data:
        raw = data.get("platforms")
        if raw is None:
            hit.pop("platforms", None)
        elif isinstance(raw, list):
            platforms = [str(x).strip().lower() for x in raw if str(x).strip().lower() in project_platform_ids]
            hit["platforms"] = platforms
        else:
            return attach_legacy_error(fail("platforms 必须是数组", code="validation_error")), 400

    if "disabled_channels" in data:
        raw = data.get("disabled_channels")
        if isinstance(raw, list):
            assigned = set(hit.get("channels") or [r["channel_id"] for r in scope_preview.get("assigned_channels") or []])
            hit["disabled_channels"] = [str(x).strip() for x in raw if str(x).strip() in assigned]
        else:
            return attach_legacy_error(fail("disabled_channels 必须是数组", code="validation_error")), 400

    if "disabled_platforms" in data:
        raw = data.get("disabled_platforms")
        if isinstance(raw, list):
            assigned = set(hit.get("platforms") or [r["platform_id"] for r in scope_preview.get("assigned_platforms") or []])
            hit["disabled_platforms"] = [str(x).strip().lower() for x in raw if str(x).strip().lower() in assigned]
        else:
            return attach_legacy_error(fail("disabled_platforms 必须是数组", code="validation_error")), 400

    _save_env_defs(project_id, defs)
    projects_repo.audit("project_update_delivery_scope", f"{project_id} {key}")
    return ok(get_env_delivery_scope(project_id, key)), 200
