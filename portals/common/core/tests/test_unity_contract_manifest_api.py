# -*- coding: utf-8 -*-
"""Public API for portable Unity contract manifest."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")


class UnityContractManifestApiTests(unittest.TestCase):
    def test_public_manifest_endpoint(self):
        from app_new import create_app

        app = create_app()
        client = app.test_client()
        resp = client.get("/api/public/unity-contract-manifest")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("manifest_version"), "1")
        contracts = data.get("contracts") or []
        self.assertGreaterEqual(len(contracts), 3)
        self.assertIn("fixture", contracts[0])


if __name__ == "__main__":
    unittest.main()
