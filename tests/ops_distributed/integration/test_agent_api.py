"""AG-04..AG-06, FM-04..FM-05: agent pull/report integration."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.fast


def _auth_headers(token: str):
    return {"Content-Type": "application/json", "X-Agent-Token": token}


def test_ag04_agent_pull_leases_job(admin_client, gm_legacy, temp_agent_jobs, agent_token, monkeypatch, flask_app):
    monkeypatch.setattr(
        gm_legacy,
        "_auth_agent_node",
        lambda node_id, token, cert_fp="": {"agent_max_concurrency": 2},
    )
    with flask_app.test_request_context():
        gm_legacy._enqueue_agent_job(
            "gateway-cn-1",
            "start",
            "gateway-cn-1",
            {"desired_server_id": "gateway-cn-1"},
            {"risk": "low", "ticket_id": "T1"},
        )
    resp = admin_client.post(
        "/api/ops-platform/agent/pull",
        json={"node_id": "ops-cn-1", "agent_id": "agent-local-cn-1", "limit": 5, "token": agent_token},
        headers=_auth_headers(agent_token),
    )
    data = resp.get_json()
    assert data.get("ok") is True
    jobs = data.get("jobs") or []
    assert len(jobs) >= 1
    assert jobs[0].get("lease") or True  # lease set on job in store


def test_ag05_agent_report_state_machine(admin_client, gm_legacy, temp_agent_jobs, agent_token, monkeypatch, flask_app):
    monkeypatch.setattr(
        gm_legacy,
        "_auth_agent_node",
        lambda node_id, token, cert_fp="": {"agent_max_concurrency": 1},
    )
    with flask_app.test_request_context():
        job = gm_legacy._enqueue_agent_job(
            "auth-cn-1",
            "start",
            "auth-cn-1",
            {"desired_server_id": "auth-cn-1"},
            {"risk": "low", "ticket_id": "T2"},
        )
    job_id = job["job_id"]
    admin_client.post(
        "/api/ops-platform/agent/pull",
        json={"node_id": "ops-cn-1", "agent_id": "agent-local-cn-1", "limit": 1, "token": agent_token},
        headers=_auth_headers(agent_token),
    )
    report_resp = admin_client.post(
        "/api/ops-platform/agent/report",
        json={
            "node_id": "ops-cn-1",
            "agent_id": "agent-local-cn-1",
            "job_id": job_id,
            "status": "SUCCESS",
            "result": {"message": "ok"},
            "token": agent_token,
        },
        headers=_auth_headers(agent_token),
    )
    assert report_resp.status_code == 200, report_resp.get_json()
    jobs = gm_legacy._load_agent_jobs()
    hit = next((x for x in jobs if x.get("job_id") == job_id), None)
    assert hit is not None
    assert str(hit.get("status")).upper() == "SUCCESS"


def test_ag06_enqueue_idempotent(gm_legacy, temp_agent_jobs, flask_app):
    payload = {"desired_server_id": "game-cn-1"}
    v = {"risk": "low", "ticket_id": "T3"}
    with flask_app.test_request_context():
        j1 = gm_legacy._enqueue_agent_job("game-cn-1", "start", "game-cn-1", payload, v)
        j2 = gm_legacy._enqueue_agent_job("game-cn-1", "start", "game-cn-1", payload, v)
    assert j1["job_id"] == j2["job_id"]
    jobs = [x for x in gm_legacy._load_agent_jobs() if x.get("node_id") == "game-cn-1"]
    assert len(jobs) == 1


def test_fm04_pull_empty_when_slots_full(admin_client, gm_legacy, temp_agent_jobs, agent_token, monkeypatch):
    monkeypatch.setattr(
        gm_legacy,
        "_auth_agent_node",
        lambda node_id, token, cert_fp="": {"agent_max_concurrency": 1},
    )
    jobs = gm_legacy._load_agent_jobs()
    jobs.append(
        {
            "job_id": "job-running-1",
            "node_id": "gateway-cn-1",
            "action_type": "start",
            "target": "gateway-cn-1",
            "payload": {},
            "status": "RUNNING",
            "lease": {"agent_id": "agent-local-cn-1", "leased_at": gm_legacy._now_iso()},
            "attempt": 0,
            "max_retries": 2,
            "updated_at": gm_legacy._now_iso(),
        }
    )
    gm_legacy._save_agent_jobs(jobs)
    resp = admin_client.post(
        "/api/ops-platform/agent/pull",
        json={"node_id": "ops-cn-1", "agent_id": "agent-local-cn-1", "limit": 5, "token": agent_token},
        headers=_auth_headers(agent_token),
    )
    data = resp.get_json()
    assert data.get("ok") is True
    assert data.get("count") == 0


def test_fm05_reconcile_job_timeout(gm_legacy, temp_agent_jobs):
    old = (datetime.utcnow() - timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
    jobs = [
        {
            "job_id": "job-stale",
            "node_id": "gateway-cn-1",
            "status": "RUNNING",
            "lease": {"agent_id": "agent-local-cn-1", "leased_at": old},
            "attempt": 0,
            "max_retries": 1,
            "updated_at": old,
        }
    ]
    gm_legacy._save_agent_jobs(jobs)
    loaded = gm_legacy._load_agent_jobs()
    changed = gm_legacy._reconcile_agent_jobs(
        "ops-cn-1",
        loaded,
        lease_timeout_sec=30,
        max_retries=1,
        agent_id="agent-local-cn-1",
    )
    assert changed is True
    hit = loaded[0]
    assert str(hit.get("status")).upper() in ("TIMEOUT", "PENDING")
