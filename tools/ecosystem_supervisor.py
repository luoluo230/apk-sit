#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动与 game-server cluster.json 对齐的多 Agent 拉取循环（macOS/Linux）。

每个 cluster 节点起一个 local_ops_agent 子进程，使用 ops-write-key-2026 与 apk-site 通信。
与 game-server tools/ServerAgent/OpsPlatformBridge 使用同一套 API。

Usage:
  python3 tools/ecosystem_supervisor.py --daemon
  python3 tools/ecosystem_supervisor.py --once --loops 120
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
AGENT_SCRIPT = ROOT / "tools" / "local_ops_agent.py"
DEFAULT_REPO = Path("/Users/wangling/Desktop/MyGame/GameClient/game-server")
TOKEN = "ops-write-key-2026"
PY = sys.executable


def _repo(explicit: str) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.getenv("GAME_SERVER_REPO", "").strip()
    if env and Path(env).is_dir():
        return Path(env)
    if DEFAULT_REPO.is_dir():
        return DEFAULT_REPO
    return DEFAULT_REPO


def _servers(repo: Path) -> List[Dict[str, Any]]:
    path = repo / "config" / "cluster.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [s for s in (data.get("Servers") or []) if isinstance(s, dict)]


def _agent_port(base_port: int, index: int) -> int:
    return base_port + index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5003")
    parser.add_argument("--project", default="GomeKu")
    parser.add_argument("--game-server-repo", default="")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--once", action="store_true", help="run each agent once and exit")
    parser.add_argument("--loops", type=int, default=0, help="agent pull loops (0=daemon default 9999)")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--agent-base-port", type=int, default=19100)
    args = parser.parse_args()

    repo = _repo(args.game_server_repo)
    servers = _servers(repo)
    if not servers:
        print(f"no servers in {repo}/config/cluster.json", file=sys.stderr)
        return 1

    loops = args.loops if args.loops > 0 else (40 if args.once else 9999)
    procs: List[subprocess.Popen] = []

    def spawn_all() -> None:
        for idx, srv in enumerate(servers):
            sid = str(srv.get("ServerId") or "").strip()
            if not sid:
                continue
            game_port = int(srv.get("Port") or 0)
            agent_port = _agent_port(args.agent_base_port, idx)
            cmd = [
                PY,
                str(AGENT_SCRIPT),
                "--base", args.base.rstrip("/"),
                "--node-id", sid,
                "--agent-id", f"agent-{sid}",
                "--token", TOKEN,
                "--project-id", args.project,
                "--device-id", "ecosystem-supervisor",
                "--port", str(game_port if game_port > 0 else agent_port),
                "--loops", str(loops),
                "--interval", str(args.interval),
            ]
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL if args.daemon else None, stderr=subprocess.DEVNULL if args.daemon else None)
            procs.append(p)
            print(f"started agent-{sid} pid={p.pid} probe_port={game_port or agent_port}")

    def stop_all(*_args: object) -> None:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    spawn_all()
    if args.once:
        for p in procs:
            p.wait()
        return 0

    print(f"supervisor running ({len(procs)} agents). Ctrl+C to stop.")
    while True:
        time.sleep(5)
        for p in procs:
            if p.poll() is not None:
                print(f"agent pid={p.pid} exited code={p.returncode}, restarting...")
                stop_all()
                procs.clear()
                spawn_all()
                break


if __name__ == "__main__":
    raise SystemExit(main())
