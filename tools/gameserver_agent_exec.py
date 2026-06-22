#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local GameServer job execution for ops-platform agent pull/report loop."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

_SERVICE_IDS = ("gateway-cn-1", "auth-cn-1", "game-cn-1", "ops-cn-1")
_TCP_PORTS = {
    "gateway-cn-1": 15050,
    "ops-cn-1": 5504,
}
_RELAY_PORTS = {
    "auth-cn-1": 15501,
    "game-cn-1": 15502,
}
_INFRA_PORTS = {
    "redis-cache-cn-1": 6379,
    "mongo-db-cn-1": 27017,
}


def _resolve_repo() -> Path:
    env = str(os.getenv("GAME_SERVER_REPO") or "").strip()
    if env:
        return Path(env)
    for candidate in (
        Path("E:/maclient/game-server"),
        ROOT.parent / "maclient" / "game-server",
        ROOT / ".." / "maclient" / "game-server",
    ):
        try:
            p = candidate.resolve()
            if (p / "game-server" / "GameServerApp.csproj").is_file():
                return p
        except Exception:
            continue
    return Path("E:/maclient/game-server")


def _resolve_exe(repo: Path) -> Tuple[str, str]:
    names = ("GameServer.GameServerApp.exe", "GameServerApp.exe")
    for config in ("Debug", "Release"):
        cfg_dir = repo / "game-server" / "bin" / config
        for name in names:
            exe = cfg_dir / name
            if exe.is_file():
                return str(exe), str(cfg_dir)
        dll = cfg_dir / "GameServer.GameServerApp.dll"
        if dll.is_file():
            return str(dll), str(cfg_dir)
    return "", ""


def _instance_dir(repo: Path, service_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", service_id) or "gameserver"
    return repo / "tools" / "SmokeTest" / "artifacts" / "instances" / safe


def _prepare_instance(repo: Path, service_id: str) -> Tuple[str, str]:
    src_exe, src_dir = _resolve_exe(repo)
    if not src_exe:
        return "", ""
    inst = _instance_dir(repo, service_id)
    inst.mkdir(parents=True, exist_ok=True)
    dst_exe = inst / Path(src_exe).name
    if not dst_exe.is_file() or dst_exe.stat().st_mtime < Path(src_exe).stat().st_mtime:
        import shutil

        shutil.copy2(src_exe, dst_exe)
    for name in ("cluster.json", "appsettings.json"):
        src = repo / "config" / name
        if src.is_file():
            import shutil

            for dst in (inst / name, inst / "config" / name):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    return str(dst_exe), str(inst)


def _probe_tcp(host: str, port: int, timeout: float = 0.4) -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_pid(service_id: str) -> int:
    needle = f"--servers={service_id}"
    if os.name != "nt":
        return 0
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='GameServer.GameServerApp.exe'\" | "
                "Select-Object ProcessId,CommandLine | ForEach-Object { "
                f"if ($_.CommandLine -like '*{needle}*') {{ $_.ProcessId }} }}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        for line in reversed((proc.stdout or "").splitlines()):
            text = line.strip()
            if text.isdigit():
                return int(text)
    except Exception:
        pass
    return 0


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10, check=False)
        else:
            os.kill(pid, 9)
    except Exception:
        pass


def _service_live(service_id: str, host: str = "127.0.0.1") -> bool:
    sid = str(service_id or "").strip().lower()
    port = int(_TCP_PORTS.get(sid) or 0)
    relay = int(_RELAY_PORTS.get(sid) or 0)
    infra = int(_INFRA_PORTS.get(sid) or 0)
    if port > 0 and _probe_tcp(host, port):
        return True
    if relay > 0 and _probe_tcp(host, relay):
        return True
    if infra > 0 and _probe_tcp(host, infra):
        return True
    pid = _find_pid(sid)
    return pid > 0


def _launch_service(repo: Path, service_id: str, reason: str = "", timeout_sec: int = 120) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    if sid not in _SERVICE_IDS:
        return {"ok": False, "message": f"unsupported service_id: {sid}"}
    if _service_live(sid):
        return {"ok": True, "message": f"{sid} already running", "already_running": True}
    exe, cwd = _prepare_instance(repo, sid)
    if not exe:
        return {"ok": False, "message": "GameServer.GameServerApp.exe not found"}
    args = [exe, f"--servers={sid}", "--headless", "--headless-seconds=86400"]
    log_path = _instance_dir(repo, sid) / "agent-launch.log"
    with open(log_path, "a", encoding="utf-8") as fp:
        fp.write(f"\n[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] launch reason={reason} cmd={' '.join(args)}\n")
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    deadline = time.time() + max(20, int(timeout_sec))
    tcp_port = int(_TCP_PORTS.get(sid) or 0)
    relay_port = int(_RELAY_PORTS.get(sid) or 0)
    while time.time() < deadline:
        if proc.poll() is not None:
            return {"ok": False, "message": f"{sid} exited code={proc.returncode}", "pid": proc.pid}
        if tcp_port > 0 and _probe_tcp("127.0.0.1", tcp_port):
            return {"ok": True, "message": f"{sid} ready port={tcp_port}", "pid": proc.pid}
        if relay_port > 0 and _probe_tcp("127.0.0.1", relay_port):
            return {"ok": True, "message": f"{sid} relay ready port={relay_port}", "pid": proc.pid}
        if proc.pid and time.time() > deadline - max(10, timeout_sec - 8):
            return {"ok": True, "message": f"{sid} started pid={proc.pid}", "pid": proc.pid}
        time.sleep(0.8)
    return {"ok": False, "message": f"{sid} launch timeout", "pid": proc.pid}


def _stop_service(service_id: str) -> Dict[str, Any]:
    sid = str(service_id or "").strip().lower()
    pid = _find_pid(sid)
    if pid <= 0:
        return {"ok": True, "message": f"{sid} not running", "already_stopped": True}
    _kill_pid(pid)
    time.sleep(0.6)
    if _find_pid(sid) > 0:
        return {"ok": False, "message": f"{sid} stop failed pid={pid}"}
    return {"ok": True, "message": f"{sid} stopped pid={pid}"}


def execute_ops_job(job: Dict[str, Any], repo: Optional[Path] = None) -> Dict[str, Any]:
    repo_path = repo or _resolve_repo()
    action = str(job.get("action_type") or "").strip().lower()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    desired = str(
        payload.get("desired_server_id")
        or payload.get("desired_service_id")
        or job.get("target")
        or job.get("node_id")
        or ""
    ).strip().lower()
    reason = str(job.get("reason") or payload.get("reason") or "agent-job").strip()
    if desired in _INFRA_PORTS:
        if action in ("start", "start_all", "smoke_test", "stress_test", "restart"):
            if _service_live(desired):
                return {
                    "ok": True,
                    "message": f"{desired} already running port={_INFRA_PORTS[desired]}",
                    "already_running": True,
                }
            return {
                "ok": False,
                "message": f"{desired} is not listening on port {_INFRA_PORTS[desired]}; start the managed infrastructure service first",
            }
        if action in ("status", "health_check", "ready_check", "runtime_snapshot"):
            live = _service_live(desired)
            return {
                "ok": live,
                "message": f"{desired} {'ready' if live else 'offline'} port={_INFRA_PORTS[desired]}",
                "services": {desired: live},
            }
        if action in ("stop", "stop_all"):
            return {
                "ok": False,
                "message": f"{desired} is externally managed; stop it from the infrastructure service manager",
            }
    if action in ("start", "start_all", "smoke_test", "stress_test", "restart"):
        if action == "restart":
            stop = _stop_service(desired)
            if not stop.get("ok"):
                return stop
        return _launch_service(repo_path, desired, reason)
    if action == "stop":
        return _stop_service(desired)
    if action == "stop_all":
        last: Dict[str, Any] = {"ok": True, "message": "no services"}
        for sid in _SERVICE_IDS:
            last = _stop_service(sid)
        return last
    if action in ("status", "health_check", "ready_check", "runtime_snapshot"):
        rows = {sid: _service_live(sid) for sid in _SERVICE_IDS}
        return {"ok": True, "message": "status ready", "services": rows}
    return {"ok": False, "message": f"unsupported action: {action}"}
