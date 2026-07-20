# -*- coding: utf-8 -*-
"""Nightly release chain smoke: fixture bootstrap gate + optional quick-publish dry-run.

Intended for scheduled CI (workflow_dispatch / cron) against a running admin instance.
Default mode seeds the release gate fixture and validates bootstrap contract.
"""

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
    p = argparse.ArgumentParser(description="Nightly release chain smoke")
    p.add_argument("--mode", choices=("fixture", "quick-publish-dry"), default="fixture")
    p.add_argument("--project-id", default=os.environ.get("RELEASE_GATE_PROJECT_ID", "GomeKu"))
    p.add_argument("--scope-id", default=os.environ.get("RELEASE_GATE_SCOPE_ID", "gomeku:development:1001"))
    p.add_argument("--base-url", default=os.environ.get("RELEASE_GATE_BASE_URL", "http://127.0.0.1:5003"))
    return p.parse_args()


def _run_fixture(scope_id: str) -> int:
    env = os.environ.copy()
    env["RELEASE_GATE_SCOPE_ID"] = scope_id
    seed = os.path.join(ROOT, "scripts", "seed_release_gate_fixture.py")
    gate = os.path.join(ROOT, "scripts", "bootstrap_gate_e2e.py")
    rc = subprocess.call([sys.executable, seed], env=env, cwd=ROOT)
    if rc != 0:
        return rc
    return subprocess.call([sys.executable, gate], env=env, cwd=ROOT)


def _run_quick_publish_dry(args: argparse.Namespace) -> int:
    from services.release.release_order_service import quick_publish_delivery

    try:
        out = quick_publish_delivery(
            str(args.project_id),
            "development",
            os.environ.get("RELEASE_GATE_CHANNEL_ID", "1001"),
            "android",
            os.environ.get("RELEASE_GATE_VERSION_ID", ""),
            "nightly_release_chain_smoke",
            skip_build=True,
            auto_verify=False,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "data": out}, ensure_ascii=False, indent=2))
    return 0 if out.get("phase") else 1


def main() -> int:
    args = _parse_args()
    if args.mode == "fixture":
        return _run_fixture(args.scope_id)
    return _run_quick_publish_dry(args)


if __name__ == "__main__":
    raise SystemExit(main())
