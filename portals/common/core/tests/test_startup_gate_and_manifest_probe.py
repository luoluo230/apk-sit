# -*- coding: utf-8 -*-
"""Regression locks for startup-gate identity + empty-manifest rejection."""

from __future__ import annotations

import json
from pathlib import Path

from services.release.bootstrap_contract import validate_bootstrap_contract
from services.release.patch_manifest_probe import allow_empty_manifest, parse_manifest_files
from services.release.startup_gate_service import resolve_startup_gate


def test_startup_gate_unknown_project_fail_closed():
    result = resolve_startup_gate(project_id="__no_such_project__")
    assert result.get("ok") is False
    assert result.get("allowed") is False


def test_startup_gate_requires_identity():
    result = resolve_startup_gate()
    assert result.get("ok") is False
    assert "必填" in str(result.get("error") or result.get("message") or "")


def test_contract_fixture_uses_pascal_env_and_identity_fields():
    path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "runtime_bootstrap_contract_v2.sample.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_bootstrap_contract(payload)
    assert errors == [], errors
    rel = payload["bootstrap"]["resource_relative_path"]
    assert rel.startswith("Development/")
    assert payload.get("channel_id")
    assert payload.get("channel_key")
    assert payload.get("env_key")


def test_parse_manifest_files_and_empty_policy():
    assert parse_manifest_files('{"files":[{"relativePath":"a.json"}]}')[0]["relativePath"] == "a.json"
    assert parse_manifest_files('{"files":[]}') == []
    assert allow_empty_manifest(is_gate_fixture=False) is False
