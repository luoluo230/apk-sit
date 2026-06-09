# -*- coding: utf-8 -*-
"""Simulate GM publish for E2E / CI (no Jenkins/APK).

非 GM UI 路径：正式发版请使用 POST /api/gm-ops/release/publish（与 GM「正式发布」按钮一致）。
本脚本用于自动化种子：precheck → 审批 → create_bundle_from_publish。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.data import approvals_db, project_versions_db, save_approvals, save_project_versions
from routes.gm_ops import _find_best_release
from services.release.bundle_service import create_bundle_from_publish, run_scope_precheck
from services.release.scope_resolver import resolve_scope_by_inputs


def _ensure_approval(project_id: str, version_name: str) -> str:
    target_id = f"{project_id}:{version_name}"
    for a in approvals_db:
        if (
            a.get("type") == "version_publish"
            and (a.get("target_id") or "").strip() == target_id
            and a.get("status") == "approved"
        ):
            return str(a.get("id") or "")
    aid = f"e2e-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    approvals_db.append(
        {
            "id": aid,
            "type": "version_publish",
            "status": "approved",
            "applicant": "admin",
            "target_type": "version",
            "target_id": target_id,
            "reason": "E2E simulate publish",
            "project_id": project_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "approvers": [],
        }
    )
    save_approvals()
    return aid


def main() -> int:
    project_id = "GomeKu"
    env = "dev"
    channel = "1001"
    platform = "android"
    version_name = os.environ.get("E2E_VERSION_NAME", "1.0.0")

    release = _find_best_release(project_id, env, channel, platform, version_name, published_only=False)
    if not release:
        print(json.dumps({"ok": False, "error": "release not found", "version_name": version_name}))
        return 1

    scope = resolve_scope_by_inputs(project_id, env, channel)
    precheck = run_scope_precheck(scope, release)
    if not precheck.get("ok"):
        print(json.dumps({"ok": False, "step": "precheck", "precheck": precheck}, ensure_ascii=False))
        return 2

    _ensure_approval(project_id, version_name)
    bundle = create_bundle_from_publish(scope, release, published_by="e2e-simulate")
    release = dict(release)
    release["publish_status"] = "published"
    release["active_bundle_id"] = bundle.get("bundle_id")
    release["updated_at"] = datetime.now().isoformat()
    release["updated_by"] = "e2e-simulate"

    versions = project_versions_db.get(project_id) or []
    for i, item in enumerate(versions):
        if str(item.get("id") or "") == str(release.get("id") or ""):
            versions[i] = release
            break
    project_versions_db[project_id] = versions
    save_project_versions()

    out = {
        "ok": True,
        "project_id": project_id,
        "version_name": version_name,
        "version_id": release.get("id"),
        "bundle_id": bundle.get("bundle_id"),
        "scope_id": scope.get("scope_id"),
        "precheck": precheck,
        "gateway_ws": (precheck.get("network_profile_preview") or {}).get("gateway_ws"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
