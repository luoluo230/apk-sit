# -*- coding: utf-8 -*-
"""MutableMapping proxies over registry repositories. Plan P0-02."""

from __future__ import annotations

from collections.abc import MutableMapping, MutableSequence
from typing import Any, Dict, Iterator, List

from repositories.registry.channel_repo import get_channel_repository
from repositories.registry.project_repo import get_project_repository
from repositories.registry.version_row_repo import get_version_row_repository


class ProjectsDbProxy(MutableMapping):
    """Dict-like view of projects backed by ProjectRepository."""

    def __getitem__(self, key: str) -> Dict[str, Any]:
        row = get_project_repository().get(str(key))
        if row is None:
            raise KeyError(key)
        return row

    def __setitem__(self, key: str, value: Any) -> None:
        get_project_repository().save(str(key), value if isinstance(value, dict) else {})

    def __delitem__(self, key: str) -> None:
        repo = get_project_repository()
        if repo.get(str(key)) is None:
            raise KeyError(key)
        repo.delete(str(key))

    def __iter__(self) -> Iterator[str]:
        return iter(get_project_repository().list())

    def __len__(self) -> int:
        return len(get_project_repository().list())

    def get(self, key, default=None):  # noqa: A003
        row = get_project_repository().get(str(key))
        return row if row is not None else default


class ChannelsDbProxy(MutableSequence):
    """List-like view of channels backed by ChannelRepository."""

    def __init__(self) -> None:
        self._cache: List[Dict[str, Any]] | None = None

    def _rows(self) -> List[Dict[str, Any]]:
        if self._cache is None:
            self._cache = get_channel_repository().list()
        return self._cache

    def _invalidate(self) -> None:
        self._cache = None

    def __getitem__(self, index):
        return self._rows()[index]

    def __setitem__(self, index, value) -> None:
        if isinstance(index, slice):
            get_channel_repository().replace_all(list(value))
            self._invalidate()
            return
        rows = list(self._rows())
        rows[index] = value
        get_channel_repository().replace_all(rows)
        self._invalidate()

    def __delitem__(self, index) -> None:
        rows = list(self._rows())
        del rows[index]
        get_channel_repository().replace_all(rows)
        self._invalidate()

    def __len__(self) -> int:
        return len(self._rows())

    def insert(self, index, value) -> None:
        rows = list(self._rows())
        rows.insert(index, value)
        get_channel_repository().replace_all(rows)
        self._invalidate()

    def append(self, value) -> None:
        rows = list(self._rows())
        rows.append(value)
        get_channel_repository().replace_all(rows)
        self._invalidate()

    def extend(self, values) -> None:
        rows = list(self._rows())
        rows.extend(values)
        get_channel_repository().replace_all(rows)
        self._invalidate()

    def clear(self) -> None:
        get_channel_repository().replace_all([])
        self._invalidate()

    def __iadd__(self, other):
        self.extend(other)
        return self


class ProjectVersionsDbProxy(MutableMapping):
    """Dict[project_id, versions] backed by VersionRowRepository."""

    def __getitem__(self, key: str) -> List[Dict[str, Any]]:
        rows = get_version_row_repository().list_by_project(str(key))
        return list(rows)

    def __setitem__(self, key: str, value: Any) -> None:
        versions = value if isinstance(value, list) else []
        get_version_row_repository().replace_project(str(key), versions)

    def __delitem__(self, key: str) -> None:
        repo = get_version_row_repository()
        if not repo.list_by_project(str(key)):
            raise KeyError(key)
        repo.delete_project(str(key))

    def __iter__(self) -> Iterator[str]:
        return iter(get_version_row_repository().list_grouped())

    def __len__(self) -> int:
        return len(get_version_row_repository().list_grouped())

    def get(self, key, default=None):  # noqa: A003
        rows = get_version_row_repository().list_by_project(str(key))
        if rows:
            return list(rows)
        return default if default is not None else None
