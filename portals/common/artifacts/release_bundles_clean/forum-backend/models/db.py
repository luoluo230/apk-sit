# -*- coding: utf-8 -*-
"""SQLite 数据层。"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, 'apk_site.db')
_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db():
    conn = _get_conn()
    conn.executescript(
        '''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT DEFAULT 'default',
            timestamp TEXT NOT NULL,
            user TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            ip TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);

        CREATE TABLE IF NOT EXISTS webhook_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT DEFAULT 'default',
            event_type TEXT NOT NULL,
            payload TEXT,
            url TEXT,
            status_code INT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS json_documents (
            document_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS request_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            path TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            duration_ms REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_request_events_created_at ON request_events(created_at);
        CREATE INDEX IF NOT EXISTS idx_request_events_path ON request_events(path);
        '''
    )
    conn.commit()


@contextmanager
def get_cursor():
    conn = _get_conn()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def log_audit_db(tenant_id, user, action, details, ip):
    init_db()
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO audit_log (tenant_id, timestamp, user, action, details, ip) VALUES (?,?,?,?,?,?)',
            (tenant_id or 'default', datetime.now().isoformat(), user, action, details or '', ip or '')
        )


def get_audit_log_from_db(limit=100, offset=0, tenant_id=None, action_filter=None, user_filter=None):
    init_db()
    conn = _get_conn()
    sql = 'SELECT * FROM audit_log WHERE 1=1'
    params = []
    if tenant_id:
        sql += ' AND tenant_id=?'
        params.append(tenant_id)
    if action_filter:
        sql += ' AND action=?'
        params.append(action_filter)
    if user_filter:
        sql += ' AND user=?'
        params.append(user_filter)
    sql += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def set_json_document(document_key, data):
    init_db()
    payload = json.dumps(data, ensure_ascii=False)
    with get_cursor() as cur:
        cur.execute(
            '''
            INSERT INTO json_documents (document_key, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(document_key)
            DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
            ''',
            (document_key, payload, datetime.now().isoformat())
        )


def get_json_document(document_key, default=None):
    init_db()
    row = _get_conn().execute(
        'SELECT payload FROM json_documents WHERE document_key=?',
        (document_key,)
    ).fetchone()
    if not row:
        return default
    try:
        return json.loads(row['payload'])
    except json.JSONDecodeError:
        return default


def has_json_document(document_key):
    init_db()
    row = _get_conn().execute(
        'SELECT 1 FROM json_documents WHERE document_key=?',
        (document_key,)
    ).fetchone()
    return bool(row)


def list_json_documents():
    init_db()
    rows = _get_conn().execute(
        'SELECT document_key, updated_at FROM json_documents ORDER BY document_key'
    ).fetchall()
    return [dict(r) for r in rows]


def delete_json_documents_by_prefix(prefix):
    """Delete JSON documents whose key starts with the given prefix."""
    init_db()
    with get_cursor() as cur:
        cur.execute(
            'SELECT COUNT(*) AS cnt FROM json_documents WHERE document_key LIKE ?',
            (f'{prefix}%',)
        )
        row = cur.fetchone()
        removed = int((row or {}).get('cnt') if isinstance(row, dict) else (row[0] if row else 0))
        cur.execute(
            'DELETE FROM json_documents WHERE document_key LIKE ?',
            (f'{prefix}%',)
        )
    return removed


def record_request_event(request_id, path, method, status_code, duration_ms):
    init_db()
    with get_cursor() as cur:
        cur.execute(
            '''
            INSERT INTO request_events (request_id, path, method, status_code, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                request_id or '',
                path or '',
                method or 'GET',
                int(status_code or 0),
                float(duration_ms or 0),
                datetime.now().isoformat(),
            )
        )


def get_request_event_summary(limit=200):
    init_db()
    rows = _get_conn().execute(
        '''
        SELECT path,
               COUNT(*) AS count,
               ROUND(AVG(duration_ms), 1) AS avg_ms,
               ROUND(MAX(duration_ms), 1) AS max_ms
        FROM (
            SELECT path, duration_ms
            FROM request_events
            ORDER BY id DESC
            LIMIT ?
        )
        GROUP BY path
        ORDER BY count DESC, avg_ms DESC
        ''',
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
