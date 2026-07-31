# -*- coding: utf-8 -*-
"""P19 release order detail page structure and API wiring."""

from __future__ import annotations

import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from app_new import app  # noqa: E402
from models.db import init_db  # noqa: E402
from services.release import order_crud as oc  # noqa: E402


class InitDbConcurrencyTests(unittest.TestCase):
    def test_init_db_parallel_calls_do_not_raise(self):
        import models.db as db_mod

        db_mod._schema_initialized = False
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: init_db(), range(8)))
        self.assertTrue(db_mod._schema_initialized)


class ReleaseOrderDetailPageTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        self.order = {
            "release_order_id": "ro-p19-1",
            "project_id": "GomeKu",
            "status": "artifacts_ready",
            "env_key": "development",
            "channel_id": "1001",
            "channel_name": "微信",
            "platform": "android",
            "version_id": "vc-p19",
            "version_name": "1.0.1",
            "version_code": "2",
            "created_by": "admin",
            "updated_at": "2026-07-22T12:00:00",
            "reason": "P19 browser gate",
            "artifacts": [],
            "payload": {"validation_plan": "ok", "rollback_plan": "ok"},
            "latest_precheck": None,
        }

    def test_detail_page_shell_markup(self):
        with mock.patch("routes.delivery.pages.get_release_order", return_value=self.order), \
             mock.patch.dict("models.data.projects_db", {"GomeKu": {"name": "GomeKu"}}, clear=False):
            with self.client.session_transaction() as sess:
                sess["user"] = "admin"
            resp = self.client.get("/admin/projects/GomeKu/release-orders/ro-p19-1")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        for marker in (
            "rod-meta-strip",
            "orderJourneyProgress",
            "orderDetailTabs",
            "orderIssues",
            "orderFixRail",
            "orderEvents",
            "delivery_order_detail.js",
            "release_order_detail.css",
        ):
            self.assertIn(marker, html, msg=f"missing {marker}")

    def test_next_action_api_for_detail_primary(self):
        with mock.patch.object(oc, "get_release_order", return_value=self.order):
            with self.client.session_transaction() as sess:
                sess["user"] = "admin"
            resp = self.client.get("/api/projects/GomeKu/release-orders/ro-p19-1/next-action")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get("ok"))
        primary = (data.get("data") or {}).get("primary") or {}
        self.assertIn("label", primary)
        self.assertIn("phases", data.get("data") or {})


if __name__ == "__main__":
    unittest.main()