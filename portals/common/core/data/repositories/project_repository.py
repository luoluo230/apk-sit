# -*- coding: utf-8 -*-
"""Project registry repository using unified Storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from data._store import PROJECTS_FILE, Storage


class ProjectRepository:
    """CRUD wrapper for project records persisted via Storage."""

    def __init__(self, storage: Optional[Storage] = None):
        self._storage = storage or Storage(PROJECTS_FILE, default=self._default_projects())

    @staticmethod
    def _default_projects() -> Dict[str, Dict[str, Any]]:
        return {
            'RecycleTycoon': {
                'name': '垃圾回收站',
                'description': '垃圾回收站游戏',
                'created_at': datetime.now().isoformat(),
                'order': 1,
                'status': 'active',
            }
        }

    def reload(self) -> Dict[str, Dict[str, Any]]:
        return self._storage.load()

    @property
    def data(self) -> Dict[str, Dict[str, Any]]:
        if not isinstance(self._storage.data, dict):
            self._storage.data = {}
        return self._storage.data

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.data)

    def find(self, project_ref: str) -> Optional[Dict[str, Any]]:
        project_id = self.find_id(project_ref)
        if not project_id:
            return None
        row = self.data.get(project_id)
        return dict(row) if isinstance(row, dict) else None

    def find_id(self, project_ref: str) -> str:
        ref = str(project_ref or '').strip()
        if not ref:
            return ''
        if ref in self.data:
            return ref
        lowered = ref.lower()
        for project_id, project in self.data.items():
            payload = project if isinstance(project, dict) else {}
            if str(payload.get('name') or '').strip().lower() == lowered:
                return str(project_id)
        return ''

    def exists(self, project_ref: str) -> bool:
        return bool(self.find_id(project_ref))

    def create(self, project_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        key = str(project_id or '').strip()
        if not key:
            raise ValueError('project_id is required')
        if key in self.data:
            raise KeyError(f'project already exists: {key}')
        payload = dict(record or {})
        payload.setdefault('created_at', datetime.now().isoformat())
        payload.setdefault('status', 'active')
        self.data[key] = payload
        self.save()
        return dict(payload)

    def update(self, project_ref: str, record: Dict[str, Any]) -> Dict[str, Any]:
        project_id = self.find_id(project_ref)
        if not project_id:
            raise KeyError(f'project not found: {project_ref}')
        current = dict(self.data.get(project_id) or {})
        current.update(dict(record or {}))
        self.data[project_id] = current
        self.save()
        return dict(current)

    def delete(self, project_ref: str) -> bool:
        project_id = self.find_id(project_ref)
        if not project_id or project_id not in self.data:
            return False
        del self.data[project_id]
        self.save()
        return True

    def save(self) -> None:
        self._storage.save(self.data)

    def sync_module_cache(self, module_cache: Dict[str, Dict[str, Any]]) -> None:
        module_cache.clear()
        module_cache.update(self.data)
