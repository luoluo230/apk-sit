# -*- coding: utf-8 -*-
"""Phase 2 gray rollout bucket tests."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from services.release.bundle_service import compute_rollout_bucket, resolve_gray_rollout_bundle


class RolloutBucketTests(unittest.TestCase):
    def test_bucket_is_stable_and_in_range(self):
        a = compute_rollout_bucket(device_id="dev-1", scope_id="scope:a", bundle_id="bundle-1")
        b = compute_rollout_bucket(device_id="dev-1", scope_id="scope:a", bundle_id="bundle-1")
        self.assertEqual(a, b)
        self.assertGreaterEqual(a, 0)
        self.assertLess(a, 100)

    def test_user_id_fallback_when_no_device(self):
        bucket = compute_rollout_bucket(user_id="user-42", scope_id="s1", bundle_id="b1")
        self.assertGreaterEqual(bucket, 0)
        self.assertLess(bucket, 100)

    def test_full_rollout_always_in_bucket(self):
        bundle = {
            "bundle_id": "bundle-new",
            "scope_id": "scope-1",
            "client": {"rollout_percentage": 100},
        }
        resolved = resolve_gray_rollout_bundle(bundle, device_id="d1")
        self.assertTrue(resolved.get("in_rollout"))
        self.assertEqual(resolved.get("bundle", {}).get("bundle_id"), "bundle-new")

    def test_gray_miss_without_superseded_returns_empty(self):
        bundle = {
            "bundle_id": "bundle-new",
            "scope_id": "scope-1",
            "supersedes_bundle_id": "",
            "client": {"rollout_percentage": 0},
        }
        resolved = resolve_gray_rollout_bundle(bundle, device_id="d1")
        self.assertTrue(resolved.get("gray_miss"))
        self.assertFalse(resolved.get("bundle"))


if __name__ == "__main__":
    unittest.main()
