# -*- coding: utf-8 -*-
"""Project registry repository backed by SQLite. Plan P0-02 Step 1."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from repositories.registry._db import get_cursor, init_db
from repositories.registry._mirror import write_json_mirror

_shared: Optional['ProjectRepository'] = None


class ProjectRepository:
    """CRUD for project records stored in the projects table."""

    def get(self, project_id: str) -> Optional[Dict[str, Any]]:
        pid = str(project_id or '').strip()
        if not pid:
            return None
        init_db()
        with get_cursor() as cur:
            row = cur.execute(
                'SELECT payload FROM projects WHERE project_id=?',
                (pid,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def list(self) -> Dict[str, Dict[str, Any]]:
        init_db()
        with get_cursor() as cur:
            rows = cur.execute(
                'SELECT project_id, payload FROM projects ORDER BY project_id'
            ).fetchall()
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            pid = str(row[0] or '').strip()
            if not pid:
                continue
            try:
                payload = json.loads(row[1])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            out[pid] = payload if isinstance(payload, dict) else {}
        return out

    def save(self, project_id: str, payload: Dict[str, Any]) -> None:
        pid = str(project_id or '').strip()
        if not pid:
            raise ValueError('project_id is required')
        body = payload if isinstance(payload, dict) else {}
        now = datetime.now().isoformat()
        init_db()
        with get_cursor() as cur:
            cur.execute(
                '''
                INSERT INTO projects (project_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                ''',
                (pid, json.dumps(body, ensure_ascii=False), now),
            )
        self._mirror_all()

    def delete(self, project_id: str) -> None:
        pid = str(project_id or '').strip()
        if not pid:
            return
        init_db()
        with get_cursor() as cur:
            cur.execute('DELETE FROM projects WHERE project_id=?', (pid,))
        self._mirror_all()

    def replace_all(self, projects: Dict[str, Dict[str, Any]]) -> None:
        now = datetime.now().isoformat()
        init_db()
        with get_cursor() as cur:
            cur.execute('DELETE FROM projects')
            if isinstance(projects, dict):
                for project_id, payload in projects.items():
                    pid = str(project_id or '').strip()
                    if not pid:
                        continue
                    body = payload if isinstance(payload, dict) else {}
                    cur.execute(
                        'INSERT INTO projects (project_id, payload, updated_at) VALUES (?, ?, ?)',
                        (pid, json.dumps(body, ensure_ascii=False), now),
                    )
        self._mirror_all()

    def _mirror_all(self) -> None:
        import os

        from config import DATA_DIR

        write_json_mirror(os.path.join(DATA_DIR, 'projects.json'), self.list())


def get_project_repository() -> ProjectRepository:
    global _shared
    if _shared is None:
        _shared = ProjectRepository()
    return _shared
