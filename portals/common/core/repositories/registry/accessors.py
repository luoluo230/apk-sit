# -*- coding: utf-8 -*-
"""Public registry accessors — no import-time mutable caches. Plan P0-02."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from repositories.registry.channel_repo import get_channel_repository
from repositories.registry.project_repo import get_project_repository
from repositories.registry.version_row_repo import get_version_row_repository


def list_projects() -> Dict[str, Dict[str, Any]]:
    return get_project_repository().list()


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    return get_project_repository().get(str(project_id or '').strip())


def has_project(project_id: str) -> bool:
    return get_project(project_id) is not None


def save_project(project_id: str, payload: Dict[str, Any]) -> None:
    get_project_repository().save(str(project_id or '').strip(), payload if isinstance(payload, dict) else {})


def delete_project(project_id: str) -> None:
    get_project_repository().delete(str(project_id or '').strip())


def replace_all_projects(projects: Dict[str, Dict[str, Any]]) -> None:
    get_project_repository().replace_all(projects if isinstance(projects, dict) else {})


def mirror_projects_json() -> None:
    get_project_repository()._mirror_all()


def list_channels() -> List[Dict[str, Any]]:
    return get_channel_repository().list()


def get_channel(channel_id: str) -> Optional[Dict[str, Any]]:
    return get_channel_repository().get(str(channel_id or '').strip())


def save_channel(channel_id: str, payload: Dict[str, Any]) -> None:
    get_channel_repository().save(str(channel_id or '').strip(), payload if isinstance(payload, dict) else {})


def replace_all_channels(channels: List[Dict[str, Any]]) -> None:
    get_channel_repository().replace_all(channels if isinstance(channels, list) else [])


def mirror_channels_json() -> None:
    get_channel_repository()._mirror_all()


def list_project_versions(project_id: str) -> List[Dict[str, Any]]:
    return get_version_row_repository().list_by_project(str(project_id or '').strip())


def list_all_project_versions() -> Dict[str, List[Dict[str, Any]]]:
    return get_version_row_repository().list_grouped()


def save_project_versions(project_id: str, versions: List[Dict[str, Any]]) -> None:
    get_version_row_repository().replace_project(
        str(project_id or '').strip(),
        versions if isinstance(versions, list) else [],
    )


def delete_project_versions(project_id: str) -> None:
    get_version_row_repository().delete_project(str(project_id or '').strip())


def mirror_project_versions_json() -> None:
    get_version_row_repository()._mirror_all()
