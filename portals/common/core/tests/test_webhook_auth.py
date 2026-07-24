# -*- coding: utf-8 -*-
"""Webhook HMAC auth tests. Plan: P0-01 Step 3."""

from __future__ import annotations

import os
import sys
import time
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from services.security.webhook_auth import (  # noqa: E402
    ip_allowed,
    resolve_webhook_secret,
    sign_webhook_body,
    verify_hmac_signature,
)


class WebhookAuthTests(unittest.TestCase):
    def setUp(self):
        self._env_backup = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_timestamp_signature_roundtrip(self):
        body = b'{"instance_id":"x","build_number":1}'
        secret = "unit-test-secret"
        header, _ts = sign_webhook_body(body, secret)
        self.assertTrue(verify_hmac_signature(body, header, secret))

    def test_legacy_hex_signature(self):
        import hashlib
        import hmac

        body = b'{"ok":true}'
        secret = "legacy-secret"
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_hmac_signature(body, digest, secret))
        self.assertTrue(verify_hmac_signature(body, f"sha256={digest}", secret))

    def test_rejects_expired_timestamp(self):
        body = b"{}"
        secret = "expired-secret"
        old_ts = int(time.time()) - 600
        header, _ = sign_webhook_body(body, secret, timestamp=old_ts)
        self.assertFalse(verify_hmac_signature(body, header, secret, max_skew_seconds=300))

    def test_resolve_secret_production_requires_env(self):
        from unittest import mock

        from config import Config

        with mock.patch.object(Config, "is_production", return_value=True):
            os.environ.pop("JENKINS_BUILD_WEBHOOK_SECRET", None)
            self.assertEqual(resolve_webhook_secret("JENKINS_BUILD_WEBHOOK_SECRET"), "")

    def test_ip_allowed_localhost(self):
        class _Req:
            headers = {}
            remote_addr = "127.0.0.1"

        self.assertTrue(ip_allowed(_Req(), {"127.0.0.1"}))


if __name__ == "__main__":
    unittest.main()
