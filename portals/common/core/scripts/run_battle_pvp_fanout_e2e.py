#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dual-client PVP fan-out E2E: verify BattleSpectatorFrameNotify reaches opponent."""

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


MACLIENT = Path(os.environ.get("MACLIENT_ROOT") or "E:/maclient")
SMOKE_EXE = MACLIENT / "game-server/tools/SmokeTest/bin/Debug/SmokeTest.exe"
SERVER_EXE = MACLIENT / "game-server/game-server/bin/Debug/GameServer.GameServerApp.exe"
OUT_DIR = MACLIENT / "game-server/tools/SmokeTest/artifacts/pvp-fanout-latest"
SERVER_ARGS = os.environ.get("GAME_SERVER_ARGS", "--servers=gateway-cn-1,auth-cn-1,game-cn-1,ops-cn-1")


def ws_port_open(port: int = 15050) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def ensure_gameserver(*, restart: bool = False) -> dict:
    if not SERVER_EXE.is_file():
        return {"ok": False, "error": f"GameServer exe missing: {SERVER_EXE}"}

    if restart:
        subprocess.run(
            ["taskkill", "/F", "/IM", "GameServer.GameServerApp.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        time.sleep(2)

    if not restart and ws_port_open():
        return {"ok": True, "mode": "reuse"}

    cwd = SERVER_EXE.parent
    if os.name == "nt":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Start-Process -FilePath '{SERVER_EXE}' -ArgumentList '{SERVER_ARGS}' -WorkingDirectory '{cwd}' -WindowStyle Hidden",
            ],
            check=False,
        )
    else:
        subprocess.Popen([str(SERVER_EXE), SERVER_ARGS], cwd=str(cwd))

    deadline = time.time() + 120
    while time.time() < deadline:
        if ws_port_open():
            time.sleep(3)
            return {"ok": True, "mode": "started"}
        time.sleep(1)
    return {"ok": False, "error": "ws 15050 not ready within 120s"}


def run_fanout(ws_url: str, timeout_ms: int, user_prefix: str) -> dict:
    if not SMOKE_EXE.is_file():
        return {"ok": False, "error": f"SmokeTest.exe missing: {SMOKE_EXE}"}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(SMOKE_EXE),
        "--mode=pvp-fanout",
        f"--ws={ws_url}",
        f"--timeout-ms={timeout_ms}",
        f"--user-prefix={user_prefix}",
        f"--output={OUT_DIR}",
    ]
    print("[pvp-fanout] cmd:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(SMOKE_EXE.parent))
    report_path = OUT_DIR / "pvp-fanout-report.json"
    detail: dict = {"exit_code": proc.returncode}
    if report_path.is_file():
        detail.update(json.loads(report_path.read_text(encoding="utf-8")))
    detail["ok"] = proc.returncode == 0 and detail.get("passed") is True
    return detail


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dual-client PVP fan-out verification")
    parser.add_argument("--ws", default=os.environ.get("GAME_WS", "ws://127.0.0.1:15050/ws/"))
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument("--user-prefix", default="fanout")
    parser.add_argument("--evidence", default="", help="optional evidence json path")
    parser.add_argument("--no-start-server", action="store_true")
    parser.add_argument("--restart-server", action="store_true")
    args = parser.parse_args()

    preflight = {"ok": True, "mode": "skipped"}
    if not args.no_start_server:
        preflight = ensure_gameserver(restart=args.restart_server)
        if not preflight.get("ok"):
            evidence = {
                "check": "battle_pvp_fanout",
                "ok": False,
                "error": preflight.get("error"),
                "preflight": preflight,
                "generatedUtc": datetime.now(timezone.utc).isoformat(),
            }
            out = Path(args.evidence) if args.evidence else (
                Path(__file__).resolve().parents[4] / "docs/evidence/pvp-fanout-latest.json"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(evidence, ensure_ascii=False, indent=2))
            return 1

    result = run_fanout(args.ws, args.timeout_ms, args.user_prefix)
    evidence = {
        "check": "battle_pvp_fanout",
        "ok": result.get("ok"),
        "battleId": result.get("battleId"),
        "notifyLatencyMs": result.get("notifyLatencyMs"),
        "error": result.get("error"),
        "preflight": preflight,
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
    }
    out = Path(args.evidence) if args.evidence else (
        Path(__file__).resolve().parents[4] / "docs/evidence/pvp-fanout-latest.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(f"[pvp-fanout] wrote {out}")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
