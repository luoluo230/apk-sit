# -*- coding: utf-8 -*-
"""Channel registry repository backed by SQLite. Plan P0-02 Step 1."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from data._store import CHANNELS_FILE
from repositories.registry._db import get_cursor, init_db
from repositories.registry._mirror import write_json_mirror

_shared: Optional['ChannelRepository'] = None


class ChannelRepository:
    """CRUD for channel records stored in the channels table."""

    def get(self, channel_id: str) -> Optional[Dict[str, Any]]:
        cid = str(channel_id or '').strip()
        if not cid:
            return None
        init_db()
        with get_cursor() as cur:
            row = cur.execute(
                'SELECT payload FROM channels WHERE channel_id=?',
                (cid,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def list(self) -> List[Dict[str, Any]]:
        init_db()
        with get_cursor() as cur:
            rows = cur.execute(
                'SELECT payload FROM channels ORDER BY channel_id'
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row[0])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict):
                out.append(payload)
        out.sort(key=lambda item: (int(item.get('order') or 0), str(item.get('id') or '')))
        return out

    def save(self, channel_id: str, payload: Dict[str, Any]) -> None:
        cid = str(channel_id or payload.get('id') or '').strip()
        if not cid:
            raise ValueError('channel_id is required')
        body = dict(payload or {})
        body['id'] = cid
        now = datetime.now().isoformat()
        init_db()
        with get_cursor() as cur:
            cur.execute(
                '''
                INSERT INTO channels (channel_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                ''',
                (cid, json.dumps(body, ensure_ascii=False), now),
            )
        self._mirror_all()

    def delete(self, channel_id: str) -> None:
        cid = str(channel_id or '').strip()
        if not cid:
            return
        init_db()
        with get_cursor() as cur:
            cur.execute('DELETE FROM channels WHERE channel_id=?', (cid,))
        self._mirror_all()

    def replace_all(self, channels: List[Dict[str, Any]]) -> None:
        now = datetime.now().isoformat()
        init_db()
        with get_cursor() as cur:
            cur.execute('DELETE FROM channels')
            if isinstance(channels, list):
                for item in channels:
                    if not isinstance(item, dict):
                        continue
                    cid = str(item.get('id') or '').strip()
                    if not cid:
                        continue
                    cur.execute(
                        'INSERT INTO channels (channel_id, payload, updated_at) VALUES (?, ?, ?)',
                        (cid, json.dumps(item, ensure_ascii=False), now),
                    )
        self._mirror_all()

    def _mirror_all(self) -> None:
        import os

        from config import DATA_DIR

        write_json_mirror(os.path.join(DATA_DIR, 'channels.json'), self.list())


def get_channel_repository() -> ChannelRepository:
    global _shared
    if _shared is None:
        _shared = ChannelRepository()
    return _shared
