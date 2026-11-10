#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""In-process client×server alignment SLA warn/block (COMM-P2-6)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from scripts.closure_evidence import write_evidence  # noqa: E402


def _run_matrix_cases() -> Tuple[bool, List[str]]:
    from services.release.client_server_alignment import (
        assert_alignment_allows_action,
        assess_client_server_alignment,
    )

    errors: List[str] = []
    ok_row = assess_client_server_alignment(
        {"status": "published", "payload": {"server_release_id": "s1"}},
        {"status": "deployed", "server_release_id": "s1"},
        env_key="staging",
    )
    if ok_row.get("state") != "ok":
        errors.append(f"deployed ok expected ok got {ok_row.get('state')}")

    block_row = assess_client_server_alignment(
        {"status": "published", "payload": {"server_release_id": "s1"}},
        {"status": "failed", "server_release_id": "s1"},
        env_key="production",
    )
    if block_row.get("state") != "block":
        errors.append("server failed must block")
    try:
        assert_alignment_allows_action(block_row, action="expand_gray")
        errors.append("expand_gray should raise on block")
    except ValueError:
        pass

    warn_row = assess_client_server_alignment({"status": "published"}, {}, env_key="staging")
    if warn_row.get("state") != "warn":
        errors.append("missing server link should warn when published")

    now = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(seconds=2000)).isoformat()
    sla_row = assess_client_server_alignment(
        {"status": "published", "payload": {"server_release_id": "s1"}, "updated_at": started},
        {"status": "deploying", "server_release_id": "s1", "deploy_started_at": started},
        env_key="production",
        now=now,
    )
    if sla_row.get("state") != "block":
        errors.append(f"production SLA overrun must block, got {sla_row.get('state')}")
    try:
        assert_alignment_allows_action(sla_row, action="production_publish")
        errors.append("production_publish should raise on SLA block")
    except ValueError:
        pass

    return len(errors) == 0, errors


def _run_lifecycle_hook() -> Tuple[bool, str]:
    """Prove expand_gray path imports alignment gate (publish lifecycle)."""
    from services.release import order_publish_lifecycle

    src = Path(order_publish_lifecycle.__file__).read_text(encoding="utf-8")
    if "assert_alignment_allows_action" not in src or "expand_gray" not in src:
        return False, "order_publish_lifecycle missing alignment gate"
    return True, "expand_gray imports assert_alignment_allows_action"


def main() -> int:
    cmd = "py -3 portals/common/core/scripts/client_server_alignment_e2e.py"
    ok_matrix, matrix_errors = _run_matrix_cases()
    ok_hook, hook_note = _run_lifecycle_hook()
    ok = ok_matrix and ok_hook
    notes: Dict[str, Any] = {
        "matrix_ok": ok_matrix,
        "matrix_errors": matrix_errors,
        "lifecycle_gate": hook_note,
    }
    write_evidence(
        "COMM-P2-6",
        command=cmd,
        exit_code=0 if ok else 1,
        status="DONE" if ok else "FAIL",
        notes=json.dumps(notes, ensure_ascii=False),
    )
    if not ok:
        print("FAIL", notes, file=sys.stderr)
        return 1
    print("OK", notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
