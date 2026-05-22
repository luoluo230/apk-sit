# -*- coding: utf-8 -*-
"""Contracts for newly split non-page admin APIs."""

import os
import sys
import unittest
import copy
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()


class TestAdminSplitRemainingContracts(unittest.TestCase):
    def setUp(self):
        from app_new import app
        from services.company_profile import get_company_profile
        from services.portal_content import get_player_portal_content, get_dev_portal_content

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        self._company_snapshot = copy.deepcopy(get_company_profile())
        self._player_snapshot = copy.deepcopy(get_player_portal_content())
        self._dev_snapshot = copy.deepcopy(get_dev_portal_content())
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def tearDown(self):
        from services.company_profile import save_company_profile
        from services.portal_content import save_player_portal_content, save_dev_portal_content

        save_company_profile(self._company_snapshot)
        save_player_portal_content(self._player_snapshot)
        save_dev_portal_content(self._dev_snapshot)

    def test_media_upload_without_file(self):
        r = self.client.post("/admin/media/upload", data={"scope": "site-config", "bucket": "shared"})
        self.assertEqual(r.status_code, 400)
        d = r.get_json() or {}
        self.assertIn("error", d)

    def test_site_config_save_endpoints(self):
        r1 = self.client.post("/admin/site-config/company", json={"company_name": "Contract Co"})
        self.assertEqual(r1.status_code, 200)
        self.assertTrue((r1.get_json() or {}).get("ok"))

        r2 = self.client.post("/admin/site-config/portal/player", json={"site_name": "Player Portal"})
        self.assertEqual(r2.status_code, 200)
        self.assertTrue((r2.get_json() or {}).get("ok"))

        r3 = self.client.post("/admin/site-config/portal/dev", json={"site_name": "Dev Portal"})
        self.assertEqual(r3.status_code, 200)
        self.assertTrue((r3.get_json() or {}).get("ok"))

    def test_site_config_visual_editor_save_invalid_kind(self):
        r = self.client.post("/admin/site-config/editor/invalid/save", json={})
        self.assertEqual(r.status_code, 400)
        d = r.get_json() or {}
        self.assertIn("error", d)

    def test_audit_export_csv(self):
        r = self.client.get("/admin/audit-log/export")
        self.assertEqual(r.status_code, 200)
        ctype = r.headers.get("Content-Type") or ""
        self.assertIn("text/csv", ctype)

    def test_users_export_and_import_contract(self):
        export_resp = self.client.get("/admin/users/export")
        self.assertEqual(export_resp.status_code, 200)
        self.assertIn("text/csv", (export_resp.headers.get("Content-Type") or ""))

        import_resp = self.client.post(
            "/admin/users/import",
            data={"file": (io.BytesIO(b"not-csv"), "users.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(import_resp.status_code, 400)
        self.assertIn("error", import_resp.get_json() or {})

    def test_projects_misc_contract(self):
        list_resp = self.client.get("/admin/projects/list")
        self.assertEqual(list_resp.status_code, 200)
        projects = (list_resp.get_json() or {}).get("projects") or []
        if projects:
            self.assertIn("can_edit", projects[0])

        options_resp = self.client.get("/admin/projects/user-options")
        self.assertEqual(options_resp.status_code, 200)
        self.assertIn("users", options_resp.get_json() or {})

        validate_resp = self.client.get("/admin/projects/validate-username?username=admin")
        self.assertEqual(validate_resp.status_code, 200)
        self.assertIn("exists", validate_resp.get_json() or {})


if __name__ == "__main__":
    unittest.main()
