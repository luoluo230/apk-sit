# -*- coding: utf-8 -*-
"""User account repository using unified Storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from data._store import LOGIN_ATTEMPTS_FILE, USERS_FILE, Storage, load_document, save_document


class UserRepository:
    """CRUD wrapper for user records persisted via Storage."""

    def __init__(self, storage: Optional[Storage] = None):
        self._storage = storage or Storage(USERS_FILE, default=self._default_users())

    @staticmethod
    def _default_users() -> Dict[str, Dict[str, Any]]:
        return {
            'admin': {
                'password': __import__('hashlib').sha256('admin123'.encode()).hexdigest(),
                'role': 'super_admin',
                'created_at': datetime.now().isoformat(),
                'email': 'admin@example.com',
                'last_login': None,
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

    def find(self, username: str) -> Optional[Dict[str, Any]]:
        key = str(username or '').strip()
        if not key:
            return None
        row = self.data.get(key)
        return dict(row) if isinstance(row, dict) else None

    def exists(self, username: str) -> bool:
        return self.find(username) is not None

    def create(self, username: str, record: Dict[str, Any]) -> Dict[str, Any]:
        key = str(username or '').strip()
        if not key:
            raise ValueError('username is required')
        if key in self.data:
            raise KeyError(f'user already exists: {key}')
        payload = dict(record or {})
        payload.setdefault('created_at', datetime.now().isoformat())
        self.data[key] = payload
        self.save()
        return dict(payload)

    def update(self, username: str, record: Dict[str, Any]) -> Dict[str, Any]:
        key = str(username or '').strip()
        if not key or key not in self.data:
            raise KeyError(f'user not found: {key}')
        current = dict(self.data.get(key) or {})
        current.update(dict(record or {}))
        self.data[key] = current
        self.save()
        return dict(current)

    def delete(self, username: str) -> bool:
        key = str(username or '').strip()
        if key not in self.data:
            return False
        del self.data[key]
        self.save()
        return True

    def save(self) -> None:
        self._storage.save(self.data)

    def sync_module_cache(self, module_cache: Dict[str, Dict[str, Any]]) -> None:
        """Mirror repository state into legacy module-level dicts."""
        module_cache.clear()
        module_cache.update(self.data)


def load_login_attempts(default=None):
    if default is None:
        default = {}
    return load_document(LOGIN_ATTEMPTS_FILE, default)


def save_login_attempts(data) -> None:
    save_document(LOGIN_ATTEMPTS_FILE, data)
