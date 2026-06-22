# -*- coding: utf-8 -*-
"""Bridge game-server cluster health probes into Ops overview (Wave 3)."""

from __future__ import annotations

import os
import socket
from typing import Any, Dict, List, Optional

from services.game_ops_client import GameOpsClient

# Aligns with arch-docs overall.md §7.3 Check-Cluster-Health nine checks.
CLUSTER_HEALTH_CHECKS = (
    "gateway_port",
    "auth_port",
    "game_port",
    "cross_port",
    "ops_health",
    "ops_ready",
    "mongodb",
    "redis",
    "resource_usage",
)


def _tcp_open(host: str, port: int, timeout: float = 1.5) -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _metric(name: str, ok: bool, detail: str = "", value: Any = None) -> Dict[str, Any]:
    row = {"name": name, "ok": bool(ok), "detail": str(detail or "")}
    if value is not None:
        row["value"] = value
    return row


def _port_from_cluster(cluster: Dict[str, Any], role: str, default: int = 0) -> int:
    servers = cluster.get("Servers") or cluster.get("servers") or []
    if not isinstance(servers, list):
        return default
    for item in servers:
        if not isinstance(item, dict):
            continue
        node_type = str(item.get("Type") or item.get("type") or "").lower()
        if node_type == role.lower():
            try:
                return int(item.get("Port") or item.get("port") or default)
            except (TypeError, ValueError):
                return default
    return default


def collect_cluster_health(
    operator: str = "intranet-ops",
    host: str = "127.0.0.1",
    client: Optional[GameOpsClient] = None,
) -> Dict[str, Any]:
    """Collect nine cluster health metrics via GameOpsClient + local TCP probes."""
    ops = client or GameOpsClient()
    health = ops.get_health(operator=operator)
    ready = ops.get_ready(operator=operator)
    cluster_resp = ops.get_cluster(operator=operator)
    runtime_resp = ops.get_runtime_snapshot(operator=operator)

    cluster_data = cluster_resp.get("data") if isinstance(cluster_resp.get("data"), dict) else {}
    runtime_data = runtime_resp.get("data") if isinstance(runtime_resp.get("data"), dict) else {}
    readiness = ready.get("data") if isinstance(ready.get("data"), dict) else {}
    checks_list = readiness.get("checks") if isinstance(readiness.get("checks"), list) else []

    mongo_ok = any(isinstance(c, dict) and c.get("name") == "mongo" and c.get("ok") for c in checks_list)
    redis_ok = any(isinstance(c, dict) and c.get("name") == "redis" and c.get("ok") for c in checks_list)

    gateway_port = _port_from_cluster(cluster_data, "Gateway", int(os.getenv("GATEWAY_WS_PORT", "15050")))
    auth_port = _port_from_cluster(cluster_data, "Auth", 15501)
    game_port = _port_from_cluster(cluster_data, "Game", 15502)
    cross_port = _port_from_cluster(cluster_data, "Cross", 15503)

    telemetry = runtime_data.get("Telemetry") if isinstance(runtime_data.get("Telemetry"), dict) else {}
    cpu = telemetry.get("CpuPercent") or telemetry.get("cpuPercent")
    mem = telemetry.get("WorkingSetMb") or telemetry.get("workingSetMb")
    resource_ok = True
    resource_detail = "unknown"
    if cpu is not None:
        try:
            resource_ok = float(cpu) < 90.0
            resource_detail = f"cpu={cpu}% mem={mem}MB"
        except (TypeError, ValueError):
            resource_detail = "cpu parse failed"

    metrics: List[Dict[str, Any]] = [
        _metric("gateway_port", _tcp_open(host, gateway_port), f"{host}:{gateway_port}"),
        _metric("auth_port", _tcp_open(host, auth_port), f"{host}:{auth_port}"),
        _metric("game_port", _tcp_open(host, game_port), f"{host}:{game_port}"),
        _metric("cross_port", _tcp_open(host, cross_port), f"{host}:{cross_port}"),
        _metric("ops_health", bool(health.get("success")), str(health.get("message") or "")),
        _metric("ops_ready", bool(ready.get("success")), str(ready.get("message") or "")),
        _metric("mongodb", mongo_ok, "from /ops/ready"),
        _metric("redis", redis_ok, "from /ops/ready"),
        _metric("resource_usage", resource_ok, resource_detail, value={"cpu": cpu, "memory_mb": mem}),
    ]

    passed = sum(1 for m in metrics if m.get("ok"))
    return {
        "ok": passed == len(metrics),
        "checks_expected": len(CLUSTER_HEALTH_CHECKS),
        "checks_passed": passed,
        "metrics": metrics,
        "ops_base_url": ops.base_url,
        "generated_from": "cluster_health_bridge",
    }


def enrich_overview(overview: Dict[str, Any], operator: str = "intranet-ops") -> Dict[str, Any]:
    """Attach cluster health block to an existing ops overview payload."""
    if not isinstance(overview, dict):
        overview = {}
    try:
        overview["cluster_health"] = collect_cluster_health(operator=operator)
    except Exception as exc:
        overview["cluster_health"] = {"ok": False, "error": str(exc), "metrics": []}
    return overview
