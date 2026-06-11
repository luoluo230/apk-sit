# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from routes.gm_ops import _resolve_public_release


class PublicReleaseGateTests(unittest.TestCase):
    def test_public_release_requires_version_name(self):
        scope, release, error = _resolve_public_release(
            "GomeKu",
            env_key="production",
            channel="1001",
            platform="android",
            version_name="",
        )
        self.assertEqual(scope, {})
        self.assertEqual(release, {})
        self.assertEqual(error[1], 400)

    def test_public_release_rejects_missing_scope(self):
        with patch("routes.gm_ops.resolve_existing_scope_by_inputs", return_value={}):
            _, _, error = _resolve_public_release(
                "GomeKu",
                env_key="production",
                channel="1001",
                platform="android",
                version_name="1.0.0",
            )
        self.assertEqual(error[1], 404)
        self.assertEqual(error[0]["error"], "RELEASE_SCOPE_NOT_FOUND")

    def test_public_release_does_not_fallback_to_non_published(self):
        scope = {"scope_id": "gomeku:production:1001", "env_key": "production", "channel_id": "1001"}
        with patch("routes.gm_ops.resolve_existing_scope_by_inputs", return_value=scope), \
             patch("routes.gm_ops._find_best_release", return_value={}) as find_release:
            _, _, error = _resolve_public_release(
                "GomeKu",
                env_key="production",
                channel="1001",
                platform="android",
                version_name="1.0.0",
            )
        self.assertEqual(error[1], 404)
        self.assertEqual(find_release.call_args.kwargs["published_only"], True)

    def test_public_release_returns_precheck_failure(self):
        scope = {"scope_id": "gomeku:production:1001", "env_key": "production", "channel_id": "1001"}
        release = {"id": "ver-1"}
        precheck = {"ok": False, "topology_runtime_aligned": True}
        with patch("routes.gm_ops.resolve_existing_scope_by_inputs", return_value=scope), \
             patch("routes.gm_ops._find_best_release", return_value=release), \
             patch("routes.gm_ops.run_scope_precheck", return_value=precheck):
            _, _, error = _resolve_public_release(
                "GomeKu",
                env_key="production",
                channel="1001",
                platform="android",
                version_name="1.0.0",
            )
        self.assertEqual(error[1], 412)
        self.assertEqual(error[0]["error"], "RELEASE_PRECHECK_FAILED")


if __name__ == "__main__":
    unittest.main()
