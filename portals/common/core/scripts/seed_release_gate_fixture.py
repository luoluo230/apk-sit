# -*- coding: utf-8 -*-
"""Seed published bundle + version rows for commercial_startup_sequence_gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SCOPE_ID = os.environ.get("RELEASE_GATE_SCOPE_ID", "gomeku:development:1001:android")
PROJECT_ID = "GomeKu"
VERSION_NAME = "1.0.0"
VERSION_CODE = "12"
CHANNEL_ID = "1001"
PLATFORM = "android"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed release gate fixture bundle")
    p.add_argument("--force-update", action="store_true", help="Set force_update on version row")
    p.add_argument("--rollout-percentage", type=int, default=None, help="Rollout percentage 0-100")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    from models.data import project_versions_db, save_project_versions
    from models.db import get_cursor, init_db
    from services.release.scope_resolver import resolve_network_profile
    from services.release.storage import find_scope

    fixture_builder = os.path.join(os.path.dirname(__file__), "build_gate_fixture_artifacts.py")
    rc = subprocess.call([sys.executable, fixture_builder], cwd=ROOT)
    if rc != 0:
        print("FAIL: build_gate_fixture_artifacts")
        return rc

    init_db()
    scope = find_scope(SCOPE_ID)
    if not scope:
        print(f"FAIL: scope not found: {SCOPE_ID}")
        return 1

    profile, profile_source = resolve_network_profile(scope, VERSION_NAME)
    versions = project_versions_db.setdefault(PROJECT_ID, [])
    version_row = None
    for row in versions:
        if not isinstance(row, dict):
            continue
        if str(row.get("version_name") or "") == VERSION_NAME and str(row.get("version_code") or "") == VERSION_CODE:
            version_row = row
            break
    if not version_row:
        version_row = {
            "id": uuid.uuid4().hex[:12],
            "channel": CHANNEL_ID,
            "version_name": VERSION_NAME,
            "version_code": VERSION_CODE,
            "platform": PLATFORM,
            "env_key": "development",
            "stage": "dev",
            "scope_id": SCOPE_ID,
        }
        versions.append(version_row)

    version_row.update({
        "resource_url": "http://127.0.0.1:5003/static/gate-fixture",
        "config_url": "http://127.0.0.1:5003/static/gate-fixture/Version_1.0.0/12/config/config_patch_manifest.json",
        "code_url": "http://127.0.0.1:5003/static/gate-fixture/Version_1.0.0/12/code/code_patch_manifest.json",
        "resource_server_url": "http://127.0.0.1:5003",
        "resource_relative_path": "",
        "config_relative_path": "static/gate-fixture/config",
        "code_relative_path": "static/gate-fixture/code",
        "catalog_file_name": "catalog_1.0.0.bin",
        "min_client_version": version_row.get("min_client_version") or "1.0.0",
        "max_client_version": version_row.get("max_client_version") or VERSION_NAME,
        "rollout_percentage": int(
            args.rollout_percentage
            if args.rollout_percentage is not None
            else (version_row.get("rollout_percentage") or 100)
        ),
        "force_update": bool(args.force_update or version_row.get("force_update", False)),
        "is_revoked": bool(version_row.get("is_revoked", False)),
    })
    save_project_versions()

    now = datetime.now().isoformat()
    bundle_id = f"rb-gate-{SCOPE_ID.replace(':', '-')}-{VERSION_CODE}"
    order_id = f"ro-gate-{VERSION_CODE}"
    bundle = {
        "bundle_id": bundle_id,
        "release_order_id": order_id,
        "project_id": PROJECT_ID,
        "scope_id": SCOPE_ID,
        "is_gate_fixture": True,
        "env_key": scope.get("env_key"),
        "channel_id": scope.get("channel_id"),
        "client": {
            "version_id": version_row.get("id"),
            "version_name": VERSION_NAME,
            "version_code": VERSION_CODE,
            "platform": PLATFORM,
            "resource_url": version_row.get("resource_url"),
            "config_url": version_row.get("config_url"),
            "code_url": version_row.get("code_url"),
            "catalog_url": f"http://127.0.0.1:5003/static/gate-fixture/{version_row.get('catalog_file_name', 'catalog_1.0.0.bin')}",
            "resource_relative_path": version_row.get("resource_relative_path"),
            "catalog_file_name": version_row.get("catalog_file_name"),
            "min_client_version": version_row.get("min_client_version"),
            "max_client_version": version_row.get("max_client_version") or VERSION_NAME,
            "rollout_percentage": version_row.get("rollout_percentage"),
            "force_update": version_row.get("force_update"),
            "is_revoked": version_row.get("is_revoked"),
        },
        "server": {
            "topology_id": scope.get("default_topology_id"),
            "runtime_run_id": "gate-fixture-runtime",
            "network_profile_snapshot": profile,
            "profile_source": profile_source,
        },
        "publish_status": "published",
        "published_at": now,
        "published_by": "seed_release_gate_fixture",
        "created_at": now,
        "updated_at": now,
    }

    import json
    payload = json.dumps(bundle, ensure_ascii=False)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE release_bundles SET publish_status='superseded', updated_at=? WHERE scope_id=? AND publish_status='published'",
            (now, SCOPE_ID),
        )
        cur.execute(
            """
            INSERT INTO release_bundles (
                bundle_id, release_order_id, project_id, scope_id, env_key, channel_id,
                publish_status, topology_id, runtime_run_id, version_name, version_code,
                platform, payload, published_at, published_by, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(bundle_id) DO UPDATE SET
                publish_status=excluded.publish_status,
                payload=excluded.payload,
                published_at=excluded.published_at,
                updated_at=excluded.updated_at
            """,
            (
                bundle_id, order_id, PROJECT_ID, SCOPE_ID, scope.get("env_key"), scope.get("channel_id"),
                "published", scope.get("default_topology_id"), "gate-fixture-runtime",
                VERSION_NAME, VERSION_CODE, PLATFORM, payload, now, "seed", now, now,
            ),
        )
        cur.execute(
            "UPDATE release_scopes SET active_bundle_id=?, updated_at=? WHERE scope_id=?",
            (bundle_id, now, SCOPE_ID),
        )

    print(json.dumps({"ok": True, "bundle_id": bundle_id, "scope_id": SCOPE_ID, "gateway_ws": profile.get("gateway_ws")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
