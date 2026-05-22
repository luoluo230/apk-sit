"""Task data access wrappers."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import projects_db, project_tasks_db, save_project_tasks, log_audit, can_view_project, can_edit_project


def has_project(project_id: str) -> bool:
    return project_id in projects_db


def get_project(project_id: str) -> Dict[str, Any] | None:
    return projects_db.get(project_id)


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
