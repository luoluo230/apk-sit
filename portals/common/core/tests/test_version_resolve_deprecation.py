# -*- coding: utf-8 -*-
"""version-resolve removed — clients must use runtime-bootstrap (P2-02 Step 4)."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")


class VersionResolveRemovedTests(unittest.TestCase):
    def test_returns_410_with_successor_link(self):
        from app_new import create_app

        app = create_app()
        client = app.test_client()
        resp = client.get("/api/runtime/version-resolve?project_id=p1&version_name=1.0.0")
        self.assertEqual(resp.status_code, 410)
        body = resp.get_json() or {}
        self.assertFalse(body.get("ok"))
        self.assertIn("runtime-bootstrap", body.get("prefer_runtime_bootstrap") or "")
        self.assertEqual(resp.headers.get("Deprecation"), "true")
        self.assertIn("runtime-bootstrap", resp.headers.get("Link") or "")


if __name__ == "__main__":
    unittest.main()
