# -*- coding: utf-8 -*-
"""P3-03 Wave C: promote requires matching artifact identity."""

from __future__ import annotations

import unittest

from services.release.artifact_identity import extract_artifact_identity, require_matching_artifact_identity


class ArtifactIdentityTests(unittest.TestCase):
    def test_extract_from_client(self):
        row = extract_artifact_identity({"client": {"artifact_id": "a1", "sha256": "deadbeef"}})
        self.assertEqual(row["artifact_id"], "a1")
        self.assertEqual(row["sha256"], "deadbeef")

    def test_require_missing_blocks(self):
        with self.assertRaises(ValueError):
            require_matching_artifact_identity({"client": {"apk_url": "http://x"}})

    def test_require_mismatch_blocks(self):
        with self.assertRaises(ValueError):
            require_matching_artifact_identity(
                {"artifact_id": "a1", "sha256": "aaa"},
                {"artifact_id": "a1", "sha256": "bbb"},
            )

    def test_require_match_ok(self):
        ident = require_matching_artifact_identity(
            {"artifact_id": "a1", "sha256": "aaa"},
            {"artifact_id": "a1", "sha256": "aaa"},
        )
        self.assertEqual(ident["artifact_id"], "a1")


if __name__ == "__main__":
    unittest.main()
