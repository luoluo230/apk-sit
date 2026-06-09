#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightly distributed acceptance runner for apk-site + game-server."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


def _probe(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def preflight(game_server_repo: str, base: str) -> Dict[str, Any]:
    repo = Path(game_server_repo)
    exe = repo / "game-server" / "bin" / "Debug" / "GameServer.GameServerApp.exe"
    return {
        "admin": _probe("127.0.0.1", 5003),
        "gateway_ws": _probe("127.0.0.1", 15050),
        "auth_relay": _probe("127.0.0.1", 15501),
        "game_relay": _probe("127.0.0.1", 15502),
        "mongo": _probe("127.0.0.1", 27017),
        "redis": _probe("127.0.0.1", 6379),
        "gameserver_exe": exe.is_file(),
        "base": base,
    }


def start_four_processes(repo: str) -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT / "tools"))
    from gameserver_agent_exec import execute_ops_job

    results = {}
    for sid in ("gateway-cn-1", "auth-cn-1", "ops-cn-1", "game-cn-1"):
        results[sid] = execute_ops_job(
            {"action_type": "start", "node_id": sid, "payload": {"desired_server_id": sid}, "reason": "acceptance"},
            repo=Path(repo),
        )
        time.sleep(0.5)
    return results


def run_pytest_live() -> Dict[str, Any]:
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    junit = reports / "distributed.xml"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/ops_distributed",
        "-m",
        "live",
        "-q",
        f"--junitxml={junit}",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
        "junit": str(junit),
    }


def run_gameserver_script(repo: str) -> Dict[str, Any]:
    ps1 = Path(repo) / "tools" / "SmokeTest" / "DistributedAcceptance.ps1"
    health_ps1 = Path(repo) / "tools" / "Check-Cluster-Health.ps1"
    sections: Dict[str, Any] = {}
    if health_ps1.is_file():
        health = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(health_ps1),
                "-Distributed",
            ],
            cwd=str(health_ps1.parent),
            capture_output=True,
            text=True,
            timeout=120,
        )
        sections["cluster_health"] = {
            "exit_code": health.returncode,
            "stdout": health.stdout[-2000:],
            "stderr": health.stderr[-500:],
        }
    if not ps1.is_file():
        sections["distributed_acceptance"] = {"skipped": True, "reason": "DistributedAcceptance.ps1 missing"}
        return sections
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
        cwd=str(ps1.parent),
        capture_output=True,
        text=True,
        timeout=300,
    )
    sections["distributed_acceptance"] = {
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-3000:],
        "stderr": proc.stderr[-1000:],
    }
    return sections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-server-repo", default=os.getenv("GAME_SERVER_REPO", "E:/maclient/game-server"))
    parser.add_argument("--base", default=os.getenv("OPS_BASE", "http://127.0.0.1:5003"))
    parser.add_argument("--start-topology", action="store_true")
    parser.add_argument("--skip-gameserver-ps1", action="store_true")
    args = parser.parse_args()

    report: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight(args.game_server_repo, args.base),
        "sections": {},
    }

    if args.start_topology:
        report["sections"]["start_topology"] = start_four_processes(args.game_server_repo)
        time.sleep(3)

    report["sections"]["pytest_live"] = run_pytest_live()
    if not args.skip_gameserver_ps1:
        report["sections"]["gameserver_ps1"] = run_gameserver_script(args.game_server_repo)

    ok = report["sections"]["pytest_live"]["exit_code"] == 0
    gs_bundle = report["sections"].get("gameserver_ps1") or {}
    health = gs_bundle.get("cluster_health") or {}
    if health and health.get("exit_code", 1) != 0:
        ok = False
    dist = gs_bundle.get("distributed_acceptance") or {}
    if not dist.get("skipped") and dist.get("exit_code", 1) != 0:
        ok = False
    report["ok"] = ok
    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    out_dir = ROOT / "data" / "acceptance_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ("distributed-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + ".json")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": ok, "report": str(out_path)}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
