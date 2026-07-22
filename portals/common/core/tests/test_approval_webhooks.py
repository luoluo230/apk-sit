# -*- coding: utf-8 -*-
"""External approval webhook tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")
os.environ["APPROVAL_WEBHOOK_SECRET_FEISHU"] = "test-secret"

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: F401
from routes import approval_webhooks as aw


class ApprovalWebhookTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_signature_verification(self):
        body = b'{"approval_id":"ra-1","action":"approve"}'
        sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(aw.verify_approval_signature("feishu", body, {"X-Approval-Signature": sig}))
        self.assertFalse(aw.verify_approval_signature("feishu", body, {"X-Approval-Signature": "bad"}))

    def test_idempotent_already_approved(self):
        with mock.patch.object(aw, "_find_order_for_approval", return_value={
            "approval_id": "ra-1",
            "release_order_id": "ro-1",
            "status": "approved",
            "project_id": "p1",
        }):
            out = aw.handle_external_approval("feishu", {"approval_id": "ra-1"})
        self.assertEqual(out.get("status"), "already_processed")

    @mock.patch.object(aw, "approve_release_order")
    @mock.patch.object(aw, "_find_order_for_approval")
    def test_inbound_webhook_approves_order(self, find_mock, approve_mock):
        find_mock.return_value = {
            "approval_id": "ra-2",
            "release_order_id": "ro-2",
            "status": "pending",
            "project_id": "p1",
        }
        approve_mock.return_value = {"status": "approved", "release_order_id": "ro-2"}
        body = {"approval_id": "ra-2", "project_id": "p1", "action": "approve", "note": "ok"}
        raw = json.dumps(body).encode("utf-8")
        sig = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
        resp = self.client.post(
            "/api/webhooks/approval/feishu",
            data=raw,
            headers={"Content-Type": "application/json", "X-Approval-Signature": sig},
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload.get("ok"))
        approve_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
