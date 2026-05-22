"""Version data access wrappers."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import (
    projects_db,
    project_versions_db,
    changelog_db,
    save_project_versions,
    save_changelog,
    log_audit,
    get_project_download_count,
    get_version_download_count,
    version_has_apk,
    version_is_recommended,
    get_platform_label,
    can_view_project,
    can_edit_project,
    get_approved_approval,
    get_system_config,
    load_download_events,
    extract_project_name,
)


def has_project(project_id: str) -> bool:
    return project_id in projects_db


def can_view(project_id: str, username: str) -> bool:
    return can_view_project(project_id, username)


def can_edit(project_id: str, username: str) -> bool:
    return can_edit_project(project_id, username)


def list_versions(project_id: str) -> List[Dict[str, Any]]:
    versions = project_versions_db.get(project_id) or []
    return versions if isinstance(versions, list) else []


def save_versions(project_id: str, versions: List[Dict[str, Any]]) -> None:
    project_versions_db[project_id] = versions
    save_project_versions()


def save_changelog_item(key: str, payload: Dict[str, Any] | None) -> None:
    if payload:
        changelog_db[key] = payload
    else:
        changelog_db.pop(key, None)
    save_changelog()


def audit(action: str, target: str) -> None:
    log_audit(action, target)


def project_download_count(project_id: str) -> int:
    return get_project_download_count(project_id)


def version_download_count(project_id: str, version: Dict[str, Any]) -> int:
    return get_version_download_count(project_id, version)


def has_apk(project_id: str, version: Dict[str, Any]) -> bool:
    return version_has_apk(project_id, version)


def is_recommended(project_id: str, version: Dict[str, Any]) -> bool:
    return version_is_recommended(project_id, version)


def platform_label(platform: str) -> str:
    return get_platform_label(platform)


def approval_required_for_delete() -> bool:
    return str(get_system_config("REQUIRE_APPROVAL_FOR_DELETE") or "").lower() in ("true", "1", "yes")


def has_approved_delete(project_id: str, version_id: str) -> bool:
    target_id = "%s:%s" % (project_id, version_id)
    return bool(get_approved_approval("delete_version", target_id))


def load_events() -> List[Dict[str, Any]]:
    return load_download_events()


def parse_event_project(filename: str) -> str:
    return extract_project_name(filename)
