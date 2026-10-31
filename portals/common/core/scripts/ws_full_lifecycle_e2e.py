#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全流程持续联调客户端（真实挂会话，禁止秒断充绿）:
  登录 → 选服 → 创角 → 心跳保活 → 大厅/档案/背包/英雄/抽卡/商店/任务/竞技场
  → 进战斗 → 双端 PVP 匹配(90001) → 保持连接 hold 秒

黑窗口会持续打日志；gateway / auth / game 节点应同时有业务流量。
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


def pack(message_id: int, data_obj: Any, data_type: str, *, token: str = "", seq: int = 1) -> bytes:
    body = {
        "MessageID": message_id,
        "Data": json.dumps(data_obj if data_obj is not None else {}, ensure_ascii=False),
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
        "Token": token or "",
        "Nonce": "",
        "Signature": "",
        "ErrorCode": 0,
        "ErrorMessage": "",
    }
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(raw)) + raw


def unpack(buf: bytes) -> dict:
    if isinstance(buf, str):
        buf = buf.encode("utf-8")
    if len(buf) < 4:
        raise ValueError("frame too short")
    (n,) = struct.unpack(">I", buf[:4])
    msg = json.loads(buf[4 : 4 + n].decode("utf-8"))
    data = msg.get("Data")
    if isinstance(data, str) and data:
        try:
            msg["DataParsed"] = json.loads(data)
        except json.JSONDecodeError:
            msg["DataParsed"] = data
    elif isinstance(data, dict):
        msg["DataParsed"] = data
    return msg


class SessionClient:
    def __init__(self, ws_url: str, name: str, timeout: float = 12.0):
        from websocket import create_connection

        self.name = name
        self.ws_url = ws_url
        self.timeout = timeout
        self.seq = 0
        self.token = ""
        self.server_id = ""
        self.player_id = 0
        self.nickname = ""
        self.ws = create_connection(ws_url, timeout=timeout)
        log(f"[{name}] CONNECT {ws_url}")

    def close(self) -> None:
        try:
            self.ws.close()
            log(f"[{self.name}] CLOSE")
        except Exception:
            pass

    def request(self, mid: int, data: Any, dtype: str, expect: int, *, label: str) -> dict:
        self.seq += 1
        frame = pack(mid, data, dtype, token=self.token, seq=self.seq)
        log(f"[{self.name}] >> {label} id={mid} seq={self.seq}")
        self.ws.settimeout(self.timeout)
        self.ws.send_binary(frame)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            remaining = max(0.2, deadline - time.time())
            self.ws.settimeout(remaining)
            raw = self.ws.recv()
            msg = unpack(raw)
            rid = int(msg.get("MessageID") or 0)
            if rid in (-1, 0):
                continue
            parsed = msg.get("DataParsed") if isinstance(msg.get("DataParsed"), dict) else {}
            ok_hint = parsed.get("Success")
            log(
                f"[{self.name}] << {label} id={rid} success={ok_hint} "
                f"msg={str(parsed.get('Message') or '')[:80]}"
            )
            if rid == expect:
                return msg
            # keep draining unexpected notifies until expect or timeout
        raise TimeoutError(f"{self.name} timeout waiting {expect} for {label}")

    def heartbeat(self) -> dict:
        return self.request(10007, {}, "Heartbeat_c2s", 10008, label="heartbeat")


def pick_server_id(login_parsed: dict) -> str:
    servers = login_parsed.get("ServerList") or []
    for s in servers:
        if isinstance(s, dict) and s.get("ServerId"):
            status = str(s.get("Status") or "").lower()
            if "mainten" in status:
                continue
            return str(s["ServerId"])
    return str(login_parsed.get("LastServerId") or "s1")


def run_player_flow(ws_url: str, name: str, hold_sec: float, password: str) -> dict:
    steps: list[dict] = []
    user = f"full_{name}_{uuid.uuid4().hex[:8]}"
    client = SessionClient(ws_url, name)
    t0 = time.time()
    try:
        # 1 login
        login = client.request(
            10001,
            {
                "Username": user,
                "Password": password,
                "Device": {
                    "Platform": "android",
                    "DeviceId": f"联调-{name}-{uuid.uuid4().hex[:6]}",
                    "ClientVersion": "1.0.0",
                },
            },
            "Login_c2s",
            10002,
            label="login",
        )
        lp = login.get("DataParsed") or {}
        ok = bool(lp.get("Success"))
        token_obj = lp.get("Token") or {}
        client.token = (token_obj.get("Token") if isinstance(token_obj, dict) else token_obj) or ""
        steps.append({"step": "login", "ok": ok and bool(client.token), "user": user})
        if not (ok and client.token):
            raise RuntimeError(f"login failed: {lp}")

        # 2 select server
        server_id = pick_server_id(lp)
        client.server_id = server_id
        sel = client.request(
            10003,
            {"ServerId": server_id},
            "SelectServer_c2s",
            10004,
            label="select_server",
        )
        sp = sel.get("DataParsed") or {}
        steps.append({"step": "select_server", "ok": bool(sp.get("Success")), "server_id": server_id})
        if not sp.get("Success"):
            raise RuntimeError(f"select_server failed: {sp}")

        # 3 create role if needed
        profile = sp.get("Profile")
        if not profile:
            nick = f"联调{name}{uuid.uuid4().hex[:4]}"
            cre = client.request(
                10005,
                {"ServerId": server_id, "Nickname": nick, "Avatar": "default"},
                "CreateRole_c2s",
                10006,
                label="create_role",
            )
            cp = cre.get("DataParsed") or {}
            profile = cp.get("Profile")
            client.nickname = nick
            steps.append({"step": "create_role", "ok": bool(cp.get("Success")), "nickname": nick})
            if not cp.get("Success"):
                raise RuntimeError(f"create_role failed: {cp}")
        else:
            client.nickname = (profile or {}).get("NickName") or (profile or {}).get("Nickname") or ""
            steps.append({"step": "create_role", "ok": True, "skipped": True, "reason": "profile_exists"})

        if isinstance(profile, dict):
            client.player_id = int(profile.get("PlayerId") or 0)

        # 4 game-bound queries (must hit game-cn-1 via cluster relay)
        game_calls = [
            (10013, {}, "GetLobbyInfo_c2s", 10014, "lobby"),
            (10011, {}, "GetPlayerProfile_c2s", 10012, "profile"),
            (10021, {}, "GetInventory_c2s", 10022, "inventory"),
            (10031, {}, "GetHeroList_c2s", 10032, "heroes"),
            (10101, {}, "GetGachaInfo_c2s", 10102, "gacha"),
            (10105, {}, "GetShopInfo_c2s", 10106, "shop"),
            (10121, {}, "GetTaskList_c2s", 10122, "tasks"),
            (10089, {}, "GetArenaInfo_c2s", 10090, "arena"),
            (10061, {}, "GetCampaignInfo_c2s", 10062, "campaign"),
        ]
        for mid, data, dtype, expect, label in game_calls:
            last_err = ""
            ok_step = False
            for attempt in range(1, 3):
                try:
                    resp = client.request(mid, data, dtype, expect, label=f"{label}#{attempt}")
                    parsed = resp.get("DataParsed") if isinstance(resp.get("DataParsed"), dict) else {}
                    # some s2c have no Success field — treat any matching response as ok
                    ok_step = True
                    if "Success" in parsed:
                        ok_step = bool(parsed.get("Success"))
                    msg = str(parsed.get("Message") or "")
                    # Multi-console nodes share one cluster log file; transient lock is not a protocol fail.
                    if (not ok_step) and ("正由另一进程使用" in msg or "being used by another process" in msg.lower()):
                        last_err = msg
                        time.sleep(0.4)
                        continue
                    break
                except Exception as exc:
                    last_err = str(exc)
                    time.sleep(0.4)
            steps.append(
                {"step": label, "ok": ok_step, "message_id": expect, **({"error": last_err} if not ok_step and last_err else {})}
            )

        # 5 enter battle (PVE smoke stage)
        try:
            battle = client.request(
                10081,
                {
                    "StageId": "stage_1",
                    "BattleMode": "PVE",
                    "SyncMode": 0,
                    "Formation": [],
                    "ClientTime": int(time.time() * 1000),
                    "Custom": "",
                },
                "EnterBattle_c2s",
                10082,
                label="enter_battle",
            )
            bp = battle.get("DataParsed") or {}
            steps.append(
                {
                    "step": "enter_battle",
                    "ok": bool(bp.get("Success")),
                    "battle_id": bp.get("BattleId"),
                    "message": bp.get("Message"),
                }
            )
        except Exception as exc:
            steps.append({"step": "enter_battle", "ok": False, "error": str(exc)})

        # Warmup heartbeat only (long hang happens after PVP in dual mode / via hold_online).
        beats = 0
        if hold_sec > 0:
            beats, hold_ok, hold_err = hold_online(
                [client],
                hold_sec=hold_sec,
                interval_sec=5.0,
                label=name,
            )
            steps.append(
                {
                    "step": "hold_online",
                    "ok": hold_ok,
                    "heartbeats": beats,
                    "hold_sec": hold_sec,
                    **({"error": hold_err} if not hold_ok else {}),
                }
            )
        else:
            # Dual mode: skip warmup heartbeat here; long hold happens after PVP.
            beats = 0
            steps.append({"step": "heartbeat_warmup", "ok": True, "skipped": True})

        failed = [s for s in steps if not s.get("ok")]
        return {
            "ok": len(failed) == 0,
            "name": name,
            "user": user,
            "token_prefix": client.token[:8] if client.token else "",
            "server_id": client.server_id,
            "player_id": client.player_id,
            "nickname": client.nickname,
            "hold_sec": hold_sec,
            "heartbeats": beats,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "failed": failed,
            "steps": steps,
            "client": client,  # kept open for dual match phase
        }
    except Exception as exc:
        failed = [s for s in steps if not s.get("ok")]
        return {
            "ok": False,
            "name": name,
            "user": user,
            "error": str(exc),
            "elapsed_ms": int((time.time() - t0) * 1000),
            "failed": failed,
            "steps": steps,
            "client": client,
        }


def hold_online(
    clients: list,
    *,
    hold_sec: float,
    interval_sec: float = 5.0,
    label: str = "online",
) -> tuple[int, bool, str]:
    """Keep WS sessions alive with heartbeats; do not close. Returns (beats, ok, error)."""
    hold_sec = max(0.0, float(hold_sec))
    interval_sec = max(1.0, float(interval_sec))
    if hold_sec <= 0 or not clients:
        return 0, True, ""

    log(f"=== 长挂在线开始 label={label} hold_sec={hold_sec:.0f}s interval={interval_sec:.0f}s ===")
    log("黑窗口应持续看到 Heartbeat；期间不会主动断开（这才是真实在线）")
    hold_until = time.time() + hold_sec
    beats = 0
    while time.time() < hold_until:
        remain = max(0.0, hold_until - time.time())
        try:
            for c in clients:
                if c is None:
                    continue
                c.heartbeat()
            beats += 1
            log(f"[{label}] 在线心跳 #{beats} 剩余 {remain:.0f}s")
        except Exception as exc:
            err = str(exc)
            log(f"[{label}] 长挂中断 heartbeat #{beats + 1}: {err}")
            return beats, False, err
        sleep_for = min(interval_sec, max(0.2, hold_until - time.time()))
        if sleep_for > 0:
            time.sleep(sleep_for)
    log(f"=== 长挂在线结束 label={label} heartbeats={beats} ===")
    return beats, True, ""


def run_dual_pvp(
    ws_url: str,
    hold_sec: float,
    password: str,
    *,
    heartbeat_interval: float = 5.0,
) -> dict:
    """Two sustained clients: full lifecycle + PVP + long online hold (no early close)."""
    results = {}
    lock = threading.Lock()

    def worker(name: str):
        # Business path only; long hang is after PVP so both stay online together.
        r = run_player_flow(ws_url, name, hold_sec=0.0, password=password)
        with lock:
            results[name] = r

    t1 = threading.Thread(target=worker, args=("A",), daemon=True)
    t2 = threading.Thread(target=worker, args=("B",), daemon=True)
    t1.start()
    time.sleep(1.0)  # stagger so game logs are readable
    t2.start()
    t1.join()
    t2.join()

    a = results.get("A") or {}
    b = results.get("B") or {}
    ca: SessionClient | None = a.get("client")
    cb: SessionClient | None = b.get("client")
    pvp = {"ok": False, "detail": "clients_unavailable"}

    try:
        if ca and cb and a.get("ok") and b.get("ok"):
            log("=== PVP match enqueue dungeon=90001 (need 2 players) ===")
            ra = ca.request(
                10087,
                {"DungeonId": 90001, "Difficulty": "normal", "Formation": []},
                "DungeonMatch_c2s",
                10088,
                label="pvp_match_A",
            )
            rb = cb.request(
                10087,
                {"DungeonId": 90001, "Difficulty": "normal", "Formation": []},
                "DungeonMatch_c2s",
                10088,
                label="pvp_match_B",
            )
            pa = ra.get("DataParsed") or {}
            pb = rb.get("DataParsed") or {}
            match_id = pb.get("MatchId") or pa.get("MatchId")
            matched = bool(pa.get("Success")) and bool(pb.get("Success")) and bool(match_id)
            pvp = {
                "ok": matched,
                "match_id_a": pa.get("MatchId"),
                "match_id_b": pb.get("MatchId"),
                "wait_a": pa.get("EstimatedWaitSeconds"),
                "wait_b": pb.get("EstimatedWaitSeconds"),
                "team_b": pb.get("Team"),
            }
            if matched:
                try:
                    bat = ca.request(
                        10081,
                        {
                            "StageId": "pvp_1v1",
                            "BattleMode": "PVP",
                            "SyncMode": 0,
                            "Formation": [],
                            "ClientTime": int(time.time() * 1000),
                            "Custom": json.dumps({"matchId": match_id}),
                        },
                        "EnterBattle_c2s",
                        10082,
                        label="pvp_enter_battle",
                    )
                    bp = bat.get("DataParsed") or {}
                    pvp["enter_battle_ok"] = bool(bp.get("Success"))
                    pvp["battle_id"] = bp.get("BattleId")
                    if not bp.get("Success"):
                        pvp["ok"] = False
                        pvp["enter_battle_message"] = bp.get("Message")
                except Exception as exc:
                    pvp["enter_battle_ok"] = False
                    pvp["enter_battle_error"] = str(exc)
                    pvp["ok"] = False

            # Real online window: both clients stay connected and only heartbeat.
            beats, hold_ok, hold_err = hold_online(
                [ca, cb],
                hold_sec=hold_sec,
                interval_sec=heartbeat_interval,
                label="A+B",
            )
            pvp["hold_sec"] = hold_sec
            pvp["hold_heartbeats"] = beats
            pvp["hold_ok"] = hold_ok
            if not hold_ok:
                pvp["ok"] = False
                pvp["hold_error"] = hold_err
        else:
            pvp = {
                "ok": False,
                "detail": "player_flow_failed",
                "a_ok": a.get("ok"),
                "b_ok": b.get("ok"),
                "a_error": a.get("error"),
                "b_error": b.get("error"),
            }
    finally:
        if ca:
            ca.close()
        if cb:
            cb.close()

    for side in (a, b):
        side.pop("client", None)

    report = {
        "check": "ws_full_lifecycle_e2e",
        "ok": bool(a.get("ok") and b.get("ok") and pvp.get("ok")),
        "player_a": a,
        "player_b": b,
        "pvp": pvp,
        "hold_sec": hold_sec,
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "ws_url": ws_url,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Full sustained WS lifecycle E2E")
    parser.add_argument("--ws", default=os.environ.get("GAME_WS", "ws://127.0.0.1:15050/ws/"))
    # Default 3 minutes online — real联调 should not look like connect/disconnect spam.
    parser.add_argument(
        "--hold-sec",
        type=float,
        default=float(os.environ.get("E2E_HOLD_SEC", "180")),
        help="seconds to stay online with heartbeats after business/PVP (default 180)",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=float(os.environ.get("E2E_HEARTBEAT_INTERVAL", "5")),
        help="seconds between heartbeats during long hold (default 5)",
    )
    parser.add_argument("--password", default="联调pass")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--single", action="store_true", help="single client only (no PVP)")
    args = parser.parse_args()

    log("======== 全流程持续联调开始 ========")
    log(f"ws={args.ws} hold_sec={args.hold_sec} heartbeat_interval={args.heartbeat_interval}")
    log("业务跑完后会长时间保持在线只打心跳；请盯 gateway/auth/game 黑窗口")

    if args.single:
        one = run_player_flow(args.ws, "S", args.hold_sec, args.password)
        client = one.pop("client", None)
        if client:
            # hold already done inside run_player_flow when hold_sec>0
            client.close()
        report = {
            "check": "ws_full_lifecycle_e2e",
            "ok": bool(one.get("ok")),
            "player": one,
            "hold_sec": args.hold_sec,
            "generatedUtc": datetime.now(timezone.utc).isoformat(),
            "ws_url": args.ws,
        }
    else:
        report = run_dual_pvp(
            args.ws,
            args.hold_sec,
            args.password,
            heartbeat_interval=args.heartbeat_interval,
        )

    out = Path(args.evidence) if args.evidence else (
        Path(__file__).resolve().parents[4] / "docs/evidence/ws-full-lifecycle-e2e-latest.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(json.dumps({k: report.get(k) for k in ("check", "ok", "pvp") if k in report}, ensure_ascii=False))
    log(f"evidence: {out}")
    if report.get("ok"):
        log("======== 全流程持续联调 PASS ========")
        return 0
    log("======== 全流程持续联调 FAIL ========")
    # print failures
    for key in ("player_a", "player_b", "player"):
        side = report.get(key)
        if isinstance(side, dict) and side.get("failed"):
            log(f"{key} failed steps: {json.dumps(side.get('failed'), ensure_ascii=False)}")
    if report.get("pvp") and not report["pvp"].get("ok"):
        log(f"pvp: {json.dumps(report['pvp'], ensure_ascii=False)}")
    if report.get("error"):
        log(f"error: {report['error']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
