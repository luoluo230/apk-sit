# -*- coding: utf-8 -*-
"""Internal Jenkins build-complete webhook."""

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
os.environ["JENKINS_BUILD_WEBHOOK_SECRET"] = "test-webhook-secret"

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: F401


def _sign(body: bytes, secret: str = "test-webhook-secret") -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class InternalJenkinsWebhookTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def test_build_complete_rejects_bad_signature(self):
        body = json.dumps({"instance_id": "inst-1", "build_number": 42}).encode("utf-8")
        resp = self.client.post(
            "/api/internal/jenkins/build-complete",
            data=body,
            headers={"Content-Type": "application/json", "X-Jenkins-Signature": "bad"},
        )
        self.assertEqual(resp.status_code, 401)

    @mock.patch("services.release.order_build_sync.sync_release_order_build_status")
    @mock.patch("services.release.order_build_sync.find_release_order_for_build")
    def test_build_complete_syncs_release_order(self, find_mock, sync_mock):
        find_mock.return_value = ("GomeKu", "ro-1")
        sync_mock.return_value = {"status": "artifacts_ready", "release_order_id": "ro-1"}
        payload = {"instance_id": "inst-1", "build_number": 42}
        body = json.dumps(payload).encode("utf-8")
        resp = self.client.post(
            "/api/internal/jenkins/build-complete",
            data=body,
            headers={"Content-Type": "application/json", "X-Jenkins-Signature": _sign(body)},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("synced"))
        sync_mock.assert_called_once_with("GomeKu", "ro-1", actor="jenkins-webhook")


if __name__ == "__main__":
    unittest.main()
