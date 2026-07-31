# -*- coding: utf-8 -*-
"""Ops agent job SQLite round-trip (action_type + payload)."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _sqlite_env(monkeypatch):
    monkeypatch.setenv("USE_SQLITE", "true")


def test_agent_job_sqlite_roundtrip_preserves_action_type_and_payload():
    from models.db import init_db
    from services.ops.storage import _sqlite_load_agent_jobs, _sqlite_save_agent_jobs

    init_db()
    job_id = "job-pytest-roundtrip-storage"
    job = {
        "job_id": job_id,
        "node_id": "game-cn-1",
        "action_type": "deploy_server_artifact",
        "target": "game-cn-1",
        "payload": {
            "command": "deploy_server_artifact",
            "service_id": "game-cn-1",
            "project_id": "GomeKu",
            "server_release_id": "sro-test",
            "bundle_path": "C:/tmp/test.zip",
        },
        "status": "PENDING",
        "risk": "high",
        "ticket_id": "SRO-sro-test",
        "reason": "pytest roundtrip",
    }
    existing = [j for j in _sqlite_load_agent_jobs() if j.get("job_id") != job_id]
    _sqlite_save_agent_jobs(existing + [job])
    loaded = {j["job_id"]: j for j in _sqlite_load_agent_jobs()}[job_id]
    assert loaded.get("action_type") == "deploy_server_artifact"
    assert loaded.get("payload", {}).get("service_id") == "game-cn-1"
    assert loaded.get("node_id") == "game-cn-1"
    assert loaded.get("reason") == "pytest roundtrip"
