# -*- coding: utf-8 -*-
"""Tests for P2-03 observability and incident loop."""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from services.monitor.release_metrics import render_prometheus_release_metrics
from services.notify import outbound_webhook as ow
from services.release import incident_loop_service as ils
from services.release import release_policy_service as rps


class TestOutboundWebhook(unittest.TestCase):
    def test_build_release_event_payload(self):
        payload = ow.build_release_event_payload("verify_failed", {"project_id": "p1"})
        self.assertEqual(payload["event"], "verify_failed")
        self.assertEqual(payload["payload"]["project_id"], "p1")

    @mock.patch("services.notify.outbound_webhook._post_signed_json")
    @mock.patch("services.notify.outbound_webhook._resolve_notify_url", return_value="http://127.0.0.1/hook")
    def test_notify_release_event_posts_signed_webhook(self, _url, post_mock):
        ow.notify_release_event("verify_failed", {"project_id": "p1", "release_order_id": "ro-1"})
        import time

        time.sleep(0.05)
        self.assertTrue(post_mock.called)

    def test_incident_actions_need_url_and_secret(self):
        with mock.patch.dict(os.environ, {"NOTIFY_WEBHOOK_URL": "", "NOTIFY_SIGNING_SECRET": "", "JENKINS_BUILD_WEBHOOK_SECRET": ""}, clear=False):
            self.assertFalse(ow.incident_actions_ready())
        with mock.patch.dict(
            os.environ,
            {"NOTIFY_WEBHOOK_URL": "http://127.0.0.1/hook", "NOTIFY_SIGNING_SECRET": "local-secret"},
            clear=False,
        ):
            self.assertTrue(ow.incident_actions_ready())

    def test_verify_failed_reaches_local_webhook(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import threading

        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                received.append(json.loads(raw.decode("utf-8")))
                self.send_response(204)
                self.end_headers()

            def log_message(self, fmt, *args):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            with mock.patch.dict(
                os.environ,
                {
                    "NOTIFY_WEBHOOK_URL": f"http://{host}:{port}/hook",
                    "NOTIFY_SIGNING_SECRET": "local-secret",
                },
                clear=False,
            ):
                ow.notify_release_event("verify_failed", {"project_id": "p1", "release_order_id": "ro-1"})
                for _ in range(50):
                    if received:
                        break
                    threading.Event().wait(0.05)
        finally:
            server.shutdown()
        self.assertTrue(received)
        self.assertEqual(received[0]["event"], "verify_failed")
        self.assertEqual(received[0]["payload"]["project_id"], "p1")


class TestReleasePolicyAutoRollback(unittest.TestCase):
    def test_staging_defaults_auto_rollback_on(self):
        policy = rps.normalize_release_policy({}, "staging")
        self.assertTrue(policy.get("auto_rollback_on_verify_fail"))

    def test_production_defaults_auto_rollback_off(self):
        policy = rps.normalize_release_policy({}, "production")
        self.assertFalse(policy.get("auto_rollback_on_verify_fail"))

    def test_should_auto_rollback_respects_override(self):
        self.assertTrue(
            rps.should_auto_rollback_on_verify_fail(
                "p1",
                "staging",
                {"auto_rollback_on_verify_fail": True},
            )
        )


class TestIncidentLoop(unittest.TestCase):
    @mock.patch("services.release.incident_loop_service.notify_release_event")
    @mock.patch("services.release.incident_loop_service.should_auto_rollback_on_verify_fail", return_value=False)
    def test_handle_verify_failure_notifies(self, _policy, notify_mock):
        order = {
            "release_order_id": "ro-1",
            "env_key": "production",
            "scope_id": "s1",
            "version_name": "1.0.0",
            "version_code": "1",
        }
        ils.handle_verify_failure("p1", order, "tester", smoke_report={"ok": False, "error": "bad smoke"})
        self.assertTrue(notify_mock.called)
        events = [call.args[0] for call in notify_mock.call_args_list]
        self.assertIn(ow.EVENT_BOOTSTRAP_SMOKE_FAILED, events)
        self.assertIn(ow.EVENT_VERIFY_FAILED, events)

    @mock.patch("services.release.incident_loop_service.incident_actions_ready", return_value=True)
    @mock.patch("services.release.order_publish_flow.rollback_release_order")
    @mock.patch("services.release.incident_loop_service.notify_release_event")
    @mock.patch("services.release.incident_loop_service.find_rollback_target_order")
    @mock.patch("services.release.incident_loop_service.should_auto_rollback_on_verify_fail", return_value=True)
    def test_auto_rollback_when_policy_and_notify_ready(self, _policy, find_mock, notify_mock, rollback_mock, _ready):
        find_mock.return_value = {"release_order_id": "ro-prev", "bundle_id": "rb-prev"}
        order = {"release_order_id": "ro-new", "scope_id": "s1", "env_key": "staging"}
        result = ils.handle_verify_failure("p1", order, "tester", smoke_report={"ok": False})
        rollback_mock.assert_called_once_with("p1", "ro-prev", "tester")
        self.assertTrue(result.get("attempted"))
        self.assertTrue(result.get("ok"))

    @mock.patch("services.release.incident_loop_service.incident_actions_ready", return_value=False)
    @mock.patch("services.release.order_publish_flow.rollback_release_order")
    @mock.patch("services.release.incident_loop_service.notify_release_event")
    @mock.patch("services.release.incident_loop_service.should_auto_rollback_on_verify_fail", return_value=True)
    def test_auto_rollback_waits_for_webhook_and_secret(self, _policy, notify_mock, rollback_mock, _ready):
        order = {"release_order_id": "ro-new", "scope_id": "s1", "env_key": "staging"}
        result = ils.handle_verify_failure("p1", order, "tester", smoke_report={"ok": False})
        rollback_mock.assert_not_called()
        self.assertFalse(result.get("attempted"))
        self.assertEqual(result["rollback"].get("reason"), "notify_not_configured")
        self.assertTrue(notify_mock.called)


class TestReleaseMetrics(unittest.TestCase):
    def test_render_prometheus_contains_expected_metrics(self):
        body, content_type = render_prometheus_release_metrics()
        self.assertIn("text/plain", content_type)
        self.assertIn("release_orders_total", body)
        self.assertIn("release_verify_failures_total", body)
        self.assertIn("bootstrap_smoke_duration_seconds", body)


if __name__ == "__main__":
    unittest.main()
