# -*- coding: utf-8 -*-
"""Portal ↔ maclient Unity contract bridge — fixtures, manifest, validation."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from services.release.bootstrap_hotupdate_regression import CATALOG_ALIGN_KEYS, NETWORK_ALIGN_KEYS

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURES = os.path.join(_CORE, "tests", "fixtures")


def _fixture_path(name: str) -> str:
    return os.path.join(_FIXTURES, name)


def _load_fixture(name: str) -> Dict[str, Any]:
    path = _fixture_path(name)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _contract_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "id": "topology_bootstrap_v2",
            "framework": "topology",
            "contract_version": "v2",
            "fixture_file": "runtime_bootstrap_contract_v2.sample.json",
            "validator_module": "services.release.bootstrap_contract",
            "validate_fn": "validate_bootstrap_contract",
            "unity_assets": [
                "Assets/Src/HotUpdate/Framework/Bootstrap/RuntimeBootstrapService.cs",
                "Assets/Resources/Protocol/ProtocolNetworkSettings.asset",
            ],
            "unity_editmode_filter": "BootstrapContractFixtureTests",
            "bootstrap_paths": [
                "/api/public/runtime-bootstrap",
                "/api/public/client-bootstrap",
            ],
            "doc": "docs/client_bootstrap_contract.md",
        },
        {
            "id": "baas_bootstrap_v1",
            "framework": "casual_baas",
            "contract_version": "v1",
            "fixture_file": "baas_bootstrap_contract_v1.sample.json",
            "validator_module": "services.release.baas_bootstrap_contract",
            "validate_fn": "validate_baas_bootstrap_contract",
            "unity_assets": [
                "Assets/Src/HotUpdate/Framework/Bootstrap/BaasBootstrapService.cs",
                "Assets/Resources/Protocol/BaasNetworkSettings.asset",
            ],
            "unity_editmode_filter": "BaasBootstrapContractFixtureTests",
            "bootstrap_paths": [
                "/api/public/baas-bootstrap",
                "/api/public/client-bootstrap",
            ],
            "doc": "docs/client_bootstrap_contract_baas.md",
        },
        {
            "id": "hotupdate_regression_v1",
            "framework": "topology",
            "contract_version": "v1",
            "fixture_file": "runtime_bootstrap_contract_v2.sample.json",
            "validator_module": "services.release.bootstrap_hotupdate_regression",
            "validate_fn": "validate_hotupdate_contract",
            "unity_assets": [
                "Assets/Src/HotUpdate/Framework/Bootstrap/RuntimeBootstrapService.cs",
                "Assets/Src/HotUpdate/Framework/Bootstrap/HotUpdateManifestReader.cs",
            ],
            "unity_editmode_filter": "HotUpdateRegressionFixtureTests",
            "bootstrap_paths": [
                "/api/public/runtime-bootstrap",
            ],
            "catalog_align_keys": list(CATALOG_ALIGN_KEYS),
            "network_align_keys": list(NETWORK_ALIGN_KEYS),
            "doc": "docs/runbooks/unity_editmode_contract_tests.md",
        },
    ]


def build_unity_contract_manifest() -> Dict[str, Any]:
    """Manifest consumed by maclient Unity EditMode / PlayMode tests."""
    contracts: List[Dict[str, Any]] = []
    for row in _contract_definitions():
        item = dict(row)
        item["fixture_path"] = _fixture_path(str(item.get("fixture_file") or ""))
        contracts.append(item)
    return {
        "manifest_version": "1",
        "portal_core": "portals/common/core",
        "contracts": contracts,
    }


def build_portable_unity_contract_manifest(*, portal_base_url: str = "") -> Dict[str, Any]:
    """Portable manifest with embedded fixtures for maclient EditMode offline tests."""
    contracts: List[Dict[str, Any]] = []
    for row in _contract_definitions():
        fixture_file = str(row.get("fixture_file") or "")
        fixture = _load_fixture(fixture_file)
        contracts.append(
            {
                "id": row.get("id"),
                "framework": row.get("framework"),
                "contract_version": row.get("contract_version"),
                "fixture_file": fixture_file,
                "fixture": fixture,
                "unity_assets": list(row.get("unity_assets") or []),
                "unity_editmode_filter": row.get("unity_editmode_filter"),
                "bootstrap_paths": list(row.get("bootstrap_paths") or []),
                "catalog_align_keys": list(row.get("catalog_align_keys") or []),
                "network_align_keys": list(row.get("network_align_keys") or []),
                "doc": row.get("doc"),
            }
        )
    base = str(portal_base_url or "").strip().rstrip("/")
    return {
        "manifest_version": "1",
        "generated_by": "apk-site",
        "portal_base_url": base,
        "manifest_url": f"{base}/api/public/unity-contract-manifest" if base else "/api/public/unity-contract-manifest",
        "contracts": contracts,
    }


def validate_all_contract_fixtures() -> List[str]:
    """Validate every fixture in manifest; return error strings."""
    errors: List[str] = []
    manifest = build_unity_contract_manifest()
    for entry in manifest.get("contracts") or []:
        if not isinstance(entry, dict):
            continue
        cid = str(entry.get("id") or "")
        path = str(entry.get("fixture_path") or "")
        mod_name = str(entry.get("validator_module") or "")
        fn_name = str(entry.get("validate_fn") or "")
        if not path or not os.path.isfile(path):
            errors.append(f"{cid}: fixture missing at {path}")
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                sample = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{cid}: fixture read error: {exc}")
            continue
        try:
            import importlib

            mod = importlib.import_module(mod_name)
            validate = getattr(mod, fn_name)
            violations = validate(sample)
        except Exception as exc:
            errors.append(f"{cid}: validator error: {exc}")
            continue
        if violations:
            errors.append(f"{cid}: " + "; ".join(violations))
    return errors


def export_manifest(dest_path: str, *, portable: bool = True) -> Dict[str, Any]:
    manifest = build_portable_unity_contract_manifest() if portable else build_unity_contract_manifest()
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return manifest
