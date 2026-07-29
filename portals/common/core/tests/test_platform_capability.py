# -*- coding: utf-8 -*-
"""Tests for platform capability registry. Plan P1-03."""

from __future__ import annotations

import os

import pytest

from services.build.platform_capability import (
    assert_platform_build_allowed,
    assert_scope_creation_allowed,
    can_build,
    can_create_scope,
    list_platform_capabilities,
    resolve_platform_capability,
)


def test_build_grid_platforms_can_build():
    for pid in ("android", "ios", "wechat_minigame"):
        cap = resolve_platform_capability(pid)
        assert cap["can_build"] is True
        assert cap["catalog_only"] is False
        assert can_build(pid)


def test_switch_is_catalog_only():
    cap = resolve_platform_capability("switch")
    assert cap["can_build"] is False
    assert cap["catalog_only"] is True
    assert cap["badge"] == "catalog_only"
    with pytest.raises(ValueError, match="未接入构建网格"):
        assert_platform_build_allowed("switch")


def test_wechat_minigame_scope_allowed():
    assert can_create_scope("wechat_minigame") is True


def test_switch_scope_blocked_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_CATALOG_ONLY_SCOPE", raising=False)
    assert can_create_scope("switch") is False
    with pytest.raises(ValueError, match="目录项"):
        assert_scope_creation_allowed("switch")


def test_switch_scope_allowed_with_env_override(monkeypatch):
    monkeypatch.setenv("ALLOW_CATALOG_ONLY_SCOPE", "1")
    assert can_create_scope("switch") is True


def test_list_capabilities_covers_catalog():
    rows = list_platform_capabilities()
    ids = {row["platform_id"] for row in rows}
    assert "android" in ids
    assert "switch" in ids
    assert len(rows) >= 10


def test_request_build_rejects_switch_platform():
    from services.release import order_build_sync as obs

    class _FakeCrud:
        @staticmethod
        def get_release_order(project_id, order_id, include_details=False):
            return {
                "release_order_id": order_id,
                "version_id": "v1",
                "version_code": "1",
                "platform": "switch",
                "status": "draft",
                "payload": {},
            }

    def _fake_find_version(project_id, version_id, version_code):
        return {"id": version_id, "platform": "switch", "version_code": version_code}

    orig_crud = obs._order_crud
    orig_find = obs._find_version
    obs._order_crud = lambda: _FakeCrud()
    obs._find_version = _fake_find_version
    try:
        with pytest.raises(ValueError, match="未接入构建网格"):
            obs.request_build("P1", "ro-1", "tester")
    finally:
        obs._order_crud = orig_crud
        obs._find_version = orig_find
