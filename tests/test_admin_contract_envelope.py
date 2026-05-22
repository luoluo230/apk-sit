# -*- coding: utf-8 -*-
"""Admin API envelope contract tests."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()


class TestAdminContractEnvelope(unittest.TestCase):
    def setUp(self):
        from app_new import app

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = "admin"

    def test_users_list_returns_envelope(self):
        r = self.client.get("/admin/users/list")
        self.assertEqual(r.status_code, 200)
        d = r.get_json() or {}
        self.assertIn("ok", d)
        self.assertIn("data", d)
        self.assertIn("meta", d)
        self.assertIn("users", d)
        self.assertIsInstance((d.get("data") or {}).get("users", []), list)

    def test_project_create_conflict_returns_envelope(self):
        pid = f"contract_proj_{int(time.time())}"
        payload = {
            "id": pid,
            "name": "Contract Project",
            "game_id": f"gid_{pid}",
            "game_key": f"gkey_{pid}",
            "editors": ["admin"],
            "viewers": [],
        }
        r1 = self.client.post("/admin/projects/create", json=payload)
        self.assertEqual(r1.status_code, 200)
        d1 = r1.get_json() or {}
        self.assertTrue(d1.get("ok"))

        r2 = self.client.post("/admin/projects/create", json=payload)
        self.assertEqual(r2.status_code, 409)
        d2 = r2.get_json() or {}
        self.assertFalse(d2.get("ok"))
        self.assertIn("error", d2)
        self.assertIn("meta", d2)

    def test_approval_create_returns_envelope(self):
        r = self.client.post(
            "/admin/approval/create",
            json={
                "type": "delete_project",
                "target_type": "delete_project",
                "target_id": "contract-target-id",
                "reason": "contract test",
            },
        )
        self.assertEqual(r.status_code, 200)
        d = r.get_json() or {}
        self.assertTrue(d.get("ok"))
        self.assertIn("data", d)
        self.assertTrue(d.get("id") or (d.get("data") or {}).get("id"))


if __name__ == "__main__":
    unittest.main()
