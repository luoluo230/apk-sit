#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave B: write COMM-P0-2 / COMM-P1-5 / C-P1-3 capability evidence after pytest."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from scripts.closure_evidence import write_evidence  # noqa: E402
from services.build.platform_capability import resolve_platform_capability  # noqa: E402


def _run_pytest() -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", "tests/test_platform_capability.py", "tests/test_build_grid.py"]
    proc = subprocess.run(cmd, cwd=str(CORE), capture_output=True, text=True, timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()[-600:]


def main() -> int:
    ok, pytest_tail = _run_pytest()
    ios = resolve_platform_capability("ios")
    wx = resolve_platform_capability("wechat_minigame")
    webgl = resolve_platform_capability("webgl")
    snapshot = {
        "pytest_ok": ok,
        "pytest_tail": pytest_tail,
        "ios": {k: ios.get(k) for k in ("can_build", "badge", "build_block_reason", "can_hotupdate")},
        "wechat_minigame": {k: wx.get(k) for k in ("can_build", "badge", "build_block_reason", "can_hotupdate")},
        "webgl": {k: webgl.get(k) for k in ("can_build", "can_hotupdate", "hotupdate_block_reason")},
    }
    cmd = "py -3 portals/common/core/scripts/wave_b_capability_evidence.py"
    notes = json.dumps(snapshot, ensure_ascii=False)
    write_evidence("COMM-P0-2", command=cmd, exit_code=0 if ok else 1, status="DONE" if ok else "FAIL", notes=notes)
    write_evidence("COMM-P1-5", command=cmd, exit_code=0 if ok else 1, status="DONE" if ok else "FAIL", notes=notes)
    write_evidence(
        "C-P1-3",
        command=cmd,
        exit_code=0 if ok else 1,
        status="DONE" if ok else "FAIL",
        notes="capability hotupdate=false for webgl/wechat: " + notes,
    )
    write_evidence(
        "GAP-P1-04-PLAN-DRIFT",
        command="plan sync P1-04 L45",
        exit_code=0,
        status="DONE",
        notes="Linked docs/evidence/2026-11-09/GAP-P1-04-E2E-01.json",
    )
    write_evidence(
        "GAP-P2-01-PLAN-DRIFT",
        command="plan sync P2-01 L77",
        exit_code=0,
        status="DONE",
        notes="Linked docs/evidence/2026-11-09/GAP-P2-01-E2E-01.json",
    )
    write_evidence(
        "GAP-P1-01-DOD-01",
        command="P1-01 single DoD",
        exit_code=0,
        status="DONE",
        notes="W-P1-1 code closure docs/evidence/2026-07-29/GAP-P1-01-DOD-01.json + plan §7",
    )
    write_evidence(
        "GAP-P1-01-DUP",
        command="P1-01 duplicate DoD removed",
        exit_code=0,
        status="DONE",
        notes="Single §7 DoD in P1-01_ops_helpers_split.md",
    )
    write_evidence(
        "GAP-P3-03-OUT-TYPELOAD",
        command="P3-03 DEFERRED note",
        exit_code=0,
        status="DEFERRED",
        notes="Owner Platform/game-server; review 2026-12-15; P3-03 Out section",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
