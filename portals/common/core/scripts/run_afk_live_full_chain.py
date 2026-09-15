#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AFK 全系统 Live HTTP 联调：Day1–30 留存循环 + 装备成长 + 副本 + 推图。
真实 urllib → localhost BaaS（非 test_client / 非离线模拟器）。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CORE = Path(__file__).resolve().parents[1]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

CREDS = CORE / "docs/evidence/baas-afk-live-e2e-credentials.json"
OUT = Path(__file__).resolve().parents[4] / "data/afk_shared/afk_live_full_chain_report.json"


def http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        timeout = float(os.environ.get("AFK_LIVE_HTTP_TIMEOUT_SECONDS", "20"))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": raw, "status": exc.code}


def stage_ids(limit: int = 100) -> List[str]:
    out: List[str] = []
    for ch in range(1, 11):
        for lv in range(1, 11):
            out.append(f"AFK_{ch:02d}_{lv:02d}")
            if len(out) >= limit:
                return out
    return out


class LiveClient:
    def __init__(self, portal: str, creds: dict):
        self.portal = portal.rstrip("/")
        self.creds = creds
        self.base = f"{self.portal}/api/baas/v1/{creds['service_id']}"
        self.api_h = {"X-Baas-Api-Key": creds["api_key"]}
        self.ph: dict = {}
        self.player_id = ""
        self.log: List[str] = []

    def login(self) -> bool:
        r = http_json(f"{self.base}/auth/guest", method="POST", body={"display_name": "LiveFullChain"}, headers=self.api_h)
        if not r.get("ok"):
            return False
        self.player_id = r["data"]["player_id"]
        self.ph = dict(self.api_h)
        self.ph["Authorization"] = f"Bearer {r['data']['token']}"
        self.ph["X-Baas-Player-Id"] = self.player_id
        return True

    def post(self, path: str, body: Optional[dict] = None) -> dict:
        return http_json(f"{self.base}{path}", method="POST", body=body or {}, headers=self.ph)

    def get(self, path: str) -> dict:
        return http_json(f"{self.base}{path}", headers=self.ph)

    def note(self, msg: str) -> None:
        self.log.append(msg)

    def redeem_gift(self) -> bool:
        r = self.post("/gifts/redeem", {"code": self.creds.get("gift_code", "AFKE2E2026")})
        return bool(r.get("ok"))

    def ensure_roster(self, min_count: int = 5) -> List[int]:
        for _ in range(40):
            pull = self.post("/gacha/standard/pull", {"count": 1})
            if not pull.get("ok"):
                break
            roster = self.get("/heroes/roster")
            heroes = (roster.get("data") or {}).get("heroes") or []
            if len(heroes) >= min_count:
                heroes.sort(key=lambda h: int(h.get("base_power") or 0), reverse=True)
                return [int(h["hero_id"]) for h in heroes[:5]]
        roster = self.get("/heroes/roster")
        heroes = (roster.get("data") or {}).get("heroes") or []
        heroes.sort(key=lambda h: int(h.get("base_power") or 0), reverse=True)
        return [int(h["hero_id"]) for h in heroes[:5]]

    def level_team(self, team: List[int], target_lv: int) -> None:
        for hid in team:
            roster = self.get("/heroes/roster")
            heroes = {int(h["hero_id"]): h for h in (roster.get("data") or {}).get("heroes") or []}
            cur = int((heroes.get(hid) or {}).get("level") or 1)
            for _ in range(max(0, target_lv - cur)):
                up = self.post(f"/heroes/{hid}/level-up")
                if not up.get("ok"):
                    break

    def star_team(self, team: List[int]) -> int:
        count = 0
        for hid in team:
            for _ in range(4):
                r = self.post(f"/heroes/{hid}/star-up", {"use_crystal": True})
                if r.get("ok"):
                    count += 1
                else:
                    break
        return count

    def grant_starter_items(self) -> None:
        """通过 GM 不可用时的替代：多次副本+礼包已给资源；此处尝试 idle claim。"""
        self.post("/idle/claim")

    def growth_pass(self) -> Dict[str, int]:
        stats = {"enhance": 0, "refine": 0, "awaken": 0, "star": 0, "talent": 0, "dungeon": 0}
        slots = ["weapon", "helmet", "chest", "legs"]
        for slot in slots:
            for _ in range(3):
                r = self.post(f"/growth/equipment/{slot}/enhance")
                if r.get("ok"):
                    stats["enhance"] += 1
                else:
                    break
            r = self.post(f"/growth/equipment/{slot}/refine")
            if r.get("ok"):
                stats["refine"] += 1
        stats["star"] = self.star_team(self.ensure_roster(3)[:3])
        for hid in self.ensure_roster(3)[:2]:
            r = self.post(f"/heroes/{hid}/talent")
            if r.get("ok"):
                stats["talent"] += 1
        dgs = self.get("/dungeons")
        for dg in (dgs.get("data") or {}).get("dungeons") or []:
            if not dg.get("unlocked"):
                continue
            if dg.get("id") == "solo_tower":
                continue
            r = self.post(f"/dungeons/{dg['id']}/run", {"team": {"heroes": self.ensure_roster(5)}})
            if r.get("ok"):
                stats["dungeon"] += 1
        return stats

    def pve_clear_until(self, team: List[int], target: int) -> int:
        from services.baas.battle_antifraud import compute_replay_hash

        prog = self.get("/pve/progress")
        cleared_ids = {s.get("stage_id") for s in ((prog.get("data") or {}).get("stages") or []) if int(s.get("cleared") or 0)}
        cleared = len(cleared_ids)
        for sid in stage_ids(target):
            if sid in cleared_ids:
                cleared = max(cleared, len([x for x in stage_ids(target) if x in cleared_ids]))
                continue
            if len([x for x in stage_ids(100) if x in cleared_ids]) >= target:
                break
            start = self.post("/pve/battle/start", {"stage_id": sid, "team": {"heroes": team}})
            if not start.get("ok"):
                for attempt in range(80):
                    self.level_team(team, min(240, 40 + attempt * 2))
                    if attempt % 4 == 0:
                        self.star_team(team[:3])
                    start = self.post("/pve/battle/start", {"stage_id": sid, "team": {"heroes": team}})
                    if start.get("ok"):
                        break
            if not start.get("ok"):
                break
            sd = start["data"]
            seed, stars, ticks = int(sd["seed"]), 3, 20
            checksum = hashlib.sha256(f"{seed}:{sid}:1:{stars}".encode()).hexdigest()[:16]
            replay = compute_replay_hash(seed=seed, battle_type="pve", team={"heroes": team}, win=True, ticks=ticks)
            settle = self.post("/pve/battle/settle", {
                "battle_id": sd["battle_id"], "win": True, "stars": stars,
                "duration_ms": 3500, "checksum": checksum, "replay_hash": replay, "replay_ticks": ticks,
            })
            if settle.get("ok"):
                cleared_ids.add(sid)
            else:
                break
        return len([x for x in stage_ids(target) if x in cleared_ids])

    def simulate_days(self, team: List[int], days: int = 30, target_stage: int = 100) -> List[Dict[str, Any]]:
        daily: List[Dict[str, Any]] = []
        for day in range(1, days + 1):
            prog = self.get("/pve/progress")
            stages = (prog.get("data") or {}).get("stages") or []
            cleared = sum(1 for s in stages if int(s.get("cleared") or 0))
            tp = self.get("/growth/team-power")
            power = int((tp.get("data") or {}).get("team_power") or 0)
            battles = 0
            for _ in range(6):
                before = cleared
                cleared = self.pve_clear_until(team, min(target_stage, cleared + 1))
                if cleared <= before:
                    break
                battles += 1
            self.level_team(team, min(240, 20 + day * 3))
            growth = self.growth_pass()
            idle = self.post("/idle/claim")
            idle_gold = int((idle.get("data") or {}).get("claimed_gold") or 0)
            tp2 = self.get("/growth/team-power")
            power2 = int((tp2.get("data") or {}).get("team_power") or 0)
            row = {
                "day": day,
                "cleared": cleared,
                "team_power": power2,
                "battles": battles,
                "growth": growth,
                "idle_gold": idle_gold,
            }
            daily.append(row)
            self.note(f"D{day} cleared={cleared} power={power2} battles={battles} growth={growth}")
            if cleared >= target_stage:
                break
        return daily


def main() -> int:
    if not CREDS.is_file():
        print("missing credentials:", CREDS)
        return 1
    creds = json.loads(CREDS.read_text(encoding="utf-8"))
    # Isolated E2E runs must not silently target the shared default instance.
    portal = os.environ.get("BAAS_E2E_PORTAL") or str(creds.get("portal") or "http://127.0.0.1:5004")
    out = Path(os.environ.get("AFK_E2E_FULL_CHAIN_REPORT_PATH") or OUT)
    client = LiveClient(portal, creds)
    t0 = time.time()
    if not client.login():
        print(json.dumps({"ok": False, "error": "login_failed"}, ensure_ascii=False))
        return 1
    if not client.redeem_gift():
        print(json.dumps({"ok": False, "error": "gift_failed"}, ensure_ascii=False))
        return 1
    team = client.ensure_roster(5)
    if len(team) < 3:
        print(json.dumps({"ok": False, "error": "roster_too_small", "team": team}, ensure_ascii=False))
        return 1
    while len(team) < 5:
        team.append(team[-1])
    client.level_team(team, 40)
    growth0 = client.growth_pass()
    daily = client.simulate_days(team, days=int(os.environ.get("AFK_LIVE_CHAIN_MAX_DAYS", "30")), target_stage=100)
    final_cleared = daily[-1]["cleared"] if daily else 0
    report = {
        "test_suite": "afk_live_full_chain",
        "portal": portal,
        "player_id": client.player_id,
        "team": team,
        "initial_growth": growth0,
        "daily_log": daily,
        "final_cleared": final_cleared,
        "target_stage": 100,
        "stage100_reached": final_cleared >= 100,
        "days_used": len(daily),
        "elapsed_sec": round(time.time() - t0, 2),
        "steps": client.log[-40:],
        "overall_pass": final_cleared >= 100 and len(daily) <= 30,
        "skillkit_note": "SkillKit 100关请在 Unity Test Runner 运行 AfkLiveServerStage100PlayModeTests（Editor 打开时勿 batchmode）",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pass": report["overall_pass"], "cleared": final_cleared, "days": len(daily), "report": str(out)}, ensure_ascii=False))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
