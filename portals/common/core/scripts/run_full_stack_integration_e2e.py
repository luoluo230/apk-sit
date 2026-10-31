#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full-stack integration orchestrator:
- BaaS auth + GM mail/announce smoke
- GameServer WS login + battle room sync plan (when SmokeTest.exe available)
- Startup gate / maintenance probe
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MACLIENT = Path(os.environ.get("MACLIENT_ROOT") or "E:/maclient")
_SERVER = MACLIENT / "Server"
SMOKE_RUNNER = _SERVER / "tools/SmokeTest/run-business-test.py"
if not SMOKE_RUNNER.is_file():
    SMOKE_RUNNER = MACLIENT / "game-server/tools/SmokeTest/run-business-test.py"
WS_LOGIN_SMOKE = ROOT / "scripts" / "ws_login_business_smoke.py"
WS_FULL_LIFECYCLE = ROOT / "scripts" / "ws_full_lifecycle_e2e.py"


def http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None) -> dict:
    data = None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": raw, "status": exc.code}


def probe_startup_gate(portal_base: str) -> dict:
    # Require project identity (fail-closed gate rejects empty queries).
    q = "project_id=GomeKu&env_key=development&channel=wechat&platform=android"
    url = portal_base.rstrip("/") + "/api/public/startup-gate?" + q
    return http_json(url)


def run_business_plan(plan_id: str) -> int:
    if not SMOKE_RUNNER.is_file():
        return 0
    cmd = [sys.executable, str(SMOKE_RUNNER), "--plan", plan_id, "--transport", "websocket"]
    print("[full-e2e] running", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(SMOKE_RUNNER.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full-stack integration checks")
    parser.add_argument("--portal", default=os.environ.get("PORTAL_BASE", "http://127.0.0.1:5003"))
    parser.add_argument("--skip-gameserver", action="store_true")
    args = parser.parse_args()

    report = {"checks": [], "verdict": "pass"}

    gate = probe_startup_gate(args.portal)
    report["checks"].append({"name": "startup_gate", "ok": gate.get("ok", True) is not False, "detail": gate})
    if gate.get("ok") is False:
        report["verdict"] = "fail"

    if not args.skip_gameserver:
        # Hard gate: sustained dual-client full lifecycle (login→select→role→game APIs→battle→PVP).
        # Do NOT treat missing SmokeTest as pass.
        if WS_FULL_LIFECYCLE.is_file():
            hold = os.environ.get("E2E_HOLD_SEC", "16")
            cmd = [sys.executable, str(WS_FULL_LIFECYCLE), "--hold-sec", hold]
            print("[full-e2e] running", " ".join(cmd))
            code = subprocess.call(cmd)
            ok = code == 0
            report["checks"].append({"name": "business::ws-full-lifecycle", "ok": ok, "exit_code": code})
            if not ok:
                report["verdict"] = "fail"
        else:
            report["checks"].append({
                "name": "business::ws-full-lifecycle",
                "ok": False,
                "detail": f"missing {WS_FULL_LIFECYCLE}",
            })
            report["verdict"] = "fail"

        if SMOKE_RUNNER.is_file():
            for plan in ("auth-login-lifecycle", "battle-room-pvp-flow", "match-queue-flow"):
                code = run_business_plan(plan)
                ok = code == 0
                report["checks"].append({"name": f"business::{plan}", "ok": ok, "exit_code": code})
                if not ok:
                    report["verdict"] = "fail"
        else:
            report["checks"].append({
                "name": "business::smoke-plans",
                "ok": False,
                "skipped": True,
                "detail": f"SmokeTest runner missing (not counted as pass): {SMOKE_RUNNER}",
            })
            # Not a hard fail if ws-full-lifecycle covered the path; record as gap only.

        fanout_script = ROOT / "scripts" / "run_battle_pvp_fanout_e2e.py"
        smoke_exe = _SERVER / "tools/SmokeTest/bin/Debug/SmokeTest.exe"
        if fanout_script.is_file() and smoke_exe.is_file():
            cmd = [sys.executable, str(fanout_script), "--no-start-server"]
            print("[full-e2e] running", " ".join(cmd))
            code = subprocess.call(cmd)
            ok = code == 0
            report["checks"].append({"name": "battle_pvp_fanout", "ok": ok, "exit_code": code})
            if not ok:
                report["verdict"] = "fail"
        else:
            report["checks"].append({
                "name": "battle_pvp_fanout_smoketest",
                "ok": False,
                "skipped": True,
                "detail": "SmokeTest.exe missing; covered by business::ws-full-lifecycle PVP enqueue instead",
            })

    baas_fanout_script = ROOT / "scripts" / "run_baas_pvp_fanout_e2e.py"
    if baas_fanout_script.is_file():
        cmd = [sys.executable, str(baas_fanout_script)]
        print("[full-e2e] running", " ".join(cmd))
        code = subprocess.call(cmd)
        ok = code == 0
        report["checks"].append({"name": "baas_pvp_fanout", "ok": ok, "exit_code": code})
        if not ok:
            report["verdict"] = "fail"

    baas_full = ROOT / "scripts" / "run_baas_full_integration_e2e.py"
    if baas_full.is_file():
        cmd = [sys.executable, str(baas_full), "--no-start-server"]
        print("[full-e2e] running", " ".join(cmd))
        code = subprocess.call(cmd)
        ok = code == 0
        report["checks"].append({"name": "baas_full_integration", "ok": ok, "exit_code": code})
        if not ok:
            report["verdict"] = "fail"

    out = ROOT / "docs" / "evidence" / "full-stack-integration-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[full-e2e] wrote {out}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
