# -*- coding: utf-8 -*-
"""BaaS bootstrap contract validation (v1)."""

from __future__ import annotations

import os
from typing import Any, List, Mapping, Sequence

CONTRACT_VERSION = "v1"

REQUIRED_TOP_LEVEL: Sequence[str] = (
    "ok",
    "project_id",
    "service_id",
    "public_api_base",
    "feature_flags",
    "endpoints",
    "auth_header_service",
    "auth_header_key",
)

OPTIONAL_TOP_LEVEL: Sequence[str] = (
    "framework",
    "client_module",
    "bootstrap_kind",
    "env_key",
    "config_version",
    "features",
)


def validate_baas_bootstrap_contract(payload: Mapping[str, Any]) -> List[str]:
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

    if "framework" in payload and str(payload.get("framework") or "") not in ("casual_baas", ""):
        errors.append(f"framework must be casual_baas, got {payload.get('framework')!r}")

    flags = payload.get("feature_flags")
    if flags is not None and not isinstance(flags, Mapping):
        errors.append("feature_flags must be an object")

    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, Mapping):
        errors.append("endpoints must be an object")
        endpoints = {}

    base = str(payload.get("public_api_base") or "").strip()
    if base and not base.startswith("/api/baas/v1/"):
        errors.append("public_api_base must start with /api/baas/v1/")

    service_id = str(payload.get("service_id") or "").strip()
    if service_id and base and service_id not in base:
        errors.append("public_api_base must include service_id")

    for name, path in (endpoints or {}).items():
        if not str(name or "").strip():
            errors.append("endpoints key must be non-empty")
        if not str(path or "").strip():
            errors.append(f"endpoints.{name} must be non-empty")

    for key in ("auth_header_service", "auth_header_key"):
        if key in payload and not str(payload.get(key) or "").strip():
            errors.append(f"{key} must be non-empty")

    return errors


def assert_baas_bootstrap_contract(payload: Mapping[str, Any]) -> None:
    errors = validate_baas_bootstrap_contract(payload)
    if errors:
        raise AssertionError("; ".join(errors))


def contract_fixture_path(name: str = "baas_bootstrap_contract_v1.sample.json") -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "tests", "fixtures", name))
