# -*- coding: utf-8 -*-
"""Tests for verify_hotupdate_config_checksum.py (P2-02 Step 3)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_SCRIPTS)
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from scripts.verify_hotupdate_config_checksum import compare, _checksum, _normalize_manifest


class VerifyHotUpdateConfigChecksumTests(unittest.TestCase):
    def test_matching_manifest_passes(self):
        asset_yaml = """
Profile: Development
Channel: wechat
ProjectId: GomeKu
CurrentClientVersion: 1.0.0
RuntimeBootstrapUrl: http://127.0.0.1:5003
VersionResolveUrl: http://127.0.0.1:5003
ResourceServerUrl: https://cdn.example/bucket
RuntimeChannel: development
ExpectedUploadEnvironment: Development
PreferWebVersionResolve: 0
AllowOssMetadataFallback: 0
PreferUnifiedBootstrap: 1
"""
        with tempfile.NamedTemporaryFile("w", suffix=".asset", delete=False, encoding="utf-8") as fh:
            fh.write(asset_yaml)
            path = fh.name
        try:
            expected = {
                "portal_base_url": "http://127.0.0.1:5003",
                "profile": "Development",
                "channel": "wechat",
                "project_id": "GomeKu",
                "version_name": "1.0.0",
                "resource_server_url": "https://cdn.example/bucket",
            }
            ok, mismatches, a_sum, e_sum = compare(path, expected)
            self.assertTrue(ok, msg=mismatches)
            self.assertEqual(a_sum, e_sum)
        finally:
            os.remove(path)

    def test_mismatch_detected(self):
        asset_yaml = "Profile: Production\nChannel: wechat\n"
        with tempfile.NamedTemporaryFile("w", suffix=".asset", delete=False, encoding="utf-8") as fh:
            fh.write(asset_yaml)
            path = fh.name
        try:
            ok, mismatches, _, _ = compare(path, {"profile": "Development", "channel": "wechat"})
            self.assertFalse(ok)
            self.assertTrue(any("Profile" in m for m in mismatches))
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
