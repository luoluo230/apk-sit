#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""COMM-P1-4: production create without rollback baseline must BLOCK."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from scripts.closure_evidence import write_evidence  # noqa: E402


def main() -> int:
    cmd = "py -3 portals/common/core/scripts/gray_baseline_e2e.py"
    notes: Dict[str, Any] = {
        "observability_live_scrape": "tracked_separately_as_GAP-P2-03-E2E-03",
    }

    from services.release import order_crud

    src = Path(order_crud.__file__).read_text(encoding="utf-8")
    contract = "production 创建发布单必须指定 rollback_baseline_bundle_id" in src
    notes["source_contract"] = contract

    fake_version = {
        "id": "v-probe",
        "version_code": "99999",
        "platform": "android",
        "env_key": "production",
        "channel_id": "dev",
        "channel": "dev",
    }
    payload = {
        "env_key": "production",
        "channel_id": "dev",
        "platform": "android",
        "version_id": "v-probe",
        "version_code": "99999",
        "rollback_baseline_bundle_id": "",
    }

    err = ""
    baseline_blocked = False
    with patch.object(order_crud, "_find_version", return_value=fake_version), patch(
        "services.release.order_crud.resolve_scope",
        return_value={"active_bundle_id": ""},
    ), patch(
        "services.release.order_crud.resolve_channel_id",
        side_effect=lambda _p, c: c,
    ), patch(
        "services.release.order_crud.is_platform_enabled_for_project",
        return_value=True,
    ), patch(
        "services.release.order_crud.normalize_release_env_key",
        return_value="production",
    ), patch(
        "services.release.order_crud.projects_db",
        {"ProbeProj": {"id": "ProbeProj"}},
    ), patch(
        "services.release.release_policy_service.apply_release_defaults_to_payload",
        side_effect=lambda _p, _e, pl: pl,
    ):
        try:
            order_crud.create_release_order("ProbeProj", payload, "admin")
        except ValueError as exc:
            err = str(exc)
            baseline_blocked = "rollback_baseline_bundle_id" in err or "回滚基线" in err
        except Exception as exc:
            err = str(exc)
            notes["unexpected"] = type(exc).__name__ + ": " + err[:240]

    notes["baseline_blocked_runtime"] = baseline_blocked
    notes["error"] = err[:400]
    ok = contract and baseline_blocked
    status = "DONE" if ok else "PARTIAL"
    write_evidence("COMM-P1-4", command=cmd, exit_code=0 if ok else 1, status=status, notes=notes)
    print("COMM-P1-4", status, notes)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
