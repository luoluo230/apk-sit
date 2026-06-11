# -*- coding: utf-8 -*-
"""End-to-end release flow simulation without APK packaging.

Flow:
1. Create/update a VersionRow
2. Precheck with artifact reachability
3. Create and approve release_publish approval
4. Publish through GM release HTTP route
5. Verify public release-config / runtime-bootstrap
6. Roll back the just-published bundle
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_PORTAL_MODE", "admin")

from app_new import app  # type: ignore  # noqa: E402
from models.data import approve_or_reject, projects_db  # noqa: E402


def _write_fixture(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _start_artifact_server(version_name: str, version_code: str) -> tuple[ThreadingHTTPServer, str, tempfile.TemporaryDirectory[str]]:
    temp_dir = tempfile.TemporaryDirectory(prefix="release-e2e-artifacts-")
    root = Path(temp_dir.name)
    rel = root / "Development" / "wechat" / "android" / "Version_{}".format(version_name) / version_code
    _write_fixture(root / "app.apk", "dummy apk")
    _write_fixture(root / "res.zip", "dummy resource")
    _write_fixture(root / "cfg.zip", "dummy config")
    _write_fixture(rel / f"catalog_{version_name}.bin", "catalog")
    _write_fixture(rel / "config" / "config_patch_manifest.json", "{}")
    _write_fixture(rel / "code" / "code_patch_manifest.json", "{}")

    handler = partial(SimpleHTTPRequestHandler, directory=temp_dir.name)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}", temp_dir


def _json_response(resp) -> Dict[str, Any]:
    body = resp.get_json(silent=True)
    return body if isinstance(body, dict) else {"raw": resp.get_data(as_text=True)}


def _step(rows: list[Dict[str, Any]], name: str, response=None, *, ok: bool | None = None, note: str = "") -> None:
    payload = _json_response(response) if response is not None else {}
    step_ok = bool(ok if ok is not None else (response is not None and response.status_code < 400 and payload.get("ok", True) is not False))
    rows.append(
        {
            "step": name,
            "ok": step_ok,
            "status": getattr(response, "status_code", 0) if response is not None else 0,
            "note": note,
            "payload": payload,
        }
    )


def main() -> int:
    project_id = "GomeKu"
    env = "dev"
    env_key = "development"
    channel = "1001"
    platform = "android"
    version_name = os.environ.get("E2E_VERSION_NAME", "1.0.0")
    version_code = os.environ.get("E2E_VERSION_CODE", datetime.now().strftime("%m%d%H%M"))

    server, artifact_base, temp_dir = _start_artifact_server(version_name, version_code)
    report: list[Dict[str, Any]] = []

    try:
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["TESTING"] = True
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user"] = "admin"

            version_entry = {
                "project_id": project_id,
                "env": env,
                "env_key": env_key,
                "channel": channel,
                "platform": platform,
                "version_name": version_name,
                "version_code": version_code,
                "apk_version": version_name,
                "resource_version": version_name,
                "config_version": version_name,
                "apk_url": f"{artifact_base}/app.apk",
                "resource_url": f"{artifact_base}/res.zip",
                "config_url": f"{artifact_base}/cfg.zip",
                "resource_server_url": artifact_base,
                "catalog_file_name": f"catalog_{version_name}.bin",
                "publish_status": "draft",
            }
            resp = client.post("/api/gm-ops/release/versions", json=version_entry)
            _step(report, "upsert_version", resp)

            base_payload = {
                "project_id": project_id,
                "env": env,
                "channel": channel,
                "platform": platform,
                "version_name": version_name,
            }

            resp = client.post("/api/gm-ops/release/precheck", json=base_payload)
            _step(report, "precheck", resp)
            if resp.status_code >= 400:
                print(json.dumps({"ok": False, "failed_step": "precheck", "report": report}, ensure_ascii=False, indent=2))
                return 2

            target = f"{project_id}:{version_name}"
            approval_req = {
                "actionType": "release_publish",
                "domain": "release",
                "target": target,
                "payload": base_payload,
                "operatorContext": {"reason": "simulate publish"},
            }
            resp = client.post("/api/gm-ops/action/approval", json=approval_req)
            _step(report, "create_approval", resp)
            approval_payload = _json_response(resp)
            approval_id = str(approval_payload.get("approval_id") or "")
            approved, error = approve_or_reject(approval_id, "admin", "approve", "simulate approve")
            _step(report, "approve_approval", ok=approved, note=error or "")
            if not approved:
                print(json.dumps({"ok": False, "failed_step": "approve_approval", "report": report}, ensure_ascii=False, indent=2))
                return 3

            resp = client.post("/api/gm-ops/release/publish", json=base_payload)
            _step(report, "publish", resp)
            publish_payload = _json_response(resp)
            if resp.status_code >= 400:
                print(json.dumps({"ok": False, "failed_step": "publish", "report": report}, ensure_ascii=False, indent=2))
                return 4

            scope_id = str(((publish_payload.get("operation") or {}).get("scope_id")) or "")
            bundle_id = str(((publish_payload.get("operation") or {}).get("bundle_id")) or "")
            rollback_target_bundle_id = str(((publish_payload.get("bundle") or {}).get("supersedes_bundle_id")) or "")

            version_resolve_qs = (
                f"/api/runtime/version-resolve?project_id={project_id}"
                f"&version_name={version_name}&channel_id={channel}&platform={platform}&env_key={env_key}&status=active"
            )
            resp = client.get(version_resolve_qs)
            _step(report, "runtime_version_resolve", resp)

            rel_cfg_qs = f"/api/public/release-config?project_id={project_id}&env_key={env_key}&channel_id={channel}&platform={platform}&version_name={version_name}"
            resp = client.get(rel_cfg_qs)
            _step(report, "public_release_config", resp)

            project = projects_db.get(project_id) or {}
            runtime_qs = (
                "/api/public/runtime-bootstrap"
                f"?game_id={project.get('game_id') or ''}"
                f"&game_key={project.get('game_key') or ''}"
                f"&env_key={env_key}&channel_id={channel}&platform={platform}&version_name={version_name}"
            )
            resp = client.get(runtime_qs)
            _step(report, "public_runtime_bootstrap", resp)

            if scope_id:
                resp = client.get(f"/api/release/scopes/{scope_id}")
                _step(report, "scope_detail", resp)
                resp = client.get(f"/api/release/bundles?scope_id={scope_id}")
                _step(report, "bundle_list", resp)
                bundle_rows = ((_json_response(resp).get("bundles") or []) if resp.status_code < 400 else [])
                if not rollback_target_bundle_id:
                    for row in bundle_rows:
                        candidate = str((row or {}).get("bundle_id") or "")
                        if candidate and candidate != bundle_id:
                            rollback_target_bundle_id = candidate
                            break

            rollback_payload = dict(base_payload)
            rollback_payload["bundle_id"] = rollback_target_bundle_id or bundle_id
            resp = client.post("/api/gm-ops/release/rollback", json=rollback_payload)
            _step(report, "rollback", resp)

        ok = all(item.get("ok") for item in report)
        summary = {
            "ok": ok,
            "project_id": project_id,
            "env_key": env_key,
            "channel_id": channel,
            "platform": platform,
            "version_name": version_name,
            "version_code": version_code,
            "artifact_base": artifact_base,
            "steps": report,
            "generated_at": datetime.now().isoformat(),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    finally:
        server.shutdown()
        server.server_close()
        temp_dir.cleanup()
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
