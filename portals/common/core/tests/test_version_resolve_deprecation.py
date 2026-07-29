# -*- coding: utf-8 -*-
"""version-resolve deprecation headers (P2-02 Step 4)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")


class VersionResolveDeprecationTests(unittest.TestCase):
    def test_success_response_includes_deprecation_headers(self):
        from app_new import create_app

        app = create_app()
        client = app.test_client()
        with mock.patch("routes.api.project_versions_db", {"p1": [{"version_name": "1.0.0", "version_code": "1", "version_status": "active", "platform": "android", "channel": "wechat", "updated_at": "2026-01-01T00:00:00Z"}]}):
            with mock.patch("routes.api._channel_matches", return_value=True):
                with mock.patch("services.release.release_context.resolve_release_context", return_value={"scope_id": "s1", "active_bundle_id": ""}):
                    with mock.patch("services.release.release_context.merge_version_resolve_with_active_bundle", side_effect=lambda d, *_a, **_k: d):
                        resp = client.get("/api/runtime/version-resolve?project_id=p1&version_name=1.0.0&platform=android&channel=wechat")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Deprecation"), "true")
        self.assertIn("runtime-bootstrap", resp.headers.get("Link") or "")


if __name__ == "__main__":
    unittest.main()
