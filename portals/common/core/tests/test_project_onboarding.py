# -*- coding: utf-8 -*-
"""Tests for project onboarding wizard. Plan P1-02."""

from __future__ import annotations

import json
import sqlite3
import uuid
from unittest.mock import patch

import pytest


@pytest.fixture()
def registry_db(tmp_path, monkeypatch):
    db_path = tmp_path / "registry_test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setenv("SAVE_JSON_MIRROR", "true")
    monkeypatch.setenv("SQLITE_MIRROR_JSON", "true")
    monkeypatch.setattr("config.Config.SQLITE_MIRROR_JSON", True)
    monkeypatch.setattr("config.DATA_DIR", str(data_dir))
    monkeypatch.setattr("data._store.DATA_DIR", str(data_dir))
    monkeypatch.setattr("models.db.DATA_DIR", str(data_dir))
    monkeypatch.setattr("models.db.DB_PATH", str(db_path))
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
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_path))
    monkeypatch.setattr(db_mod, "DATA_DIR", str(data_dir))
    db_mod.reset_db_connection(close_all=True)
    db_mod.init_db()

    yield str(db_path), str(data_dir)

    registry_db_mod._db_mod = None


@pytest.fixture()
def onboarding_db(registry_db, monkeypatch):
    db_path, data_dir = registry_db
    from repositories.admin import users_repo
    from repositories.registry.channel_repo import get_channel_repository
    import repositories.registry.channel_repo as channel_repo_mod

    channel_repo_mod._shared = None
    get_channel_repository().save(
        "1001",
        {"id": "1001", "name": "WeChat", "apk_subdir": "wechat", "order": 1},
    )

    username = f"admin-{uuid.uuid4().hex[:6]}"
    users_repo.upsert_user(username, {"password": "x", "role": "super_admin"})
    yield db_path, data_dir, username


def _run_onboard(payload, username):
    from app_new import app
    from services.admin import project_onboarding_service

    with app.test_request_context():
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user"] = username
            return project_onboarding_service.onboard_project(payload, username)


def test_onboard_project_creates_full_state(onboarding_db):
    db_path, _data_dir, username = onboarding_db
    from repositories.admin import projects_repo
    from repositories.admin import versions_repo
    from services.release.storage import load_scopes

    project_id = f"Onb-{uuid.uuid4().hex[:8]}"
    payload = {
        "id": project_id,
        "name": "Onboard Test",
        "git_url": "git@example.com/demo.git",
        "unity_project_path": "E:/maclient",
        "channels": ["1001"],
        "platforms": ["android"],
        "env_keys": ["development", "testing"],
        "jenkins_instance_id": "8082",
        "seed_version_group": {
            "version_name": "1.0.0",
            "env_key": "development",
            "channel_id": "1001",
            "platform": "android",
        },
    }
    result, status = _run_onboard(payload, username)
    assert status == 200, result
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    assert data.get("project_id") == project_id
    assert data.get("version_id")
    assert data.get("scope_ids")

    proj = projects_repo.get_project(project_id)
    assert proj is not None
    assert "1001" in (proj.get("channels") or [])
    assert proj.get("jenkins_instance_id") == "8082"

    versions = versions_repo.list_versions(project_id)
    assert len(versions) >= 1
    assert any(str(v.get("version_name") or "") == "1.0.0" for v in versions)

    scopes = [row for row in load_scopes() if row.get("project_id") == project_id]
    assert len(scopes) >= 2

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT payload FROM projects WHERE project_id=?", (project_id,)).fetchone()
    conn.close()
    assert row is not None


def test_onboard_project_rolls_back_on_version_failure(onboarding_db):
    _db_path, _data_dir, username = onboarding_db
    from repositories.admin import projects_repo

    project_id = f"Rb-{uuid.uuid4().hex[:8]}"
    payload = {
        "id": project_id,
        "name": "Rollback Test",
        "channels": ["1001"],
        "platforms": ["android"],
        "env_keys": ["development"],
        "seed_version_group": {"version_name": "1.0.0", "channel_id": "1001", "platform": "android"},
    }
    with patch(
        "services.admin.project_onboarding_service.version_service.create_version",
        return_value=({"error": "boom"}, 400),
    ):
        result, status = _run_onboard(payload, username)
    assert status == 500
    assert not projects_repo.has_project(project_id)


def test_assign_channels_adds_delivery_scope(onboarding_db):
    _db_path, _data_dir, username = onboarding_db
    from app_new import app
    from services.admin import channel_assignment_service
    from repositories.admin import projects_repo

    project_id = f"Asg-{uuid.uuid4().hex[:8]}"
    onboard_payload = {
        "id": project_id,
        "name": "Assign Test",
        "channels": ["1001"],
        "platforms": ["android"],
        "env_keys": ["development"],
        "seed_version_group": {"version_name": "1.0.0", "channel_id": "1001", "platform": "android"},
    }
    _run_onboard(onboard_payload, username)

    with app.test_request_context():
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user"] = username
            result, status = channel_assignment_service.assign_channels(
                project_id,
                {"channel_ids": ["1001"], "copy_version_rows": False},
                username,
            )
    assert status == 200, result
    proj = projects_repo.get_project(project_id)
    env_rows = proj.get("release_environments") or []
    dev = next((row for row in env_rows if row.get("env_key") == "development"), None)
    assert dev is not None
    assert "1001" in (dev.get("channels") or [])
