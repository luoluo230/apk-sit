# -*- coding: utf-8 -*-
"""Project version row repository backed by SQLite. Plan P0-02 Step 1."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from data._store import PROJECT_VERSIONS_FILE
from repositories.registry._db import get_cursor, init_db
from repositories.registry._mirror import write_json_mirror

_shared: Optional['VersionRowRepository'] = None


def _version_row_id(project_id: str, version: Dict[str, Any], index: int = 0) -> str:
    pid = str(project_id or '').strip()
    explicit = str(version.get('id') or '').strip()
    if explicit:
        scoped = explicit if explicit.startswith(f'{pid}::') else f'{pid}::{explicit}'
        return scoped
    vn = str(version.get('version_name') or '').strip()
    vc = str(version.get('version_code') or '').strip()
    if vn or vc:
        return f'{pid}::{vn}:{vc}:{index}'
    return f'{pid}::row:{index}'


class VersionRowRepository:
    """CRUD for per-project version rows."""

    def get(self, version_id: str) -> Optional[Dict[str, Any]]:
        vid = str(version_id or '').strip()
        if not vid:
            return None
        init_db()
        with get_cursor() as cur:
            row = cur.execute(
                'SELECT payload FROM project_versions WHERE version_id=?',
                (vid,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def list_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        pid = str(project_id or '').strip()
        if not pid:
            return []
        init_db()
        with get_cursor() as cur:
            rows = cur.execute(
                '''
                SELECT payload FROM project_versions
                WHERE project_id=?
                ORDER BY updated_at ASC, version_id ASC
                ''',
                (pid,),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row[0])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict):
                out.append(payload)
        return out

    def list_grouped(self) -> Dict[str, List[Dict[str, Any]]]:
        init_db()
        with get_cursor() as cur:
            rows = cur.execute(
                '''
                SELECT project_id, payload FROM project_versions
                ORDER BY project_id ASC, updated_at ASC, version_id ASC
                '''
            ).fetchall()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            pid = str(row[0] or '').strip()
            if not pid:
                continue
            try:
                payload = json.loads(row[1])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if not isinstance(payload, dict):
                continue
            grouped.setdefault(pid, []).append(payload)
        return grouped

    def save(self, version_id: str, project_id: str, payload: Dict[str, Any]) -> None:
        vid = str(version_id or payload.get('id') or '').strip()
        pid = str(project_id or '').strip()
        if not vid or not pid:
            raise ValueError('version_id and project_id are required')
        body = dict(payload or {})
        body['id'] = vid
        now = datetime.now().isoformat()
        init_db()
        with get_cursor() as cur:
            cur.execute(
                '''
                INSERT INTO project_versions (version_id, project_id, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(version_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                ''',
                (vid, pid, json.dumps(body, ensure_ascii=False), now),
            )
        self._mirror_all()

    def delete(self, version_id: str) -> None:
        vid = str(version_id or '').strip()
        if not vid:
            return
        init_db()
        with get_cursor() as cur:
            cur.execute('DELETE FROM project_versions WHERE version_id=?', (vid,))
        self._mirror_all()

    def delete_project(self, project_id: str) -> None:
        pid = str(project_id or '').strip()
        if not pid:
            return
        init_db()
        with get_cursor() as cur:
            cur.execute('DELETE FROM project_versions WHERE project_id=?', (pid,))
        self._mirror_all()

    def replace_project(self, project_id: str, versions: List[Dict[str, Any]]) -> None:
        pid = str(project_id or '').strip()
        if not pid:
            return
        now = datetime.now().isoformat()
        init_db()
        with get_cursor() as cur:
            cur.execute('DELETE FROM project_versions WHERE project_id=?', (pid,))
            if isinstance(versions, list):
                for index, item in enumerate(versions):
                    if not isinstance(item, dict):
                        continue
                    vid = _version_row_id(pid, item, index)
                    body = dict(item)
                    if not str(body.get('id') or '').strip():
                        body['id'] = vid.split('::', 1)[-1]
                    cur.execute(
                        '''
                        INSERT INTO project_versions (version_id, project_id, payload, updated_at)
                        VALUES (?, ?, ?, ?)
                        ''',
                        (vid, pid, json.dumps(body, ensure_ascii=False), now),
                    )
        self._mirror_all()

    def replace_all(self, grouped: Dict[str, List[Dict[str, Any]]]) -> None:
        now = datetime.now().isoformat()
        init_db()
        with get_cursor() as cur:
            cur.execute('DELETE FROM project_versions')
            if isinstance(grouped, dict):
                for project_id, versions in grouped.items():
                    pid = str(project_id or '').strip()
                    if not pid or not isinstance(versions, list):
                        continue
                    for index, item in enumerate(versions):
                        if not isinstance(item, dict):
                            continue
                        vid = _version_row_id(pid, item, index)
                        body = dict(item)
                        body['id'] = vid
                        cur.execute(
                            '''
                            INSERT INTO project_versions (version_id, project_id, payload, updated_at)
                            VALUES (?, ?, ?, ?)
                            ''',
                            (vid, pid, json.dumps(body, ensure_ascii=False), now),
                        )
        self._mirror_all()

    def _mirror_all(self) -> None:
        import os

        from config import DATA_DIR

        write_json_mirror(os.path.join(DATA_DIR, 'project_versions.json'), self.list_grouped())


def get_version_row_repository() -> VersionRowRepository:
    global _shared
    if _shared is None:
        _shared = VersionRowRepository()
    return _shared
