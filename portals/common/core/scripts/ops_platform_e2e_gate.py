# -*- coding: utf-8 -*-
"""CI gate: ops platform overview/diagnostics/actions/agents/governance (T-C09–C12, T-D07)."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("GAME_OPS_TIMEOUT_SECONDS", "1")


def main() -> int:
    from app_new import app
    from data.repositories.user_repository import UserRepository
    from services.ops.cluster_health_bridge import collect_cluster_health

    repo = UserRepository()
    repo.reload()
    users = repo.list_all()
    username = next(iter(users.keys()), "admin")
    errors: list[str] = []

    cluster = collect_cluster_health(operator=username)
    metrics = cluster.get("metrics") if isinstance(cluster.get("metrics"), list) else []
    if len(metrics) != 9:
        errors.append(f"cluster_health metrics expected 9, got {len(metrics)}")

    project_id = os.environ.get("OPS_GATE_PROJECT_ID", "GomeKu")

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = username

        catalog = client.get("/api/ops-platform/action-catalog")
        if catalog.status_code != 200:
            errors.append(f"action catalog status {catalog.status_code}")

        validate = client.post(
            "/api/ops-platform/actions/validate",
            json={
                "action": "health_check",
                "project_id": project_id,
                "env_key": "development",
                "dry_run": True,
            },
        )
        if validate.status_code not in (200, 400):
            errors.append(f"validate dry_run status {validate.status_code}")

        from services.ops.modules import diagnostics, agent_control, change_governance

        summary = diagnostics.build_summary(project_id=project_id, env_key="development")
        if not isinstance(summary, dict):
            errors.append("diagnostics summary not dict")
        elif not summary.get("cluster_health") and not summary.get("nodes"):
            errors.append("diagnostics summary missing cluster_health/nodes")

        rules = diagnostics.list_rules()
        if int(rules.get("count") or 0) < 3:
            errors.append("diagnostics rules too few")

        agent_summary = agent_control.build_control_plane_summary()
        if not agent_summary.get("ok"):
            errors.append("agent_control summary not ok")

        upsert = client.post(
            "/api/ops-platform/agents/upsert",
            json={
                "agent_id": "closure-gate-agent",
                "display_name": "Closure Gate Agent",
                "project_id": project_id,
                "create_if_missing": True,
            },
        )
        if upsert.status_code not in (200, 404):
            errors.append(f"agent upsert status {upsert.status_code}")

        gov = change_governance.build_summary(project_id=project_id, env_key="development")
        if not gov.get("ok"):
            errors.append("change_governance summary not ok")

        freeze_on = client.post(
            "/api/ops-platform/change-governance/freeze",
            json={
                "project_id": project_id,
                "active": True,
                "reason": "closure-gate-test",
            },
        )
        if freeze_on.status_code != 200:
            errors.append(f"freeze on status {freeze_on.status_code}")

        freeze_off = client.post(
            "/api/ops-platform/change-governance/freeze",
            json={
                "project_id": project_id,
                "active": False,
                "reason": "closure-gate-cleanup",
            },
        )
        if freeze_off.status_code != 200:
            errors.append(f"freeze off status {freeze_off.status_code}")

        policy = agent_control.get_policy()
        if not policy.get("ok"):
            errors.append("agent policy not ok")

    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "cluster_metrics": len(metrics)}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
