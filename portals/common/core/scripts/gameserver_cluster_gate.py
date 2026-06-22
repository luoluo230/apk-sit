# -*- coding: utf-8 -*-
"""Verify GameServer cluster (--all or partial) exposes gateway WS."""

from __future__ import annotations

import json
import os
import socket
import sys


def _tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    require_all = os.environ.get("GAMESERVER_CLUSTER_GATE_STRICT", "").strip() == "1"
    checks = {
        "gateway_ws": _tcp("127.0.0.1", 15050),
        "ops_http": _tcp("127.0.0.1", 5054),
        "auth_http": _tcp("127.0.0.1", 5051),
    }
    ok = checks["gateway_ws"] and (all(checks.values()) if require_all else True)
    print(json.dumps({"ok": ok, "checks": checks, "strict": require_all}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
