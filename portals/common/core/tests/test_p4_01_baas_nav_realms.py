# -*- coding: utf-8 -*-
"""P4-01: nav policy, realm open/merge, node heartbeat."""

from __future__ import annotations


def test_nav_policy_topology_hides_baas(monkeypatch):
    from services.baas import project_nav_policy as policy

    monkeypatch.setattr(policy, "project_server_mode", lambda _pid: "topology")
    ids = policy.visible_nav_item_ids("Any")
    assert "agent-control" in ids
    assert "baas-gm" not in ids
    assert "casual-services" not in ids


def test_nav_policy_baas_hides_agents(monkeypatch):
    from services.baas import project_nav_policy as policy

    monkeypatch.setattr(policy, "project_server_mode", lambda _pid: "casual_baas")
    ids = policy.visible_nav_item_ids("Any")
    assert "baas-gm" in ids
    assert "agent-control" not in ids
    flags = policy.hub_tab_flags("Any")
    assert flags["show_baas_tab"] is True
    assert flags["show_topology_tab"] is False
    assert flags["monitor_only"] is True


def test_realm_open_and_merge():
    from models.db import init_db
    from services.baas import realm_service

    init_db()
    sid = "svc-p4-test"
    a = realm_service.open_realm(sid, name="一区", actor="test", status="open")
    b = realm_service.open_realm(sid, name="二区", actor="test", status="new")
    assert a.get("realm_id")
    assert b.get("realm_id")
    realm_service.assign_player_realm(sid, "p1", a["realm_id"])
    merged = realm_service.start_merge(sid, a["realm_id"], b["realm_id"], actor="test")
    assert merged["status"] == "completed"
    closed = realm_service.get_realm(sid, a["realm_id"])
    assert closed.get("status") == "closed"
    target = realm_service.get_realm(sid, b["realm_id"])
    assert target.get("status") in ("open", "new")


def test_node_heartbeat():
    from models.db import init_db
    from services.baas import node_registry

    init_db()
    row = node_registry.heartbeat(service_id="svc-p4-test", node_id="n1", host="127.0.0.1", port=5004)
    assert row["node_id"] == "n1"
    items = node_registry.list_nodes("svc-p4-test")
    assert any(i.get("node_id") == "n1" for i in items)
