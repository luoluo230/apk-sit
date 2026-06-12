# -*- coding: utf-8 -*-
"""SQLite 数据层。"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, 'apk_site.db')
_conn = None
# waitress 多线程 + 后台 scheduler 共用单连接时，无锁会触发 libsqlite3 SIGSEGV（exit 139）
_db_lock = threading.RLock()


def _get_conn():
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
        _conn.row_factory = sqlite3.Row
        try:
            _conn.execute('PRAGMA journal_mode=WAL')
        except sqlite3.Error:
            pass
    return _conn


def init_db():
    with _db_lock:
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

        -- Ops platform tables
        CREATE TABLE IF NOT EXISTS ops_agents (
            agent_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL DEFAULT '',
            device_id TEXT DEFAULT '',
            display_name TEXT DEFAULT '',
            host_ip TEXT DEFAULT '',
            port INTEGER DEFAULT 0,
            status TEXT DEFAULT 'OFFLINE',
            capabilities TEXT DEFAULT '[]',
            desc TEXT DEFAULT '',
            region TEXT DEFAULT '',
            last_heartbeat TEXT DEFAULT '',
            probe_status TEXT DEFAULT '',
            probe_ts TEXT DEFAULT '',
            meta TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ops_agents_project ON ops_agents(project_id);
        CREATE INDEX IF NOT EXISTS idx_ops_agents_status ON ops_agents(status);

        CREATE TABLE IF NOT EXISTS ops_agent_jobs (
            job_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL DEFAULT '',
            project_id TEXT DEFAULT '',
            action TEXT DEFAULT '',
            target TEXT DEFAULT '',
            status TEXT DEFAULT 'PENDING',
            params TEXT DEFAULT '{}',
            result TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            retries INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ops_jobs_agent ON ops_agent_jobs(agent_id);
        CREATE INDEX IF NOT EXISTS idx_ops_jobs_status ON ops_agent_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_ops_jobs_created ON ops_agent_jobs(created_at);

        CREATE TABLE IF NOT EXISTS ops_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL DEFAULT '',
            project_id TEXT DEFAULT '',
            scope TEXT DEFAULT '',
            message TEXT DEFAULT '',
            severity TEXT DEFAULT 'info',
            details TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ops_events_project ON ops_events(project_id);
        CREATE INDEX IF NOT EXISTS idx_ops_events_created ON ops_events(created_at);
        CREATE INDEX IF NOT EXISTS idx_ops_events_type ON ops_events(event_type);

        CREATE TABLE IF NOT EXISTS ops_runtime_runs (
            run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL DEFAULT '',
            env_key TEXT DEFAULT '',
            topology_id TEXT DEFAULT '',
            op TEXT NOT NULL DEFAULT '',
            status TEXT DEFAULT 'PENDING',
            nodes TEXT DEFAULT '[]',
            result TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ops_runs_project ON ops_runtime_runs(project_id);
        CREATE INDEX IF NOT EXISTS idx_ops_runs_status ON ops_runtime_runs(status);

        CREATE TABLE IF NOT EXISTS ops_topologies (
            topology_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL DEFAULT '',
            env_key TEXT DEFAULT 'production',
            name TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            is_default INTEGER DEFAULT 0,
            nodes TEXT DEFAULT '[]',
            edges TEXT DEFAULT '[]',
            meta TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ops_topo_project ON ops_topologies(project_id, env_key);

        -- Unified project delivery domain
        CREATE TABLE IF NOT EXISTS release_scopes (
            scope_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            env_key TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            channel_key TEXT DEFAULT '',
            default_topology_id TEXT DEFAULT '',
            active_bundle_id TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            payload TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_release_scope_target
            ON release_scopes(project_id, env_key, channel_id);

        CREATE TABLE IF NOT EXISTS release_bundles (
            bundle_id TEXT PRIMARY KEY,
            release_order_id TEXT DEFAULT '',
            project_id TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            env_key TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            publish_status TEXT NOT NULL,
            topology_id TEXT DEFAULT '',
            runtime_run_id TEXT DEFAULT '',
            version_name TEXT DEFAULT '',
            version_code TEXT DEFAULT '',
            platform TEXT DEFAULT '',
            payload TEXT NOT NULL,
            published_at TEXT DEFAULT '',
            published_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_release_bundle_scope
            ON release_bundles(scope_id, publish_status, published_at);
        CREATE INDEX IF NOT EXISTS idx_release_bundle_order
            ON release_bundles(release_order_id);

        CREATE TABLE IF NOT EXISTS topology_bindings (
            binding_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            env_key TEXT DEFAULT '',
            channel_id TEXT DEFAULT '',
            version_name TEXT DEFAULT '',
            topology_id TEXT NOT NULL,
            level TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            note TEXT DEFAULT '',
            payload TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_topology_binding_target
            ON topology_bindings(project_id, env_key, channel_id, version_name);

        CREATE TABLE IF NOT EXISTS release_orders (
            release_order_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            env_key TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            version_id TEXT NOT NULL,
            version_name TEXT NOT NULL,
            version_code TEXT NOT NULL,
            scope_id TEXT DEFAULT '',
            topology_id TEXT DEFAULT '',
            topology_binding_source TEXT DEFAULT '',
            runtime_run_id TEXT DEFAULT '',
            bundle_id TEXT DEFAULT '',
            status TEXT NOT NULL,
            reason TEXT DEFAULT '',
            payload TEXT DEFAULT '{}',
            created_by TEXT DEFAULT '',
            approved_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            published_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_release_order_project
            ON release_orders(project_id, env_key, channel_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_release_order_version
            ON release_orders(project_id, version_id);

        CREATE TABLE IF NOT EXISTS release_order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            release_order_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            from_status TEXT DEFAULT '',
            to_status TEXT DEFAULT '',
            actor TEXT DEFAULT '',
            payload TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_release_order_events_order
            ON release_order_events(release_order_id, created_at);

        CREATE TABLE IF NOT EXISTS release_order_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            release_order_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            artifact_url TEXT DEFAULT '',
            artifact_path TEXT DEFAULT '',
            status TEXT DEFAULT 'registered',
            payload TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_release_order_artifacts_order
            ON release_order_artifacts(release_order_id);

        CREATE TABLE IF NOT EXISTS release_order_prechecks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            release_order_id TEXT NOT NULL,
            ok INTEGER NOT NULL DEFAULT 0,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_release_order_prechecks_order
            ON release_order_prechecks(release_order_id, created_at);

        CREATE TABLE IF NOT EXISTS release_approvals (
            approval_id TEXT PRIMARY KEY,
            release_order_id TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_by TEXT DEFAULT '',
            approved_by TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_release_approvals_order
            ON release_approvals(release_order_id, created_at);
        '''
        )
        scope_columns = {row["name"] for row in conn.execute("PRAGMA table_info(release_scopes)").fetchall()}
        if "active_bundle_id" not in scope_columns:
            conn.execute("ALTER TABLE release_scopes ADD COLUMN active_bundle_id TEXT DEFAULT ''")
        conn.commit()


@contextmanager
def get_cursor():
    with _db_lock:
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
    with _db_lock:
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
    with _db_lock:
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
    with _db_lock:
        row = _get_conn().execute(
            'SELECT 1 FROM json_documents WHERE document_key=?',
            (document_key,)
        ).fetchone()
    return bool(row)


def list_json_documents():
    init_db()
    with _db_lock:
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
    with _db_lock:
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
