"""TS-01..TS-03: cluster relay metadata and topology service dict."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.fast


def test_ts02_cluster_relay_metadata_auth(gm_legacy):
    meta = gm_legacy._enrich_cluster_relay_metadata({}, "Auth", "auth")
    assert meta["ClusterRelayPort"] == "15501"
    assert meta["ClusterRelayToken"] == gm_legacy._CLUSTER_RELAY_TOKEN_DEFAULT


def test_ts02_cluster_relay_metadata_game(gm_legacy):
    meta = gm_legacy._enrich_cluster_relay_metadata({}, "Game", "business")
    assert meta["ClusterRelayPort"] == "15502"


def test_ts03_service_dict_from_topology_node(gm_legacy, sample_topology):
    node = sample_topology["nodes"][1]
    svc = gm_legacy._service_dict_from_topology_node("GomeKu", node)
    assert svc["probe_host"] == "10.0.1.20"
    assert svc["cluster_relay_port"] == 15501
    assert svc["service_id"] == "auth-cn-1"


def test_or01_unified_all_disabled_by_default(monkeypatch, gm_legacy):
    monkeypatch.delenv("OPS_DEV_UNIFIED_GAMESERVER_ALL", raising=False)
    assert gm_legacy._should_use_unified_gameserver_all(["gateway-cn-1"], {}) is False


def test_or02_unified_all_dev_flag(monkeypatch, gm_legacy):
    monkeypatch.setenv("OPS_DEV_UNIFIED_GAMESERVER_ALL", "1")
    if gm_legacy.os.name != "nt":
        pytest.skip("windows-only unified-all flag")
    assert gm_legacy._should_use_unified_gameserver_all(["gateway-cn-1"], {}) is True
