#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Staging incident notify + rollback against a real release order.

Uses a local signed webhook when NOTIFY_WEBHOOK_URL is unset. Does not mock
policy or rollback. The failed order must end as rolled_back.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

CAPTURED: list = []


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        CAPTURED.append(
            {
                "path": self.path,
                "signature": self.headers.get("X-Signature-SHA256") or "",
                "body": body.decode("utf-8", errors="replace"),
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, fmt, *args):
        return


def _run_capture_server(port: int) -> HTTPServer:
    srv = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _wait_events(names: set, timeout: float = 5.0) -> set:
    deadline = time.time() + timeout
    seen = set()
    while time.time() < deadline:
        for item in CAPTURED:
            try:
                event = str(json.loads(item["body"]).get("event") or "")
            except json.JSONDecodeError:
                continue
            if event:
                seen.add(event)
        if names <= seen:
            return seen
        time.sleep(0.1)
    return seen


def _insert_pair(project_id: str, env_key: str) -> dict:
    from models.db import get_cursor

    stamp = uuid.uuid4().hex[:10]
    scope_id = f"e2e-incident:{stamp}"
    prev_id = f"ro-e2e-prev-{stamp}"
    fail_id = f"ro-e2e-fail-{stamp}"
    prev_bundle = f"bun-e2e-prev-{stamp}"
    fail_bundle = f"bun-e2e-fail-{stamp}"
    now_prev = "2026-10-28T01:00:00Z"
    now_fail = "2026-10-28T02:00:00Z"
    with get_cursor() as cur:
        for order_id, bundle_id, published_at, bundle_status in (
            (prev_id, prev_bundle, now_prev, "superseded"),
            (fail_id, fail_bundle, now_fail, "published"),
        ):
            cur.execute(
                """
                INSERT INTO release_orders (
                    release_order_id, project_id, env_key, channel_id, platform, version_id,
                    version_name, version_code, scope_id, topology_id, topology_binding_source,
                    runtime_run_id, bundle_id, status, reason, payload, created_by, approved_by,
                    created_at, updated_at, published_at, batch_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    order_id, project_id, env_key, "1001", "android", f"ver-{stamp}",
                    "1.0.0", "100", scope_id, "", "",
                    "", bundle_id, "published", "incident e2e", "{}", "e2e", "",
                    published_at, published_at, published_at, "",
                ),
            )
            cur.execute(
                """
                INSERT INTO release_bundles (
                    bundle_id, release_order_id, project_id, scope_id, env_key, channel_id,
                    publish_status, topology_id, runtime_run_id, version_name, version_code,
                    platform, payload, published_at, published_by, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    bundle_id, order_id, project_id, scope_id, env_key, "1001",
                    bundle_status, "", "", "1.0.0", "100",
                    "android", json.dumps({"publish_status": bundle_status}), published_at, "e2e",
                    published_at, published_at,
                ),
            )
    return {
        "scope_id": scope_id,
        "prev_id": prev_id,
        "fail_id": fail_id,
        "prev_bundle": prev_bundle,
        "fail_bundle": fail_bundle,
    }


def _order_status(project_id: str, order_id: str) -> str:
    from models.db import get_cursor

    with get_cursor() as cur:
        row = cur.execute(
            "SELECT status FROM release_orders WHERE project_id=? AND release_order_id=?",
            (project_id, order_id),
        ).fetchone()
    return str(row["status"] if row else "")


def main() -> int:
    port = int(os.environ.get("NOTIFY_TEST_PORT") or "8765")
    external = str(os.environ.get("NOTIFY_WEBHOOK_URL") or "").startswith("http")
    srv = None
    if not external:
        srv = _run_capture_server(port)
        os.environ["NOTIFY_WEBHOOK_URL"] = f"http://127.0.0.1:{port}/hook"
    os.environ.setdefault("NOTIFY_SIGNING_SECRET", "test-secret")

    from models.db import init_db
    from repositories.admin import projects_repo
    from scripts.closure_evidence import write_evidence
    from services.notify.outbound_webhook import incident_actions_ready
    from services.release.incident_loop_service import handle_verify_failure
    from services.release.release_policy_service import get_env_release_policy

    init_db()
    project_id = os.environ.get("INCIDENT_E2E_PROJECT") or "GomeKu"
    project = projects_repo.get_project(project_id)
    if not project:
        print(f"staging_incident_notify_e2e FAILED: project {project_id} missing")
        return 1
    defs = list(project.get("release_environments") or [])
    env_key = "staging"
    hit = next((row for row in defs if str(row.get("env_key") or "").lower() == env_key), None)
    if hit is None:
        env_key = "development"
        hit = next((row for row in defs if str(row.get("env_key") or "").lower() == env_key), None)
    if hit is None:
        print("staging_incident_notify_e2e FAILED: no staging or development environment")
        return 1
    previous = dict(hit.get("release_policy") or {}) if isinstance(hit.get("release_policy"), dict) else {}
    patched = dict(previous)
    patched["auto_rollback_on_verify_fail"] = True
    hit["release_policy"] = patched
    project["release_environments"] = defs
    projects_repo.upsert_project(project_id, project)
    try:
        if not get_env_release_policy(project_id, env_key).get("auto_rollback_on_verify_fail"):
            print("staging_incident_notify_e2e FAILED: auto rollback still off")
            return 1
        if not incident_actions_ready():
            print("staging_incident_notify_e2e FAILED: incident actions not ready")
            return 1

        pair = _insert_pair(project_id, env_key)
        failed = {
            "release_order_id": pair["fail_id"],
            "scope_id": pair["scope_id"],
            "env_key": env_key,
            "project_id": project_id,
            "bundle_id": pair["fail_bundle"],
            "platform": "android",
            "channel_id": "1001",
            "status": "published",
            "payload": {},
        }
        result = handle_verify_failure(project_id, failed, "e2e", smoke_report={"ok": False, "error": "e2e smoke"})
        seen = _wait_events({"verify_failed", "bootstrap_smoke_failed", "auto_rollback_executed"})
        signed = [item for item in CAPTURED if str(item.get("signature") or "").startswith("t=")]
        status = _order_status(project_id, pair["fail_id"])
        if "verify_failed" not in seen or not signed:
            print(f"staging_incident_notify_e2e FAILED: webhook seen={sorted(seen)} signed={len(signed)}")
            return 1
        if not (result.get("rollback") or {}).get("ok"):
            print(f"staging_incident_notify_e2e FAILED: rollback {result}")
            return 1
        if status != "rolled_back":
            print(f"staging_incident_notify_e2e FAILED: status={status}")
            return 1
        notes = json.dumps({"pair": pair, "events": sorted(seen), "rollback": result.get("rollback")}, ensure_ascii=False)
        write_evidence("GAP-P2-03-E2E-01", command="staging_incident_notify_e2e.py", exit_code=0, notes=notes)
        write_evidence("GAP-P2-03-E2E-02", command="staging_incident_notify_e2e.py real rollback", exit_code=0, notes=notes)
        write_evidence("GAP-P2-03-OPS-01", command="NOTIFY_WEBHOOK_URL signed capture", exit_code=0, notes=notes)
        print("staging_incident_notify_e2e PASS")
        return 0
    finally:
        restored = projects_repo.get_project(project_id) or {}
        rows = list(restored.get("release_environments") or [])
        for row in rows:
            if str(row.get("env_key") or "").lower() == env_key:
                row["release_policy"] = previous
        restored["release_environments"] = rows
        projects_repo.upsert_project(project_id, restored)
        if srv is not None:
            srv.shutdown()


if __name__ == "__main__":
    sys.exit(main())
