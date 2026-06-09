#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Admin 管理端回归门禁 — 模块化拆分前后必跑。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], timeout: int = 600) -> dict:
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    return {
        "cmd": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-800:],
        "stderr_tail": (proc.stderr or "")[-400:],
        "ok": proc.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Admin regression gate")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-live", action="store_true", help="Skip live pytest and agent control")
    args = parser.parse_args()
    py = sys.executable
    rows = []

    rows.append(_run([py, "-m", "py_compile", "portals/common/core/routes/gm_legacy.py"], timeout=120))
    ops_routes = list((ROOT / "portals/common/core/routes/ops").glob("*.py"))
    if ops_routes:
        rows.append(_run([py, "-m", "py_compile"] + [str(p.relative_to(ROOT)).replace("\\", "/") for p in ops_routes]))
    ops_svc = list((ROOT / "portals/common/core/services/ops").glob("*.py"))
    if ops_svc:
        rows.append(_run([py, "-m", "py_compile"] + [str(p.relative_to(ROOT)).replace("\\", "/") for p in ops_svc]))

    rows.append(_run([py, "-m", "pytest", "tests/ops_distributed", "-m", "fast", "-q"], timeout=120))
    rows.append(_run([py, "dev/tools/ops_platform_smoke.py", "--project", "GomeKu", "--strict"], timeout=300))
    rows.append(_run([py, "dev/tools/ops_workbench_chain_audit.py", "--project", "GomeKu", "--strict"], timeout=300))

    if not args.skip_live:
        rows.append(_run([py, "dev/tools/_verify_agent_control.py"], timeout=300))

    fails = [r for r in rows if not r["ok"]]
    out = {"total": len(rows), "failed": len(fails), "results": rows}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if fails and args.strict:
        return 1
    return 0 if not fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
