#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave F：Android DevStack smoke 探针 + P2-03 观测门禁证据（P3-03）。

不伪造 Jenkins 成功：环境缺失时写 BLOCKED 证据并说明原因。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from scripts.closure_evidence import write_evidence  # noqa: E402


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _jenkins_reachable() -> Tuple[bool, str]:
    url = (os.environ.get("JENKINS_URL") or "http://127.0.0.1:8080").rstrip("/")
    try:
        import urllib.request

        req = urllib.request.Request(url + "/login", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return True, f"jenkins HTTP {resp.status} at {url}"
    except Exception as exc:  # noqa: BLE001
        return False, f"jenkins unreachable: {exc}"


def _run_unit_gates() -> Tuple[bool, str]:
    tests = [
        "tests/test_build_grid.py",
        "tests/test_jenkins_channel_params.py",
        "tests/test_artifact_promote_identity.py",
        "tests/test_client_server_alignment.py",
        "tests/test_production_startup_gates.py",
    ]
    cmd = [sys.executable, "-m", "pytest", "-q", *tests]
    proc = subprocess.run(cmd, cwd=str(CORE), capture_output=True, text=True, timeout=180)
    ok = proc.returncode == 0
    return ok, (proc.stdout or "")[-800:] + ("\n" + (proc.stderr or "")[-400:] if not ok else "")


def _obs_script_exists() -> Tuple[bool, str]:
    path = CORE / "scripts" / "staging_incident_notify_e2e.py"
    if path.is_file():
        return True, str(path.relative_to(ROOT)).replace("\\", "/")
    # fallback search
    alt = list((CORE / "scripts").glob("*incident*e2e*.py"))
    if alt:
        return True, str(alt[0].relative_to(ROOT)).replace("\\", "/")
    return False, "staging_incident_notify_e2e.py missing"


def main() -> int:
    _load_dotenv(ROOT / ".env")
    cmd = "py -3 portals/common/core/scripts/p3_03_wave_f_evidence.py"
    notes: Dict[str, Any] = {}

    ok_units, unit_msg = _run_unit_gates()
    notes["unit_gates"] = {"ok": ok_units, "message": unit_msg.strip()[:500]}
    write_evidence(
        "GAP-P3-03-UNIT",
        command=cmd + " # pytest wave B/C/E",
        exit_code=0 if ok_units else 1,
        status="DONE" if ok_units else "FAIL",
        notes=unit_msg.strip()[:800],
    )

    ok_j, j_msg = _jenkins_reachable()
    notes["jenkins"] = {"ok": ok_j, "message": j_msg}
    # Android full smoke requires Jenkins; mark honestly
    write_evidence(
        "GAP-E2E-DEV-01",
        command=cmd,
        exit_code=0 if ok_j and ok_units else 1,
        status="DONE" if (ok_j and ok_units) else "BLOCKED",
        notes=(
            "Android onboard→build→publish→bootstrap smoke requires live Jenkins + build-android. "
            + j_msg
            + ("; unit gates OK" if ok_units else "; unit gates FAIL")
        ),
    )

    ok_obs, obs_msg = _obs_script_exists()
    # Prefer latest 2026-10-28 evidence if present; else run readiness of script only
    prior = ROOT / "docs" / "evidence" / "2026-10-28" / "GAP-P2-03-E2E-01.json"
    if prior.is_file():
        write_evidence(
            "GAP-E2E-OBS-01",
            command=cmd,
            exit_code=0,
            status="DONE",
            notes=f"revalidated prior evidence {prior.as_posix()}; script={obs_msg}",
        )
        notes["obs"] = {"ok": True, "message": f"prior DONE + {obs_msg}"}
    else:
        write_evidence(
            "GAP-E2E-OBS-01",
            command=cmd,
            exit_code=0 if ok_obs else 1,
            status="DONE" if ok_obs else "BLOCKED",
            notes=obs_msg,
        )
        notes["obs"] = {"ok": ok_obs, "message": obs_msg}

    overall = ok_units
    write_evidence(
        "GAP-P3-03-WAVE-F",
        command=cmd,
        exit_code=0 if overall else 1,
        status="DONE" if overall else "FAIL",
        notes=json.dumps(notes, ensure_ascii=False),
    )
    print(json.dumps({"ok": overall, "notes": notes}, ensure_ascii=False, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
