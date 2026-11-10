#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave A：本地 Postgres 双进程 release_order 可见性（COMM-P0-1 / W-P0-4）。

复用 p3_03_wave_a_prod_evidence 的检查逻辑；从仓库根 `.env` 读取 DATABASE_URL。
生产多 worker 运维签字不在本脚本范围（见 OPEN_ITEMS_MASTER COMM-P0-1）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
ROOT = CORE.parents[2]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from scripts.closure_evidence import write_evidence  # noqa: E402

CMD = "py -3 portals/common/core/scripts/wave_a_pg_multi_worker_gate.py"
PARENT = ROOT / "portals" / "common" / "core" / "scripts" / "p3_03_wave_a_prod_evidence.py"


def _run_parent() -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(PARENT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = (proc.stdout or "").strip()
    checks: dict = {}
    if out:
        try:
            payload = json.loads(out)
            checks = payload.get("checks") or {}
        except json.JSONDecodeError:
            checks = {"parse_error": out[:500]}
    return proc.returncode, checks


def main() -> int:
    code, checks = _run_parent()
    secrets = (checks.get("secrets_fail_fast") or {}).get("ok") is True
    pg = (checks.get("postgres_live") or {}).get("ok") is True
    mw = (checks.get("multi_worker_read") or {}).get("ok") is True
    mw_msg = str((checks.get("multi_worker_read") or {}).get("message") or "")

    write_evidence(
        "W-P0-4",
        command=CMD,
        exit_code=0 if mw else 1,
        status="DONE" if mw else "PARTIAL",
        notes=mw_msg or json.dumps(checks, ensure_ascii=False),
    )

    comm_ok = secrets and pg and mw
    comm_notes = json.dumps(
        {
            "secrets_fail_fast": checks.get("secrets_fail_fast"),
            "postgres_live": checks.get("postgres_live"),
            "multi_worker_read": checks.get("multi_worker_read"),
            "remaining_for_full_done": "production multi-worker deploy sign-off (ops); this gate proves local PG two-process only",
        },
        ensure_ascii=False,
    )
    write_evidence(
        "COMM-P0-1",
        command=CMD,
        exit_code=0 if comm_ok else 1,
        status="PARTIAL" if comm_ok else "FAIL",
        notes=comm_notes,
    )

    print(json.dumps({"exit_parent": code, "checks": checks, "w_p0_4": mw, "comm_p0_1_partial": comm_ok}, ensure_ascii=False, indent=2))
    return 0 if mw else 1


if __name__ == "__main__":
    raise SystemExit(main())
