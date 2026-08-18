# -*- coding: utf-8 -*-
"""Unity contract bridge — manifest + fixture validation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from services.release.unity_contract_bridge import (
    build_unity_contract_manifest,
    export_manifest,
    validate_all_contract_fixtures,
)


class UnityContractBridgeTests(unittest.TestCase):
    def test_manifest_has_two_contracts(self):
        manifest = build_unity_contract_manifest()
        contracts = manifest.get("contracts") or []
        self.assertEqual(len(contracts), 2)
        ids = {c.get("id") for c in contracts}
        self.assertIn("topology_bootstrap_v2", ids)
        self.assertIn("baas_bootstrap_v1", ids)

    def test_all_fixtures_pass_validators(self):
        errors = validate_all_contract_fixtures()
        self.assertEqual([], errors, msg="; ".join(errors))

    def test_export_manifest_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "unity_contract_manifest.json")
            manifest = export_manifest(dest)
            self.assertTrue(os.path.isfile(dest))
            with open(dest, encoding="utf-8") as fh:
                loaded = json.load(fh)
            self.assertEqual(loaded.get("manifest_version"), manifest.get("manifest_version"))


if __name__ == "__main__":
    unittest.main()
