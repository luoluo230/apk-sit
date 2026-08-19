# -*- coding: utf-8
"""CLI tool for BaaS room/battle integration testing."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _request(method: str, url: str, headers: dict, body: dict | None = None) -> dict:
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for key, val in headers.items():
        req.add_header(key, val)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {"ok": False, "error": payload, "status": exc.code}


def main() -> int:
    p = argparse.ArgumentParser(description="BaaS room/battle integration tester")
    p.add_argument("--base", default=os.getenv("BAAS_BASE_URL", "http://127.0.0.1:5003"))
    p.add_argument("--service-id", default=os.getenv("BAAS_SERVICE_ID", "casual-demo"))
    p.add_argument("--api-key", default=os.getenv("BAAS_API_KEY", ""))
    p.add_argument("--action", choices=("guest", "create", "join", "match", "sync", "start", "finish"), default="match")
    p.add_argument("--room-id", default="")
    p.add_argument("--invite-code", default="")
    p.add_argument("--player-name", default="cli-player")
    args = p.parse_args()

    base = str(args.base).rstrip("/")
    sid = args.service_id
    prefix = f"{base}/api/baas/v1/{sid}"
    headers = {"X-Baas-Api-Key": args.api_key, "X-Baas-Service-Id": sid}

    if args.action == "guest":
        out = _request("POST", f"{prefix}/auth/guest", headers, {"display_name": args.player_name})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") else 1

    guest = _request("POST", f"{prefix}/auth/guest", headers, {"display_name": args.player_name})
    if not guest.get("ok"):
        print(json.dumps(guest, ensure_ascii=False, indent=2))
        return 1
    token = guest["data"]["token"]
    player_id = guest["data"]["player_id"]
    auth = {
        **headers,
        "Authorization": f"Bearer {token}",
        "X-Baas-Player-Id": player_id,
    }

    if args.action == "create":
        out = _request("POST", f"{prefix}/rooms", auth, {"visibility": "public", "battle_mode": "pvp_1v1"})
    elif args.action == "join":
        out = _request(
            "POST",
            f"{prefix}/rooms/join",
            auth,
            {"room_id": args.room_id, "invite_code": args.invite_code},
        )
    elif args.action == "match":
        out = _request("POST", f"{prefix}/pvp/matchmake", auth, {"battle_mode": "pvp_1v1"})
    elif args.action == "start":
        out = _request("POST", f"{prefix}/rooms/{args.room_id}/start-battle", auth, {})
    elif args.action == "sync":
        out = _request("POST", f"{prefix}/pvp/rooms/{args.room_id}/state", auth, {"state": {"hp": 100, "x": 1}})
    elif args.action == "finish":
        out = _request("POST", f"{prefix}/rooms/{args.room_id}/finish-battle", auth, {"result": {"winner": player_id}})
    else:
        out = {"ok": False, "error": "unsupported"}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
