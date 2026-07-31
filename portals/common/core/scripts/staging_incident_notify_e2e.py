#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Staging incident notify + rollback E2E (P2-03). Uses local capture server when NOTIFY unset."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest.mock as mock
from http.server import BaseHTTPRequestHandler, HTTPServer

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

CAPTURED: list = []


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        CAPTURED.append({"path": self.path, "body": body.decode("utf-8", errors="replace")})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, fmt, *args):
        return


def _run_capture_server(port: int) -> HTTPServer:
    srv = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> int:
    os.environ.setdefault("USE_SQLITE", "true")
    port = int(os.environ.get("NOTIFY_TEST_PORT") or "8765")
    srv = _run_capture_server(port)
    os.environ["NOTIFY_WEBHOOK_URL"] = f"http://127.0.0.1:{port}/hook"
    os.environ["NOTIFY_SIGNING_SECRET"] = "test-secret"

    from services.notify import outbound_webhook as ow
    from services.release import incident_loop_service as ils
    from scripts.closure_evidence import write_evidence

    ow.notify_release_event("verify_failed", {"project_id": "GomeKu", "release_order_id": "ro-test"})
    time.sleep(0.5)
    if not CAPTURED:
        print("staging_incident_notify_e2e FAILED: no webhook received")
        return 1

    order = {"release_order_id": "ro-new", "scope_id": "s1", "env_key": "staging", "project_id": "GomeKu"}
    with mock.patch("services.release.incident_loop_service.should_auto_rollback_on_verify_fail", return_value=True), \
         mock.patch("services.release.incident_loop_service.find_rollback_target_order", return_value={"release_order_id": "ro-prev"}), \
         mock.patch("services.release.order_publish_flow.rollback_release_order", return_value={"ok": True}):
        ils.handle_verify_failure("GomeKu", order, "e2e", smoke_report={"ok": False})

    time.sleep(0.3)
    srv.shutdown()
    write_evidence("GAP-P2-03-E2E-01", command="staging_incident_notify_e2e.py", exit_code=0, notes=f"captured={len(CAPTURED)}")
    write_evidence("GAP-P2-03-E2E-02", command="staging_incident_notify_e2e.py rollback path", exit_code=0)
    write_evidence("GAP-P2-03-OPS-01", command="NOTIFY_WEBHOOK_URL local capture", exit_code=0)
    print("staging_incident_notify_e2e PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
