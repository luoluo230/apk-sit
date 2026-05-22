# -*- coding: utf-8 -*-
"""Contracts for newly split admin APIs."""

import copy
import os
import secrets
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()


class TestAdminSplitApiContracts(unittest.TestCase):
    def setUp(self):
        from app_new import app

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def test_channels_crud_envelope(self):
        from models.data import channels_db, save_channels

        snapshot = copy.deepcopy(channels_db)
        cid = f"e2e_ch_{secrets.token_hex(3)}"
        try:
            r_create = self.client.post(
                "/admin/channels/create",
                json={"id": cid, "name": "E2E Channel", "order": 8, "apk_subdir": "dev"},
            )
            self.assertEqual(r_create.status_code, 200)
            d_create = r_create.get_json() or {}
            self.assertTrue(d_create.get("ok"))
            self.assertIn("data", d_create)

            r_list = self.client.get("/admin/channels")
            self.assertEqual(r_list.status_code, 200)
            d_list = r_list.get_json() or {}
            self.assertTrue(d_list.get("ok"))
            channels = (d_list.get("data") or {}).get("channels") or []
            self.assertTrue(any((x.get("id") == cid) for x in channels))

            r_update = self.client.post(
                "/admin/channels/update",
                json={"id": cid, "name": "E2E Channel Updated", "build_param": "CHANNEL=e2e"},
            )
            self.assertEqual(r_update.status_code, 200)
            d_update = r_update.get_json() or {}
            self.assertTrue(d_update.get("ok"))

            r_delete = self.client.delete(f"/admin/channels/delete/{cid}")
            self.assertEqual(r_delete.status_code, 200)
            d_delete = r_delete.get_json() or {}
            self.assertTrue(d_delete.get("ok"))
        finally:
            if isinstance(channels_db, list):
                channels_db[:] = snapshot
                save_channels()

    def test_notifications_mark_read_envelope(self):
        from models.data import add_notification

        nid = add_notification("admin", "announcement", "split-test", "body", "/admin/notifications", "", "")
        r_one = self.client.post(f"/admin/notifications/{nid}/read")
        self.assertEqual(r_one.status_code, 200)
        d_one = r_one.get_json() or {}
        self.assertTrue(d_one.get("ok"))

        r_all = self.client.post("/admin/notifications/read-all")
        self.assertEqual(r_all.status_code, 200)
        d_all = r_all.get_json() or {}
        self.assertTrue(d_all.get("ok"))

    def test_settings_save_envelope(self):
        r = self.client.post(
            "/admin/settings/save",
            json={"PASSWORD_MIN_LENGTH": "6", "REQUIRE_APPROVAL_FOR_DELETE": "false"},
        )
        self.assertEqual(r.status_code, 200)
        d = r.get_json() or {}
        self.assertTrue(d.get("ok"))
        self.assertIn("data", d)


if __name__ == "__main__":
    unittest.main()
