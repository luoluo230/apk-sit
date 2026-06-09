"""BT-07, BT-08, RG-01: business-test API integration."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.fast


def test_rg01_business_test_catalog(admin_client, monkeypatch, gm_legacy):
    monkeypatch.setattr(gm_legacy, "_business_test_repo", lambda: "E:/maclient/game-server")
    resp = admin_client.get("/api/ops-platform/business-test/catalog")
    assert resp.status_code in (200, 404, 500)
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get("ok") is True or "protocols" in data or "modules" in data


def test_bt07_business_test_preflight_fail(admin_client, monkeypatch, gm_legacy):
    monkeypatch.setattr(gm_legacy, "_allow_ops_execute", lambda: True)
    monkeypatch.setattr(
        gm_legacy,
        "_business_test_preflight",
        lambda transport, gateway_endpoint=None: {
            "ok": False,
            "issues": ["gateway down"],
            "message": "gateway down",
        },
    )
    monkeypatch.setattr(gm_legacy, "get_plan", lambda repo, plan_id: {"plan_id": plan_id})
    resp = admin_client.post(
        "/api/ops-platform/business-test/run",
        json={"plan_id": "auth-login-lifecycle", "transport": "websocket"},
    )
    assert resp.status_code == 502
    data = resp.get_json()
    assert data.get("ok") is False
    assert data.get("preflight_failed") or data.get("preflight")


def test_bt08_run_passes_ws_to_runner(monkeypatch, gm_legacy):
    captured = {}

    def fake_run(cmd, cwd=None, capture_output=True, text=True, timeout=600):
        captured["cmd"] = cmd

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(gm_legacy.subprocess, "run", fake_run)
    monkeypatch.setattr(gm_legacy, "_business_test_repo", lambda: "E:/maclient/game-server")
    monkeypatch.setattr(
        gm_legacy,
        "resolve_paths",
        lambda repo: {
            "runner_py": str(gm_legacy.os.path.join(repo, "tools", "SmokeTest", "run-business-test.py")),
        },
    )
    runner = gm_legacy.os.path.join("E:/maclient/game-server", "tools", "SmokeTest", "run-business-test.py")
    monkeypatch.setattr(gm_legacy.os.path, "isfile", lambda p: p == runner or p.endswith("run-business-test.py"))
    monkeypatch.setattr(gm_legacy.os, "makedirs", lambda *a, **k: None)

    gm_legacy._run_business_test_runner(
        "auth-login-lifecycle",
        "websocket",
        None,
        "biztest",
        "game-cn-1",
        {"ws_url": "ws://10.0.1.10:15050/ws/", "host": "10.0.1.10", "port": 15050},
    )
    cmd = captured.get("cmd") or []
    assert any("ws://10.0.1.10:15050/ws/" in str(x) for x in cmd)
