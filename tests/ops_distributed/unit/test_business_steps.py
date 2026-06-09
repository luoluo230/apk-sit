"""BT-05, BT-06: business step normalization and process counting."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.fast


def test_bt05_normalize_pascal_case_steps(gm_legacy, pascal_business_run):
    steps = gm_legacy._normalize_business_steps(pascal_business_run["Steps"])
    assert len(steps) == 1
    assert steps[0]["step_id"] == "s1"
    assert steps[0]["protocol"] == "Login_c2s"
    assert steps[0]["message_id"] == 10001
    assert steps[0]["result"] == "ok"
    assert steps[0]["server"]["latency_ms"] == 5


def test_bt05_biz_run_get_passed(gm_legacy, pascal_business_run):
    assert gm_legacy._biz_run_get(pascal_business_run, "passed") is True
    assert gm_legacy._biz_run_get(pascal_business_run, "plan_id") == "auth-login-lifecycle"


@pytest.mark.windows
def test_bt06_tasklist_truncation_count(monkeypatch, gm_legacy):
    def fake_check_output(cmd, text=True, errors="replace"):
        return "GameServer.GameServerApp.    12345 Console\n"

    monkeypatch.setattr(gm_legacy.subprocess, "check_output", fake_check_output)
    assert gm_legacy._count_gameserver_processes() >= 1
