# -*- coding: utf-8 -*-
"""PostgreSQL 数据层 (P0-02 Step 6)."""

import json
import os
import re

import threading

import psycopg2

from contextlib import contextmanager
from datetime import datetime

import os

from config import DATA_DIR

DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_PATH = os.path.join(DATA_DIR, 'apk_site.db')  # compat for tests referencing path
_local = threading.local()
# Per-thread SQLite connections (WAL). Replaces global _conn — avoids SIGSEGV under Waitress.
_db_lock = threading.RLock()
_schema_initialized = False


class _PGRow:
    """Tuple + dict row access (sqlite3.Row compatible)."""

    __slots__ = ("_cols", "_vals", "_dict")

    def __init__(self, description, values):
        self._cols = [d[0] for d in description] if description else []
        self._vals = tuple(values) if values is not None else ()
        self._dict = dict(zip(self._cols, self._vals))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._dict[key]

    def keys(self):
        return self._dict.keys()

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def __contains__(self, key):
        return key in self._dict

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


def _get_conn():
    conn = getattr(_local, 'conn', None)
    if conn is None:
        if not DATABASE_URL:
            raise RuntimeError('DATABASE_URL is required for PostgreSQL backend')
        raw = psycopg2.connect(DATABASE_URL)
        conn = _PGConn(raw)
        _local.conn = conn
    return conn


class _PGCursor:
    def __init__(self, cur):
        self._cur = cur

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def execute(self, sql, params=None):
        sql = _translate_sql(sql)
        if params is None:
            self._cur.execute(sql)
        else:
            self._cur.execute(sql, params)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return _PGRow(self._cur.description, row)

    def fetchall(self):
        desc = self._cur.description
        return [_PGRow(desc, row) for row in self._cur.fetchall()]


class _PGConn:
    def __init__(self, raw):
        self._raw = raw

    def cursor(self):
        return _PGCursor(self._raw.cursor())

    def execute(self, sql, params=()):
        sql = _translate_sql(sql)
        cur = self._raw.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        if not sql.lstrip().upper().startswith("SELECT"):
            self._raw.commit()
        return _PGCursor(cur)

    def executemany(self, sql, seq):
        sql = _translate_sql(sql)
        cur = self._raw.cursor()
        try:
            cur.executemany(sql, seq)
            self._raw.commit()
        finally:
            cur.close()

    def executescript(self, script):
        cur = self._raw.cursor()
        try:
            for stmt in _split_sql_script(script):
                stmt = _translate_sql(stmt)
                if stmt.strip():
                    cur.execute(stmt)
            self._raw.commit()
        finally:
            cur.close()

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def _split_sql_script(script: str):
    return [part.strip() for part in script.split(";") if part.strip()]


def _translate_sql(sql: str) -> str:
    s = sql.strip()
    m = re.match(r"PRAGMA\s+table_info\s*\(\s*([^\)]+)\s*\)", s, re.I)
    if m:
        tbl = m.group(1).strip().strip("'\"")
        return (
            "SELECT column_name AS name FROM information_schema.columns "
            f"WHERE table_schema = current_schema() AND table_name = '{tbl}'"
        )
    if s.upper().startswith("PRAGMA"):
        return "SELECT 1"
    s = s.replace("?", "%s")
    s = re.sub(
        r"INTEGER PRIMARY KEY AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        s,
        flags=re.I,
    )
    had_ignore = bool(re.search(r"INSERT OR IGNORE INTO", sql, re.I))
    s = re.sub(
        r"INSERT OR IGNORE INTO",
        "INSERT INTO",
        s,
        flags=re.I,
    )
    if had_ignore and " ON CONFLICT " not in s.upper():
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    s = s.replace("sqlite_master", "information_schema.tables")
    s = _quote_pg_reserved_identifiers(s)
    return s


def _quote_pg_reserved_identifiers(sql: str) -> str:
    s = sql
    for col in ("user", "desc"):
        s = re.sub(
            rf"(?m)^(\s+){col}(\s+(?:TEXT|INTEGER|INT|REAL|DEFAULT|NOT NULL))",
            rf'\1"{col}"\2',
            s,
            flags=re.I,
        )
    s = s.replace("(tenant_id, timestamp, user, action", '(tenant_id, timestamp, "user", action')
    s = s.replace(" AND user=", ' AND "user"=')
    return s



def reset_db_connection(close_all: bool = False) -> None:
    """Close thread-local DB handle (tests / worker recycle)."""
    global _schema_initialized
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _local.conn = None
    if close_all:
        _schema_initialized = False


def _release_scope_platforms():
    from data.platforms import VALID_PLATFORMS

    preferred = ('android', 'ios', 'wechat_minigame')
    return tuple(p for p in preferred if p in VALID_PLATFORMS) or ('android', 'ios')


def _is_scope_platform(plat: str) -> bool:
    return str(plat or '').strip().lower() in set(_release_scope_platforms())


def _bundle_platform(row) -> str:
    plat = str(row["platform"] or "").strip().lower() if "platform" in row.keys() else ""
    if _is_scope_platform(plat):
        return plat
    try:
        payload = json.loads(row["payload"] or "{}")
        client = payload.get("client") if isinstance(payload.get("client"), dict) else {}
        plat = str(client.get("platform") or "android").strip().lower()
    except (TypeError, json.JSONDecodeError, AttributeError):
        plat = "android"
    return plat if _is_scope_platform(plat) else "android"


def _migration_applied(conn, name: str) -> bool:
    try:
        row = conn.execute('SELECT 1 FROM schema_migrations WHERE name=?', (name,)).fetchone()
        return bool(row)
    except Exception:
        return False


def _mark_migration(conn, name: str) -> None:
    conn.execute(
        'INSERT OR IGNORE INTO schema_migrations (name, applied_at) VALUES (?, ?)',
        (name, datetime.now().isoformat()),
    )


def _migrate_release_scopes_platform(conn) -> None:
    """Split legacy env×channel scopes into env×channel×platform scopes."""
    rows = conn.execute("SELECT scope_id, platform FROM release_scopes").fetchall()
    legacy_ids = []
    for row in rows:
        sid = str(row["scope_id"] or "")
        parts = [p for p in sid.split(":") if p]
        if len(parts) == 3:
            legacy_ids.append(sid)
        elif len(parts) == 4 and parts[3] in set(_release_scope_platforms()) and not str(row["platform"] or "").strip():
            conn.execute("UPDATE release_scopes SET platform=? WHERE scope_id=?", (parts[3], sid))
    if not legacy_ids:
        return
    now = datetime.now().isoformat()
    migrated = set()
    for sid in legacy_ids:
        if sid in migrated:
            continue
        migrated.add(sid)
        row = conn.execute("SELECT * FROM release_scopes WHERE scope_id=?", (sid,)).fetchone()
        if not row:
            continue
        parts = [p for p in sid.split(":") if p]
        slug, env_key, channel_id = parts[0], parts[1], parts[2]
        active_by_platform = {plat: "" for plat in _release_scope_platforms()}
        bundles = conn.execute(
            "SELECT bundle_id, platform, payload, publish_status FROM release_bundles WHERE scope_id=?",
            (sid,),
        ).fetchall()
        for bundle in bundles:
            plat = _bundle_platform(bundle)
            if str(bundle["publish_status"] or "") == "published":
                active_by_platform[plat] = str(bundle["bundle_id"] or "")
        legacy_active = str(row["active_bundle_id"] or "").strip()
        if legacy_active and not any(active_by_platform.values()):
            for bundle in bundles:
                if str(bundle["bundle_id"] or "") == legacy_active:
                    active_by_platform[_bundle_platform(bundle)] = legacy_active
                    break
            if not any(active_by_platform.values()):
                active_by_platform["android"] = legacy_active
        for plat in _release_scope_platforms():
            new_sid = f"{slug}:{env_key}:{channel_id}:{plat}"
            conn.execute(
                """
                INSERT INTO release_scopes (
                    scope_id, project_id, env_key, channel_id, channel_key, platform,
                    default_topology_id, active_bundle_id, status, payload, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(scope_id) DO UPDATE SET
                    platform=excluded.platform,
                    active_bundle_id=CASE
                        WHEN excluded.active_bundle_id != '' THEN excluded.active_bundle_id
                        ELSE release_scopes.active_bundle_id
                    END,
                    updated_at=excluded.updated_at
                """,
                (
                    new_sid,
                    row["project_id"],
                    env_key,
                    channel_id,
                    row["channel_key"],
                    plat,
                    row["default_topology_id"],
                    active_by_platform[plat],
                    row["status"],
                    row["payload"],
                    row["created_at"],
                    now,
                ),
            )
        for bundle in bundles:
            plat = _bundle_platform(bundle)
            new_sid = f"{slug}:{env_key}:{channel_id}:{plat}"
            conn.execute(
                "UPDATE release_bundles SET scope_id=? WHERE bundle_id=?",
                (new_sid, bundle["bundle_id"]),
            )
        for order in conn.execute(
            "SELECT release_order_id, platform FROM release_orders WHERE scope_id=?",
            (sid,),
        ).fetchall():
            plat = str(order["platform"] or "android").strip().lower()
            if not _is_scope_platform(plat):
                plat = "android"
            new_sid = f"{slug}:{env_key}:{channel_id}:{plat}"
            conn.execute(
                "UPDATE release_orders SET scope_id=? WHERE release_order_id=?",
                (new_sid, order["release_order_id"]),
            )
        conn.execute("DELETE FROM release_scopes WHERE scope_id=?", (sid,))


def _load_legacy_json_file(filename: str, default=None):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            return json.load(fp)
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _read_json_document_row(conn, document_key, default=None):
    row = conn.execute(
        'SELECT payload FROM json_documents WHERE document_key=?',
        (document_key,),
    ).fetchone()
    if not row:
        return default
    try:
        return json.loads(row['payload'])
    except (TypeError, json.JSONDecodeError):
        return default


def _migrate_config_registry(conn) -> None:
    """Seed typed registry tables from json_documents or legacy JSON files. Plan P0-02."""
    now = datetime.now().isoformat()

    project_count = conn.execute('SELECT COUNT(*) AS cnt FROM projects').fetchone()
    if int(project_count['cnt'] if project_count else 0) == 0:
        projects_data = _read_json_document_row(conn, 'data/projects.json', None)
        if projects_data is None:
            projects_data = _load_legacy_json_file('projects.json', {})
        if isinstance(projects_data, dict):
            for project_id, payload in projects_data.items():
                pid = str(project_id or '').strip()
                if not pid:
                    continue
                body = payload if isinstance(payload, dict) else {}
                conn.execute(
                    'INSERT OR IGNORE INTO projects (project_id, payload, updated_at) VALUES (?, ?, ?)',
                    (pid, json.dumps(body, ensure_ascii=False), now),
                )
        if conn.execute('SELECT COUNT(*) AS cnt FROM projects').fetchone()['cnt'] == 0:
            default_project = {
                'name': '垃圾回收站',
                'description': '垃圾回收站游戏',
                'created_at': now,
                'order': 1,
                'status': 'active',
            }
            conn.execute(
                'INSERT OR IGNORE INTO projects (project_id, payload, updated_at) VALUES (?, ?, ?)',
                ('RecycleTycoon', json.dumps(default_project, ensure_ascii=False), now),
            )

    channel_count = conn.execute('SELECT COUNT(*) AS cnt FROM channels').fetchone()
    if int(channel_count['cnt'] if channel_count else 0) == 0:
        channels_data = _read_json_document_row(conn, 'data/channels.json', None)
        if channels_data is None:
            channels_data = _load_legacy_json_file('channels.json', [])
        if isinstance(channels_data, list):
            for item in channels_data:
                if not isinstance(item, dict):
                    continue
                cid = str(item.get('id') or '').strip()
                if not cid:
                    continue
                conn.execute(
                    'INSERT OR IGNORE INTO channels (channel_id, payload, updated_at) VALUES (?, ?, ?)',
                    (cid, json.dumps(item, ensure_ascii=False), now),
                )
        if conn.execute('SELECT COUNT(*) AS cnt FROM channels').fetchone()['cnt'] == 0:
            for item in (
                {'id': 'dev', 'name': '开发版', 'description': '内部开发、自测使用', 'order': 10, 'apk_subdir': 'dev', 'build_param': 'CHANNEL=dev'},
                {'id': 'test', 'name': '测试版', 'description': '功能联调、提测与回归测试使用', 'order': 20, 'apk_subdir': 'test', 'build_param': 'CHANNEL=test'},
                {'id': 'production', 'name': '线上版', 'description': '正式对外发布给用户的版本', 'order': 30, 'apk_subdir': '', 'build_param': 'CHANNEL=production'},
            ):
                cid = str(item.get('id') or '').strip()
                conn.execute(
                    'INSERT OR IGNORE INTO channels (channel_id, payload, updated_at) VALUES (?, ?, ?)',
                    (cid, json.dumps(item, ensure_ascii=False), now),
                )

    version_count = conn.execute('SELECT COUNT(*) AS cnt FROM project_versions').fetchone()
    if int(version_count['cnt'] if version_count else 0) == 0:
        versions_data = _read_json_document_row(conn, 'data/project_versions.json', None)
        if versions_data is None:
            versions_data = _load_legacy_json_file('project_versions.json', {})
        if isinstance(versions_data, dict):
            for project_id, rows in versions_data.items():
                pid = str(project_id or '').strip()
                if not pid or not isinstance(rows, list):
                    continue
                for index, item in enumerate(rows):
                    if not isinstance(item, dict):
                        continue
                    vid = str(item.get('id') or '').strip()
                    if not vid:
                        vn = str(item.get('version_name') or '').strip()
                        vc = str(item.get('version_code') or '').strip()
                        vid = (
                            f"{pid}:{vn}:{vc}:{index}"
                            if (vn or vc)
                            else f"{pid}:row:{index}"
                        )
                    body = dict(item)
                    body['id'] = vid
                    conn.execute(
                        'INSERT OR IGNORE INTO project_versions (version_id, project_id, payload, updated_at) VALUES (?, ?, ?, ?)',
                        (vid, pid, json.dumps(body, ensure_ascii=False), now),
                    )


def init_db():
    global _schema_initialized
    with _db_lock:
        if _schema_initialized:
            return
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
            platform TEXT DEFAULT '',
            default_topology_id TEXT DEFAULT '',
            active_bundle_id TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            payload TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_release_scope_target
            ON release_scopes(project_id, env_key, channel_id, platform);

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

        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_versions (
            version_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_project_versions_project
            ON project_versions(project_id);

        CREATE TABLE IF NOT EXISTS infra_nodes (
            node_id TEXT PRIMARY KEY,
            project_id TEXT DEFAULT '',
            role TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            host TEXT DEFAULT '',
            port INTEGER DEFAULT 0,
            jenkins_label TEXT DEFAULT '',
            jenkins_instance_id TEXT DEFAULT '',
            capabilities TEXT DEFAULT '{}',
            agent_ws_url TEXT DEFAULT '',
            status TEXT DEFAULT 'unknown',
            last_heartbeat_at TEXT DEFAULT '',
            payload TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_infra_nodes_role ON infra_nodes(role);
        CREATE INDEX IF NOT EXISTS idx_infra_nodes_project ON infra_nodes(project_id);
        CREATE INDEX IF NOT EXISTS idx_infra_nodes_status ON infra_nodes(status);

        CREATE TABLE IF NOT EXISTS server_artifacts (
            artifact_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            version_label TEXT DEFAULT '',
            bundle_path TEXT DEFAULT '',
            checksum TEXT DEFAULT '',
            protocol_version TEXT DEFAULT '',
            payload TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_server_artifacts_project ON server_artifacts(project_id);

        CREATE TABLE IF NOT EXISTS server_release_orders (
            server_release_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            env_key TEXT NOT NULL,
            topology_id TEXT NOT NULL,
            artifact_id TEXT DEFAULT '',
            status TEXT NOT NULL,
            target_services TEXT DEFAULT '[]',
            payload TEXT DEFAULT '{}',
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_server_release_project ON server_release_orders(project_id, env_key);
        CREATE INDEX IF NOT EXISTS idx_server_release_status ON server_release_orders(status);
        '''
        )
        scope_columns = {row["name"] for row in conn.execute("PRAGMA table_info(release_scopes)").fetchall()}
        if "active_bundle_id" not in scope_columns:
            conn.execute("ALTER TABLE release_scopes ADD COLUMN active_bundle_id TEXT DEFAULT ''")
        if "platform" not in scope_columns:
            conn.execute("ALTER TABLE release_scopes ADD COLUMN platform TEXT DEFAULT ''")
        conn.execute("DROP INDEX IF EXISTS idx_release_scope_target")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_release_scope_target "
            "ON release_scopes(project_id, env_key, channel_id, platform)"
        )
        _migrate_config_registry(conn)
        if not _migration_applied(conn, 'release_scopes_platform_v2'):
            _migrate_release_scopes_platform(conn)
            _mark_migration(conn, 'release_scopes_platform_v2')
        binding_columns = {row["name"] for row in conn.execute("PRAGMA table_info(topology_bindings)").fetchall()}
        if "platform" not in binding_columns:
            conn.execute("ALTER TABLE topology_bindings ADD COLUMN platform TEXT DEFAULT ''")
        conn.execute("DROP INDEX IF EXISTS idx_topology_binding_target")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_topology_binding_target "
            "ON topology_bindings(project_id, env_key, channel_id, platform, version_name)"
        )
        if not _migration_applied(conn, "release_batches_v1"):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS release_batches (
                    batch_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    env_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    shared_plan TEXT DEFAULT '{}',
                    line_targets TEXT DEFAULT '[]',
                    announcement TEXT DEFAULT '{}',
                    created_by TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_release_batches_project
                    ON release_batches(project_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS release_batch_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT DEFAULT '',
                    to_status TEXT DEFAULT '',
                    actor TEXT DEFAULT '',
                    payload TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_release_batch_events_batch
                    ON release_batch_events(batch_id, created_at);
                """
            )
            order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(release_orders)").fetchall()}
            if "batch_id" not in order_columns:
                conn.execute("ALTER TABLE release_orders ADD COLUMN batch_id TEXT DEFAULT ''")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_release_order_batch ON release_orders(batch_id)"
                )
            _mark_migration(conn, "release_batches_v1")
        if not _migration_applied(conn, "baas_services_v1"):
            from models.baas_migrations import BAAS_SERVICES_V1_SQL

            conn.executescript(BAAS_SERVICES_V1_SQL)
            _mark_migration(conn, "baas_services_v1")
        if not _migration_applied(conn, "baas_gm_v1"):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS baas_gift_codes (
                    service_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    rewards_json TEXT DEFAULT '[]',
                    max_uses INTEGER DEFAULT 0,
                    use_count INTEGER DEFAULT 0,
                    expires_at TEXT DEFAULT '',
                    created_by TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, code)
                );
                """
            )
            _mark_migration(conn, "baas_gm_v1")
        if not _migration_applied(conn, "baas_gm_v2"):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS baas_player_bans (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    expires_at TEXT DEFAULT '',
                    created_by TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id)
                );
                CREATE TABLE IF NOT EXISTS baas_ip_bans (
                    service_id TEXT NOT NULL,
                    ip_pattern TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    expires_at TEXT DEFAULT '',
                    created_by TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, ip_pattern)
                );
                CREATE TABLE IF NOT EXISTS baas_activities (
                    activity_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    activity_type TEXT DEFAULT 'event',
                    starts_at TEXT DEFAULT '',
                    ends_at TEXT DEFAULT '',
                    gates_json TEXT DEFAULT '{}',
                    payload_json TEXT DEFAULT '{}',
                    status TEXT DEFAULT 'draft',
                    created_by TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            gift_cols = {row["name"] for row in conn.execute("PRAGMA table_info(baas_gift_codes)").fetchall()}
            if "code_type" not in gift_cols:
                conn.execute("ALTER TABLE baas_gift_codes ADD COLUMN code_type TEXT DEFAULT 'shared'")
            if "per_player_limit" not in gift_cols:
                conn.execute("ALTER TABLE baas_gift_codes ADD COLUMN per_player_limit INTEGER DEFAULT 1")
            if "assigned_player_id" not in gift_cols:
                conn.execute("ALTER TABLE baas_gift_codes ADD COLUMN assigned_player_id TEXT DEFAULT ''")
            if "meta_json" not in gift_cols:
                conn.execute("ALTER TABLE baas_gift_codes ADD COLUMN meta_json TEXT DEFAULT '{}'")
            ann_cols = {row["name"] for row in conn.execute("PRAGMA table_info(baas_announcements)").fetchall()}
            if "display_type" not in ann_cols:
                conn.execute("ALTER TABLE baas_announcements ADD COLUMN display_type TEXT DEFAULT 'login'")
            if "priority" not in ann_cols:
                conn.execute("ALTER TABLE baas_announcements ADD COLUMN priority INTEGER DEFAULT 0")
            mail_cols = {row["name"] for row in conn.execute("PRAGMA table_info(baas_mail_messages)").fetchall()}
            if "body_links_json" not in mail_cols:
                conn.execute("ALTER TABLE baas_mail_messages ADD COLUMN body_links_json TEXT DEFAULT '[]'")
            _mark_migration(conn, "baas_gm_v2")
        if not _migration_applied(conn, "baas_gift_redemptions_v3"):
            red_cols = {row["name"] for row in conn.execute("PRAGMA table_info(baas_gift_redemptions)").fetchall()}
            if red_cols and "redemption_id" not in red_cols:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS baas_gift_redemptions_v2 (
                        redemption_id TEXT PRIMARY KEY,
                        service_id TEXT NOT NULL,
                        player_id TEXT NOT NULL,
                        code TEXT NOT NULL,
                        rewards_json TEXT DEFAULT '[]',
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_baas_gift_redemptions_lookup
                        ON baas_gift_redemptions_v2(service_id, player_id, code);
                    INSERT OR IGNORE INTO baas_gift_redemptions_v2 (
                        redemption_id, service_id, player_id, code, rewards_json, created_at
                    )
                    SELECT service_id || ':' || player_id || ':' || code, service_id, player_id, code, rewards_json, created_at
                    FROM baas_gift_redemptions;
                    DROP TABLE baas_gift_redemptions;
                    ALTER TABLE baas_gift_redemptions_v2 RENAME TO baas_gift_redemptions;
                    """
                )
            _mark_migration(conn, "baas_gift_redemptions_v3")
        if not _migration_applied(conn, "baas_services_v2"):
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(baas_services)").fetchall()}
            if "description" not in cols:
                conn.execute("ALTER TABLE baas_services ADD COLUMN description TEXT DEFAULT ''")
            if "icon_url" not in cols:
                conn.execute("ALTER TABLE baas_services ADD COLUMN icon_url TEXT DEFAULT ''")
            if "disabled" not in cols:
                conn.execute("ALTER TABLE baas_services ADD COLUMN disabled INTEGER DEFAULT 0")
            _mark_migration(conn, "baas_services_v2")
        if not _migration_applied(conn, "baas_player_identity_aliases_v1"):
            from models.baas_migrations import (
                BAAS_PLAYER_IDENTITY_ALIASES_V1_SQL,
                backfill_guest_installation_aliases,
            )

            conn.executescript(BAAS_PLAYER_IDENTITY_ALIASES_V1_SQL)
            backfill_guest_installation_aliases(conn)
            _mark_migration(conn, "baas_player_identity_aliases_v1")
        if not _migration_applied(conn, "baas_rooms_v1"):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS baas_rooms (
                    room_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'waiting',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_baas_rooms_service_status
                    ON baas_rooms(service_id, status);
                CREATE TABLE IF NOT EXISTS baas_room_replays (
                    replay_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    room_id TEXT NOT NULL DEFAULT '',
                    battle_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_baas_room_replays_service
                    ON baas_room_replays(service_id, created_at);
                """
            )
            _mark_migration(conn, "baas_rooms_v1")
        if not _migration_applied(conn, "baas_pve_arena_v1"):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS baas_battles (
                    battle_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    battle_type TEXT NOT NULL DEFAULT 'pve',
                    stage_id TEXT NOT NULL DEFAULT '',
                    defender_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    seed INTEGER NOT NULL DEFAULT 0,
                    team_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL,
                    settled_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_baas_battles_player
                    ON baas_battles(service_id, player_id, status);
                CREATE TABLE IF NOT EXISTS baas_chapter_progress (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    stage_id TEXT NOT NULL,
                    stars INTEGER NOT NULL DEFAULT 0,
                    best_time_ms INTEGER NOT NULL DEFAULT 0,
                    cleared INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id, stage_id)
                );
                CREATE TABLE IF NOT EXISTS baas_player_snapshots (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    snapshot_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    power INTEGER NOT NULL DEFAULT 0,
                    display_name TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id, snapshot_type)
                );
                CREATE TABLE IF NOT EXISTS baas_arena_ratings (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    rating INTEGER NOT NULL DEFAULT 1000,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    daily_attempts_used INTEGER NOT NULL DEFAULT 0,
                    daily_reset_date TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id)
                );
                """
            )
            _mark_migration(conn, "baas_pve_arena_v1")
        if not _migration_applied(conn, "baas_pve_arena_v2"):
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(baas_battles)").fetchall()}
            if cols and "replay_hash" not in cols:
                conn.execute("ALTER TABLE baas_battles ADD COLUMN replay_hash TEXT NOT NULL DEFAULT ''")
            _mark_migration(conn, "baas_pve_arena_v2")
        if not _migration_applied(conn, "baas_afk_pack_v1"):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS baas_player_heroes (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    hero_id INTEGER NOT NULL,
                    level INTEGER NOT NULL DEFAULT 1,
                    exp INTEGER NOT NULL DEFAULT 0,
                    equipment_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (service_id, player_id, hero_id)
                );
                CREATE TABLE IF NOT EXISTS baas_gacha_state (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    pool_id TEXT NOT NULL,
                    pity_counter INTEGER NOT NULL DEFAULT 0,
                    total_pulls INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (service_id, player_id, pool_id)
                );
                CREATE TABLE IF NOT EXISTS baas_gacha_pulls (
                    pull_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    pool_id TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_baas_gacha_pulls_player
                    ON baas_gacha_pulls(service_id, player_id, created_at);
                CREATE TABLE IF NOT EXISTS baas_idle_state (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    last_claim_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (service_id, player_id)
                );
                CREATE TABLE IF NOT EXISTS baas_tower_progress (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    tower_id TEXT NOT NULL,
                    floor INTEGER NOT NULL DEFAULT 0,
                    best_stars INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (service_id, player_id, tower_id)
                );
                CREATE TABLE IF NOT EXISTS baas_iap_orders (
                    order_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT '',
                    receipt_hash TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    rewards_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT '',
                    verified_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_baas_iap_orders_player
                    ON baas_iap_orders(service_id, player_id, status);
                """
            )
            _mark_migration(conn, "baas_afk_pack_v1")
        if not _migration_applied(conn, "baas_phase2_v1"):
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS baas_player_inventory (
                    item_uid TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    item_def_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_baas_player_inventory_player
                    ON baas_player_inventory(service_id, player_id, item_def_id);
                CREATE TABLE IF NOT EXISTS baas_guild_war_entries (
                    service_id TEXT NOT NULL,
                    season_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    total_score INTEGER NOT NULL DEFAULT 0,
                    battles_won INTEGER NOT NULL DEFAULT 0,
                    battles_lost INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (service_id, season_id, guild_id)
                );
                CREATE TABLE IF NOT EXISTS baas_guild_war_matches (
                    match_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    season_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    win INTEGER NOT NULL DEFAULT 0,
                    score_delta INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_baas_guild_war_matches_guild
                    ON baas_guild_war_matches(service_id, season_id, guild_id, created_at);
                """
            )
            _mark_migration(conn, "baas_phase2_v1")
        if not _migration_applied(conn, "baas_afk_growth_v1"):
            hero_cols = {row["name"] for row in conn.execute("PRAGMA table_info(baas_player_heroes)").fetchall()}
            if hero_cols and "star" not in hero_cols:
                conn.execute("ALTER TABLE baas_player_heroes ADD COLUMN star INTEGER NOT NULL DEFAULT 1")
            if hero_cols and "shards" not in hero_cols:
                conn.execute("ALTER TABLE baas_player_heroes ADD COLUMN shards INTEGER NOT NULL DEFAULT 0")
            if hero_cols and "talent_points" not in hero_cols:
                conn.execute("ALTER TABLE baas_player_heroes ADD COLUMN talent_points INTEGER NOT NULL DEFAULT 0")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS baas_player_equipment (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    quality INTEGER NOT NULL DEFAULT 3,
                    enhance_level INTEGER NOT NULL DEFAULT 0,
                    refine_level INTEGER NOT NULL DEFAULT 0,
                    awaken INTEGER NOT NULL DEFAULT 0,
                    gem_count INTEGER NOT NULL DEFAULT 0,
                    affix_seed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (service_id, player_id, slot)
                );
                CREATE TABLE IF NOT EXISTS baas_dungeon_daily (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    dungeon_id TEXT NOT NULL,
                    run_date TEXT NOT NULL,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (service_id, player_id, dungeon_id, run_date)
                );
                CREATE TABLE IF NOT EXISTS baas_afk_solo_tower (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    floor INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (service_id, player_id)
                );
                """
            )
            _mark_migration(conn, "baas_afk_growth_v1")
        conn.commit()
        _schema_initialized = True


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
