#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Master Plan Closure gate — requires evidence JSON per GAP ID."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from scripts.closure_evidence import evidence_status, write_evidence  # noqa: E402

# Required GAP IDs from PLAN_CLOSURE_STATUS.md (Wave 7 = all DONE)
REQUIRED_GAPS = [
    "GAP-P0-02-PRE-01",
    "GAP-P0-OPS-01",
    "GAP-P0-02-PRE-02",
    "GAP-P0-01-DOD-01",
    "GAP-P0-01-CI-01",
    "GAP-P0-01-SEC-02",
    "GAP-P0-SEC-01",
    "W-P0-2",
    "W-P0-5",
    "GAP-P0-02-DOD-01",
    "GAP-P0-DB-01",
    "GAP-P0-02-S6-02",
    "GAP-P0-02-S6-01",
    "GAP-P0-02-S2-01",
    "GAP-P0-DB-02",
    "GAP-P0-02-S3-01",
    "GAP-P0-02-S4-01",
    "GAP-P0-02-DOD-02",
    "GAP-P0-02-S5-01",
    "GAP-E2E-MG-01",
    "GAP-P1-01-DOD-01",
    "GAP-P1-01-DOC-01",
    "GAP-E2E-DEV-01",
    "GAP-P1-02-E2E-01",
    "GAP-P1-02-E2E-02",
    "GAP-P1-04-E2E-01",
    "GAP-P1-04-REV-01",
    "GAP-P1-05-OPT-01",
    "GAP-P1-05-REV-01",
    "GAP-P2-01-OUT-01",
    "GAP-P2-01-OUT-02",
    "GAP-P2-01-E2E-01",
    "GAP-P2-01-S5-01",
    "GAP-P2-01-REV-01",
    "GAP-P2-02-E2E-01",
    "GAP-P2-02-OUT-01",
    "GAP-P2-03-E2E-01",
    "GAP-P2-03-E2E-02",
    "GAP-P2-03-E2E-03",
    "GAP-P2-03-OPS-01",
    "W-P1-2",
    "W-P2-1",
    "W-P2-2",
    "C-P1-1",
    "C-P1-2",
    "C-P1-3",
    "C-P1-4",
]

# Explicit external block until provisioning checklist complete
BLOCKED_UNTIL_PROVISIONING = {"GAP-P2-02-E2E-01", "C-P1-4"}


def _run_subgate(script: str, gap_id: str, extra_args: list[str] | None = None) -> int:
    path = os.path.join(_CORE, "scripts", script)
    cmd = [sys.executable, path] + (extra_args or [])
    proc = subprocess.run(cmd, cwd=_CORE, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    write_evidence(
        gap_id,
        command=" ".join(cmd),
        exit_code=proc.returncode,
        status="DONE" if proc.returncode == 0 else "FAIL",
    )
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan Closure master gate")
    parser.add_argument("--run-subgates", action="store_true", help="Run automated sub-gates first")
    parser.add_argument("--allow-blocked", action="store_true", help="Treat BLOCKED iOS gaps as skip")
    args = parser.parse_args()

    if args.run_subgates:
        subgates = [
            ("production_secret_gate.py", "GAP-P0-01-CI-01"),
            ("registry_integration_smoke.py", "GAP-P0-02-DOD-02"),
            ("release_order_stress_gate.py", "GAP-P0-02-S3-01"),
        ]
        for script, gap in subgates:
            script_path = os.path.join(_CORE, "scripts", script)
            if os.path.isfile(script_path):
                code = _run_subgate(script, gap)
                if code != 0:
                    print(f"subgate failed: {script}", file=sys.stderr)

    missing = []
    blocked = []
    failed = []
    for gap_id in REQUIRED_GAPS:
        st = evidence_status(gap_id)
        if st == "DONE":
            continue
        if gap_id in BLOCKED_UNTIL_PROVISIONING and st in ("MISSING", "BLOCKED"):
            blocked.append(gap_id)
            continue
        if st in ("FAIL", "BLOCKED"):
            failed.append(gap_id)
        else:
            missing.append(gap_id)

    print("=== Plan Closure Master Gate ===")
    print(f"required: {len(REQUIRED_GAPS)}")
    done = len(REQUIRED_GAPS) - len(missing) - len(failed) - len(blocked)
    print(f"done: {done}")
    if blocked:
        print(f"blocked (iOS provisioning): {len(blocked)}")
        for g in blocked:
            print(f"  BLOCKED {g}")
    if missing:
        print(f"missing evidence: {len(missing)}")
        for g in missing[:30]:
            print(f"  MISSING {g}")
        if len(missing) > 30:
            print(f"  ... and {len(missing) - 30} more")
    if failed:
        print(f"failed: {len(failed)}")
        for g in failed:
            print(f"  FAIL {g}")

    if missing or failed:
        return 1
    if blocked and not args.allow_blocked:
        print("Master gate: iOS gaps blocked — run ios_provisioning_checklist.md first")
        return 1
    print("plan_closure_gate PASS")
    write_evidence(
        "MASTER-CLOSURE",
        command="run_plan_closure_gate.py",
        exit_code=0,
        notes=f"all {done} gaps with evidence",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
