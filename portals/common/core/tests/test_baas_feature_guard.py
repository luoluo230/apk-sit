# -*- coding: utf-8 -*-
"""Tests for BaaS feature_guard helpers."""

from __future__ import annotations

import pytest

from services.baas.errors import BaasError
from services.baas.feature_guard import load_feature_config, require_feature, require_player


def test_require_player_empty_raises():
    with pytest.raises(BaasError) as exc:
        require_player("")
    assert exc.value.code == "BAAS_NOT_LOGGED_IN"


def test_require_feature_disabled_raises(monkeypatch):
    monkeypatch.setattr(
        "services.baas.feature_guard.feature_enabled",
        lambda sid, key: False,
    )
    with pytest.raises(BaasError) as exc:
        require_feature("svc1", "pve")
    assert exc.value.code == "BAAS_PVE_DISABLED"


def test_load_feature_config_merges(monkeypatch):
    monkeypatch.setattr(
        "services.baas.feature_guard.feature_enabled",
        lambda sid, key: True,
    )
    monkeypatch.setattr(
        "services.baas.feature_guard.get_feature_config",
        lambda sid, key: {"stamina_max": 99},
    )
    cfg = load_feature_config("svc1", "pve")
    assert cfg["stamina_max"] == 99
