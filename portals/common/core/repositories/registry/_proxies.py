# -*- coding: utf-8 -*-
"""DB-backed mapping proxies (no import-time JSON cache). Plan P0-02."""

from __future__ import annotations

from collections.abc import MutableMapping, MutableSequence
from typing import Any, Dict, Iterator, List

from repositories.registry.accessors import (
    get_project,
    has_project,
    list_all_project_versions,
    list_channels,
    list_project_versions,
    list_projects,
    replace_all_channels,
    save_project,
    save_project_versions,
)


class ProjectsDbProxy(MutableMapping):
    """Dict-like view; every read/write goes to SQLite registry."""

    def __getitem__(self, key: str) -> Dict[str, Any]:
        row = get_project(str(key))
        if row is None:
            raise KeyError(key)
        return row

    def __setitem__(self, key: str, value: Any) -> None:
        save_project(str(key), value if isinstance(value, dict) else {})

    def __delitem__(self, key: str) -> None:
        from repositories.registry.accessors import delete_project

        if not has_project(str(key)):
            raise KeyError(key)
        delete_project(str(key))

    def __iter__(self) -> Iterator[str]:
        return iter(list_projects())

    def __len__(self) -> int:
        return len(list_projects())

    def get(self, key, default=None):  # noqa: A003
        row = get_project(str(key))
        return row if row is not None else default


class ChannelsDbProxy(MutableSequence):
    """List-like view backed by channel repository (no in-memory cache)."""

    def _rows(self) -> List[Dict[str, Any]]:
        return list_channels()

    def __getitem__(self, index):
        return self._rows()[index]

    def __setitem__(self, index, value) -> None:
        if isinstance(index, slice):
            replace_all_channels(list(value))
            return
        rows = list(self._rows())
        rows[index] = value
        replace_all_channels(rows)

    def __delitem__(self, index) -> None:
        rows = list(self._rows())
        del rows[index]
        replace_all_channels(rows)

    def __len__(self) -> int:
        return len(self._rows())

    def insert(self, index, value) -> None:
        rows = list(self._rows())
        rows.insert(index, value)
        replace_all_channels(rows)

    def append(self, value) -> None:
        rows = list(self._rows())
        rows.append(value)
        replace_all_channels(rows)

    def extend(self, values) -> None:
        rows = list(self._rows())
        rows.extend(values)
        replace_all_channels(rows)

    def clear(self) -> None:
        replace_all_channels([])

    def __iadd__(self, other):
        self.extend(other)
        return self


class ProjectVersionsDbProxy(MutableMapping):
    """Dict[project_id, versions] backed by version row repository."""

    def __getitem__(self, key: str) -> List[Dict[str, Any]]:
        return list(list_project_versions(str(key)))

    def __setitem__(self, key: str, value: Any) -> None:
        save_project_versions(str(key), value if isinstance(value, list) else [])

    def __delitem__(self, key: str) -> None:
        from repositories.registry.accessors import delete_project_versions

        if not list_project_versions(str(key)):
            raise KeyError(key)
        delete_project_versions(str(key))

    def __iter__(self) -> Iterator[str]:
        return iter(list_all_project_versions())

    def __len__(self) -> int:
        return len(list_all_project_versions())

    def get(self, key, default=None):  # noqa: A003
        rows = list_project_versions(str(key))
        if rows:
            return list(rows)
        return default if default is not None else None

    def setdefault(self, key, default=None):  # noqa: A003
        rows = list_project_versions(str(key))
        if rows:
            return list(rows)
        value = default if isinstance(default, list) else []
        save_project_versions(str(key), value)
        return list(value)
