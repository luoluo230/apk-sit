"""Channel data access wrappers."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import log_audit, save_channels
from repositories.registry.accessors import list_all_project_versions
from repositories.registry.accessors import list_channels as _registry_list_channels
from repositories.registry.accessors import replace_all_channels


def list_channels() -> List[Dict[str, Any]]:
    return _registry_list_channels()


def save() -> None:
    save_channels()


def audit(action: str, target: str) -> None:
    log_audit(action, target)


def replace_channels(channels: List[Dict[str, Any]]) -> None:
    replace_all_channels(channels if isinstance(channels, list) else [])


def version_project_ids_using_channel(channel_id: str) -> List[str]:
    project_ids: List[str] = []
    for pid, versions in list_all_project_versions().items():
        rows = versions or []
        if any((v.get("channel") or "") == channel_id for v in rows if isinstance(v, dict)):
            project_ids.append(str(pid))
    return project_ids
