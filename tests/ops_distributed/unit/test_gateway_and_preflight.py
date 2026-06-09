"""BT-01..BT-04: gateway endpoint resolution and business test preflight."""
from __future__ import annotations

import pytest

from services.business_test_catalog import resolve_gateway_endpoint

pytestmark = pytest.mark.fast


def test_bt01_resolve_gateway_endpoint(sample_topology):
    ep = resolve_gateway_endpoint(sample_topology, {}, "websocket")
    assert ep["host"] == "10.0.1.10"
    assert ep["port"] == 15050
    assert ep["ws_url"] == "ws://10.0.1.10:15050/ws/"


def test_bt02_resolve_gateway_fallback_empty_topology():
    ep = resolve_gateway_endpoint(None, None, "websocket")
    assert ep["host"] == "127.0.0.1"
    assert ep["port"] == 15050


def test_bt03_business_test_preflight_ok(monkeypatch, gm_legacy):
    monkeypatch.setattr(gm_legacy, "_ws_handshake_probe", lambda h, p=15050, **kw: (True, "ws_open"))
    monkeypatch.setattr(gm_legacy, "_business_test_login_probe", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(gm_legacy, "_count_gameserver_processes", lambda: 4)
    out = gm_legacy._business_test_preflight(
        "websocket",
        {"host": "127.0.0.1", "port": 15050, "ws_url": "ws://127.0.0.1:15050/ws/"},
    )
    assert out["ok"] is True
    assert out["login_probe_ok"] is True


def test_bt04_preflight_relay_failure_message(monkeypatch, gm_legacy):
    monkeypatch.setattr(gm_legacy, "_ws_handshake_probe", lambda h, p=15050, **kw: (True, "ws_open"))
    monkeypatch.setattr(
        gm_legacy,
        "_business_test_login_probe",
        lambda *a, **k: (False, "auth_cluster_relay_unreachable:127.0.0.1:15501"),
    )
    monkeypatch.setattr(gm_legacy, "_count_gameserver_processes", lambda: 4)
    out = gm_legacy._business_test_preflight("websocket", {"host": "127.0.0.1", "port": 15050})
    assert out["ok"] is False
    msg = out["message"]
    assert "15501" in msg
    assert "--all" not in msg
