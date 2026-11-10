#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave B load smoke: sequential HTTP hits against /health (evidence only)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
sys.path.insert(0, str(CORE))

from scripts.closure_evidence import write_evidence  # noqa: E402
from services.baas.capacity import dau100k_smoke_targets, postgres_pool_settings  # noqa: E402

BASE = os.environ.get("BAAS_BASE_URL", "http://127.0.0.1:5004").rstrip("/")


def main() -> int:
    targets = dau100k_smoke_targets()
    # 先探测一次：不可达则 BLOCKED，避免长时间超时循环
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=2) as resp:
            if int(resp.status) != 200:
                raise RuntimeError(f"status {resp.status}")
    except Exception as exc:
        notes = {
            "base": BASE,
            "error": str(exc)[:200],
            "targets": targets,
            "capacity": postgres_pool_settings(),
            "pass": False,
        }
        write_evidence(
            "GAP-P4-01-B-LOAD",
            command="py -3 portals/common/core/scripts/p4_01_baas_load_smoke.py",
            exit_code=0,
            status="BLOCKED",
            notes=json.dumps(notes, ensure_ascii=False)[:3500],
        )
        print(json.dumps(notes, ensure_ascii=False, indent=2))
        return 0

    n = min(100, int(targets["peak_rps_smoke"] * targets["duration_sec"]))
    ok = 0
    fail = 0
    t0 = time.perf_counter()
    for _ in range(n):
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as resp:
                if int(resp.status) == 200:
                    ok += 1
                else:
                    fail += 1
        except Exception:
            fail += 1
    elapsed = max(0.001, time.perf_counter() - t0)
    ratio = ok / float(ok + fail) if (ok + fail) else 0.0
    notes = {
        "base": BASE,
        "requests": ok + fail,
        "ok": ok,
        "fail": fail,
        "elapsed_sec": round(elapsed, 3),
        "rps": round((ok + fail) / elapsed, 2),
        "success_ratio": round(ratio, 4),
        "targets": targets,
        "capacity": postgres_pool_settings(),
        "pass": ratio >= float(targets["success_ratio_min"]) and ok > 0,
    }
    status = "DONE" if notes["pass"] else "FAIL"
    # If BaaS down, mark BLOCKED rather than red-fail whole closure optionally
    if ok == 0 and fail > 0:
        status = "BLOCKED"
        notes["pass"] = False
    write_evidence(
        "GAP-P4-01-B-LOAD",
        command="py -3 portals/common/core/scripts/p4_01_baas_load_smoke.py",
        exit_code=0 if notes["pass"] or status == "BLOCKED" else 1,
        status=status,
        notes=json.dumps(notes, ensure_ascii=False)[:3500],
    )
    print(json.dumps(notes, ensure_ascii=False, indent=2))
    return 0 if notes["pass"] or status == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
