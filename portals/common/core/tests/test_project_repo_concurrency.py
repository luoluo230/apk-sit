# -*- coding: utf-8 -*-
"""Concurrent registry read/write. Plan P0-02 Step 2/3."""

from __future__ import annotations

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
