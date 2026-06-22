# -*- coding: utf-8 -*-
"""CI gate: Feishu webhook — publish/rollback/approval/build/ops-failure (T-C13)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_received: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        _received.append({"path": self.path, "body": body})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, format, *args):
        return


def _run_mock_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{port}/feishu"


def _send_scenarios(mock_url: str) -> list[str]:
    from services.webhook import send_feishu

    scenarios = [
        ("release_publish", "发布单已发布"),
        ("release_rollback", "发布单已回滚"),
        ("approval_submitted", "审批已提交"),
        ("approval_approved", "审批已通过"),
        ("build_complete", "Jenkins 构建完成"),
        ("ops_action_failed", "Ops 高危动作失败"),
    ]
    errors: list[str] = []
    _received.clear()
    for title, content in scenarios:
        ok = send_feishu(title, content, url=mock_url)
        if not ok:
            errors.append(f"send failed: {title}")
    time.sleep(0.3)
    if len(_received) < len(scenarios):
        errors.append(f"expected>={len(scenarios)} webhook posts, got {len(_received)}")
    return errors


def main() -> int:
    configured = (os.environ.get("WEBHOOK_FEISHU_URL") or "").strip()
    if configured and not os.environ.get("WEBHOOK_GATE_FORCE_MOCK"):
        from services.webhook import send_feishu

        ok = send_feishu("webhook_feishu_gate", "ci probe", url=configured)
        print(json.dumps({"ok": ok, "mode": "live_url"}, ensure_ascii=False))
        return 0 if ok else 1

    server, thread, mock_url = _run_mock_server()
    os.environ["WEBHOOK_FEISHU_URL"] = mock_url
    try:
        errors = _send_scenarios(mock_url)
    finally:
        server.shutdown()
        thread.join(timeout=1)

    ok = not errors
    print(
        json.dumps(
            {"ok": ok, "mode": "mock", "received": len(_received), "errors": errors},
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
