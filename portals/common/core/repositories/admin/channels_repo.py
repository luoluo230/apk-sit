"""Channel data access wrappers."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import channels_db, project_versions_db, save_channels, log_audit


def list_channels() -> List[Dict[str, Any]]:
    return channels_db if isinstance(channels_db, list) else []


def save() -> None:
    save_channels()


def audit(action: str, target: str) -> None:
    log_audit(action, target)


def replace_channels(channels: List[Dict[str, Any]]) -> None:
    if isinstance(channels_db, list):
        channels_db[:] = channels
        save_channels()


def version_project_ids_using_channel(channel_id: str) -> List[str]:
    project_ids: List[str] = []
    for pid, versions in (project_versions_db or {}).items():
        rows = versions or []
        if any((v.get("channel") or "") == channel_id for v in rows if isinstance(v, dict)):
            project_ids.append(str(pid))
    return project_ids
