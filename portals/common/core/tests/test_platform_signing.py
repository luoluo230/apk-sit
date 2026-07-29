# -*- coding: utf-8 -*-
"""Tests for iOS signing automation + validation checklist."""

from __future__ import annotations

import json
import unittest

from services.build.platform_signing_service import (
    assess_ios_signing_setup,
    ios_signing_json_for_jenkins,
    merge_platform_config_into_group_meta,
    normalize_ios_signing,
    sanitize_ios_signing_for_api,
    validate_ios_signing_for_build,
)


class TestPlatformSigningService(unittest.TestCase):
    def test_normalize_hybrid_jenkins_mode(self):
        cfg = normalize_ios_signing(
            {
                "mode": "upload",
                "team_id": "abcde12345",
                "bundle_id": "com.example.app",
                "jenkins_credential_id": "asc-key-1",
                "export_method": "app-store",
            }
        )
        self.assertEqual(cfg["secret_mode"], "jenkins")
        self.assertEqual(cfg["team_id"], "ABCDE12345")
        self.assertEqual(cfg["jenkins_asc_credential_id"], "asc-key-1")

    def test_sanitize_api_strips_secrets_in_jenkins_mode(self):
        cfg = sanitize_ios_signing_for_api(
            {
                "secret_mode": "jenkins",
                "asc_api_key_id": "SHOULD_HIDE",
                "cert_password": "secret",
                "team_id": "ABCDE12345",
                "bundle_id": "com.example.app",
            }
        )
        self.assertEqual(cfg["asc_api_key_id"], "")
        self.assertNotIn("secret", cfg.get("cert_password", ""))

    def test_jenkins_json_has_no_raw_secrets(self):
        payload = json.loads(
            ios_signing_json_for_jenkins(
                {
                    "secret_mode": "jenkins",
                    "team_id": "ABCDE12345",
                    "bundle_id": "com.example.app",
                    "jenkins_asc_credential_id": "asc-1",
                    "cert_p12_path": "/tmp/secret.p12",
                }
            )
        )
        self.assertEqual(payload["jenkins_asc_credential_id"], "asc-1")
        self.assertEqual(payload.get("cert_p12_path"), "")

    def test_assess_blocks_missing_bundle_and_team(self):
        result = assess_ios_signing_setup({"secret_mode": "jenkins"})
        self.assertFalse(result["ready"])
        ids = {row["id"] for row in result["checklist"]}
        self.assertIn("bundle_id", ids)
        self.assertIn("team_id", ids)
        self.assertTrue(result["blocking_errors"])

    def test_assess_jenkins_mode_requires_cert_credential(self):
        result = assess_ios_signing_setup(
            {
                "secret_mode": "jenkins",
                "team_id": "ABCDE12345",
                "bundle_id": "com.example.app",
                "jenkins_asc_credential_id": "asc-1",
            }
        )
        cert = next(row for row in result["checklist"] if row["id"] == "jenkins_cert_credential")
        self.assertEqual(cert["status"], "fail")

    def test_validate_for_build_returns_joined_message(self):
        msg = validate_ios_signing_for_build({})
        self.assertIsNotNone(msg)
        self.assertIn("Bundle ID", msg)

    def test_merge_strips_secrets_on_jenkins_mode(self):
        merged = merge_platform_config_into_group_meta(
            {},
            {
                "ios_signing": {
                    "secret_mode": "jenkins",
                    "asc_api_key_path": "/secret/key.p8",
                    "team_id": "ABCDE12345",
                    "bundle_id": "com.example.app",
                    "jenkins_cert_credential_id": "cert-1",
                }
            },
        )
        ios = merged["ios_signing"]
        self.assertEqual(ios["asc_api_key_path"], "")
        self.assertEqual(ios["jenkins_cert_credential_id"], "cert-1")


if __name__ == "__main__":
    unittest.main()
