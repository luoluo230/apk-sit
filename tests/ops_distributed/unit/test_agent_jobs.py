"""AG-01..AG-03: agent job routing helpers."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.fast


def test_ag01_job_matches_by_node_id(gm_legacy):
    job = {"node_id": "gateway-cn-1", "payload": {}}
    assert gm_legacy._job_matches_agent(job, "agent-local-cn-1", "ops-cn-1") is True


def test_ag02_job_matches_by_desired_server_id(gm_legacy):
    job = {
        "node_id": "auth-cn-1",
        "payload": {"desired_server_id": "auth-cn-1"},
        "action_type": "start",
    }
    assert gm_legacy._job_matches_agent(job, "agent-local-cn-1", "ops-cn-1") is True


def test_ag03_job_does_not_match_foreign_agent(monkeypatch, gm_legacy):
    monkeypatch.setattr(
        gm_legacy,
        "_agent_managed_service_ids",
        lambda agent_id, pull_node_id="": {"ops-cn-1"},
    )
    job = {"node_id": "game-cn-1", "payload": {"desired_server_id": "game-cn-1"}}
    assert gm_legacy._job_matches_agent(job, "agent-remote-1", "ops-cn-1") is False
