# -*- coding: utf-8 -*-
"""Portal ↔ maclient Unity contract bridge — fixtures, manifest, validation."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURES = os.path.join(_CORE, "tests", "fixtures")


def _fixture_path(name: str) -> str:
    return os.path.join(_FIXTURES, name)


def build_unity_contract_manifest() -> Dict[str, Any]:
    """Manifest consumed by maclient Unity EditMode / PlayMode tests."""
    return {
        "manifest_version": "1",
        "portal_core": "portals/common/core",
        "contracts": [
            {
                "id": "topology_bootstrap_v2",
                "framework": "topology",
                "contract_version": "v2",
                "fixture_file": "runtime_bootstrap_contract_v2.sample.json",
                "fixture_path": _fixture_path("runtime_bootstrap_contract_v2.sample.json"),
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
                "fixture_path": _fixture_path("baas_bootstrap_contract_v1.sample.json"),
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
        ],
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


def export_manifest(dest_path: str) -> Dict[str, Any]:
    manifest = build_unity_contract_manifest()
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return manifest
