"""TS-04, XR-01: cluster sync payload integration."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.fast


def test_ts04_topology_payload_includes_relay_metadata(monkeypatch, gm_legacy, sample_topology):
    monkeypatch.setattr(
        gm_legacy,
        "_load_topology_scoped",
        lambda pid, env, tid: {
            "nodes": sample_topology["nodes"],
            "edges": sample_topology["edges"],
            "meta": {},
            "registry": {"name": "test-topo"},
        },
    )
    monkeypatch.setattr(gm_legacy, "_load_scope_agent_bindings", lambda tid: {})
    monkeypatch.setattr(gm_legacy, "_load_scope_service_bindings", lambda tid: {})
    monkeypatch.setattr(gm_legacy, "_services_for_project", lambda pid: [])
    monkeypatch.setattr(gm_legacy, "_agents_v2_for_project", lambda pid: [])

    payload = gm_legacy._topology_to_cluster_payload("GomeKu", "production", "topology-test")
    servers = payload.get("cluster", {}).get("Servers") or []
    by_id = {s.get("ServerId"): s for s in servers}
    assert by_id["gateway-cn-1"]["ProbeHost"] == "10.0.1.10"
    auth_meta = by_id["auth-cn-1"].get("Metadata") or {}
    assert auth_meta.get("ClusterRelayPort") == "15501"
    assert auth_meta.get("ClusterRelayToken")


def test_xr01_cross_host_probe_hosts(monkeypatch, gm_legacy, sample_topology):
    monkeypatch.setattr(
        gm_legacy,
        "_load_topology_scoped",
        lambda pid, env, tid: {
            "nodes": sample_topology["nodes"],
            "edges": sample_topology["edges"],
            "meta": {},
            "registry": {},
        },
    )
    monkeypatch.setattr(gm_legacy, "_load_scope_agent_bindings", lambda tid: {})
    monkeypatch.setattr(gm_legacy, "_load_scope_service_bindings", lambda tid: {})
    monkeypatch.setattr(gm_legacy, "_services_for_project", lambda pid: [])
    monkeypatch.setattr(gm_legacy, "_agents_v2_for_project", lambda pid: [])
    payload = gm_legacy._topology_to_cluster_payload("GomeKu", "production", "topology-test")
    servers = {s["ServerId"]: s for s in payload["cluster"]["Servers"]}
    assert servers["gateway-cn-1"]["ProbeHost"] == "10.0.1.10"
    assert servers["auth-cn-1"]["ProbeHost"] == "10.0.1.20"
