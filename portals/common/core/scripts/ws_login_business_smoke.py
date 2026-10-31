#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live GameServer WS login smoke (gateway → auth relay). Logs prove black-console联调."""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _pack(message_id: int, data_obj: dict, data_type: str, seq: int = 1) -> bytes:
    body = {
        "MessageID": message_id,
        "Data": json.dumps(data_obj, ensure_ascii=False),
        "DataType": data_type,
        "SequenceId": seq,
        "RequiresAck": False,
        "IsAck": False,
        "AckSequenceId": 0,
        "Priority": 0,
        "IsChunk": False,
        "ChunkId": 0,
        "ChunkIndex": 0,
        "ChunkTotal": 0,
        "Token": "",
        "Nonce": "",
        "Signature": "",
        "ErrorCode": 0,
        "ErrorMessage": "",
    }
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(raw)) + raw


def _unpack(buf: bytes) -> dict:
    if len(buf) < 4:
        raise ValueError("frame too short")
    (n,) = struct.unpack(">I", buf[:4])
    payload = buf[4 : 4 + n]
    msg = json.loads(payload.decode("utf-8"))
    data = msg.get("Data")
    if isinstance(data, str) and data:
        try:
            msg["DataParsed"] = json.loads(data)
        except json.JSONDecodeError:
            msg["DataParsed"] = data
    return msg


def run_login(ws_url: str, username: str, password: str, timeout_sec: float) -> dict:
    from websocket import create_connection

    started = time.time()
    ws = create_connection(ws_url, timeout=timeout_sec)
    try:
        frame = _pack(
            10001,
            {
                "Username": username,
                "Password": password,
                "Device": {
                    "DeviceId": "联调-" + uuid.uuid4().hex[:8],
                    "Platform": "android",
                    "OsVersion": "联调",
                    "AppVersion": "1.0.0",
                },
            },
            "Login_c2s",
            seq=1,
        )
        ws.send_binary(frame)
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            ws.settimeout(max(0.2, deadline - time.time()))
            raw = ws.recv()
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            msg = _unpack(raw)
            mid = int(msg.get("MessageID") or 0)
            if mid == 10002:
                parsed = msg.get("DataParsed") or {}
                ok = bool(parsed.get("Success"))
                return {
                    "ok": ok,
                    "message_id": mid,
                    "success": ok,
                    "message": parsed.get("Message"),
                    "has_token": bool((parsed.get("Token") or {}).get("Token") if isinstance(parsed.get("Token"), dict) else parsed.get("Token")),
                    "elapsed_ms": int((time.time() - started) * 1000),
                    "username": username,
                    "ws_url": ws_url,
                }
            if mid in (-1, 0):
                continue
        return {"ok": False, "error": "login_timeout", "elapsed_ms": int((time.time() - started) * 1000), "ws_url": ws_url}
    finally:
        try:
            ws.close()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="WS login business smoke against live GameServer")
    parser.add_argument("--ws", default=os.environ.get("GAME_WS", "ws://127.0.0.1:15050/ws/"))
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="联调pass")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()

    user = args.user.strip() or ("e2e_" + uuid.uuid4().hex[:10])
    try:
        result = run_login(args.ws, user, args.password, args.timeout)
    except Exception as exc:
        result = {"ok": False, "error": str(exc), "ws_url": args.ws, "username": user}

    result["generatedUtc"] = datetime.now(timezone.utc).isoformat()
    result["check"] = "ws_login_business_smoke"
    print(json.dumps(result, ensure_ascii=False, indent=2))

    out = Path(args.evidence) if args.evidence else (
        Path(__file__).resolve().parents[4] / "docs/evidence/ws-login-business-smoke-latest.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ws-login] wrote {out}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
