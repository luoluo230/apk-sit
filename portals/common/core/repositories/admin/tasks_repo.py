"""Task data access wrappers."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import project_tasks_db, save_project_tasks, log_audit, can_view_project, can_edit_project
from repositories.registry.accessors import get_project, has_project, list_projects, save_project, list_channels, list_project_versions, save_project_versions


def has_project(project_id: str) -> bool:
    return has_project(project_id)


def get_project(project_id: str) -> Dict[str, Any] | None:
    return get_project(project_id)


def can_view(project_id: str, username: str) -> bool:
    return can_view_project(project_id, username)


def can_edit(project_id: str, username: str) -> bool:
    return can_edit_project(project_id, username)


def list_tasks(project_id: str) -> List[Dict[str, Any]]:
    rows = project_tasks_db.get(project_id) or []
    return rows if isinstance(rows, list) else []


def save_tasks(project_id: str, rows: List[Dict[str, Any]]) -> None:
    project_tasks_db[project_id] = rows
    save_project_tasks()


def audit(action: str, target: str) -> None:
    log_audit(action, target)