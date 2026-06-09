# -*- coding: utf-8 -*-
"""Build NetworkProfile from ops topology."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.business_test_catalog import resolve_gateway_endpoint


def _find_node(nodes: List[Dict[str, Any]], role: str, prefix: str = "") -> Optional[Dict[str, Any]]:
    role_l = role.strip().lower()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or node.get("server_id") or "").strip().lower()
        node_role = str(node.get("role") or "").strip().lower()
        if node_role == role_l:
            return node
        if prefix and nid.startswith(prefix):
            return node
    return None


def _node_host_port(node: Optional[Dict[str, Any]], default_port: int) -> tuple[str, int]:
    if not isinstance(node, dict):
        return "127.0.0.1", default_port
    ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
    remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
    network = ui.get("network") if isinstance(ui.get("network"), dict) else {}
    host = "127.0.0.1"
    for candidate in (
        str(remote.get("host") or remote.get("probe_host") or "").strip(),
        str(network.get("probe_host") or network.get("host") or "").strip(),
    ):
        if candidate and candidate not in ("0.0.0.0", "*"):
            host = candidate
            break
    port = default_port
    for candidate in (
        int(remote.get("port") or 0),
        int(network.get("port") or 0),
        int(node.get("port") or 0),
        int(node.get("daemon_port") or 0),
    ):
        if candidate > 0:
            port = int(candidate)
            break
    return host, port


def _relay_port(node: Optional[Dict[str, Any]], default_port: int) -> int:
    if not isinstance(node, dict):
        return default_port
    ui = node.get("ui") if isinstance(node.get("ui"), dict) else {}
    remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
    meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    for candidate in (
        int(remote.get("cluster_relay_port") or 0),
        int(meta.get("ClusterRelayPort") or 0),
    ):
        if candidate > 0:
            return int(candidate)
    _, port = _node_host_port(node, default_port)
    return port


def build_network_profile_from_topology(
    topology: Optional[Dict[str, Any]],
    *,
    notice_url: str = "",
    agent_bindings: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    nodes = topology.get("nodes") if isinstance(topology, dict) and isinstance(topology.get("nodes"), list) else []
    gateway = resolve_gateway_endpoint(topology if isinstance(topology, dict) else None, agent_bindings)
    gateway_ws = str(gateway.get("ws_url") or "").strip()
    if not gateway_ws:
        host = str(gateway.get("host") or "127.0.0.1")
        port = int(gateway.get("port") or 15050)
        gateway_ws = f"ws://{host}:{port}/ws/"

    auth = _find_node(nodes, "auth", "auth-")
    game = _find_node(nodes, "business", "game-") or _find_node(nodes, "game", "game-")
    ops = _find_node(nodes, "ops", "ops-")

    auth_host, auth_port = _node_host_port(auth, 5501)
    game_relay = _relay_port(game, 15502)
    ops_host, ops_port = _node_host_port(ops, 5504)

    profile = {
        "gateway_ws": gateway_ws,
        "login_http": f"http://{auth_host}:{auth_port}",
        "game_ws": f"ws://{auth_host}:{game_relay}/ws/",
        "ops_http": f"http://{ops_host}:{ops_port}",
    }
    if notice_url:
        profile["notice_url"] = notice_url
    return profile


def merge_network_profiles(auto: Dict[str, Any], manual: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(auto or {})
    if not isinstance(manual, dict):
        return out
    for key, value in manual.items():
        if value is not None and str(value).strip():
            out[key] = value
    return out
