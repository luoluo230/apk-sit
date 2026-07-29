# -*- coding: utf-8 -*-
"""Runtime-bootstrap contract validation (P2-02 Step 1)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

CONTRACT_VERSION = "v2"

REQUIRED_TOP_LEVEL: Sequence[str] = (
    "ok",
    "project_id",
    "scope_id",
    "active_bundle_id",
    "bootstrap",
    "network_profile",
)

REQUIRED_BOOTSTRAP: Sequence[str] = (
    "resource_relative_path",
    "catalog_file_name",
    "min_client_version",
    "max_client_version",
    "rollout_percentage",
    "force_update",
    "is_revoked",
)

REQUIRED_NETWORK: Sequence[str] = ("gateway_ws",)

OPTIONAL_BOOTSTRAP: Sequence[str] = (
    "version_name",
    "version_code",
    "platform",
    "catalog_url",
    "config_manifest_url",
    "code_manifest_url",
    "resource_server_url",
)


def validate_bootstrap_contract(payload: Mapping[str, Any]) -> List[str]:
    """Return human-readable contract violations; empty list means PASS."""
    errors: List[str] = []
    if not isinstance(payload, Mapping):
        return ["payload must be an object"]

    if payload.get("ok") is not True:
        errors.append(f"ok must be true, got {payload.get('ok')!r}")
        return errors

    for key in REQUIRED_TOP_LEVEL:
        if key not in payload:
            errors.append(f"missing top-level field: {key}")

    bootstrap = payload.get("bootstrap")
    if not isinstance(bootstrap, Mapping):
        errors.append("bootstrap must be an object")
        bootstrap = {}

    network = payload.get("network_profile")
    if not isinstance(network, Mapping):
        errors.append("network_profile must be an object")
        network = {}

    for key in REQUIRED_BOOTSTRAP:
        if key not in bootstrap:
            errors.append(f"missing bootstrap field: {key}")

    rollout = bootstrap.get("rollout_percentage")
    try:
        rollout_val = int(rollout)
        if rollout_val < 0 or rollout_val > 100:
            errors.append(f"rollout_percentage out of range: {rollout_val}")
    except (TypeError, ValueError):
        errors.append(f"rollout_percentage not int: {rollout!r}")

    if "force_update" in bootstrap and not isinstance(bootstrap.get("force_update"), bool):
        errors.append("force_update must be boolean")
    if "is_revoked" in bootstrap and not isinstance(bootstrap.get("is_revoked"), bool):
        errors.append("is_revoked must be boolean")

    rel_path = str(bootstrap.get("resource_relative_path") or "")
    if rel_path and "/Android/" in rel_path:
        errors.append("resource_relative_path must use lowercase android segment")

    for key in REQUIRED_NETWORK:
        if not str(network.get(key) or "").strip():
            errors.append(f"missing network_profile.{key}")

    gateway = str(network.get("gateway_ws") or "")
    if gateway and ":15050" not in gateway:
        errors.append("network_profile.gateway_ws must include port :15050 in CI fixture")

    return errors


def assert_bootstrap_contract(payload: Mapping[str, Any]) -> None:
    errors = validate_bootstrap_contract(payload)
    if errors:
        raise AssertionError("; ".join(errors))


def contract_fixture_path(name: str = "runtime_bootstrap_contract_v2.sample.json") -> str:
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(
        os.path.join(here, "..", "..", "tests", "fixtures", name)
    )
