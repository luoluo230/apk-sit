"""Project data access wrappers."""

from __future__ import annotations

from typing import Dict, Any, List

from models.data import (
    projects_db,
    users_db,
    channels_db,
    project_versions_db,
    save_projects,
    save_project_versions,
    log_audit,
)


def list_projects() -> Dict[str, Dict[str, Any]]:
    return projects_db


def get_project(project_id: str) -> Dict[str, Any] | None:
    return projects_db.get(project_id)


def has_project(project_id: str) -> bool:
    return project_id in projects_db


def upsert_project(project_id: str, payload: Dict[str, Any]) -> None:
    projects_db[project_id] = payload
    save_projects()


def save_projects_repo() -> None:
    save_projects()


def delete_project(project_id: str) -> None:
    projects_db.pop(project_id, None)
    save_projects()


def delete_project_versions(project_id: str) -> None:
    if project_id in project_versions_db:
        project_versions_db.pop(project_id, None)
        save_project_versions()


def list_users() -> Dict[str, Dict[str, Any]]:
    return users_db


def list_channels() -> List[Dict[str, Any]]:
    return channels_db if isinstance(channels_db, list) else []


def audit(action: str, target: str) -> None:
    log_audit(action, target)
