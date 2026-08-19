# -*- coding: utf-8 -*-
"""HTTP bridge from Portal BaaS GM to local GameServer Ops API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


def _ops_base() -> str:
    host = os.environ.get("GAME_OPS_HOST", "127.0.0.1")
    port = int(os.environ.get("GAME_OPS_PORT", "5504"))
    return f"http://{host}:{port}"


def _ops_headers(actor: str, reason: str = "baas-gm") -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Ops-Key": os.environ.get("GAME_OPS_WRITE_KEY", "ops-write-key-2026"),
        "X-Ops-Actor": actor or "gm",
        "X-Ops-Role": "SuperAdmin",
        "X-Ops-Reason": reason or "baas-gm",
    }


def _ops_request(path: str, *, method: str = "GET", body: Optional[dict] = None, actor: str = "gm") -> Dict[str, Any]:
    url = _ops_base().rstrip("/") + path
    data = None
    headers = _ops_headers(actor)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"success": True}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {"success": False, "message": raw, "status": exc.code}
        detail.setdefault("success", False)
        detail["status"] = exc.code
        return detail
    except urllib.error.URLError as exc:
        return {"success": False, "message": str(exc.reason or exc), "reachable": False}


def ops_health(actor: str = "gm") -> Dict[str, Any]:
    return _ops_request("/ops/ready", actor=actor)


def kick_session(session_or_token: str, *, actor: str = "gm") -> Dict[str, Any]:
    token = str(session_or_token or "").strip()
    if not token:
        raise ValueError("session_or_token 必填")
    qs = urllib.parse.quote(token, safe="")
    return _ops_request(f"/ops/kick-session?sessionId={qs}", method="POST", actor=actor)


def execute_action(
    action_type: str,
    *,
    target: str = "*",
    domain: str = "gateway",
    payload: Optional[dict] = None,
    actor: str = "gm",
    dry_run: bool = False,
) -> Dict[str, Any]:
    body = {
        "ActionType": action_type,
        "Target": target or "*",
        "Domain": domain,
        "Payload": payload or {},
        "DryRun": bool(dry_run),
    }
    return _ops_request("/ops/action", method="POST", body=body, actor=actor)


def trigger_maintenance(message: str, *, target: str = "gateway-cn-1", actor: str = "gm") -> Dict[str, Any]:
    msg = str(message or "服务器维护中，请稍后再试").strip()
    return execute_action("maintenance", target=target, payload={"message": msg}, actor=actor)


def stop_gateway(message: str = "", *, actor: str = "gm") -> Dict[str, Any]:
    if message:
        trigger_maintenance(message, actor=actor)
    return execute_action("stop", target="gateway-cn-1", actor=actor)


def stop_all_servers(*, actor: str = "gm") -> Dict[str, Any]:
    return execute_action("stop_all", target="*", actor=actor)
