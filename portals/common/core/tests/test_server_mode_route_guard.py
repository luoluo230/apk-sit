# -*- coding: utf-8 -*-
"""Deep-link guards align with project_nav_policy."""

from __future__ import annotations


def test_baas_project_blocks_agent_deep_link(monkeypatch):
    from services.baas import project_nav_policy as policy
    from services.baas.server_mode_route_guard import redirect_if_server_mode_blocks_page

    monkeypatch.setattr(policy, "project_server_mode", lambda _pid: "casual_baas")
    resp = redirect_if_server_mode_blocks_page("P1", "agent-control", "staging")
    assert resp is not None
    assert resp.status_code in (302, 303)
    loc = resp.headers.get("Location") or ""
    assert "/server-management" in loc
    assert "server_mode_blocked=1" in loc


def test_topology_project_blocks_baas_gm(monkeypatch):
    from services.baas import project_nav_policy as policy
    from services.baas.server_mode_route_guard import redirect_if_server_mode_blocks_page

    monkeypatch.setattr(policy, "project_server_mode", lambda _pid: "topology")
    resp = redirect_if_server_mode_blocks_page("P1", "baas-gm", "development")
    assert resp is not None
    assert "/overview" in (resp.headers.get("Location") or "")


def test_allowed_pages_do_not_redirect(monkeypatch):
    from services.baas import project_nav_policy as policy
    from services.baas.server_mode_route_guard import redirect_if_server_mode_blocks_page

    monkeypatch.setattr(policy, "project_server_mode", lambda _pid: "topology")
    assert redirect_if_server_mode_blocks_page("P1", "agent-control", "development") is None
    monkeypatch.setattr(policy, "project_server_mode", lambda _pid: "casual_baas")
    assert redirect_if_server_mode_blocks_page("P1", "casual-services", "development") is None
