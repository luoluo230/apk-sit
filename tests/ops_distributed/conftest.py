"""Shared fixtures for distributed ops / agent / business-test pytest suite."""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "portals" / "common" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def gm_legacy():
    os.environ.setdefault("APP_PORTAL_MODE", "admin")
    import services.ops.helpers as mod  # type: ignore

    return mod


@pytest.fixture
def sample_topology() -> Dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "gateway-cn-1",
                "server_id": "gateway-cn-1",
                "role": "gateway",
                "name": "Gateway",
                "ui": {"remote": {"host": "10.0.1.10", "port": 15050}},
            },
            {
                "id": "auth-cn-1",
                "server_id": "auth-cn-1",
                "role": "auth",
                "name": "Auth",
                "ui": {"remote": {"host": "10.0.1.20", "port": 5501}},
            },
            {
                "id": "game-cn-1",
                "server_id": "game-cn-1",
                "role": "business",
                "name": "Game",
                "ui": {"remote": {"host": "127.0.0.1", "port": 5502}},
            },
        ],
        "edges": [
            {"from": "gateway-cn-1", "to": "auth-cn-1"},
            {"from": "auth-cn-1", "to": "game-cn-1"},
        ],
    }


@pytest.fixture
def pascal_business_run() -> Dict[str, Any]:
    return {
        "PlanId": "auth-login-lifecycle",
        "Passed": True,
        "Steps": [
            {
                "StepId": "s1",
                "Protocol": "Login_c2s",
                "MessageId": 10001,
                "Result": "ok",
                "Client": {"RequestJson": "{}", "Transport": "websocket", "Seq": 1},
                "Server": {"ResponseJson": "{}", "ErrorCode": 0, "LatencyMs": 5, "DataType": "Login_s2c"},
            }
        ],
    }


@pytest.fixture
def flask_app():
    os.environ["APP_PORTAL_MODE"] = "admin"
    from app_new import app  # type: ignore

    app.config["TESTING"] = True
    return app


@pytest.fixture
def admin_client(flask_app):
    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
    return client


@pytest.fixture
def agent_token() -> str:
    return "ops-write-key-2026"


def live_dependency_ok() -> Dict[str, bool]:
    import socket

    checks = {
        "admin_5003": False,
        "gateway_15050": False,
        "auth_relay_15501": False,
        "mongo_27017": False,
        "redis_6379": False,
    }

    def probe(host: str, port: int, timeout: float = 0.35) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    checks["admin_5003"] = probe("127.0.0.1", 5003)
    checks["gateway_15050"] = probe("127.0.0.1", 15050)
    checks["auth_relay_15501"] = probe("127.0.0.1", 15501)
    checks["mongo_27017"] = probe("127.0.0.1", 27017)
    checks["redis_6379"] = probe("127.0.0.1", 6379)
    return checks


@pytest.fixture(scope="session")
def live_env():
    return live_dependency_ok()


def pytest_runtest_setup(item):
    if item.get_closest_marker("live"):
        env = live_dependency_ok()
        if not env.get("gateway_15050"):
            pytest.skip("live: gateway 15050 not reachable")
    if item.get_closest_marker("windows") and os.name != "nt":
        pytest.skip("windows-only test")


@pytest.fixture
def temp_agent_jobs(tmp_path, monkeypatch, gm_legacy):
    jobs_path = tmp_path / "agent_jobs.json"
    jobs_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(gm_legacy, "_load_agent_jobs", lambda: json.loads(jobs_path.read_text(encoding="utf-8")))
    monkeypatch.setattr(
        gm_legacy,
        "_save_agent_jobs",
        lambda jobs: jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8"),
    )
    return jobs_path
