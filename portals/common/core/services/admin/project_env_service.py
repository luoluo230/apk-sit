"""Project release environment configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from repositories.admin import projects_repo
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


def list_environments(project_id: str) -> Tuple[Dict[str, Any], int]:
    if not projects_repo.get_project(project_id):
        return attach_legacy_error(fail("项目不存在", code="not_found", legacy={"error": "项目不存在"})), 404
    return ok({"environments": get_project_env_defs(project_id)}), 200


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
    return ok({"environments": get_project_env_defs(project_id)}), 201


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
    _save_env_defs(project_id, defs)
    projects_repo.audit("project_update_environment", f"{project_id} {key}")
    return ok({"environments": get_project_env_defs(project_id)}), 200


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
    return ok({"environments": get_project_env_defs(project_id)}), 200
