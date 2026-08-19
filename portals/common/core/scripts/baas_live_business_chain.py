#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live HTTP business-chain scenarios against running BaaS Portal."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple


def http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None) -> dict:
    data = None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"ok": False, "error": raw, "status": exc.code}
        payload.setdefault("status", exc.code)
        return payload


class BaasLiveBusinessChain:
    def __init__(self, portal: str, service_id: str, api_key: str, game_id: str, game_key: str):
        self.portal = portal.rstrip("/")
        self.service_id = service_id
        self.api_key = api_key
        self.game_id = game_id
        self.game_key = game_key
        self.base = f"{self.portal}/api/baas/v1/{service_id}"
        self.api_headers = {"X-Baas-Api-Key": api_key, "Content-Type": "application/json"}
        self.scenarios: List[Dict[str, Any]] = []

    def _record(self, name: str, ok: bool, detail: dict | None = None) -> bool:
        self.scenarios.append({"name": name, "ok": ok, "detail": detail or {}})
        return ok

    def _guest(self, name: str) -> Tuple[dict, dict]:
        out = http_json(f"{self.base}/auth/guest", method="POST", body={"display_name": name}, headers=self.api_headers)
        if not out.get("ok"):
            raise RuntimeError(f"guest login failed: {out}")
        data = out["data"]
        auth = dict(self.api_headers)
        auth["Authorization"] = f"Bearer {data['token']}"
        auth["X-Baas-Player-Id"] = data["player_id"]
        return data, auth

    def run_all(self) -> dict:
        ok = True
        ok &= self.scenario_bootstrap()
        ok &= self.scenario_phase1_core()
        ok &= self.scenario_phase2_retention()
        ok &= self.scenario_phase3_social()
        ok &= self.scenario_phase4_compliance()
        ok &= self.scenario_pvp_fanout()
        return {"ok": ok, "scenarios": self.scenarios}

    def scenario_bootstrap(self) -> bool:
        try:
            q = f"game_id={self.game_id}&game_key={self.game_key}&env=development&service_id={self.service_id}"
            boot = http_json(f"{self.portal}/api/public/client-bootstrap?{q}")
            legacy = http_json(f"{self.portal}/api/public/baas-bootstrap?{q}")
            ok = boot.get("ok") and legacy.get("ok") and boot.get("service_id") == self.service_id
            return self._record("bootstrap_dual_path", ok, {"client_bootstrap": boot.get("ok"), "baas_bootstrap": legacy.get("ok")})
        except Exception as exc:
            return self._record("bootstrap_dual_path", False, {"error": str(exc)})

    def scenario_phase1_core(self) -> bool:
        try:
            p1, h1 = self._guest("ChainP1")
            suffix = str(int(time.time()))[-6:]
            username = f"e2e_user_{suffix}"
            reg = http_json(
                f"{self.base}/auth/register",
                method="POST",
                body={"username": username, "password": "Test1234!", "display_name": "RegUser"},
                headers=self.api_headers,
            )
            login = http_json(
                f"{self.base}/auth/login",
                method="POST",
                body={"username": username, "password": "Test1234!"},
                headers=self.api_headers,
            )
            ann = http_json(f"{self.base}/announcements/active", headers=self.api_headers)
            acts = http_json(f"{self.base}/activities/active", headers=h1)
            inbox = http_json(f"{self.base}/mail/inbox", headers=h1)
            put = http_json(f"{self.base}/cloudsave/profile", method="PUT", body={"value": {"level": 9}}, headers=h1)
            get = http_json(f"{self.base}/cloudsave/profile", headers=h1)
            list_keys = http_json(f"{self.base}/cloudsave", headers=h1)
            level_ok = ((get.get("data") or {}).get("value") or {}).get("level") == 9
            ok = all([
                ann.get("ok"),
                acts.get("ok"),
                inbox.get("ok"),
                put.get("ok"),
                get.get("ok"),
                list_keys.get("ok"),
                level_ok,
                reg.get("ok") or login.get("ok"),
            ])
            return self._record("phase1_core", ok, {
                "register": reg.get("ok"),
                "announce": ann.get("ok"),
                "mail_inbox": inbox.get("ok"),
                "cloudsave_level": level_ok,
            })
        except Exception as exc:
            return self._record("phase1_core", False, {"error": str(exc)})

    def scenario_phase2_retention(self) -> bool:
        try:
            p1, h1 = self._guest("RetP1")
            submit = http_json(
                f"{self.base}/leaderboards/default/submit",
                method="POST",
                body={"score": 12345, "display_name": "RetP1"},
                headers=h1,
            )
            top = http_json(f"{self.base}/leaderboards/default/top", headers=self.api_headers)
            wallet = http_json(f"{self.base}/shop/wallet", headers=h1)
            catalog = http_json(f"{self.base}/shop/catalog", headers=self.api_headers)
            purchase = http_json(
                f"{self.base}/shop/purchase",
                method="POST",
                body={"product_id": "potion_small"},
                headers=h1,
            )
            ach_list = http_json(f"{self.base}/achievements", headers=h1)
            ach_prog = http_json(
                f"{self.base}/achievements/first_login/progress",
                method="POST",
                body={"progress": 1},
                headers=h1,
            )
            ach_claim = http_json(
                f"{self.base}/achievements/first_login/claim",
                method="POST",
                body={},
                headers=h1,
            )
            ok = all([
                submit.get("ok"),
                top.get("ok"),
                wallet.get("ok"),
                catalog.get("ok"),
                purchase.get("ok"),
                ach_list.get("ok"),
                ach_prog.get("ok"),
                ach_claim.get("ok"),
            ])
            return self._record("phase2_retention", ok, {
                "leaderboard": submit.get("ok"),
                "shop_purchase": purchase.get("ok"),
                "achievement_claim": ach_claim.get("ok"),
            })
        except Exception as exc:
            return self._record("phase2_retention", False, {"error": str(exc)})

    def scenario_phase3_social(self) -> bool:
        try:
            leader, h_leader = self._guest("GuildLead")
            guild = http_json(f"{self.base}/guilds", method="POST", body={"name": "E2EGuild"}, headers=h_leader)
            guild_id = (guild.get("data") or {}).get("guild_id")
            member, h_member = self._guest("GuildMem")
            joined = http_json(f"{self.base}/guilds/{guild_id}/join", method="POST", body={}, headers=h_member)
            got = http_json(f"{self.base}/guilds/{guild_id}", headers=h_member)
            bp_state = http_json(f"{self.base}/battlepass/state", headers=h_leader)
            bp_xp = http_json(f"{self.base}/battlepass/xp", method="POST", body={"xp": 150}, headers=h_leader)
            bp_claim = http_json(f"{self.base}/battlepass/claim", method="POST", body={"level": 1}, headers=h_leader)
            tasks = http_json(f"{self.base}/tasks/periodic", headers=h_leader)
            task_id = "daily_login"
            if tasks.get("ok") and (tasks.get("data") or []):
                task_id = str((tasks["data"][0] or {}).get("task_id") or task_id)
            t_prog = http_json(
                f"{self.base}/tasks/{task_id}/progress",
                method="POST",
                body={"progress": 1},
                headers=h_leader,
            )
            t_claim = http_json(f"{self.base}/tasks/{task_id}/claim", method="POST", body={}, headers=h_leader)
            ok = all([
                guild.get("ok"),
                joined.get("ok"),
                got.get("ok"),
                bp_state.get("ok"),
                bp_xp.get("ok"),
                bp_claim.get("ok"),
                tasks.get("ok"),
                t_prog.get("ok"),
                t_claim.get("ok"),
            ])
            return self._record("phase3_social", ok, {
                "guild_create": guild.get("ok"),
                "battlepass_claim": bp_claim.get("ok"),
                "task_claim": t_claim.get("ok"),
            })
        except Exception as exc:
            return self._record("phase3_social", False, {"error": str(exc)})

    def scenario_phase4_compliance(self) -> bool:
        try:
            p1, h1 = self._guest("CompP1")
            start = http_json(f"{self.base}/compliance/session-start", method="POST", body={}, headers=h1)
            beat = http_json(f"{self.base}/compliance/heartbeat", method="POST", body={"minutes": 1}, headers=h1)
            verify = http_json(
                f"{self.base}/compliance/verify-real-name",
                method="POST",
                body={"real_name": "测试", "id_number": "110101199001011234"},
                headers=h1,
            )
            ok = all([start.get("ok"), beat.get("ok"), verify.get("ok") or verify.get("status") in (400, 422)])
            return self._record("phase4_compliance", ok, {
                "session_start": start.get("ok"),
                "heartbeat": beat.get("ok"),
                "verify": verify.get("ok"),
            })
        except Exception as exc:
            return self._record("phase4_compliance", False, {"error": str(exc)})

    def scenario_pvp_fanout(self) -> bool:
        try:
            p1, h1 = self._guest("FanA")
            p2, h2 = self._guest("FanB")
            room1 = http_json(f"{self.base}/pvp/matchmake", method="POST", body={"battle_mode": "pvp_1v1"}, headers=h1)["data"]
            room_id = room1["room_id"]
            room2 = http_json(f"{self.base}/pvp/matchmake", method="POST", body={"battle_mode": "pvp_1v1"}, headers=h2)["data"]
            if room2["room_id"] != room_id:
                raise RuntimeError("matchmake room mismatch")
            started = http_json(f"{self.base}/rooms/{room_id}/start-battle", method="POST", body={}, headers=h1)
            wait_ms = 3000
            result: dict = {}
            started_evt = threading.Event()

            def poll_opponent():
                started_evt.set()
                t0 = time.perf_counter()
                polled = http_json(
                    f"{self.base}/rooms/{room_id}/frames?since_seq=0&wait_ms={wait_ms}",
                    headers={**self.api_headers, "X-Baas-Player-Id": p2["player_id"]},
                )
                result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                result["payload"] = polled.get("data") or {}

            worker = threading.Thread(target=poll_opponent, daemon=True)
            worker.start()
            started_evt.wait(timeout=2)
            time.sleep(0.05)
            push = http_json(
                f"{self.base}/rooms/{room_id}/frames",
                method="POST",
                body={"frame": {"action": "attack", "skill": 101}},
                headers=h1,
            )
            worker.join(timeout=max(5, wait_ms / 1000 + 2))
            polled = result.get("payload") or {}
            frames = polled.get("frames") or []
            ok = (
                started.get("ok")
                and push.get("ok")
                and polled.get("polled") is True
                and len(frames) == 1
            )
            finish = http_json(
                f"{self.base}/rooms/{room_id}/finish-battle",
                method="POST",
                body={"result": {"winner": p1["player_id"], "reason": "e2e"}},
                headers=h1,
            )
            ok = ok and finish.get("ok")
            return self._record("pvp_frame_fanout", ok, {
                "room_id": room_id,
                "notifyLatencyMs": result.get("latency_ms"),
                "frame_count": len(frames),
                "finish": finish.get("ok"),
            })
        except Exception as exc:
            return self._record("pvp_frame_fanout", False, {"error": str(exc)})

    def scenario_gift_redeem(self, code: str = "PRODE2E2026") -> bool:
        try:
            p1, h1 = self._guest("GiftP1")
            redeem = http_json(
                f"{self.base}/gifts/redeem",
                method="POST",
                body={"code": code},
                headers=h1,
            )
            ok = redeem.get("ok") is True
            return self._record("gift_redeem_gm_code", ok, {"code": code, "response": redeem.get("ok")})
        except Exception as exc:
            return self._record("gift_redeem_gm_code", False, {"error": str(exc)})

    def scenario_mail_claim_after_gm_broadcast(self) -> bool:
        try:
            p1, h1 = self._guest("MailClaim")
            inbox = http_json(f"{self.base}/mail/inbox", headers=h1)
            mails = (inbox.get("data") or {}).get("messages") or inbox.get("data") or []
            if not mails:
                return self._record("mail_claim", True, {"skipped": True, "reason": "no mail yet"})
            mail_id = str(mails[0].get("mail_id") or mails[0].get("id") or "")
            claim = http_json(f"{self.base}/mail/{mail_id}/claim", method="POST", body={}, headers=h1)
            ok = claim.get("ok") is True
            return self._record("mail_claim", ok, {"mail_id": mail_id})
        except Exception as exc:
            return self._record("mail_claim", False, {"error": str(exc)})


def run_chain(creds: dict, *, after_gm: bool = False) -> dict:
    runner = BaasLiveBusinessChain(
        creds["portal"],
        creds["service_id"],
        creds["api_key"],
        creds["game_id"],
        creds["game_key"],
    )
    result = runner.run_all()
    if after_gm:
        result["ok"] = result["ok"] and runner.scenario_gift_redeem()
        result["ok"] = result["ok"] and runner.scenario_mail_claim_after_gm_broadcast()
        result["scenarios"] = runner.scenarios
    return result
