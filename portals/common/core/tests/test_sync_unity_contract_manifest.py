# -*- coding: utf-8 -*-
"""Tests for unity contract manifest sync script."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from scripts.sync_unity_contract_manifest import sync_manifest


class SyncUnityContractManifestTests(unittest.TestCase):
    def test_local_sync_writes_embedded_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "unity_contract_manifest.json")
            path = sync_manifest(dest=dest, local_only=True)
            self.assertEqual(path, dest)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            contracts = data.get("contracts") or []
            self.assertGreaterEqual(len(contracts), 3)
            self.assertIsInstance(contracts[0].get("fixture"), dict)


if __name__ == "__main__":
    unittest.main()
