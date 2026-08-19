#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dual-client BaaS casual-room PVP frame fan-out E2E."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

_TEST_PROJECT = "baas_pvp_fanout_e2e"
_GAME_ID = "baas-pvp-fanout-game"
_GAME_KEY = "baas-pvp-fanout-key"


def http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None) -> dict:
    data = None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"ok": False, "error": raw, "status": exc.code}
        payload.setdefault("status", exc.code)
        return payload


def _enable_pvp(service_id: str) -> None:
    from models.db import get_cursor, init_db

    init_db()
    with get_cursor() as cur:
        cur.execute(
            "UPDATE baas_services SET feature_flags=? WHERE service_id=?",
            ('{"login":true,"cloudsave":true,"mail":true,"announce":true,"pvp":true}', service_id),
        )


def _bootstrap_in_process() -> tuple:
    from models.data import projects_db
    from repositories.admin import projects_repo
    from services.baas import room_service
    from services.baas.service_crud import ensure_service, rotate_api_secret

    from app_new import app

    projects_db[_TEST_PROJECT] = {
        "name": "BaaS PVP Fanout E2E",
        "game_id": _GAME_ID,
        "game_key": _GAME_KEY,
        "server_mode": "casual_baas",
        "status": "active",
        "created_by": "admin",
    }
    projects_repo.upsert_project(_TEST_PROJECT, projects_db[_TEST_PROJECT])
    svc, api_secret = ensure_service(_TEST_PROJECT, "development", actor="admin")
    service_id = svc["service_id"]
    if not api_secret:
        api_secret, _ = rotate_api_secret(_TEST_PROJECT, service_id)
    _enable_pvp(service_id)
    room_service._rooms.clear()
    room_service._replays.clear()
    app.config["WTF_CSRF_ENABLED"] = False
    return app.test_client(), service_id, api_secret


def _guest(client, base: str, headers: dict, name: str) -> tuple[dict, dict]:
    resp = client.post(f"{base}/auth/guest", headers=headers, json={"display_name": name})
    payload = resp.get_json()
    if resp.status_code != 200 or not payload.get("ok"):
        raise RuntimeError(f"guest login failed: {payload}")
    data = payload["data"]
    auth = dict(headers)
    auth["Authorization"] = f"Bearer {data['token']}"
    auth["X-Baas-Player-Id"] = data["player_id"]
    return data, auth


def run_in_process(*, wait_ms: int = 3000) -> dict:
    from services.baas import room_service

    client, service_id, api_secret = _bootstrap_in_process()
    base = f"/api/baas/v1/{service_id}"
    headers = {"X-Baas-Api-Key": api_secret, "Content-Type": "application/json"}

    p1, h1 = _guest(client, base, headers, "FanA")
    p2, h2 = _guest(client, base, headers, "FanB")

    m1 = client.post(f"{base}/pvp/matchmake", headers=h1, json={"battle_mode": "pvp_1v1"})
    room1 = m1.get_json()["data"]
    room_id = room1["room_id"]

    m2 = client.post(f"{base}/pvp/matchmake", headers=h2, json={"battle_mode": "pvp_1v1"})
    room2 = m2.get_json()["data"]
    if room2["room_id"] != room_id:
        raise RuntimeError(f"matchmake mismatch: {room1} vs {room2}")

    start = client.post(f"{base}/rooms/{room_id}/start-battle", headers=h1, json={})
    battle_id = start.get_json()["data"]["battle_id"]

    result: dict = {}
    started = threading.Event()

    def poll_opponent():
        started.set()
        t0 = time.perf_counter()
        polled = room_service.poll_frames(
            service_id,
            room_id,
            since_seq=0,
            wait_ms=wait_ms,
            exclude_player_id=p2["player_id"],
        )
        result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        result["payload"] = polled

    worker = threading.Thread(target=poll_opponent, daemon=True)
    worker.start()
    started.wait(timeout=2)
    time.sleep(0.05)
    push = client.post(
        f"{base}/rooms/{room_id}/frames",
        headers=h1,
        json={"frame": {"action": "attack", "skill": 101}},
    )
    worker.join(timeout=max(5, wait_ms / 1000 + 2))

    push_body = push.get_json()
    polled = result.get("payload") or {}
    frames = polled.get("frames") or []
    passed = (
        push.status_code == 200
        and push_body.get("ok") is True
        and polled.get("polled") is True
        and len(frames) == 1
        and frames[0].get("player_id") == p1["player_id"]
    )
    return {
        "ok": passed,
        "passed": passed,
        "mode": "in_process",
        "service_id": service_id,
        "room_id": room_id,
        "battle_id": battle_id,
        "notifyLatencyMs": result.get("latency_ms"),
        "frame_count": len(frames),
        "push_ok": push_body.get("ok"),
        "polled": polled.get("polled"),
    }


def run_portal(portal_base: str, service_id: str, api_key: str, *, wait_ms: int = 3000) -> dict:
    base = portal_base.rstrip("/") + f"/api/baas/v1/{service_id}"
    headers = {"X-Baas-Api-Key": api_key, "Content-Type": "application/json"}

    def guest(name: str):
        out = http_json(f"{base}/auth/guest", method="POST", body={"display_name": name}, headers=headers)
        if not out.get("ok"):
            raise RuntimeError(f"guest login failed: {out}")
        data = out["data"]
        auth = dict(headers)
        auth["Authorization"] = f"Bearer {data['token']}"
        auth["X-Baas-Player-Id"] = data["player_id"]
        return data, auth

    p1, h1 = guest("FanA")
    p2, h2 = guest("FanB")
    room1 = http_json(f"{base}/pvp/matchmake", method="POST", body={"battle_mode": "pvp_1v1"}, headers=h1)["data"]
    room_id = room1["room_id"]
    room2 = http_json(f"{base}/pvp/matchmake", method="POST", body={"battle_mode": "pvp_1v1"}, headers=h2)["data"]
    if room2["room_id"] != room_id:
        raise RuntimeError(f"matchmake mismatch: {room1} vs {room2}")

    started = http_json(f"{base}/rooms/{room_id}/start-battle", method="POST", body={}, headers=h1)
    battle_id = (started.get("data") or {}).get("battle_id")

    result: dict = {}
    started_evt = threading.Event()

    def poll_opponent():
        started_evt.set()
        t0 = time.perf_counter()
        polled = http_json(
            f"{base}/rooms/{room_id}/frames?since_seq=0&wait_ms={wait_ms}",
            headers={**headers, "X-Baas-Player-Id": p2["player_id"]},
        )
        result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        result["payload"] = polled.get("data") or {}

    worker = threading.Thread(target=poll_opponent, daemon=True)
    worker.start()
    started_evt.wait(timeout=2)
    time.sleep(0.05)
    push = http_json(
        f"{base}/rooms/{room_id}/frames",
        method="POST",
        body={"frame": {"action": "attack", "skill": 101}},
        headers=h1,
    )
    worker.join(timeout=max(5, wait_ms / 1000 + 2))

    polled = result.get("payload") or {}
    frames = polled.get("frames") or []
    passed = (
        push.get("ok") is True
        and polled.get("polled") is True
        and len(frames) == 1
        and frames[0].get("player_id") == p1["player_id"]
    )
    return {
        "ok": passed,
        "passed": passed,
        "mode": "portal",
        "portal": portal_base,
        "service_id": service_id,
        "room_id": room_id,
        "battle_id": battle_id,
        "notifyLatencyMs": result.get("latency_ms"),
        "frame_count": len(frames),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BaaS casual-room dual-client frame fan-out E2E")
    parser.add_argument("--portal", default="", help="portal base URL; omit for in-process mode")
    parser.add_argument("--service-id", default=os.environ.get("BAAS_SERVICE_ID", ""))
    parser.add_argument("--api-key", default=os.environ.get("BAAS_API_KEY", ""))
    parser.add_argument("--wait-ms", type=int, default=3000)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()

    try:
        if args.portal:
            if not args.service_id or not args.api_key:
                raise RuntimeError("--portal mode requires --service-id and --api-key")
            detail = run_portal(args.portal, args.service_id, args.api_key, wait_ms=args.wait_ms)
        else:
            detail = run_in_process(wait_ms=args.wait_ms)
    except Exception as exc:
        detail = {"ok": False, "passed": False, "error": str(exc)}

    evidence = {
        "check": "baas_pvp_fanout",
        "ok": detail.get("ok") is True,
        "passed": detail.get("passed") is True,
        "detail": detail,
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
    }
    out = Path(args.evidence) if args.evidence else ROOT.parents[2] / "docs/evidence/baas-pvp-fanout-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(f"[baas-pvp-fanout] wrote {out}")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
