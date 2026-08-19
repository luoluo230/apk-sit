# -*- coding: utf-8 -*-
"""Simulate E2E publish: --fixture (dev gate) or --full (GM Ops chain)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Simulate E2E publish without APK build")
    p.add_argument("--mode", choices=("fixture", "full", "dry-run"), default="fixture",
                   help="fixture=seed bundle for CI; full=precheck→approve→publish; dry-run=plan only")
    p.add_argument("--project-id", default="GomeKu")
    p.add_argument("--scope", default="gomeku:development:1001")
    p.add_argument("--env-key", default="development")
    p.add_argument("--channel-id", default="1001")
    p.add_argument("--platform", default="android", choices=("android", "ios"))
    p.add_argument("--version-name", default="1.0.0")
    p.add_argument("--version-code", default="12")
    p.add_argument("--actor", default="simulate_e2e_publish")
    # legacy
    p.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args()


def _run_fixture(scope: str) -> int:
    env = os.environ.copy()
    env["RELEASE_GATE_SCOPE_ID"] = scope
    rc = subprocess.call([sys.executable, os.path.join(ROOT, "scripts", "seed_release_gate_fixture.py")], env=env)
    return rc


def _ensure_runtime_for_scope(project_id: str, env_key: str, channel_id: str, platform: str, version_name: str) -> bool:
    import time
    import uuid

    from services.ops.runtime_service import _runtime_active_for_scope
    from services.ops.runtime_orchestrator import _spawn_runtime_start_orchestration
    from services.release.scope_resolver import resolve_scope, resolve_topology_binding_for_scope
    from services.ops.topology_registry import (
        _load_topology_scoped,
        _load_scope_agent_bindings,
        _load_scope_service_bindings,
        _project_uses_runtime_topology,
    )
    from services.ops.storage import _upsert_runtime_run, _now_iso

    scope = resolve_scope(project_id, env_key, channel_id, platform=platform, auto_create=False)
    binding = resolve_topology_binding_for_scope(scope, version_name) if scope else {}
    topology_id = str(binding.get("topology_id") or "")
    runtime = _runtime_active_for_scope(project_id, env_key, topology_id)
    if runtime.get("active"):
        return True
    if not topology_id:
        print(f"WARN: runtime ensure skipped, topology_id missing for {project_id}/{env_key}")
        return True

    try:
        topo = _load_topology_scoped(project_id, env_key, topology_id)
        topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
        topo_edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
        run_id = "run-" + uuid.uuid4().hex[:12]
        now = _now_iso()
        if _project_uses_runtime_topology(project_id):
            _upsert_runtime_run(
                {
                    "run_id": run_id,
                    "project_id": project_id,
                    "env_key": env_key,
                    "topology_id": topology_id,
                    "op": "start",
                    "status": "running",
                    "created_at": now,
                    "updated_at": now,
                    "items": [],
                    "logs": [],
                }
            )
            _spawn_runtime_start_orchestration(
                run_id,
                project_id,
                env_key,
                topology_id,
                topo_nodes,
                topo_edges,
                _load_scope_service_bindings(topology_id),
                _load_scope_agent_bindings(topology_id),
                "simulate_e2e_publish",
            )
            print(f"runtime start queued run_id={run_id}")
        deadline = time.time() + 120
        while time.time() < deadline:
            runtime = _runtime_active_for_scope(project_id, env_key, topology_id)
            if runtime.get("active"):
                return True
            time.sleep(5)
    except Exception as exc:
        print(f"WARN: runtime ensure failed: {exc}")
    return bool(_runtime_active_for_scope(project_id, env_key, topology_id).get("active"))


def _run_full(args: argparse.Namespace) -> int:
    from models.data import project_versions_db, projects_db
    from services.release.bundle_service import find_active_bundle
    from services.release.release_order_service import (
        approve_release_order,
        create_release_order,
        precheck_release_order,
        publish_release_order,
    )

    project_id = str(args.project_id).strip()
    scope_id = str(args.scope).strip()
    if project_id not in projects_db:
        print(f"FAIL: unknown project_id={project_id}")
        return 1

    versions = project_versions_db.get(project_id) or []
    version_row = next(
        (
            row
            for row in versions
            if isinstance(row, dict)
            and str(row.get("version_name") or "") == args.version_name
            and str(row.get("version_code") or "") == args.version_code
            and str(row.get("scope_id") or "") == scope_id
        ),
        None,
    )
    if not version_row:
        version_row = next(
            (
                row
                for row in versions
                if isinstance(row, dict)
                and str(row.get("version_name") or "") == args.version_name
                and str(row.get("version_code") or "") == args.version_code
            ),
            None,
        )
    if not version_row:
        print(f"FAIL: version {args.version_name}/{args.version_code} not found")
        return 1

    order = create_release_order(
        project_id,
        {
            "scope_id": scope_id,
            "env_key": args.env_key,
            "channel_id": args.channel_id,
            "platform": args.platform,
            "version_id": version_row.get("id"),
            "notes": "simulate_e2e_publish --full",
        },
        actor=args.actor,
    )
    order_id = str(order.get("release_order_id") or order.get("order_id") or order.get("id") or "")
    if not order_id:
        print("FAIL: create_release_order returned no id")
        return 2

    _ensure_runtime_for_scope(
        project_id,
        args.env_key,
        args.channel_id,
        args.platform,
        args.version_name,
    )

    pre = precheck_release_order(project_id, order_id, actor=args.actor)
    if not pre.get("ok", True) and pre.get("blocking"):
        print(json.dumps({"step": "precheck", "result": pre}, ensure_ascii=False, indent=2))
        return 3

    status = str(pre.get("status") or "")
    if status == "awaiting_approval":
        approve_release_order(project_id, order_id, actor=args.actor, note="simulate_e2e_publish auto-approve")
    elif status not in {"ready", "published"}:
        print(json.dumps({"step": "approve", "error": f"unexpected status after precheck: {status}"}, ensure_ascii=False))
        return 5

    if status == "published":
        published = pre
    else:
        published = publish_release_order(project_id, order_id, actor=args.actor)
    final_status = str(published.get("publish_status") or published.get("status") or "")
    print(json.dumps({
        "mode": "full",
        "order_id": order_id,
        "status": final_status,
        "active_bundle_id": (find_active_bundle(scope_id) or {}).get("bundle_id"),
    }, ensure_ascii=False, indent=2))
    return 0 if final_status == "published" else 4


def main() -> int:
    args = _parse_args()
    mode = "dry-run" if args.dry_run else args.mode
    scope_id = str(args.scope).strip()

    if mode == "dry-run":
        from models.data import projects_db
        from services.release.bundle_service import find_active_bundle, list_bundles
        print(json.dumps({
            "mode": mode,
            "project_id": args.project_id,
            "scope_id": scope_id,
            "active_bundle_id": (find_active_bundle(scope_id) or {}).get("bundle_id"),
            "bundle_count": len(list_bundles(scope_id=scope_id)),
            "project_exists": args.project_id in projects_db,
        }, ensure_ascii=False, indent=2))
        return 0

    if mode == "fixture":
        rc = _run_fixture(scope_id)
        if rc == 0:
            print(json.dumps({"mode": "fixture", "scope_id": scope_id, "ok": True}, ensure_ascii=False))
        return rc

    return _run_full(args)


if __name__ == "__main__":
    raise SystemExit(main())
