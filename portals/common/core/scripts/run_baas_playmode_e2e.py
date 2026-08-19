#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Portal + Unity PlayMode BaaS room fan-out E2E orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
CORE = Path(__file__).resolve().parents[1]
MACLIENT = Path(os.environ.get("MACLIENT_ROOT") or "E:/maclient")
CREDS = CORE / "docs/evidence/baas-playmode-e2e-credentials.json"
if not CREDS.is_file():
    CREDS = REPO / "docs/evidence/baas-playmode-e2e-credentials.json"


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def ensure_baas(portal: str) -> dict:
    host = "127.0.0.1"
    port = 5004
    if "://" in portal:
        tail = portal.split("://", 1)[1]
        if ":" in tail:
            port = int(tail.split(":")[1].split("/")[0])
    health = portal.rstrip("/") + "/health"
    if _port_open(host, port):
        try:
            with urllib.request.urlopen(health, timeout=5) as resp:
                if resp.status == 200:
                    return {"ok": True, "mode": "reuse"}
        except (urllib.error.URLError, OSError):
            pass
    script = REPO / "scripts" / "Start-BaaSStack.ps1"
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Background",
            "-Port",
            str(port),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr[-500:] or proc.stdout[-500:]}
    deadline = time.time() + 90
    while time.time() < deadline:
        if _port_open(host, port):
            try:
                with urllib.request.urlopen(health, timeout=5) as resp:
                    if resp.status == 200:
                        return {"ok": True, "mode": "started"}
            except (urllib.error.URLError, OSError):
                pass
        time.sleep(1)
    return {"ok": False, "error": "health timeout"}


def seed_credentials(portal: str) -> dict:
    env = os.environ.copy()
    env["BAAS_E2E_PORTAL"] = portal
    prod_creds_path = REPO / "docs/evidence/baas-production-e2e-credentials.json"
    env["BAAS_E2E_CREDENTIALS"] = str(prod_creds_path)
    proc = subprocess.run(
        [sys.executable, str(CORE / "scripts/seed_baas_production_e2e.py")],
        cwd=str(CORE),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr or proc.stdout}
    if not prod_creds_path.is_file():
        return {"ok": False, "error": f"credentials missing: {prod_creds_path}"}
    return {"ok": True, "credentials": json.loads(prod_creds_path.read_text(encoding="utf-8"))}


def find_unity() -> Path | None:
    for key in ("UNITY_EXE", "UNITY_PATH", "UNITY_EDITOR"):
        val = os.environ.get(key, "").strip()
        if val and Path(val).is_file():
            return Path(val)
    ver_file = MACLIENT / "ProjectSettings/ProjectVersion.txt"
    ver = ""
    if ver_file.is_file():
        for line in ver_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("m_EditorVersion:"):
                ver = line.split(":", 1)[1].strip()
                break
    hub = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Unity" / "Hub" / "Editor"
    if ver:
        exe = hub / ver / "Editor" / "Unity.exe"
        if exe.is_file():
            return exe
    if hub.is_dir():
        for d in sorted(hub.iterdir(), reverse=True):
            exe = d / "Editor" / "Unity.exe"
            if exe.is_file():
                return exe
    return None


def run_playmode(portal: str, creds: dict) -> dict:
    unity = find_unity()
    if not unity:
        return {"ok": False, "error": "Unity.exe not found"}
    log = MACLIENT / "Temp/baas-playmode-e2e.log"
    results = MACLIENT / "Temp/baas-playmode-results.xml"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["BAAS_E2E_PORTAL"] = portal
    env["BAAS_E2E_SERVICE_ID"] = creds["service_id"]
    env["BAAS_E2E_API_KEY"] = creds["api_key"]
    env["BAAS_E2E_GAME_ID"] = creds.get("game_id", "")
    env["BAAS_E2E_GAME_KEY"] = creds.get("game_key", "")
    cmd = [
        str(unity),
        "-batchmode",
        "-nographics",
        "-projectPath",
        str(MACLIENT),
        "-runTests",
        "-testPlatform",
        "PlayMode",
        "-assemblyNames",
        "MAClient.Network.Baas.PlayModeTests",
        "-testFilter",
        "BaasPveArenaPlayModeTests|BaasRoomFanoutPlayModeTests",
        "-testResults",
        str(results),
        "-logFile",
        str(log),
    ]
    print("[playmode] running Unity PlayMode Baas PVE/Arena + Room fanout tests")
    proc = subprocess.Popen(cmd, env=env, cwd=str(MACLIENT))
    deadline = time.time() + 300
    while time.time() < deadline:
        if results.is_file() and proc.poll() is not None:
            break
        if results.is_file():
            text = results.read_text(encoding="utf-8", errors="replace")
            if "test-run" in text or "testcase" in text:
                time.sleep(2)
                break
        time.sleep(1)
    if proc.poll() is None:
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    tail = log.read_text(encoding="utf-8", errors="replace")[-4000:] if log.is_file() else ""
    xml = results.read_text(encoding="utf-8", errors="replace") if results.is_file() else ""
    passed = proc.returncode == 0 and results.is_file() and (
        'result="Passed"' in xml or 'passed="1"' in xml.lower() or "result=\"Pass\"" in xml
    )
    return {
        "ok": passed,
        "exit_code": proc.returncode,
        "log_tail": tail,
        "results_xml": xml[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portal", default="http://127.0.0.1:5004")
    parser.add_argument("--skip-server", action="store_true")
    args = parser.parse_args()

    report = {"checks": [], "verdict": "pass"}
    if not args.skip_server:
        srv = ensure_baas(args.portal)
        report["checks"].append({"name": "baas_server", "ok": srv.get("ok"), "detail": srv})
        if not srv.get("ok"):
            report["verdict"] = "fail"
            _write(report)
            return 1

    creds_detail = seed_credentials(args.portal)
    report["checks"].append({"name": "seed_credentials", "ok": creds_detail.get("ok"), "detail": creds_detail})
    if not creds_detail.get("ok"):
        report["verdict"] = "fail"
        _write(report)
        return 1

    fanout = subprocess.run(
        [
            sys.executable,
            str(CORE / "scripts/run_baas_pvp_fanout_e2e.py"),
            "--portal",
            args.portal,
            "--service-id",
            creds_detail["credentials"]["service_id"],
            "--api-key",
            creds_detail["credentials"]["api_key"],
        ],
        cwd=str(CORE),
    )
    report["checks"].append({"name": "portal_fanout_http", "ok": fanout.returncode == 0, "exit_code": fanout.returncode})

    play = run_playmode(args.portal, creds_detail["credentials"])
    report["checks"].append({"name": "unity_playmode", "ok": play.get("ok"), "detail": play})
    if not play.get("ok"):
        report["verdict"] = "fail"
    if fanout.returncode != 0:
        report["verdict"] = "fail"

    _write(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "pass" else 1


def _write(report: dict) -> None:
    out = REPO / "docs/evidence/baas-playmode-e2e-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[playmode-e2e] wrote {out}")


if __name__ == "__main__":
    raise SystemExit(main())
