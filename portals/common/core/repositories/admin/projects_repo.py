"""Project data access wrappers."""

from __future__ import annotations

from typing import Dict, Any, List

from repositories.registry.project_repo import get_project_repository
from models.data import (
    channels_db,
    project_versions_db,
    log_audit,
)


def list_projects() -> Dict[str, Dict[str, Any]]:
    return get_project_repository().list()


def get_project(project_id: str) -> Dict[str, Any] | None:
    return get_project_repository().get(project_id)


def has_project(project_id: str) -> bool:
    return get_project_repository().get(project_id) is not None


def upsert_project(project_id: str, payload: Dict[str, Any]) -> None:
    get_project_repository().save(project_id, payload)


def save_projects_repo() -> None:
    get_project_repository()._mirror_all()


def delete_project(project_id: str) -> None:
    get_project_repository().delete(project_id)


def delete_project_versions(project_id: str) -> None:
    from repositories.registry.version_row_repo import get_version_row_repository

    get_version_row_repository().delete_project(project_id)


def list_users() -> Dict[str, Dict[str, Any]]:
    from repositories.admin import users_repo

    return users_repo.list_users()


def list_channels() -> List[Dict[str, Any]]:
    return channels_db if isinstance(channels_db, list) else []


def audit(action: str, target: str) -> None:
    log_audit(action, target)
