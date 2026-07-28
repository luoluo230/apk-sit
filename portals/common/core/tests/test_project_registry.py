# -*- coding: utf-8 -*-
"""Tests for typed config registry repositories. Plan P0-02 Step 1."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid

import pytest


@pytest.fixture()
def registry_db(tmp_path, monkeypatch):
    db_path = tmp_path / 'registry_test.db'
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    monkeypatch.setenv('USE_SQLITE', 'true')
    monkeypatch.setenv('SAVE_JSON_MIRROR', 'true')
    monkeypatch.setenv('SQLITE_MIRROR_JSON', 'true')
    monkeypatch.setattr('config.Config.SQLITE_MIRROR_JSON', True)
    monkeypatch.setattr('config.DATA_DIR', str(data_dir))
    monkeypatch.setattr('data._store.DATA_DIR', str(data_dir))
    monkeypatch.setattr('models.db.DATA_DIR', str(data_dir))
    monkeypatch.setattr('models.db.DB_PATH', str(db_path))
    from models import db as db_mod

    db_mod.reset_db_connection(close_all=True)

    import repositories.registry._db as registry_db_mod
    import repositories.registry.project_repo as project_repo_mod
    import repositories.registry.channel_repo as channel_repo_mod
    import repositories.registry.version_row_repo as version_repo_mod

    registry_db_mod._db_mod = None
    project_repo_mod._shared = None
    channel_repo_mod._shared = None
    version_repo_mod._shared = None

    db_mod = registry_db_mod.db_module()
    monkeypatch.setattr(db_mod, 'DB_PATH', str(db_path))
    monkeypatch.setattr(db_mod, 'DATA_DIR', str(data_dir))
    db_mod.reset_db_connection(close_all=True)
    db_mod.init_db()

    yield str(db_path), str(data_dir)

    registry_db_mod._db_mod = None


def test_project_repo_persists_and_mirrors_json(registry_db):
    db_path, data_dir = registry_db
    from repositories.registry.project_repo import get_project_repository

    repo = get_project_repository()
    project_id = f"P-{uuid.uuid4().hex[:8]}"
    payload = {'name': 'Registry Test', 'status': 'active', 'created_at': '2026-07-24T00:00:00'}
    repo.save(project_id, payload)

    conn = sqlite3.connect(db_path)
    row = conn.execute('SELECT payload FROM projects WHERE project_id=?', (project_id,)).fetchone()
    conn.close()
    assert row is not None
    assert json.loads(row[0])['name'] == 'Registry Test'

    mirror_path = os.path.join(data_dir, 'projects.json')
    assert os.path.isfile(mirror_path)
    with open(mirror_path, 'r', encoding='utf-8') as fp:
        mirror = json.load(fp)
    assert mirror[project_id]['name'] == 'Registry Test'

    import repositories.registry.project_repo as project_repo_mod

    project_repo_mod._shared = None
    from repositories.registry.project_repo import get_project_repository as reload_repo

    reloaded = reload_repo().get(project_id)
    assert reloaded is not None
    assert reloaded['name'] == 'Registry Test'


def test_project_service_create_uses_registry(registry_db, monkeypatch):
    db_path, data_dir = registry_db
    from app_new import app
    from repositories.admin import users_repo

    username = f"admin-{uuid.uuid4().hex[:6]}"
    users_repo.upsert_user(username, {'password': 'x', 'role': 'super_admin'})

    from services.admin import project_service

    project_id = f"Svc-{uuid.uuid4().hex[:8]}"
    payload = {
        'id': project_id,
        'name': 'Service Create',
        'game_id': f'game-{uuid.uuid4().hex[:8]}',
        'game_key': uuid.uuid4().hex,
    }
    with app.test_request_context():
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = username
            result, status = project_service.create_project(payload, created_by=username)
    assert status == 200, result

    conn = sqlite3.connect(db_path)
    row = conn.execute('SELECT payload FROM projects WHERE project_id=?', (project_id,)).fetchone()
    conn.close()
    assert row is not None
    assert json.loads(row[0])['name'] == 'Service Create'
