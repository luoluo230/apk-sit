# -*- coding: utf-8 -*-
"""P3-03 Wave E: client × server alignment matrix."""

from __future__ import annotations

import unittest

from services.release.client_server_alignment import (
    assert_alignment_allows_action,
    assess_client_server_alignment,
)


class ClientServerAlignmentTests(unittest.TestCase):
    def test_deployed_ok(self):
        row = assess_client_server_alignment(
            {"status": "published", "payload": {"server_release_id": "s1"}},
            {"status": "deployed", "server_release_id": "s1"},
            env_key="staging",
        )
        self.assertEqual(row["state"], "ok")
        self.assertFalse(row["block_gray_expand"])

    def test_server_failed_blocks(self):
        row = assess_client_server_alignment(
            {"status": "published", "payload": {"server_release_id": "s1"}},
            {"status": "failed", "server_release_id": "s1"},
            env_key="production",
        )
        self.assertEqual(row["state"], "block")
        self.assertTrue(row["block_gray_expand"])
        with self.assertRaises(ValueError):
            assert_alignment_allows_action(row, action="expand_gray")

    def test_no_server_link_warn_when_published(self):
        row = assess_client_server_alignment({"status": "published"}, {}, env_key="staging")
        self.assertEqual(row["state"], "warn")


if __name__ == "__main__":
    unittest.main()
