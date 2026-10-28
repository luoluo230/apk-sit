# -*- coding: utf-8 -*-
"""Concurrent registry read/write. Plan P0-02 Step 2/3."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import uuid

import pytest


@pytest.fixture()
def registry_db(tmp_path, monkeypatch):
    db_path = tmp_path / 'concurrency_test.db'
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    monkeypatch.setenv('USE_SQLITE', 'true')
    monkeypatch.setattr('config.DATA_DIR', str(data_dir))
    monkeypatch.setattr('data._store.DATA_DIR', str(data_dir))
    monkeypatch.setattr('models.db.DATA_DIR', str(data_dir))
    monkeypatch.setattr('models.db.DB_PATH', str(db_path))

    from models import db as db_mod

    db_mod.reset_db_connection(close_all=True)
    db_mod.init_db()

    import repositories.registry.project_repo as project_repo_mod

    project_repo_mod._shared = None
    yield
    project_repo_mod._shared = None
    db_mod.reset_db_connection(close_all=True)


def test_concurrent_project_reads_and_writes(registry_db):
    from repositories.registry.project_repo import get_project_repository

    repo = get_project_repository()
    project_id = f'Conc-{uuid.uuid4().hex[:8]}'
    errors = []

    def writer():
        try:
            for i in range(20):
                repo.save(project_id, {'name': f'v{i}', 'status': 'active'})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def reader():
        try:
            for _ in range(40):
                row = repo.get(project_id)
                if row is not None:
                    assert 'name' in row
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    final = repo.get(project_id)
    assert final is not None
    assert final.get('status') == 'active'


def test_other_process_reads_project_write(registry_db):
    from repositories.registry._db import db_module
    from repositories.registry.project_repo import get_project_repository

    repo = get_project_repository()
    project_id = f'Proc-{uuid.uuid4().hex[:8]}'
    repo.save(project_id, {'name': 'from-a', 'status': 'active'})
    db_path = db_module().DB_PATH
    script = (
        "import sqlite3,sys;"
        "row=sqlite3.connect(sys.argv[1]).execute("
        "'SELECT payload FROM projects WHERE project_id=?',(sys.argv[2],)).fetchone();"
        "print(row[0] if row else '')"
    )
    proc = subprocess.run(
        [sys.executable, '-c', script, db_path, project_id],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload.get('name') == 'from-a'


def test_ten_threads_insert_release_orders(registry_db):
    from repositories.registry._db import get_cursor, init_db

    init_db()
    project_id = f'Stress-{uuid.uuid4().hex[:8]}'
    errors = []

    def writer(index: int):
        try:
            order_id = f'{project_id}-{index}-{uuid.uuid4().hex[:6]}'
            now = '2026-09-22T00:00:00'
            with get_cursor() as cur:
                cur.execute(
                    '''
                    INSERT INTO release_orders (
                        release_order_id, project_id, env_key, channel_id, platform,
                        version_id, version_name, version_code, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        order_id, project_id, 'development', 'wechat', 'android',
                        'v1', '1.0.0', '1', 'draft', now, now,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    with get_cursor() as cur:
        count = cur.execute(
            'SELECT COUNT(*) FROM release_orders WHERE project_id=?',
            (project_id,),
        ).fetchone()[0]
    assert count == 10
