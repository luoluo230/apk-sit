# -*- coding: utf-8 -*-
"""Transport login matrix smoke: HTTP / WS login probe / TCP / KCP reachability."""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_BASE = os.environ.get("TRANSPORT_MATRIX_BASE_URL", "http://127.0.0.1:5003")
DEFAULT_HOST = os.environ.get("TRANSPORT_MATRIX_HOST", "127.0.0.1")
DEFAULT_GATEWAY_WS_PORT = int(os.environ.get("GATEWAY_WS_PORT", "15050"))
DEFAULT_AUTH_TCP_PORT = int(os.environ.get("AUTH_TCP_PORT", "15501"))
DEFAULT_GAME_TCP_PORT = int(os.environ.get("GAME_TCP_PORT", "15502"))
DEFAULT_KCP_UDP_PORT = int(os.environ.get("KCP_UDP_PORT", "5602"))


def _import_smoke_probes():
    try:
        from services.ops.runtime_orchestrator import (
            _business_test_login_probe,
            _probe_tcp_open,
            _ws_handshake_probe,
        )

        return _business_test_login_probe, _probe_tcp_open, _ws_handshake_probe
    except Exception:
        return None, None, None


def _tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    _, probe_tcp_open, _ = _import_smoke_probes()
    if probe_tcp_open is not None:
        return probe_tcp_open(host, port, timeout=timeout)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _udp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(b"\x00", (host, port))
        return True
    except OSError:
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def _http_health(base_url: str) -> tuple[bool, str]:
    url = f"{base_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            ok = resp.status == 200 and body.get("status") == "ok"
            return ok, json.dumps(body, ensure_ascii=False)
    except Exception as exc:
        return False, str(exc)


def _ws_login_probe(host: str, gateway_port: int, auth_port: int) -> tuple[bool, str]:
    login_probe, _, ws_probe = _import_smoke_probes()
    if login_probe is not None:
        return login_probe(host, gateway_port, host, auth_port)

    if ws_probe is not None:
        ws_ok, ws_detail = ws_probe(host, gateway_port)
        if not ws_ok:
            return False, "gateway_ws_failed:" + ws_detail
        if auth_port > 0 and not _tcp_open(host, auth_port, timeout=0.6):
            return False, f"auth_cluster_relay_unreachable:{host}:{auth_port}"
        return True, "gateway_ws_and_auth_relay_ok"

    try:
        sock = socket.create_connection((host, gateway_port), timeout=3.0)
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        req = (
            f"GET /ws/ HTTP/1.1\r\n"
            f"Host: {host}:{gateway_port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        sock.settimeout(3.0)
        data = sock.recv(256).decode("latin-1", errors="ignore")
        sock.close()
        ws_ok = "101" in data and "Upgrade" in data
        if not ws_ok:
            return False, data.split("\r\n", 1)[0] if data else "empty"
        if auth_port > 0 and not _tcp_open(host, auth_port, timeout=0.6):
            return False, f"auth_cluster_relay_unreachable:{host}:{auth_port}"
        return True, "gateway_ws_and_auth_relay_ok"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    base = DEFAULT_BASE
    host = DEFAULT_HOST
    print("=== Transport Login Matrix ===")
    print(f"base={base} host={host}")

    results = []
    ok_http, detail_http = _http_health(base)
    results.append({"transport": "HTTP", "ok": ok_http, "detail": detail_http})

    ok_ws_login, detail_ws_login = _ws_login_probe(host, DEFAULT_GATEWAY_WS_PORT, DEFAULT_AUTH_TCP_PORT)
    results.append(
        {
            "transport": "WS_LOGIN",
            "ok": ok_ws_login,
            "detail": detail_ws_login,
            "endpoint": f"{host}:{DEFAULT_GATEWAY_WS_PORT}",
            "auth_relay": f"{host}:{DEFAULT_AUTH_TCP_PORT}",
            "probe": "SmokeTest._business_test_login_probe",
        }
    )

    ok_auth = _tcp_open(host, DEFAULT_AUTH_TCP_PORT)
    results.append({"transport": "TCP_AUTH", "ok": ok_auth, "endpoint": f"{host}:{DEFAULT_AUTH_TCP_PORT}"})

    ok_game = _tcp_open(host, DEFAULT_GAME_TCP_PORT)
    results.append({"transport": "TCP_GAME", "ok": ok_game, "endpoint": f"{host}:{DEFAULT_GAME_TCP_PORT}"})

    ok_kcp = _udp_open(host, DEFAULT_KCP_UDP_PORT)
    results.append({"transport": "KCP_UDP", "ok": ok_kcp, "endpoint": f"{host}:{DEFAULT_KCP_UDP_PORT}"})

    failed = [row for row in results if not row.get("ok")]
    print(json.dumps({"results": results, "failed": len(failed)}, ensure_ascii=False, indent=2))

    try:
        from services.client_telemetry import record_gate_pass

        record_gate_pass("transport_login_matrix", passed=not failed)
    except Exception:
        pass

    if failed:
        print(f"FAIL: {len(failed)} transport checks failed")
        return 1

    print("PASS: all transport checks succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
