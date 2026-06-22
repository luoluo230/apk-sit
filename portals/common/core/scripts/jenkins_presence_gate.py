# -*- coding: utf-8 -*-
"""Gate T0–T1: Jenkins reachability or documented skip for dev-only publish."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    host = os.environ.get("JENKINS_GATE_HOST", "127.0.0.1")
    port = int(os.environ.get("JENKINS_GATE_PORT", "8080"))
    if _tcp(host, port):
        print(json.dumps({"ok": True, "mode": "jenkins_online", "host": host, "port": port}))
        return 0
    if os.environ.get("JENKINS_GATE_DEV_SKIP") == "1":
        print(json.dumps({"ok": True, "mode": "dev_skip", "reason": "simulate_e2e_publish path"}))
        return 0
    if os.environ.get("CLOSURE_MODE") == "1":
        rc = subprocess.call(
            [sys.executable, os.path.join(ROOT, "scripts", "simulate_e2e_publish.py"), "--mode", "fixture"],
            cwd=ROOT,
        )
        if rc == 0:
            print(json.dumps({"ok": True, "mode": "simulate_e2e_fixture", "host": host, "port": port}))
            return 0
        print(json.dumps({"ok": False, "mode": "simulate_e2e_fixture_failed", "exit_code": rc}))
        return rc
    print(
        json.dumps(
            {
                "ok": False,
                "error": f"jenkins unreachable at {host}:{port}",
                "hint": "start Jenkins or set JENKINS_GATE_DEV_SKIP=1 for dev-only",
            },
            ensure_ascii=False,
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
