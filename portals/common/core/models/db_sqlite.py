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
_local = threading.local()
# Per-thread SQLite connections (WAL). Replaces global _conn — avoids SIGSEGV under Waitress.
_db_lock = threading.RLock()
_schema_initialized = False


def _get_conn():
    conn = getattr(_local, 'conn', None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA journal_mode=WAL')
        except sqlite3.Error:
            pass
        _local.conn = conn
    return conn


def reset_db_connection(close_all: bool = False) -> None:
    """Close thread-local DB handle (tests / worker recycle)."""
    global _schema_initialized
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
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
    except sqlite3.Error:
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS baas_services (
                    service_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    env_key TEXT NOT NULL DEFAULT 'development',
                    name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    feature_flags TEXT DEFAULT '{}',
                    api_secret_hash TEXT DEFAULT '',
                    config_version INTEGER DEFAULT 1,
                    created_by TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_baas_services_project ON baas_services(project_id, env_key);

                CREATE TABLE IF NOT EXISTS baas_feature_configs (
                    service_id TEXT NOT NULL,
                    feature_key TEXT NOT NULL,
                    config_json TEXT DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, feature_key)
                );

                CREATE TABLE IF NOT EXISTS baas_players (
                    player_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    auth_provider TEXT NOT NULL DEFAULT 'guest',
                    external_id TEXT NOT NULL DEFAULT '',
                    display_name TEXT DEFAULT '',
                    profile_json TEXT DEFAULT '{}',
                    token TEXT NOT NULL DEFAULT '',
                    token_expires_at TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_baas_players_service ON baas_players(service_id, external_id);

                CREATE TABLE IF NOT EXISTS baas_player_data (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    data_key TEXT NOT NULL,
                    value_json TEXT DEFAULT 'null',
                    version INTEGER DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id, data_key)
                );

                CREATE TABLE IF NOT EXISTS baas_announcements (
                    announcement_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    body TEXT DEFAULT '',
                    audience TEXT DEFAULT 'all',
                    effective_at TEXT DEFAULT '',
                    expires_at TEXT DEFAULT '',
                    status TEXT DEFAULT 'draft',
                    created_by TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS baas_mail_messages (
                    mail_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    body TEXT DEFAULT '',
                    attachments_json TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'unread',
                    created_by TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    claimed_at TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS baas_leaderboard_scores (
                    service_id TEXT NOT NULL,
                    board_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    display_name TEXT DEFAULT '',
                    score REAL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, board_id, player_id)
                );

                CREATE TABLE IF NOT EXISTS baas_wallets (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    currency_id TEXT NOT NULL,
                    balance INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id, currency_id)
                );

                CREATE TABLE IF NOT EXISTS baas_shop_orders (
                    order_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    price INTEGER DEFAULT 0,
                    currency_id TEXT DEFAULT 'gold',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS baas_player_achievements (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    achievement_id TEXT NOT NULL,
                    status TEXT DEFAULT 'locked',
                    progress INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    claimed_at TEXT DEFAULT '',
                    PRIMARY KEY (service_id, player_id, achievement_id)
                );

                CREATE TABLE IF NOT EXISTS baas_gift_redemptions (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    rewards_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id, code)
                );

                CREATE TABLE IF NOT EXISTS baas_guilds (
                    guild_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    leader_player_id TEXT NOT NULL,
                    member_count INTEGER DEFAULT 1,
                    payload_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS baas_guild_members (
                    guild_id TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    role TEXT DEFAULT 'member',
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id)
                );

                CREATE TABLE IF NOT EXISTS baas_battlepass_progress (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    season_id TEXT NOT NULL,
                    level INTEGER DEFAULT 1,
                    xp INTEGER DEFAULT 0,
                    premium INTEGER DEFAULT 0,
                    claimed_levels_json TEXT DEFAULT '[]',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (service_id, player_id, season_id)
                );

                CREATE TABLE IF NOT EXISTS baas_periodic_tasks (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_type TEXT DEFAULT 'daily',
                    progress INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    updated_at TEXT NOT NULL,
                    claimed_at TEXT DEFAULT '',
                    PRIMARY KEY (service_id, player_id, task_id)
                );

                CREATE TABLE IF NOT EXISTS baas_compliance_sessions (
                    service_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    last_heartbeat_at TEXT NOT NULL,
                    total_minutes INTEGER DEFAULT 0,
                    payload_json TEXT DEFAULT '{}',
                    PRIMARY KEY (service_id, player_id)
                );
                """
            )
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
        if not _migration_applied(conn, "baas_services_v2"):
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(baas_services)").fetchall()}
            if "description" not in cols:
                conn.execute("ALTER TABLE baas_services ADD COLUMN description TEXT DEFAULT ''")
            if "icon_url" not in cols:
                conn.execute("ALTER TABLE baas_services ADD COLUMN icon_url TEXT DEFAULT ''")
            if "disabled" not in cols:
                conn.execute("ALTER TABLE baas_services ADD COLUMN disabled INTEGER DEFAULT 0")
            _mark_migration(conn, "baas_services_v2")
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
