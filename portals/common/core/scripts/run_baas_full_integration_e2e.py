#!/usr/bin/env python3
# -*- coding: utf-8
"""Full BaaS casual-server integration: pytest + portal fan-out + optional Unity PlayMode."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
MACLIENT = Path(os.environ.get("MACLIENT_ROOT") or "E:/maclient")


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status < 500
    except (urllib.error.URLError, OSError):
        return False


def ensure_baas_server(portal: str) -> dict:
    host = portal.replace("http://", "").replace("https://", "").split(":")[0] or "127.0.0.1"
    port = 5004
    if ":" in portal.split("//")[-1]:
        try:
            port = int(portal.split(":")[-1].split("/")[0])
        except ValueError:
            pass
    health = portal.rstrip("/") + "/health"
    if _http_ok(health) or _port_open(host, port):
        return {"ok": True, "mode": "reuse", "portal": portal}
    script = REPO / "scripts" / "Start-BaaSStack.ps1"
    if not script.is_file():
        return {"ok": False, "error": f"Start-BaaSStack.ps1 missing: {script}"}
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Background",
    ]
    subprocess.run(cmd, cwd=str(REPO), check=False)
    deadline = time.time() + 90
    while time.time() < deadline:
        if _http_ok(health) or _port_open(host, port):
            time.sleep(2)
            return {"ok": True, "mode": "started", "portal": portal}
        time.sleep(1)
    return {"ok": False, "error": f"BaaS portal not ready: {portal}"}


def run_pytest() -> dict:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_baas_room_service.py",
        "tests/test_baas_gm_ops.py",
        "tests/test_baas_public_api.py",
        "tests/test_baas_auth.py",
        "tests/test_baas_standalone.py",
        "tests/test_server_framework_modules.py",
        "-q",
        "--tb=line",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "output_tail": proc.stdout[-2000:] + proc.stderr[-2000:]}


def run_inprocess_fanout() -> dict:
    script = ROOT / "scripts" / "run_baas_pvp_fanout_e2e.py"
    proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT))
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode}


def run_portal_fanout(portal: str, service_id: str, api_key: str) -> dict:
    script = ROOT / "scripts" / "run_baas_pvp_fanout_e2e.py"
    if not service_id or not api_key:
        return {"ok": False, "skipped": True, "error": "BAAS_E2E_SERVICE_ID / BAAS_E2E_API_KEY not set"}
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--portal",
            portal,
            "--service-id",
            service_id,
            "--api-key",
            api_key,
        ],
        cwd=str(ROOT),
    )
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode}


def run_unity_playmode(portal: str) -> dict:
    if os.environ.get("BAAS_E2E_SKIP_UNITY") == "1":
        return {"ok": True, "skipped": True}
    unity = os.environ.get("UNITY_PATH") or os.environ.get("UNITY_EDITOR") or ""
    if not unity or not Path(unity).is_file():
        return {"ok": True, "skipped": True, "reason": "UNITY_PATH not set"}
    if not (MACLIENT / "Assets/Src/HotUpdate/Tests/PlayMode/BaasRoomFanoutPlayModeTests.cs").is_file():
        return {"ok": False, "error": "PlayMode test missing in maclient"}
    log = MACLIENT / "Temp/baas-playmode-e2e.log"
    env = os.environ.copy()
    env["BAAS_E2E_PORTAL"] = portal
    cmd = [
        unity,
        "-batchmode",
        "-nographics",
        "-projectPath",
        str(MACLIENT),
        "-runTests",
        "-testPlatform",
        "PlayMode",
        "-testFilter",
        "BaasRoomFanoutPlayModeTests",
        "-logFile",
        str(log),
        "-quit",
    ]
    proc = subprocess.run(cmd, env=env, cwd=str(MACLIENT))
    tail = log.read_text(encoding="utf-8", errors="replace")[-3000:] if log.is_file() else ""
    if proc.returncode != 0 and "Set BAAS_E2E_API_KEY" in tail:
        return {"ok": True, "skipped": True, "reason": "credentials not configured"}
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "log_tail": tail}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full BaaS integration pipeline")
    parser.add_argument("--portal", default=os.environ.get("BAAS_E2E_PORTAL", "http://127.0.0.1:5004"))
    parser.add_argument("--no-start-server", action="store_true")
    args = parser.parse_args()

    report = {"checks": [], "verdict": "pass", "generatedUtc": datetime.now(timezone.utc).isoformat()}

    if not args.no_start_server:
        pre = ensure_baas_server(args.portal)
        report["checks"].append({"name": "baas_server", "ok": pre.get("ok"), "detail": pre})
        if not pre.get("ok"):
            report["verdict"] = "fail"

    for name, fn in (
        ("pytest_baas", run_pytest),
        ("fanout_in_process", run_inprocess_fanout),
    ):
        detail = fn()
        report["checks"].append({"name": name, "ok": detail.get("ok"), "detail": detail})
        if not detail.get("ok"):
            report["verdict"] = "fail"

    portal_fanout = run_portal_fanout(
        args.portal,
        os.environ.get("BAAS_E2E_SERVICE_ID", ""),
        os.environ.get("BAAS_E2E_API_KEY", ""),
    )
    report["checks"].append({"name": "fanout_portal", "ok": portal_fanout.get("ok") or portal_fanout.get("skipped"), "detail": portal_fanout})
    if not portal_fanout.get("ok") and not portal_fanout.get("skipped"):
        report["verdict"] = "fail"

    playmode = run_unity_playmode(args.portal)
    report["checks"].append({"name": "unity_playmode_fanout", "ok": playmode.get("ok") or playmode.get("skipped"), "detail": playmode})
    if not playmode.get("ok") and not playmode.get("skipped"):
        report["verdict"] = "fail"

    out = REPO / "docs/evidence/baas-full-integration-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[baas-full-e2e] wrote {out}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
