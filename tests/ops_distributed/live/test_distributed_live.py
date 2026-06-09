"""Live E2E: BT-09/10, AG-07/08, OR-05, CR-05 (requires running stack)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

pytestmark = pytest.mark.live


def _login(base: str):
    from ops_ecosystem_chain import login

    return login(base)


@pytest.mark.live
def test_bt09_cli_auth_login_lifecycle():
    repo = os.getenv("GAME_SERVER_REPO", "E:/maclient/game-server")
    runner = Path(repo) / "tools" / "SmokeTest" / "run-business-test.py"
    if not runner.is_file():
        pytest.skip("run-business-test.py missing")
    proc = subprocess.run(
        [
            sys.executable,
            str(runner),
            "--plan",
            "auth-login-lifecycle",
            "--transport",
            "websocket",
            "--ws",
            "ws://127.0.0.1:15050/ws/",
            "--timeout-ms",
            "15000",
        ],
        cwd=str(runner.parent),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-500:]


@pytest.mark.live
def test_bt10_api_business_test_run():
    base = os.getenv("OPS_BASE", "http://127.0.0.1:5003")
    ok, cookie = _login(base)
    if not ok:
        pytest.skip("admin login failed")
    resp = requests.post(
        base.rstrip("/") + "/api/ops-platform/business-test/run",
        headers={"Cookie": cookie, "Content-Type": "application/json"},
        data=json.dumps(
            {
                "plan_id": "auth-login-lifecycle",
                "transport": "websocket",
                "gateway_endpoint": {
                    "host": "127.0.0.1",
                    "port": 15050,
                    "ws_url": "ws://127.0.0.1:15050/ws/",
                },
            }
        ),
        timeout=120,
    )
    body = resp.json()
    assert resp.status_code == 200, body
    assert body.get("ok") is True
    steps = body.get("steps") or []
    if not steps:
        run = body.get("business_run") or {}
        steps = run.get("steps") or run.get("Steps") or []
    assert len(steps) >= 1


@pytest.mark.live
def test_ag07_gameserver_agent_exec_status():
    from gameserver_agent_exec import execute_ops_job

    out = execute_ops_job({"action_type": "status", "node_id": "ops-cn-1", "payload": {}})
    assert out.get("ok") is True
    services = out.get("services") or {}
    assert services.get("gateway-cn-1") is True


@pytest.mark.live
@pytest.mark.windows
def test_or05_four_gameserver_processes():
    proc = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq GameServer.GameServerApp.exe", "/NH"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    count = sum(1 for line in proc.stdout.splitlines() if "GameServer.GameServerApp" in line)
    assert count >= 4, f"expected >=4 GameServer processes, got {count}"


@pytest.mark.live
def test_cr05_auth_relay_port_open():
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 15501), timeout=1.0):
            pass
    except OSError as ex:
        pytest.fail(f"auth cluster relay 15501 not open: {ex}")
